"""CHURN-20 / CHURN-25 — input validation, boundary values and edge cases.

Rule of thumb enforced here: invalid input is a 4xx with a clear message, and
NO input — however malformed — produces a 500.
"""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import main as api_main

LO = {k: v[0] for k, v in api_main.WHATIF_BOUNDS.items()}
HI = {k: v[1] for k, v in api_main.WHATIF_BOUNDS.items()}


@pytest.fixture(scope='module')
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def cid(scored_ids):
    return scored_ids[0]


def _check(r, status, error=None, mentions=None):
    assert r.status_code == status, (r.status_code, r.text)
    body = r.json()
    assert isinstance(body['detail'], str)
    if error:
        assert body['error'] == error
    if mentions:
        assert mentions in body['detail'] or any(e['field'] == mentions for e in body.get('errors', []))


# ── Customer IDs ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize('bad', ['', '   ', 'CUST 0001', "CUST'; DROP TABLE--", 'ä' * 5,
                                 'A' * 33, 'CUST00001\x00', 'CUST\n00001', '../etc/passwd'])
def test_malformed_customer_id_in_body_is_422(client, bad):
    for path in ('/whatif', '/api/customer-similarity', '/customer-similarity'):
        _check(client.post(path, json={'customer_id': bad}), 422, 'validation_error', 'customer_id')


@pytest.mark.parametrize('bad', [123, None, True, ['CUST00001'], {'id': 'CUST00001'}])
def test_non_string_customer_id_is_422(client, bad):
    _check(client.post('/whatif', json={'customer_id': bad}), 422, 'validation_error')


@pytest.mark.parametrize('path', ['/customer/{}', '/retention/{}'])
@pytest.mark.parametrize('bad', ['CUST%20%200001', 'A' * 33, "x'y", 'a.b'])
def test_malformed_customer_id_in_path_is_422(client, path, bad):
    _check(client.get(path.format(bad)), 422, 'validation_error')


@pytest.mark.parametrize('unknown', ['NOPE', 'CUST00000', 'cust00001', 'CUST123456', 'X'])
def test_unknown_but_well_formed_id_is_404_everywhere(client, unknown):
    _check(client.get(f'/customer/{unknown}'), 404, 'customer_not_found')
    _check(client.get(f'/retention/{unknown}'), 404, 'customer_not_found')
    _check(client.post('/whatif', json={'customer_id': unknown}), 404, 'customer_not_found')
    _check(client.post('/api/customer-similarity', json={'customer_id': unknown}), 404,
           'customer_not_found')


def test_surrounding_whitespace_is_ignored_on_every_endpoint(client, cid):
    padded = f'  {cid}\t'
    assert client.get(f'/customer/%20{cid}%20').json()['customer_id'] == cid
    assert client.get(f'/retention/%20{cid}').json()['customer_id'] == cid
    assert client.post('/whatif', json={'customer_id': padded}).json()['customer_id'] == cid
    sim = client.post('/api/customer-similarity', json={'customer_id': padded}).json()
    assert sim['selected_customer']['customer_id'] == cid


# ── Request bodies ───────────────────────────────────────────────────────────
@pytest.mark.parametrize('path', ['/whatif', '/api/customer-similarity', '/send-email'])
@pytest.mark.parametrize('content', [b'', b'{not json', b'[]', b'"CUST00001"', b'null', b'{"a":'])
def test_empty_and_malformed_bodies_are_422(client, path, content, email_auth):
    # /send-email needs the CHURN-44 bearer token before its body is even read
    r = client.post(path, content=content, headers={'content-type': 'application/json',
                                                     **email_auth})
    _check(r, 422, 'validation_error')


def test_wrong_content_type_is_422(client, cid):
    r = client.post('/whatif', content=f'customer_id={cid}',
                    headers={'content-type': 'application/x-www-form-urlencoded'})
    _check(r, 422, 'validation_error')


