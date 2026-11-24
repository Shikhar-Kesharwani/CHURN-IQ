"""CHURN-18 / CHURN-19 — endpoint inventory, response contracts and error shape.

See docs/api/README.md for the endpoint inventory and validation results.
"""
import math

import pytest
from fastapi.testclient import TestClient

import main as api_main
from main import (CustomerDetailResponse, CustomersResponse, CustomerSimilarityResponse,
                  DashboardResponse, EmailStatusResponse, ErrorResponse, HealthResponse,
                  RetentionResponse, SegmentsResponse, WhatIfResponse)

RISK_LEVELS = {'HIGH', 'MEDIUM', 'LOW'}

# Every route the API serves (CHURN-18 inventory, docs/api/README.md §1)
EXPECTED_ROUTES = {
    ('GET', '/'), ('GET', '/customers'), ('GET', '/customer/{customer_id}'),
    ('POST', '/whatif'), ('POST', '/api/customer-similarity'), ('POST', '/customer-similarity'),
    ('GET', '/retention/{customer_id}'), ('POST', '/send-email'), ('GET', '/email-status'),
    ('GET', '/segments'), ('GET', '/dashboard/summary'),
}


@pytest.fixture(scope='module')
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def ids(api):
    p = api[0].PREDICTIONS_DF
    pick = lambda src: p.loc[p['prediction_source'] == src, 'customer_id'].iloc[0]
    return {'holdout': pick('holdout_test'), 'oof': pick('cv_out_of_fold'), 'demo': pick('demo')}


