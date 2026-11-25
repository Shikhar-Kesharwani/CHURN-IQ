"""CHURN-54: the API answers CORS only for the deployed frontend and local dev servers."""
import pytest

import cors_config as cc

PROD = 'https://churn-iq-frontend-five.vercel.app'
PREFLIGHT = {'Access-Control-Request-Method': 'GET'}


@pytest.fixture(scope='module')
def client(api):
    return api[1]


# ── Allowed and rejected origins on the real app ─────────────────────────────

@pytest.mark.parametrize('origin', [PROD, 'http://localhost:5173', 'http://127.0.0.1:5173',
                                    'http://localhost:4173'])
def test_allowed_origin_is_echoed_without_credentials(client, origin):
    r = client.get('/', headers={'Origin': origin})
    assert r.status_code == 200
    assert r.headers['access-control-allow-origin'] == origin
    assert 'access-control-allow-credentials' not in r.headers


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://localhost:3000',
                                    'https://churn-iq-frontend-five.vercel.app.evil.example',
                                    'http://churn-iq-frontend-five.vercel.app', 'null'])
def test_rejected_origin_gets_no_cors_headers(client, origin):
    r = client.get('/', headers={'Origin': origin})
    assert r.status_code == 200           # the server still answers; the browser blocks the read
    assert 'access-control-allow-origin' not in r.headers
    assert 'access-control-allow-credentials' not in r.headers


def test_never_answers_with_a_wildcard(client):
    for origin in (PROD, 'https://evil.example'):
        r = client.get('/dashboard/summary', headers={'Origin': origin})
        assert r.headers.get('access-control-allow-origin') != '*'


def test_preflight_from_allowed_origin_succeeds(client):
    r = client.options('/whatif', headers={'Origin': PROD, 'Access-Control-Request-Method': 'POST',
                                           'Access-Control-Request-Headers': 'content-type'})
    assert r.status_code == 200
    assert r.headers['access-control-allow-origin'] == PROD
    assert 'POST' in r.headers['access-control-allow-methods']


def test_preflight_from_rejected_origin_is_refused(client):
    r = client.options('/whatif', headers={'Origin': 'https://evil.example', **PREFLIGHT})
    assert r.status_code == 400
    assert 'access-control-allow-origin' not in r.headers


def test_preflight_rejects_unlisted_method(client):
    r = client.options('/', headers={'Origin': PROD, 'Access-Control-Request-Method': 'DELETE'})
    assert r.status_code == 400


def test_app_uses_the_default_list_when_env_is_unset(api, monkeypatch):
    main, _ = api
    monkeypatch.delenv(cc.ENV_VAR, raising=False)
    assert main.CORS_ALLOWED_ORIGINS == cc.parse_allowed_origins(None) == list(cc.DEFAULT_ALLOWED_ORIGINS)


# ── Parsing CORS_ALLOWED_ORIGINS ─────────────────────────────────────────────

def test_defaults_contain_production_and_local_dev_only():
    assert cc.DEFAULT_ALLOWED_ORIGINS[0] == PROD
    assert all(o.startswith(('http://localhost:', 'http://127.0.0.1:')) for o in cc.DEFAULT_ALLOWED_ORIGINS[1:])
    assert cc.ALLOW_CREDENTIALS is False


@pytest.mark.parametrize('raw', [None, '', '   ', '*', ' * , ', 'not a url', 'ftp://x.example'])
def test_unset_blank_or_all_invalid_falls_back_to_defaults(raw):
    assert cc.parse_allowed_origins(raw) == list(cc.DEFAULT_ALLOWED_ORIGINS)


def test_env_list_is_normalised_deduplicated_and_drops_wildcards():
    raw = 'https://App.Example.com/, https://app.example.com , *, http://localhost:5173,https://x.example/path'
    assert cc.parse_allowed_origins(raw) == ['https://app.example.com', 'http://localhost:5173']
    assert cc.invalid_entries(raw) == ['*', 'https://x.example/path']


@pytest.mark.parametrize('value,expected', [
    ('https://a.example', 'https://a.example'),
    ('https://a.example:8443/', 'https://a.example:8443'),
    ('HTTP://LOCALHOST:5173', 'http://localhost:5173'),
    ('https://*.vercel.app', None),
    ('https://a.example/app', None),
    ('https://user@a.example', None),
    ('a.example', None),
])
def test_normalise_origin(value, expected):
    assert cc.normalise_origin(value) == expected
