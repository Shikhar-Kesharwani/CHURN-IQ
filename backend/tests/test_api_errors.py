"""CHURN-21 — consistent JSON errors, logging, artifact-loading failures, no leaks."""
import logging
import os
import shutil
import smtplib
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE_KEY = 'AIzaFAKE_TEST_KEY_not_a_real_key'
SECRET_PATH = '/home/secret/models/churniq_model.pkl'
AUTH = {'Authorization': 'Bearer test-token-0123456789-abcdefghij'}   # conftest.TEST_EMAIL_TOKEN


@pytest.fixture
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


def _assert_no_leak(text):
    for needle in ('Traceback', SECRET_PATH, FAKE_KEY, 'RuntimeError', 'ZeroDivisionError'):
        assert needle not in text, needle


# ── Unhandled exceptions ─────────────────────────────────────────────────────
def test_unhandled_exception_returns_json_500_with_request_id(api, client, monkeypatch, caplog):
    main = api[0]

    def boom(_):
        raise RuntimeError(f'boom at {SECRET_PATH} key={FAKE_KEY}')

    monkeypatch.setattr(main, '_mean_or_none', boom)
    with caplog.at_level(logging.ERROR, logger='churniq.api'):
        r = client.get('/dashboard/summary')
    assert r.status_code == 500 and r.headers['content-type'].startswith('application/json')
    body = r.json()
    assert body['error'] == 'internal_error' and body['status_code'] == 500
    assert len(body['request_id']) == 12
    _assert_no_leak(r.text)
    # Server log has the details (with traceback) but not the key
    assert body['request_id'] in caplog.text and 'boom' in caplog.text
    assert 'Traceback' in caplog.text and FAKE_KEY not in caplog.text


def test_whatif_model_failure_is_a_generic_500(api, client, scored_ids, monkeypatch, caplog):
    main = api[0]

    class Broken:
        def predict_proba(self, X):
            raise ZeroDivisionError(f'xgboost failed reading {SECRET_PATH}')

    monkeypatch.setattr(main, 'MODEL', Broken())
    with caplog.at_level(logging.ERROR, logger='churniq.api'):
        r = client.post('/whatif', json={'customer_id': scored_ids[0]})
    assert r.status_code == 500 and r.json()['error'] == 'prediction_failed'
    _assert_no_leak(r.text)
    assert scored_ids[0] in caplog.text and 'ZeroDivisionError' in caplog.text


def test_whatif_non_finite_model_output_is_a_500_not_nan_json(api, client, scored_ids, monkeypatch):
    main = api[0]

    class NanModel:
        def predict_proba(self, X):
            return [[float('nan'), float('nan')]]

    monkeypatch.setattr(main, 'MODEL', NanModel())
    r = client.post('/whatif', json={'customer_id': scored_ids[0]})
    assert r.status_code == 500 and r.json()['error'] == 'prediction_failed'


def test_similarity_engine_unavailable_is_503(api, client, scored_ids, monkeypatch):
    monkeypatch.setattr(api[0], 'SIMILARITY_ENGINE', None)
    r = client.post('/api/customer-similarity', json={'customer_id': scored_ids[0]})
    assert r.status_code == 503 and r.json()['error'] == 'similarity_unavailable'
    assert client.get('/').json()['similarity_ready'] is False


def test_similarity_engine_crash_is_a_generic_500(api, client, scored_ids, monkeypatch):
    main = api[0]

    def crash(*a, **k):
        raise RuntimeError(f'cannot read {SECRET_PATH}')

    monkeypatch.setattr(main.SIMILARITY_ENGINE, 'find_similar_customers', crash)
    r = client.post('/api/customer-similarity', json={'customer_id': scored_ids[0]})
    assert r.status_code == 500 and r.json()['error'] == 'similarity_failed'
    _assert_no_leak(r.text)


def test_similarity_engine_stale_index_is_404(api, client, scored_ids, monkeypatch):
    main = api[0]

    def missing(*a, **k):
        raise KeyError('not indexed')

    monkeypatch.setattr(main.SIMILARITY_ENGINE, 'find_similar_customers', missing)
    r = client.post('/api/customer-similarity', json={'customer_id': scored_ids[0]})
    assert r.status_code == 404 and r.json()['error'] == 'customer_not_found'


# ── Artifact loading ─────────────────────────────────────────────────────────
def test_missing_required_artifact_raises_clear_error(api):
    main = api[0]
    with pytest.raises(main.ArtifactLoadError) as exc:
        main.load_required_artifact('no_such_model.pkl', main._load_pickle, 'test model')
    msg = str(exc.value)
    assert "'no_such_model.pkl'" in msg and 'not found' in msg and 'test model' in msg
    assert BACKEND_DIR not in msg                         # no internal paths in the message


def test_corrupt_required_artifact_raises_clear_error(api, tmp_path, monkeypatch):
    main = api[0]
    bad = tmp_path / 'corrupt.pkl'
    bad.write_bytes(b'not a pickle')
    monkeypatch.setattr(main, 'find_file', lambda name: str(bad))
    with pytest.raises(main.ArtifactLoadError) as exc:
        main.load_required_artifact('corrupt.pkl', main._load_pickle, 'test model')
    assert 'could not be loaded' in str(exc.value) and 'UnpicklingError' in str(exc.value)