def test_unknown_whatif_field_is_rejected_not_ignored(client, cid):
    # A typo used to be silently ignored, returning an unchanged prediction
    _check(client.post('/whatif', json={'customer_id': cid, 'watch_hourz': 1}), 422,
           'validation_error', 'watch_hourz')


# ── What-if values ───────────────────────────────────────────────────────────
@pytest.mark.parametrize('field', list(api_main.WHATIF_BOUNDS))
def test_whatif_boundary_values_are_accepted(client, cid, field):
    for value in (LO[field], HI[field]):
        r = client.post('/whatif', json={'customer_id': cid, field: value})
        assert r.status_code == 200, (field, value, r.text)
        assert 0 <= r.json()['new_churn_prob'] <= 1


@pytest.mark.parametrize('field', list(api_main.WHATIF_BOUNDS))
def test_whatif_values_just_outside_bounds_are_422(client, cid, field):
    step = 0.1 if isinstance(LO[field], float) else 1
    for value in (LO[field] - step, HI[field] + step):
        _check(client.post('/whatif', json={'customer_id': cid, field: value}), 422,
               'validation_error', field)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', 1e308, -1e308, '12', True, [1], {}])
def test_whatif_non_finite_and_wrong_type_values_are_422(client, cid, value):
    for field in ('watch_hours_per_week', 'tenure_months'):
        _check(client.post('/whatif', json={'customer_id': cid, field: value}), 422,
               'validation_error', field)


def test_whatif_raw_nan_literal_is_rejected(client, cid):
    # Python's json emits a bare NaN token; it must not be silently replaced by
    # build_feature_row's default (5.0 hrs) as it was before CHURN-20.
    raw = json.dumps({'customer_id': cid, 'watch_hours_per_week': float('nan')})
    assert 'NaN' in raw
    r = client.post('/whatif', content=raw, headers={'content-type': 'application/json'})
    assert r.status_code == 422


def test_whatif_fractional_int_is_422_but_integral_float_for_hours_is_ok(client, cid):
    _check(client.post('/whatif', json={'customer_id': cid, 'tenure_months': 2.5}), 422)
    assert client.post('/whatif', json={'customer_id': cid, 'watch_hours_per_week': 8}).status_code == 200


def test_whatif_null_values_keep_the_customers_actual_values(client, cid):
    nulls = {f: None for f in api_main.WHATIF_BOUNDS}
    a = client.post('/whatif', json={'customer_id': cid, **nulls}).json()
    b = client.post('/whatif', json={'customer_id': cid}).json()
    assert a == b and abs(a['change']) <= 1e-3


# ── Similarity n_neighbors ───────────────────────────────────────────────────
@pytest.mark.parametrize('n', [0, -1, -100, api_main.MAX_SIMILAR_NEIGHBORS + 1, 5000, 2.5, '5', True])
def test_invalid_n_neighbors_is_422_not_silently_replaced(client, cid, n):
    _check(client.post('/api/customer-similarity', json={'customer_id': cid, 'n_neighbors': n}),
           422, 'validation_error', 'n_neighbors')


def test_missing_or_null_n_neighbors_defaults_to_five(client, cid):
    for body in ({'customer_id': cid}, {'customer_id': cid, 'n_neighbors': None}):
        assert client.post('/api/customer-similarity', json=body).json()['count'] == 5


# ── /customers query parameters ──────────────────────────────────────────────
@pytest.mark.parametrize('query,field', [
    ('limit=0', 'limit'), ('limit=-1', 'limit'), ('limit=abc', 'limit'),
    (f'limit={api_main.MAX_CUSTOMERS_LIMIT + 1}', 'limit'),
    ('risk_level=BOGUS', None), ('plan_type=Gold', None),
    ('sort_by=churn_probability', None), ('sort_by=churn', None), ('sort_by=email', None),
])
def test_invalid_customers_query_is_422(client, query, field):
    _check(client.get(f'/customers?{query}'), 422, 'validation_error', field)


