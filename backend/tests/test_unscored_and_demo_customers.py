"""CHURN-16 follow-up: unscored customers (Bug A, interim fix) and demo customer (Bug B).

See docs/ml/06-followup-audit.md.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import churniq_core as core

UNSCORED_ID = 'CUST00002'   # training-split customer (no out-of-sample prediction)
DEMO_ID = 'CUST99999'


@pytest.fixture(scope='module')
def client(api):
    main, _ = api
    return TestClient(main.app, raise_server_exceptions=False)


def test_unscored_customers_are_exactly_the_training_split(api, artifacts):
    main, _ = api
    unscored = set(main.FULL_DF.loc[main.FULL_DF['churn_prob'].isna(), 'customer_id'])
    train_ids = set(artifacts['base'].loc[artifacts['X_train'].index, 'customer_id'])
    assert unscored == train_ids and len(unscored) == 4000
    assert UNSCORED_ID in unscored


# ── Bug A (interim): never fabricate zero risk, never 500 ───────────────────
def test_unscored_customer_detail_is_explicitly_not_scored(client):
    body = client.get(f'/customer/{UNSCORED_ID}').json()
    assert body['scored'] is False and body['prediction_source'] is None
    assert body['churn_prob'] is None and body['risk_level'] == 'NOT_SCORED'
    assert body['clv_score'] is None and body['clv_segment'] == 'Unknown'
    assert body['clv_formatted'] == 'N/A' and body['clv_breakdown']['retention_factor'] is None
    assert body['top_reason_1'].startswith('Not scored')


def test_scored_customer_detail_unchanged(client, scored_ids):
    body = client.get(f'/customer/{scored_ids[0]}').json()
    assert body['scored'] is True and body['prediction_source'] == 'holdout_test'
    assert isinstance(body['churn_prob'], float)
    assert body['risk_level'] in ('HIGH', 'MEDIUM', 'LOW')


@pytest.mark.parametrize('call', ['whatif', 'retention'])
def test_unscored_whatif_and_retention_return_409_not_500(client, call):
    r = (client.post('/whatif', json={'customer_id': UNSCORED_ID}) if call == 'whatif'
         else client.get(f'/retention/{UNSCORED_ID}'))
    assert r.status_code == 409
    assert 'not scored' in r.json()['detail']


@pytest.mark.parametrize('query', ['/customers?limit=5001', '/customers?plan_type=Basic',
                                   '/customers?plan_type=Standard', '/customers?plan_type=Premium'])
def test_customer_lists_including_unscored_rows_do_not_500(client, query):
    r = client.get(query)
    assert r.status_code == 200
    rows = r.json()['customers']
    unscored = [c for c in rows if not c['scored']]
    assert unscored, 'expected unscored rows in this list'
    for c in unscored:
        assert c['churn_prob'] is None and c['risk_level'] == 'NOT_SCORED'
        assert c['clv_score'] is None and c['clv_segment'] == 'Unknown'
    # Scored rows still come first when sorting by churn_prob
    flags = [c['scored'] for c in rows]
    assert flags == sorted(flags, reverse=True)


def test_dashboard_counts_reconcile(client):
    k = client.get('/dashboard/summary').json()['kpis']
    assert k['high_risk_count'] + k['medium_risk_count'] + k['low_risk_count'] + k['unscored_count'] \
        == k['total_customers'] == 5001
    assert k['scored_customers'] == 1001
    assert k['high_risk_pct'] == round(k['high_risk_count'] / k['scored_customers'] * 100, 1)


def test_segments_report_unscored_as_unknown(client):
    r = client.get('/segments')
    assert r.status_code == 200
    by_clv = {g['clv_segment']: g for g in r.json()['by_clv']}
    assert by_clv['Unknown']['count'] == 4000
    assert by_clv['Unknown']['avg_churn'] is None          # no fabricated rate
    assert sum(g['count'] for g in by_clv.values()) == 5001


def test_similarity_never_shows_generator_probability(api, client):
    main, _ = api
    dataset = main.DATASET_DF.set_index('customer_id')
    body = client.post('/api/customer-similarity', json={'customer_id': UNSCORED_ID}).json()
    assert body['selected_customer']['churn_prob'] is None
    assert body['selected_customer']['risk_level'] == 'NOT_SCORED'
    body = client.post('/api/customer-similarity', json={'customer_id': 'CUST01033'}).json()
    scored = set(main.FULL_DF.loc[main.FULL_DF['churn_prob'].notna(), 'customer_id'])
    for n in body['similar_customers']:
        if n['customer_id'] in scored:
            assert n['churn_prob'] is not None
        else:
            assert n['churn_prob'] is None and n['risk_level'] == 'NOT_SCORED'
            assert n['churn_percent'] == 'Not scored'
        assert n['churn_prob'] != round(float(dataset.loc[n['customer_id'], 'churn_probability']), 4) \
            or n['customer_id'] in scored


@pytest.mark.xfail(strict=True, reason='Bug A (full fix, pending approval): out-of-fold '
                                       'predictions for the 4,000 training-split customers')
def test_every_customer_has_an_out_of_sample_prediction(api):
    main, _ = api
    assert main.FULL_DF['churn_prob'].notna().all()


# ── Bug B: demo customer scored by the model ────────────────────────────────
def test_demo_customer_scored_by_model_not_hand_typed(api, client):
    main, _ = api
    import shap
    X = main.FEATURE_MATRIX.loc[[DEMO_ID]]
    prob = float(main.MODEL.predict_proba(X)[0][1])
    body = client.get(f'/customer/{DEMO_ID}').json()
    assert body['prediction_source'] == 'demo_live_model'
    assert body['churn_prob'] == round(prob, 4)
    assert body['churn_prob'] != 0.96                       # no longer hand-set
    expected_clv = core.calc_clv(body['monthly_charge'], body['tenure_months'], prob)
    assert body['clv_score'] == round(expected_clv, 2)
    assert body['clv_score'] != 500.0
    assert body['clv_segment'] == core.get_clv_segment(expected_clv)
    reasons = core.get_top_shap_reasons(shap.TreeExplainer(main.MODEL).shap_values(X)[0],
                                        main.FEATURE_NAMES)
    for k, raw in enumerate(reasons, start=1):
        assert body[f'top_reason_{k}'] == main.explain_reason(DEMO_ID, raw)


def test_no_hard_coded_demo_override_left_in_main():
    import inspect
    import main
    code = '\n'.join(line.split('#')[0] for line in
                     inspect.getsource(main.get_customer_detail).splitlines())
    assert '500.0' not in code and '0.96' not in code and 'CUST99999' not in code
