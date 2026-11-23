"""CHURN-24 — What-If prediction endpoint (POST /whatif).

Covers: exact reproduction of the served probability, the correct scoring
model per customer (fold model for out-of-fold customers, production model
for held-out test and demo customers), no in-sample / generator-oracle
fallback, directional sanity of key features, and the WhatIfResponse contract.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import WhatIfResponse

# The API rounds both probabilities to 4 dp, so a no-op change is within 1e-4.
NOOP_TOL = 1e-4 + 1e-12


@pytest.fixture(scope='module')
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def preds(api):
    return api[0].PREDICTIONS_DF.set_index('customer_id')


@pytest.fixture(scope='module')
def sample(api):
    p = api[0].PREDICTIONS_DF
    return (list(p.loc[p['prediction_source'] == 'holdout_test', 'customer_id'][::5])
            + list(p.loc[p['prediction_source'] == 'cv_out_of_fold', 'customer_id'][::20]))


def _whatif(client, cid, **changes):
    r = client.post('/whatif', json={'customer_id': cid, **changes})
    assert r.status_code == 200, r.text
    return WhatIfResponse.model_validate(r.json())


class Sentinel:
    """A model that returns a fixed probability and records its inputs."""

    def __init__(self, prob):
        self.prob, self.inputs = prob, []

    def predict_proba(self, X):
        self.inputs.append(X.copy())
        return np.array([[1 - self.prob, self.prob]])


class MustNotBeCalled:
    def predict_proba(self, X):
        raise AssertionError('wrong model used for this customer')


# ── Unchanged inputs reproduce the served prediction ─────────────────────────
@pytest.mark.parametrize('source', ['holdout_test', 'cv_out_of_fold', 'demo'])
def test_noop_reproduces_served_probability(api, client, preds, source):
    ids = preds.index[preds['prediction_source'] == source]
    ids = ids[::max(1, len(ids) // 150)]
    for cid in ids:
        r = _whatif(client, cid)
        assert r.original_churn_prob == round(float(preds.loc[cid, 'churn_prob']), 4)
        assert abs(r.new_churn_prob - r.original_churn_prob) <= NOOP_TOL, cid
        assert r.change == 0.0 and r.change_percent == '+0.0%' and r.improved is False
        assert r.original_risk == r.new_risk


def test_setting_fields_to_their_current_values_is_also_a_noop(api, client, sample):
    main = api[0]
    for cid in sample[:40]:
        row = main.FULL_DF.set_index('customer_id').loc[cid]
        same = {'watch_hours_per_week': float(row['watch_hours_per_week']),
                'tenure_months': int(row['tenure_months']),
                'payment_failures_3m': int(row['payment_failures_3m']),
                'support_tickets': int(row['support_tickets']),
                'logins_last_30_days': int(row['logins_last_30_days']),
                'monthly_charge': int(row['monthly_charge'])}
        assert _whatif(client, cid, **same).change == 0.0


# ── Correct model per customer; no in-sample or oracle fallback ──────────────
def test_oof_customers_use_their_own_fold_model(api, client, preds, monkeypatch):
    main = api[0]
    sentinels = [Sentinel(0.05 + 0.1 * k) for k in range(len(main.FOLD_MODELS))]
    monkeypatch.setattr(main, 'FOLD_MODELS', sentinels)
    monkeypatch.setattr(main, 'MODEL', MustNotBeCalled())   # production model is in-sample here
    oof = preds[preds['prediction_source'] == 'cv_out_of_fold']
    for fold, grp in oof.groupby('fold'):
        for cid in grp.index[:5]:
            r = _whatif(client, cid, support_tickets=1)
            assert r.new_churn_prob == round(sentinels[int(fold)].prob, 4), (cid, fold)


@pytest.mark.parametrize('source', ['holdout_test', 'demo'])
def test_test_and_demo_customers_use_the_production_model(api, client, preds, monkeypatch, source):
    main = api[0]
    prod = Sentinel(0.4321)
    monkeypatch.setattr(main, 'MODEL', prod)
    monkeypatch.setattr(main, 'FOLD_MODELS', [MustNotBeCalled()] * 5)
    for cid in preds.index[preds['prediction_source'] == source][:5]:
        assert _whatif(client, cid, support_tickets=1).new_churn_prob == 0.4321
    assert prod.inputs


def test_without_fold_models_oof_whatif_is_refused_not_rescored_in_sample(api, client, preds,
                                                                         monkeypatch):
    main = api[0]
    monkeypatch.setattr(main, 'FOLD_MODELS', None)
    monkeypatch.setattr(main, 'MODEL', MustNotBeCalled())
    cid = preds.index[preds['prediction_source'] == 'cv_out_of_fold'][0]
    r = client.post('/whatif', json={'customer_id': cid, 'support_tickets': 1})
    assert r.status_code == 409 and r.json()['error'] == 'fold_model_unavailable'


def test_original_probability_never_comes_from_the_generator_oracle(api, client, sample,
                                                                    monkeypatch):
    main = api[0]
    before = {cid: _whatif(client, cid, support_tickets=2).model_dump() for cid in sample[:20]}
    df = main.FULL_DF.copy()
    df['churn_probability'] = 0.5          # the generator's true probability
    df['churn'] = 1 - df['churn']          # and the ground-truth label
    monkeypatch.setattr(main, 'FULL_DF', df)
    for cid, b in before.items():
        assert _whatif(client, cid, support_tickets=2).model_dump() == b


def test_model_receives_the_customer_features_with_only_the_change_applied(api, client, preds,
                                                                           monkeypatch):
    main = api[0]
    cid = preds.index[preds['prediction_source'] == 'holdout_test'][0]
    spy = Sentinel(0.5)
    monkeypatch.setattr(main, 'MODEL', spy)
    _whatif(client, cid, payment_failures_3m=3)
    X = spy.inputs[0]
    base = main.FEATURE_MATRIX.loc[[cid]].reset_index(drop=True)
    assert list(X.columns) == list(main.FEATURE_NAMES)
    changed = [c for c in X.columns if not np.isclose(float(X[c].iloc[0]), float(base[c].iloc[0]))]
    if main.FEATURE_MATRIX.loc[cid, 'payment_failures_3m'] != 3:
        assert 'payment_failures_3m' in changed
        assert set(changed) <= {'payment_failures_3m', 'friction_score'}
    # one-hot columns survive (CHURN-13 regression guard)
    assert X.filter(like='device_type_').sum(axis=1).iloc[0] == 1


# ── Valid changes move the prediction in the expected direction ──────────────
@pytest.mark.parametrize('change,direction,min_share', [
    ({'payment_failures_3m': 4}, +1, 0.90),
    ({'support_tickets': 5}, +1, 0.90),
    ({'tenure_months': 1}, +1, 0.90),
    ({'watch_hours_per_week': 0.5}, +1, 0.80),
])
def test_risk_increasing_changes(client, sample, change, direction, min_share):
    ch = np.array([_whatif(client, cid, **change).change for cid in sample])
    assert ch.mean() > 0.1
    assert (ch > 0).mean() >= min_share, (change, (ch > 0).mean())


def test_clearing_payment_failures_never_meaningfully_increases_risk(client, sample):
    ch = np.array([_whatif(client, cid, payment_failures_3m=0).change for cid in sample])
    assert ch.mean() < 0 and (ch > 0.01).mean() <= 0.02


@pytest.mark.parametrize('change', [{'watch_hours_per_week': 40.0}, {'logins_last_30_days': 26},
                                    {'tenure_months': 72}])
def test_engagement_and_loyalty_improvements_lower_risk_on_average(client, sample, change):
    # Not monotonic per customer (see docs/api/README.md §6) — asserted on average.
    ch = np.array([_whatif(client, cid, **change).change for cid in sample])
    assert ch.mean() < 0


def test_multiple_simultaneous_changes(client, sample):
    worse = _whatif(client, sample[0], payment_failures_3m=4, support_tickets=5, tenure_months=1,
                    watch_hours_per_week=0.5, logins_last_30_days=0)
    better = _whatif(client, sample[0], payment_failures_3m=0, support_tickets=0, tenure_months=72,
                     watch_hours_per_week=20.0, logins_last_30_days=26)
    assert worse.new_churn_prob > better.new_churn_prob
    assert worse.new_risk == 'HIGH'


def test_response_fields_are_internally_consistent(api, client, sample):
    main = api[0]
    for cid in sample[:50]:
        r = _whatif(client, cid, payment_failures_3m=2, watch_hours_per_week=3.5)
        assert 0 <= r.new_churn_prob <= 1 and 0 <= r.original_churn_prob <= 1
        assert r.change == pytest.approx(r.new_churn_prob - r.original_churn_prob, abs=1e-4)
        assert r.change_percent == f'{r.change * 100:+.1f}%'
        assert r.improved is (r.change < 0)
        assert r.new_risk == main.get_risk_level(r.new_churn_prob)
