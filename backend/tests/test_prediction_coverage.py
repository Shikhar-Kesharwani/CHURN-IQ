"""CHURN-37 / CHURN-38 — full prediction coverage, leakage safety, fallbacks, demo customer.

See docs/ml/04-clv-verification.md and docs/ml/06-followup-audit.md.
"""
import pickle

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import churniq_core as core
import churniq_ml_pipeline as pipeline
import evaluate_model as ev

DEMO_ID = 'CUST99999'


@pytest.fixture(scope='module')
def client(api):
    main, _ = api
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def fold_bundle():
    with open(ev._path('oof_fold_models.pkl'), 'rb') as f:
        return pickle.load(f)


# ── Coverage ────────────────────────────────────────────────────────────────
def test_every_eligible_customer_has_a_prediction(api):
    main, _ = api
    preds, data = main.PREDICTIONS_DF, main.DATASET_DF
    eligible = [r['customer_id'] for r in data.to_dict(orient='records')
                if not core.validate_raw_record(r)]
    assert len(eligible) == len(data) == 5001
    assert set(preds['customer_id']) == set(eligible)
    assert preds['customer_id'].is_unique
    assert preds['churn_prob'].between(0, 1).all()
    assert not preds[['churn_prob', 'risk_level', 'clv_score', 'actual_churn',
                      'prediction_source']].isna().any().any()
    assert main.FULL_DF['churn_prob'].notna().all()
    assert preds['prediction_source'].value_counts().to_dict() == {
        'cv_out_of_fold': 4000, 'holdout_test': 1000, 'demo': 1}


def test_predictions_are_not_the_generator_probability(api):
    main, _ = api
    m = main.PREDICTIONS_DF.merge(main.DATASET_DF[['customer_id', 'churn_probability']],
                                  on='customer_id')
    # Identical to 4 dp would only happen by coincidence
    assert (m['churn_prob'] == m['churn_probability']).mean() < 0.01


# ── Leakage safety of out-of-fold predictions ───────────────────────────────
def test_oof_customers_are_the_training_split_and_folds_are_reproducible(api, artifacts):
    main, _ = api
    p = main.PREDICTIONS_DF.set_index('customer_id')
    X_train, y_train, base = artifacts['X_train'], artifacts['y_train'], artifacts['base']
    train_ids = base.loc[X_train.index, 'customer_id'].values
    oof = p[p['prediction_source'] == 'cv_out_of_fold']
    assert set(oof.index) == set(train_ids)
    for fold, (tr, va) in enumerate(pipeline.oof_folds(X_train, y_train)):
        held_out = set(train_ids[va])
        assert set(oof.index[oof['fold'] == fold]) == held_out
        assert held_out.isdisjoint(set(train_ids[tr]))      # never scored by a model that saw them


def test_oof_probabilities_come_from_their_fold_model(api, fold_bundle):
    main, _ = api
    p = main.PREDICTIONS_DF
    oof = p[p['prediction_source'] == 'cv_out_of_fold']
    assert fold_bundle['model_config'] == 'baseline' and len(fold_bundle['models']) == 5
    for fold, grp in oof.groupby('fold'):
        X = main.FEATURE_MATRIX.loc[grp['customer_id']]
        prob = fold_bundle['models'][int(fold)].predict_proba(X)[:, 1]
        assert np.abs(np.round(prob, 4) - grp['churn_prob'].values).max() < 1e-6


def test_holdout_rows_still_come_from_committed_model(artifacts):
    preds = artifacts['predictions'].set_index('customer_id')
    ids = artifacts['base'].loc[artifacts['X_test'].index, 'customer_id']
    assert (preds.loc[ids, 'prediction_source'] == 'holdout_test').all()
    prob = artifacts['model'].predict_proba(artifacts['X_test'])[:, 1]
    assert np.abs(prob - preds.loc[ids, 'churn_prob'].values).max() <= 1e-4