def test_customers_filters_are_case_insensitive_and_applied(client):
    for level in ('high', 'Medium', 'LOW'):
        rows = client.get(f'/customers?risk_level={level}&limit=10000').json()['customers']
        assert rows and {r['risk_level'] for r in rows} == {level.upper()}
    rows = client.get('/customers?plan_type=premium&limit=10000').json()['customers']
    assert rows and {r['plan_type'] for r in rows} == {'Premium'}
    assert client.get('/customers?risk_level=NOT_SCORED').json()['count'] == 0  # all scored


def test_customers_limit_boundaries(client):
    assert client.get('/customers?limit=1').json()['count'] == 1
    assert client.get(f'/customers?limit={api_main.MAX_CUSTOMERS_LIMIT}').json()['count'] == 5001


@pytest.mark.parametrize('field', api_main.CUSTOMERS_SORT_FIELDS)
def test_every_allowed_sort_field_works(client, field):
    assert client.get(f'/customers?sort_by={field}&limit=3').status_code == 200


# ── /send-email ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize('body', [
    {'subject': 'Hi\nBcc: victim@example.com', 'body': 'x'},     # header injection
    {'subject': 'Hi\r\nX-Header: 1', 'body': 'x'},
    {'subject': '', 'body': 'x'}, {'subject': '   ', 'body': 'x'},
    {'subject': 'x' * 201, 'body': 'x'}, {'subject': 'Hi', 'body': ''},
    {'subject': 'Hi', 'body': '  '}, {'subject': 'Hi', 'body': 'x' * 5001},
    {'subject': 'Hi'}, {'body': 'x'}, {'subject': 'Hi', 'body': 'x', 'to': 'a@b.c'},
])
def test_send_email_rejects_bad_bodies_before_anything_else(client, cid, body, email_auth):
    _check(client.post('/send-email', json={'customer_id': cid, **body}, headers=email_auth),
           422, 'validation_error')


# ── NOT_SCORED behaviour (Aryan, CHURN-37) is preserved ──────────────────────
def test_not_scored_customer_still_returns_409_with_new_error_shape(api, monkeypatch):
    main = api[0]
    target = main.FULL_DF['customer_id'].iloc[0]
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == target,
           ['churn_prob', 'risk_level', 'clv_score', 'prediction_source', 'fold']] = np.nan
    monkeypatch.setattr(main, 'FULL_DF', df)
    client = TestClient(main.app, raise_server_exceptions=False)
    for r in (client.post('/whatif', json={'customer_id': target}),
              client.get(f'/retention/{target}')):
        _check(r, 409, 'customer_not_scored')
        assert 'not scored by the model' in r.json()['detail']
    detail = client.get(f'/customer/{target}').json()
    assert detail['risk_level'] == 'NOT_SCORED' and detail['churn_prob'] is None
    rows = client.get('/customers?risk_level=NOT_SCORED').json()['customers']
    assert [r['customer_id'] for r in rows] == [target]
    sim = client.post('/api/customer-similarity', json={'customer_id': target}).json()
    assert sim['selected_customer']['risk_level'] == 'NOT_SCORED'


# ── Fuzz: nothing produces a 500 ─────────────────────────────────────────────
def test_randomised_whatif_inputs_never_cause_500(client, scored_ids):
    rng = np.random.RandomState(7)
    pool = [None, -1, 0, 1, 3.7, 40, 1e6, 'x', True, [], {}]
    for i in range(150):
        body = {'customer_id': scored_ids[i % len(scored_ids)]}
        for field in api_main.WHATIF_BOUNDS:
            if rng.rand() < 0.5:
                body[field] = pool[rng.randint(len(pool))]
        r = client.post('/whatif', json=body)
        assert r.status_code in (200, 422), (body, r.status_code, r.text)