def _assert_finite_json(obj, path='$'):
    """No NaN / Infinity anywhere (JSON has no representation for them)."""
    if isinstance(obj, float):
        assert math.isfinite(obj), path
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _assert_finite_json(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_finite_json(v, f'{path}[{i}]')


def _assert_prob_fields(c):
    """Scored ↔ churn_prob in [0, 1] and a HIGH/MEDIUM/LOW tier; else null + NOT_SCORED."""
    if c['churn_prob'] is None:
        assert c['risk_level'] == 'NOT_SCORED'
    else:
        assert 0.0 <= c['churn_prob'] <= 1.0
        assert c['risk_level'] in RISK_LEVELS
        assert c['risk_level'] == api_main.get_risk_level(c['churn_prob'])


# ── Inventory (CHURN-18) ─────────────────────────────────────────────────────
def test_route_inventory_matches_documentation(api):
    served = {(m, r.path) for r in api[0].app.routes
              if getattr(r, 'include_in_schema', False) for m in r.methods}
    assert served == EXPECTED_ROUTES


def test_docs_and_openapi_are_served(client):
    for path in ('/docs', '/redoc', '/openapi.json'):
        assert client.get(path).status_code == 200


def test_openapi_declares_response_models_and_error_shape(client):
    spec = client.get('/openapi.json').json()
    assert 'ErrorResponse' in spec['components']['schemas']
    for path, ops in spec['paths'].items():
        for method, op in ops.items():
            ok = op['responses']['200']['content']['application/json']['schema']
            assert ok, (method, path)                     # every 200 has a declared schema
            assert '$ref' in ok, f'{method.upper()} {path} has no response model'


# ── Response contracts (CHURN-19) ────────────────────────────────────────────
def test_health_contract(client):
    body = client.get('/').json()
    HealthResponse.model_validate(body)
    assert body['model_loaded'] is True and body['fold_models_loaded'] is True
    assert body['similarity_ready'] is True and body['total_customers'] == 5001
    assert set(body['endpoints']) >= {'customers', 'customer_detail', 'what_if',
                                      'customer_similarity', 'retention', 'segments', 'dashboard'}


def test_customers_contract(client):
    body = client.get('/customers?limit=5001').json()
    CustomersResponse.model_validate(body)
    _assert_finite_json(body)
    assert body['count'] == len(body['customers']) == 5001
    for c in body['customers']:
        _assert_prob_fields(c)
        assert c['churn_percent'] == f"{c['churn_prob'] * 100:.1f}%"
        assert c['scored'] is (c['churn_prob'] is not None)
        assert (c['clv_score'] is None) is (c['churn_prob'] is None)
    probs = [c['churn_prob'] for c in body['customers']]
    assert probs == sorted(probs, reverse=True)               # default sort: churn_prob desc
    s = body['summary']
    assert s['high_risk_count'] + s['medium_risk_count'] + s['low_risk_count'] \
        + s['unscored_count'] == s['total_customers']


@pytest.mark.parametrize('kind', ['holdout', 'oof', 'demo'])
def test_customer_detail_contract(client, ids, kind):
    body = client.get(f'/customer/{ids[kind]}').json()
    CustomerDetailResponse.model_validate(body)
    _assert_finite_json(body)
    _assert_prob_fields(body)
    assert set(body) == set(CustomerDetailResponse.model_fields)   # no undeclared fields
    assert body['prediction_source'] in ('holdout_test', 'cv_out_of_fold', 'demo')


def test_whatif_contract(client, ids):
    body = client.post('/whatif', json={'customer_id': ids['holdout'], 'support_tickets': 3}).json()
    WhatIfResponse.model_validate(body)
    assert set(body) == set(WhatIfResponse.model_fields)
    assert body['change'] == pytest.approx(body['new_churn_prob'] - body['original_churn_prob'],
                                           abs=1e-4)
    assert body['change_percent'] == f"{body['change'] * 100:+.1f}%"
    assert body['improved'] is (body['change'] < 0)
    for k in ('original', 'new'):
        assert body[f'{k}_risk'] == api_main.get_risk_level(body[f'{k}_churn_prob'])


def test_similarity_contract(client, ids):
    body = client.post('/api/customer-similarity', json={'customer_id': ids['holdout']}).json()
    CustomerSimilarityResponse.model_validate(body)
    _assert_finite_json(body)
    _assert_prob_fields(body['selected_customer'])
    for n in body['similar_customers']:
        _assert_prob_fields(n)
        assert n['historical_churn'] in (0, 1)


def test_retention_contract(client, ids):
    body = client.get(f"/retention/{ids['holdout']}").json()
    RetentionResponse.model_validate(body)
    assert set(body) == set(RetentionResponse.model_fields)
    _assert_prob_fields(body)
    assert body['churn_percent'] == f"{body['churn_prob'] * 100:.1f}%"
    assert len(body['top_reasons']) == 3 and body['actions']


def test_segments_contract(client):
    body = client.get('/segments').json()
    SegmentsResponse.model_validate(body)
    _assert_finite_json(body)
    assert sum(g['count'] for g in body['by_plan']) == 5001
    assert len(body['monthly_trend']) == 12


def test_segments_revenue_at_risk_per_plan(client, api):
    """CHURN-53: the Segments page shows per-plan revenue at risk from the API.

    Each plan's value is monthly_charge × churn_prob summed over that plan's
    customers (unscored customers add nothing), and the plans add up to
    overall.total_revenue_at_risk.
    """
    body = client.get('/segments').json()
    df = api[0].FULL_DF
    for row in body['by_plan']:
        assert isinstance(row['revenue_at_risk'], float)
        part = df[df['plan_type'] == row['plan_type']]
        expected = float((part['monthly_charge'] * part['churn_prob']).sum())
        assert row['revenue_at_risk'] == pytest.approx(expected, abs=0.01)
    total = sum(r['revenue_at_risk'] for r in body['by_plan'])
    assert total == pytest.approx(body['overall']['total_revenue_at_risk'], abs=0.05)


def test_segments_trend_is_deterministic_and_leaves_global_rng_alone(client):
    import numpy as np
    np.random.seed(123)
    expected_next = np.random.RandomState(123).random_sample()
    first = client.get('/segments').json()['monthly_trend']
    assert np.random.random_sample() == expected_next     # global RNG not re-seeded
    assert client.get('/segments').json()['monthly_trend'] == first


def test_dashboard_contract(client):
    body = client.get('/dashboard/summary').json()
    DashboardResponse.model_validate(body)
    _assert_finite_json(body)
    assert 1 <= len(body['priority_customers']) <= 5
    for c in body['priority_customers']:
        assert c['risk_level'] == 'HIGH' and 0.7 <= c['churn_prob'] <= 1


def test_email_status_contract(client):
    EmailStatusResponse.model_validate(client.get('/email-status').json())


def test_churn_prob_is_the_same_value_and_scale_on_every_endpoint(client, ids):
    """CHURN-19: /retention used to report churn_prob on a 0-100 scale."""
    cid = ids['holdout']
    detail = client.get(f'/customer/{cid}').json()['churn_prob']
    assert client.get(f'/retention/{cid}').json()['churn_prob'] == detail
    assert client.post('/whatif', json={'customer_id': cid}).json()['original_churn_prob'] == detail
    sim = client.post('/api/customer-similarity', json={'customer_id': cid}).json()
    assert sim['selected_customer']['churn_prob'] == detail
    row = next(c for c in client.get('/customers?limit=5001').json()['customers']
               if c['customer_id'] == cid)
    assert row['churn_prob'] == detail


# ── Error shape (CHURN-19 / CHURN-21) ────────────────────────────────────────
@pytest.mark.parametrize('method,path,kwargs,status', [
    ('get', '/customer/NOPE', {}, 404),
    ('get', '/retention/NOPE', {}, 404),
    ('post', '/whatif', {'json': {'customer_id': 'NOPE'}}, 404),
    ('post', '/api/customer-similarity', {'json': {'customer_id': 'NOPE'}}, 404),
    ('get', '/no/such/route', {}, 404),
    ('post', '/whatif', {'json': {}}, 422),
    ('get', '/customers?limit=0', {}, 422),
    ('delete', '/customers', {}, 405),
])
def test_every_error_has_the_same_json_shape(client, method, path, kwargs, status):
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == status
    assert r.headers['content-type'].startswith('application/json')
    body = r.json()
    ErrorResponse.model_validate(body)
    assert isinstance(body['detail'], str) and body['detail']
    assert body['status_code'] == status and body['error']


def test_validation_errors_list_fields_without_echoing_input(client, ids):
    secret = 'x' * 40
    r = client.post('/whatif', json={'customer_id': ids['holdout'], 'watch_hours_per_week': -1,
                                     'tenure_months': 'abc', 'unknown_field': secret})
    body = r.json()
    assert r.status_code == 422 and body['error'] == 'validation_error'
    assert {e['field'] for e in body['errors']} == {'watch_hours_per_week', 'tenure_months',
                                                    'unknown_field'}
    assert secret not in r.text and 'abc' not in r.text
