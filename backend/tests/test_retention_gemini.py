"""CHURN-22 — Gemini retention API (GET /retention/{id}) integration tests.

Gemini is mocked: no network call, no API key needed, deterministic. The real
HTTP endpoint, customer lookup, SHAP reasons and prompt construction run
unmocked. A live-key smoke test is in docs/api/README.md §5 (manual).
"""
import json
import logging
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from google.api_core import exceptions as gexc

from main import RetentionResponse

FAKE_KEY = 'AIzaFAKE_TEST_KEY_not_a_real_key'
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOOD = {
    'subject': 'We miss you, friend',
    'email': 'Hi there,\n\nHere is a month on us.\n\nBest,\nThe Team',
    'actions': ['Call within 24h to fix billing', 'Send a curated content digest'],
    'priority': 'high',
    'suggested_offer': '1 month free',
}


class FakeResponse:
    def __init__(self, text):
        self._text = text

    @property
    def text(self):
        if isinstance(self._text, Exception):
            raise self._text
        return self._text


class FakeGemini:
    """Stands in for genai.GenerativeModel; records every call."""

    def __init__(self, reply=None, raises=None):
        self.reply, self.raises, self.calls = reply, raises, []

    def generate_content(self, prompt, request_options=None):
        self.calls.append({'prompt': prompt, 'request_options': request_options})
        if self.raises is not None:
            raise self.raises
        return FakeResponse(self.reply)


@pytest.fixture
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture
def gemini(api, monkeypatch):
    """Install a FakeGemini as if a key were configured."""
    main = api[0]

    def install(**kw):
        fake = FakeGemini(**kw)
        monkeypatch.setattr(main, 'GEMINI_API_KEY', FAKE_KEY)
        monkeypatch.setattr(main, 'GEMINI_ENABLED', True)
        monkeypatch.setattr(main, 'GEMINI_MODEL', fake)
        return fake
    return install


@pytest.fixture(scope='module')
def risk_mix(api):
    """Six customers: two per risk tier, mixing holdout, out-of-fold and demo."""
    p = api[0].PREDICTIONS_DF
    picks = []
    for level in ('HIGH', 'MEDIUM', 'LOW'):
        tier = p[p['risk_level'] == level]
        picks.append(tier[tier['prediction_source'] == 'holdout_test']['customer_id'].iloc[0])
        picks.append(tier[tier['prediction_source'] == 'cv_out_of_fold']['customer_id'].iloc[0])
    return picks


def _check_body(body, cid):
    RetentionResponse.model_validate(body)
    assert body['customer_id'] == cid
    assert 0 <= body['churn_prob'] <= 1
    assert len(body['top_reasons']) == 3 and all(body['top_reasons'])
    assert body['subject'].strip() and body['email'].strip() and body['actions']


# ── Genuine Gemini output ────────────────────────────────────────────────────
def test_gemini_output_for_customers_across_risk_levels(api, client, gemini, risk_mix):
    main = api[0]
    fake = gemini(reply=json.dumps(GOOD))
    seen_levels = set()
    for cid in risk_mix:
        r = client.get(f'/retention/{cid}')
        assert r.status_code == 200, r.text
        body = r.json()
        _check_body(body, cid)
        assert body['ai_generated'] is True and body['fallback_reason'] is None
        assert body['generated_by'] == main.GEMINI_MODEL_NAME == 'gemini-2.5-flash'
        assert body['subject'] == GOOD['subject'] and body['actions'] == GOOD['actions']
        assert body['priority'] == 'HIGH'                   # normalised to upper case
        expected = main.PREDICTIONS_DF.set_index('customer_id').loc[cid, 'churn_prob']
        assert body['churn_prob'] == round(float(expected), 4)
        seen_levels.add(body['risk_level'])
        # Prompt is grounded in this customer's model output
        prompt = fake.calls[-1]['prompt']
        assert f"{body['churn_prob'] * 100:.1f}%" in prompt
        for reason in body['top_reasons']:
            assert reason in prompt
    assert seen_levels == {'HIGH', 'MEDIUM', 'LOW'} and len(risk_mix) >= 5


def test_gemini_call_has_a_timeout(api, client, gemini, risk_mix):
    fake = gemini(reply=json.dumps(GOOD))
    client.get(f'/retention/{risk_mix[0]}')
    assert fake.calls[0]['request_options'] == {'timeout': api[0].GEMINI_TIMEOUT_SECONDS}
    assert 0 < api[0].GEMINI_TIMEOUT_SECONDS <= 60


@pytest.mark.parametrize('wrapped', ['```json\n{}\n```', '```\n{}\n```', '  {}  '])
def test_markdown_fenced_json_is_accepted(client, gemini, risk_mix, wrapped):
    gemini(reply=wrapped.replace('{}', json.dumps(GOOD)))
    assert client.get(f'/retention/{risk_mix[0]}').json()['ai_generated'] is True


def test_invalid_gemini_priority_falls_back_to_risk_tier(client, gemini, risk_mix):
    gemini(reply=json.dumps({**GOOD, 'priority': 'URGENT!!'}))
    body = client.get(f'/retention/{risk_mix[-1]}').json()   # a LOW-risk customer
    assert body['ai_generated'] is True and body['priority'] == body['risk_level'] == 'LOW'


# ── Fallbacks: always labelled, never a crash ────────────────────────────────
def test_missing_api_key_uses_labelled_rule_based_fallback(api, client, risk_mix, monkeypatch):
    main = api[0]
    monkeypatch.setattr(main, 'GEMINI_ENABLED', False)
    monkeypatch.setattr(main, 'GEMINI_MODEL', None)
    for cid in risk_mix:
        r = client.get(f'/retention/{cid}')
        assert r.status_code == 200
        body = r.json()
        _check_body(body, cid)
        assert body['generated_by'] == 'rule-based-fallback'
        assert body['ai_generated'] is False
        assert body['fallback_reason'] == 'gemini_not_configured'
        assert body['priority'] == body['risk_level']        # LOW is no longer reported as MEDIUM