def test_oof_quality_comparable_to_holdout():
    import json, os
    with open(os.path.join(ev.RESULTS_DIR, 'prediction_coverage.json')) as f:
        r = json.load(f)['metrics_by_source']
    assert r['holdout_test']['roc_auc'] == 0.7167
    assert 0.70 < r['cv_out_of_fold']['roc_auc'] < 0.80     # not in-sample (that would be ~0.96)
    for src in ('holdout_test', 'cv_out_of_fold'):
        assert abs(r[src]['mean_predicted'] - r[src]['observed_churn_rate']) < 0.03


def test_generation_is_deterministic():
    import generate_predictions
    r1, _, _ = generate_predictions.run(write=False)
    r2, _, _ = generate_predictions.run(write=False)
    r1 = r1.astype({'fold': 'float64'})
    r2 = r2.astype({'fold': 'float64'})
    # Generation must be 100% deterministic within the environment
    pd.testing.assert_frame_equal(
        r1.reset_index(drop=True).fillna({'top_reason_2': 'N/A', 'top_reason_3': 'N/A'}),
        r2.reset_index(drop=True).fillna({'top_reason_2': 'N/A', 'top_reason_3': 'N/A'}),
        check_dtype=False)

    # Verification against on-disk artifacts
    on_disk = pd.read_csv(ev._path('customer_predictions.csv'))
    m = r1.merge(on_disk, on='customer_id', suffixes=('_regen', '_disk'))
    # Held-out test customers must match committed model predictions identically
    holdout = m[m['prediction_source_disk'] == 'holdout_test']
    np.testing.assert_allclose(holdout['churn_prob_regen'], holdout['churn_prob_disk'], atol=1e-5)
    # Demo customer must match committed model prediction identically
    demo = m[m['prediction_source_disk'] == 'demo']
    np.testing.assert_allclose(demo['churn_prob_regen'], demo['churn_prob_disk'], atol=1e-5)
    # Out-of-fold customer predictions must maintain high cross-platform rank correlation (>0.95)
    assert m['churn_prob_regen'].corr(m['churn_prob_disk'], method='spearman') > 0.95


# ── API for out-of-fold customers ───────────────────────────────────────────
def test_oof_customer_detail_is_scored(client, oof_ids):
    body = client.get(f'/customer/{oof_ids[0]}').json()
    assert body['scored'] is True and body['prediction_source'] == 'cv_out_of_fold'
    assert 0 <= body['churn_prob'] <= 1 and body['risk_level'] in ('HIGH', 'MEDIUM', 'LOW')
    assert body['clv_score'] == round(core.calc_clv(body['monthly_charge'], body['tenure_months'],
                                                    body['churn_prob']), 2) or \
        abs(body['clv_score'] - core.calc_clv(body['monthly_charge'], body['tenure_months'],
                                              body['churn_prob'])) < 3
    assert not body['top_reason_1'].startswith('Not scored')


def test_noop_whatif_for_oof_customers_uses_their_fold_model(client, oof_ids):
    for cid in oof_ids[::200]:
        r = client.post('/whatif', json={'customer_id': cid}).json()
        assert abs(r['change']) <= 1e-3, (cid, r)


def test_retention_available_for_oof_customer(client, oof_ids):
    r = client.get(f'/retention/{oof_ids[0]}')
    assert r.status_code == 200 and r.json()['churn_prob'] is not None


@pytest.mark.parametrize('query', ['/customers?limit=5001', '/customers?plan_type=Basic',
                                   '/customers?plan_type=Standard', '/customers?plan_type=Premium'])
def test_customer_lists_cover_everyone(client, query):
    r = client.get(query)
    assert r.status_code == 200
    rows = r.json()['customers']
    assert all(c['scored'] and c['churn_prob'] is not None for c in rows)


def test_dashboard_and_segments_reconcile(client):
    k = client.get('/dashboard/summary').json()['kpis']
    assert k['unscored_count'] == 0 and k['scored_customers'] == k['total_customers'] == 5001
    assert k['high_risk_count'] + k['medium_risk_count'] + k['low_risk_count'] == 5001
    seg = client.get('/segments').json()
    assert 'Unknown' not in {g['clv_segment'] for g in seg['by_clv']}
    assert sum(g['count'] for g in seg['by_clv']) == 5001


