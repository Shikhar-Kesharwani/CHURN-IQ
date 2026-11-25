"""CHURN-55: the frontend's recorded API fixtures must match the live API's shape.

The frontend unit tests (vitest) run against JSON captured from the API in
frontend/src/test/fixtures/. If the backend renames, removes, adds or retypes
a field, those tests would keep passing against stale JSON. This test calls
the real app for every fixture and compares field names and JSON types
recursively. It does not compare values: the model, and therefore every
number, may change without the contract changing.
"""
import json
import os

import pytest

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'test', 'fixtures')

# fixture file → the request the frontend makes for it (frontend/src/api/churniq.js)
CONTRACTS = {
    'dashboard.json':               ('GET',  '/dashboard/summary', None),
    'segments.json':                ('GET',  '/segments', None),
    'customers-sample.json':        ('GET',  '/customers?limit=10000', None),
    'customer-CUST00001.json':      ('GET',  '/customer/CUST00001', None),
    'customer-CUST02261.json':      ('GET',  '/customer/CUST02261', None),
    'retention-CUST02261.json':     ('GET',  '/retention/CUST02261', None),
    'whatif-CUST00001.json':        ('POST', '/whatif', {'customer_id': 'CUST00001', 'watch_hours_per_week': 20}),
    'similarity-CUST00001-3.json':  ('POST', '/api/customer-similarity', {'customer_id': 'CUST00001', 'n_neighbors': 3}),
}


def json_type(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'boolean'
    if isinstance(v, (int, float)):
        return 'number'          # JSON has one number type: 40.0 and 40 are the same
    if isinstance(v, str):
        return 'string'
    if isinstance(v, list):
        return 'array'
    return 'object'


def shape_diff(fixture, live, path='$'):
    """List the differences in field names and JSON types between two values.

    * Objects must have exactly the same keys, in both directions.
    * `null` on either side matches any type (the field is optional or nullable).
    * Arrays: every element of the fixture is compared with the first live element,
      so a stale element anywhere in the fixture is caught. Empty arrays are skipped.
    """
    ft, lt = json_type(fixture), json_type(live)
    if 'null' in (ft, lt):
        return []
    if ft != lt:
        return [f'{path}: fixture has {ft}, API returns {lt}']
    out = []
    if ft == 'object':
        for k in sorted(set(fixture) - set(live)):
            out.append(f'{path}.{k}: in fixture, no longer returned by the API')
        for k in sorted(set(live) - set(fixture)):
            out.append(f'{path}.{k}: returned by the API, missing from the fixture')
        for k in sorted(set(fixture) & set(live)):
            out += shape_diff(fixture[k], live[k], f'{path}.{k}')
    elif ft == 'array' and fixture and live:
        for i, item in enumerate(fixture):
            out += shape_diff(item, live[0], f'{path}[{i}]')
    return out


@pytest.fixture(scope='module')
def client(api):
    return api[1]


@pytest.fixture
def no_gemini(api, monkeypatch):
    """/retention must use its deterministic rule-based path: no network call."""
    main = api[0]
    monkeypatch.setattr(main, 'GEMINI_ENABLED', False)
    monkeypatch.setattr(main, 'GEMINI_MODEL', None)


def load(name):
    with open(os.path.join(FIXTURE_DIR, name), encoding='utf-8') as f:
        return json.load(f)


def test_every_fixture_has_a_contract():
    files = sorted(f for f in os.listdir(FIXTURE_DIR) if f.endswith('.json'))
    assert files == sorted(CONTRACTS), 'add new fixtures to CONTRACTS so their shape is checked'


@pytest.mark.parametrize('name', sorted(CONTRACTS))
def test_fixture_matches_live_api_shape(client, no_gemini, name):
    method, path, body = CONTRACTS[name]
    r = client.get(path) if method == 'GET' else client.post(path, json=body)
    assert r.status_code == 200, (path, r.text[:300])
    diffs = shape_diff(load(name), r.json())
    assert not diffs, f'{name} no longer matches {method} {path}:\n' + '\n'.join(diffs)


# ── The checker itself ───────────────────────────────────────────────────────

def test_shape_diff_detects_renamed_removed_added_and_retyped_fields():
    live = {'a': 1, 'b': 'x', 'c': [{'d': True}], 'e': {'f': 1.5}}
    assert shape_diff(live, live) == []
    assert shape_diff({**live, 'a': 2.0, 'b': 'y'}, live) == []                 # values may differ
    assert shape_diff({**live, 'old': 1}, live) == ['$.old: in fixture, no longer returned by the API']
    assert shape_diff({k: v for k, v in live.items() if k != 'b'}, live) == [
        '$.b: returned by the API, missing from the fixture']
    assert shape_diff({**live, 'b': 3}, live) == ['$.b: fixture has number, API returns string']
    assert shape_diff({**live, 'c': [{'d': 'yes'}]}, live) == [
        '$.c[0].d: fixture has string, API returns boolean']
    assert shape_diff({**live, 'e': {'g': 1}}, live) == [
        '$.e.g: in fixture, no longer returned by the API',
        '$.e.f: returned by the API, missing from the fixture']


def test_shape_diff_allows_null_and_empty_arrays():
    assert shape_diff({'a': None, 'b': []}, {'a': 'x', 'b': [{'c': 1}]}) == []
    assert shape_diff({'a': 1}, {'a': None}) == []


def test_contract_check_fails_on_a_stale_fixture(client):
    stale = load('dashboard.json')
    stale['kpis']['high_risk_total'] = stale['kpis'].pop('high_risk_count')    # simulated rename
    diffs = shape_diff(stale, client.get('/dashboard/summary').json())
    assert '$.kpis.high_risk_total: in fixture, no longer returned by the API' in diffs
    assert '$.kpis.high_risk_count: returned by the API, missing from the fixture' in diffs