@pytest.mark.parametrize('error,reason', [
    (gexc.DeadlineExceeded('Deadline Exceeded'), 'gemini_timeout'),
    (TimeoutError('read timed out'), 'gemini_timeout'),
    (gexc.ResourceExhausted('429 quota exceeded'), 'gemini_api_error'),
    (gexc.ServiceUnavailable('503 backend unavailable'), 'gemini_api_error'),
    (gexc.PermissionDenied(f'403 API key not valid: {FAKE_KEY}'), 'gemini_api_error'),
    (ConnectionError('network unreachable'), 'gemini_api_error'),
    (RuntimeError('unexpected client failure'), 'gemini_api_error'),
])
def test_upstream_failures_fall_back_without_crashing(client, gemini, risk_mix, error, reason):
    gemini(raises=error)
    r = client.get(f'/retention/{risk_mix[0]}')
    assert r.status_code == 200
    body = r.json()
    assert body['ai_generated'] is False and body['generated_by'] == 'rule-based-fallback'
    assert body['fallback_reason'] == reason
    assert FAKE_KEY not in r.text


@pytest.mark.parametrize('reply', [
    'Sure! Here is your email: Dear customer...',          # not JSON
    '{"subject": "Hi", "email": "Body"',                    # truncated JSON
    '[1, 2, 3]',                                            # JSON but not an object
    json.dumps({**GOOD, 'email': ''}),                      # empty email
    json.dumps({**GOOD, 'subject': None}),                  # missing subject
    json.dumps({k: v for k, v in GOOD.items() if k != 'actions'}),
    json.dumps({**GOOD, 'actions': 'call them'}),           # actions not a list
    json.dumps({**GOOD, 'actions': []}),
    json.dumps({**GOOD, 'actions': ['ok', 3]}),
    ValueError('response.text quick accessor: blocked by safety'),   # blocked response
])
def test_unusable_gemini_output_is_never_passed_off_as_ai(client, gemini, risk_mix, reply):
    gemini(reply=reply)
    body = client.get(f'/retention/{risk_mix[0]}').json()
    assert body['ai_generated'] is False
    assert body['fallback_reason'] == 'gemini_invalid_response'
    assert body['email'].strip() and body['subject'].strip()


def test_api_key_never_appears_in_logs_or_response(client, gemini, risk_mix, caplog):
    gemini(raises=gexc.PermissionDenied(
        f'403 POST https://generativelanguage.googleapis.com/v1beta/models?key={FAKE_KEY}: '
        f'API key {FAKE_KEY} not valid'))
    with caplog.at_level(logging.DEBUG):
        r = client.get(f'/retention/{risk_mix[0]}')
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in r.text
    assert 'PermissionDenied' in caplog.text and '[REDACTED]' in caplog.text


def test_unknown_and_not_scored_customers_do_not_call_gemini(api, client, gemini, monkeypatch):
    import numpy as np
    main = api[0]
    fake = gemini(reply=json.dumps(GOOD))
    assert client.get('/retention/NOPE').status_code == 404
    cid = main.FULL_DF['customer_id'].iloc[0]
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == cid, ['churn_prob', 'risk_level', 'clv_score']] = np.nan
    monkeypatch.setattr(main, 'FULL_DF', df)
    assert client.get(f'/retention/{cid}').status_code == 409
    assert fake.calls == []


# ── Start-up configuration (real module import in a subprocess) ──────────────
@pytest.mark.parametrize('key,enabled', [(None, False), ('', False),
                                         ('YOUR_GEMINI_API_KEY', False), (FAKE_KEY, True)])
def test_startup_gemini_configuration(key, enabled):
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
    if key is not None:
        env['GEMINI_API_KEY'] = key
    code = ('import main, json; print("RESULT", json.dumps([main.GEMINI_ENABLED, '
            'main.GEMINI_MODEL_NAME]))')
    proc = subprocess.run([sys.executable, '-c', code], cwd=BACKEND_DIR, env=env,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.split('RESULT', 1)[1])
    assert result == [enabled, 'gemini-2.5-flash']
    assert FAKE_KEY not in proc.stdout and FAKE_KEY not in proc.stderr


@pytest.mark.parametrize('reason,offer_fragment', [
    ('friction_score (impact: +2.10)', 'payment assistance'),
    ('payment_failures_3m (impact: +1.20)', 'payment assistance'),
    ('watch_hours_per_week (impact: +0.90)', 'Premium upgrade'),
    ('engagement_score (impact: +0.70)', 'Premium upgrade'),
    ('tenure_months (impact: +0.80)', 'loyalty discount'),
    ('is_new_customer (impact: +0.60)', 'loyalty discount'),
    ('age (impact: +0.30)', 'loyalty reward'),
    ('', 'loyalty reward'),
])
def test_every_rule_based_template_is_reachable_and_complete(api, client, monkeypatch, risk_mix,
                                                             reason, offer_fragment):
    main = api[0]
    monkeypatch.setattr(main, 'GEMINI_ENABLED', False)
    cid = risk_mix[0]
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == cid, 'top_reason_1'] = reason
    monkeypatch.setattr(main, 'FULL_DF', df)
    body = client.get(f'/retention/{cid}').json()
    _check_body(body, cid)
    assert offer_fragment in body['suggested_offer']
    assert body['name'] in body['email'] and len(body['actions']) == 2
    assert body['ai_generated'] is False