def test_similarity_shows_model_predictions_not_generator_values(api, client):
    main, _ = api
    p = main.PREDICTIONS_DF.set_index('customer_id')
    body = client.post('/api/customer-similarity', json={'customer_id': 'CUST00002'}).json()
    people = [body['selected_customer']] + body['similar_customers']
    for c in people:
        assert c['churn_prob'] == round(float(p.loc[c['customer_id'], 'churn_prob']), 4)


# ── Fallback for genuinely unprocessable records ────────────────────────────
@pytest.mark.parametrize('broken', [{'tenure_months': None}, {'plan_type': 'Gold'},
                                    {'device_type': 'Fridge'}, {'age': -5},
                                    {'watch_hours_per_week': 'lots'}])
def test_validator_rejects_malformed_records(api, broken):
    main, _ = api
    rec = main.DATASET_DF.iloc[0].to_dict()
    rec.update(broken)
    assert core.validate_raw_record(rec)


def test_unscored_record_falls_back_to_not_scored_never_zero(api, monkeypatch):
    main, _ = api
    cid = main.FULL_DF['customer_id'].iloc[0]
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == cid,
           ['churn_prob', 'risk_level', 'clv_score', 'prediction_source', 'fold']] = np.nan
    df.loc[df['customer_id'] == cid, 'clv_segment'] = 'Unknown'
    monkeypatch.setattr(main, 'FULL_DF', df)
    client = TestClient(main.app, raise_server_exceptions=False)
    body = client.get(f'/customer/{cid}').json()
    assert body['scored'] is False and body['churn_prob'] is None
    assert body['risk_level'] == 'NOT_SCORED' and body['clv_score'] is None
    assert body['clv_segment'] == 'Unknown' and body['clv_formatted'] == 'N/A'
    assert client.post('/whatif', json={'customer_id': cid}).status_code == 409
    assert client.get(f'/retention/{cid}').status_code == 409
    assert client.get('/customers?limit=5001').status_code == 200
    assert client.get('/segments').status_code == 200


# ── CHURN-38: demo customer computed by the real model pipeline ─────────────
def test_demo_customer_scored_by_model_not_hand_typed(api, client):
    main, _ = api
    import shap
    X = main.FEATURE_MATRIX.loc[[DEMO_ID]]
    prob = float(main.MODEL.predict_proba(X)[0][1])
    body = client.get(f'/customer/{DEMO_ID}').json()
    assert body['prediction_source'] == 'demo'
    assert body['churn_prob'] == round(prob, 4) and body['churn_prob'] != 0.96
    expected_clv = core.calc_clv(body['monthly_charge'], body['tenure_months'], prob)
    assert body['clv_score'] == round(expected_clv, 2) and body['clv_score'] != 500.0
    assert body['clv_segment'] == core.get_clv_segment(expected_clv)
    reasons = core.get_top_shap_reasons(shap.TreeExplainer(main.MODEL).shap_values(X)[0],
                                        main.FEATURE_NAMES)
    for k, raw in enumerate(reasons, start=1):
        assert body[f'top_reason_{k}'] == main.explain_reason(DEMO_ID, raw)
    r = client.post('/whatif', json={'customer_id': DEMO_ID}).json()
    assert abs(r['change']) <= 1e-3


def test_no_hard_coded_demo_values_left_in_code():
    import inspect
    import main
    for fn in (main.get_customer_detail, main.what_if_simulation):
        code = '\n'.join(line.split('#')[0] for line in inspect.getsource(fn).splitlines())
        assert '500.0' not in code and '0.96' not in code and 'CUST99999' not in code
    src = open(ev._path('fix_cust99999.py')).read()
    code = '\n'.join(line.split('#')[0] for line in src.splitlines())
    assert "'churn_prob':   0.96" not in code and '500.0' not in code