def test_server_refuses_to_start_without_the_model(tmp_path):
    """Start main.py from a directory without churniq_model.pkl: clear one-line failure."""
    for name in ('main.py', 'churniq_core.py', 'customer_similarity.py'):
        shutil.copy(os.path.join(BACKEND_DIR, name), tmp_path / name)
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
    proc = subprocess.run([sys.executable, '-c', 'import main'], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "ArtifactLoadError: Required artifact 'churniq_model.pkl'" in proc.stderr


def test_missing_fold_models_never_fall_back_to_production_model(api, client, oof_ids, monkeypatch):
    main = api[0]
    monkeypatch.setattr(main, 'FOLD_MODELS', None)
    r = client.post('/whatif', json={'customer_id': oof_ids[0]})
    assert r.status_code == 409 and r.json()['error'] == 'fold_model_unavailable'
    assert client.get('/').json()['fold_models_loaded'] is False


# ── Secret redaction ─────────────────────────────────────────────────────────
def test_redact_removes_keys_and_configured_secrets(api, monkeypatch):
    main = api[0]
    monkeypatch.setattr(main, 'GEMINI_API_KEY', 'my-configured-secret')
    text = main.redact(f'url?key={FAKE_KEY}&x=1 token=abc123 {FAKE_KEY} my-configured-secret')
    assert FAKE_KEY not in text and 'abc123' not in text and 'my-configured-secret' not in text
    assert text.count('[REDACTED]') >= 3


# ── /send-email failures (SMTP mocked; nothing is sent) ──────────────────────
@pytest.fixture
def email_on(api, monkeypatch, email_auth):
    main = api[0]
    monkeypatch.setattr(main, 'EMAIL_ENABLED', True)
    monkeypatch.setattr(main, 'GMAIL_SENDER', 'sender.account@gmail.com')
    monkeypatch.setattr(main, 'GMAIL_APP_PASS', 'app-pass-secret')
    monkeypatch.setattr(main, 'DEMO_RECEIVER', 'receiver.person@gmail.com')
    sent = []

    class FakeSMTP:
        mode = 'ok'

        def __init__(self, host, port):
            assert (host, port) == ('smtp.gmail.com', 465)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            if FakeSMTP.mode == 'auth':
                raise smtplib.SMTPAuthenticationError(535, b'5.7.8 bad credentials app-pass-secret')

        def send_message(self, msg):
            if FakeSMTP.mode == 'smtp':
                raise smtplib.SMTPServerDisconnected(f'lost connection to {SECRET_PATH}')
            sent.append(msg)

    monkeypatch.setattr(main.smtplib, 'SMTP_SSL', FakeSMTP)
    return FakeSMTP, sent


def test_send_email_success_masks_address_and_escapes_html(client, email_on, scored_ids):
    fake, sent = email_on
    body = '<script>alert(1)</script> Hi & welcome'
    r = client.post('/send-email', json={'customer_id': scored_ids[0], 'subject': 'Hello <b>',
                                         'body': body}, headers=AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['success'] is True and out['sent_to'] == 'r*************n@gmail.com'
    assert 'receiver.person' not in r.text
    html_part = sent[0].get_payload()[1].get_payload(decode=True).decode()
    assert '<script>' not in html_part and '&lt;script&gt;' in html_part
    plain_part = sent[0].get_payload()[0].get_payload(decode=True).decode()
    assert body in plain_part                              # plain text unchanged


@pytest.mark.parametrize('mode,code', [('auth', 'smtp_auth_failed'), ('smtp', 'smtp_error')])
def test_send_email_smtp_failures_are_502_without_server_text(client, email_on, scored_ids,
                                                              mode, code):
    fake, _ = email_on
    fake.mode = mode
    r = client.post('/send-email', json={'customer_id': scored_ids[0], 'subject': 'Hi', 'body': 'x'},
                    headers=AUTH)
    assert r.status_code == 502 and r.json()['error'] == code
    _assert_no_leak(r.text)
    assert 'app-pass-secret' not in r.text and 'bad credentials' not in r.text


def test_send_email_not_configured_is_503(api, client, scored_ids, monkeypatch, email_auth):
    monkeypatch.setattr(api[0], 'EMAIL_ENABLED', False)
    r = client.post('/send-email', json={'customer_id': scored_ids[0], 'subject': 'Hi', 'body': 'x'},
                    headers=AUTH)
    assert r.status_code == 503 and r.json()['error'] == 'email_not_configured'


def test_send_email_unknown_customer_is_404(client, email_on):
    r = client.post('/send-email', json={'customer_id': 'NOPE', 'subject': 'Hi', 'body': 'x'},
                    headers=AUTH)
    assert r.status_code == 404


def test_email_status_masks_addresses(client, email_on):
    body = client.get('/email-status').json()
    assert body['email_enabled'] is True
    assert body['sender'] == 's************t@gmail.com'
    assert 'sender.account' not in str(body) and 'receiver.person' not in str(body)


@pytest.mark.parametrize('addr,masked', [('', 'not configured'), ('ab@x.io', 'a***@x.io'),
                                         ('abc@x.io', 'a*c@x.io'), ('nodomain', '***')])
def test_mask_email(api, addr, masked):
    assert api[0]._mask_email(addr) == masked


def test_logged_tracebacks_are_redacted_for_handled_failures(api, client, scored_ids,
                                                            monkeypatch, caplog):
    main = api[0]

    class Broken:
        def predict_proba(self, X):
            raise RuntimeError(f'remote model store rejected key={FAKE_KEY}')

    monkeypatch.setattr(main, 'MODEL', Broken())
    with caplog.at_level(logging.ERROR, logger='churniq.api'):
        client.post('/whatif', json={'customer_id': scored_ids[0]})
    assert 'Traceback' in caplog.text and FAKE_KEY not in caplog.text
