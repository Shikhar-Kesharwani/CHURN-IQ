"""CHURN-44 — /send-email authentication, rate limiting, injection protection
and secret hygiene.

SMTP is always replaced by a fake (FakeSMTP below): NO real email is sent.
"""
import logging
import smtplib

import pytest
from fastapi.testclient import TestClient

import email_security as esec
from conftest import TEST_EMAIL_TOKEN

SMTP_PASS = 'gmail-app-pass-SECRET-123'
SENDER = 'sender.account@gmail.com'
RECEIVER = 'receiver.person@gmail.com'


@pytest.fixture
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture
def smtp(api, monkeypatch, email_auth):
    """Email configured with fake credentials; SMTP replaced by a recorder."""
    main = api[0]
    monkeypatch.setattr(main, 'EMAIL_ENABLED', True)
    monkeypatch.setattr(main, 'GMAIL_SENDER', SENDER)
    monkeypatch.setattr(main, 'GMAIL_APP_PASS', SMTP_PASS)
    monkeypatch.setattr(main, 'DEMO_RECEIVER', RECEIVER)

    class FakeSMTP:
        mode = 'ok'
        sent = []
        logins = []

        def __init__(self, host, port):
            assert (host, port) == ('smtp.gmail.com', 465)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            FakeSMTP.logins.append((user, password))
            if FakeSMTP.mode == 'auth':
                raise smtplib.SMTPAuthenticationError(
                    535, f'5.7.8 Username and Password not accepted {user} {password}'.encode())

        def send_message(self, msg):
            if FakeSMTP.mode == 'refused':
                raise smtplib.SMTPRecipientsRefused({RECEIVER: (550, b'no such user')})
            if FakeSMTP.mode == 'oserror':
                raise OSError(f'connection reset while sending as {SENDER} pass={SMTP_PASS}')
            FakeSMTP.sent.append(msg)

    monkeypatch.setattr(main.smtplib, 'SMTP_SSL', FakeSMTP)
    return FakeSMTP


@pytest.fixture
def payload(scored_ids):
    return {'customer_id': scored_ids[0], 'subject': 'We miss you', 'body': 'Hi there,\nCome back!'}


def _err(r, status, code):
    assert r.status_code == status, (r.status_code, r.text)
    body = r.json()
    assert body['status_code'] == status and body['error'] == code
    assert isinstance(body['detail'], str) and body['detail']
    return body


def _assert_no_secrets(text):
    for needle in (TEST_EMAIL_TOKEN, SMTP_PASS, SENDER, RECEIVER, 'receiver.person',
                   'sender.account', 'Traceback', 'Username and Password'):
        assert needle not in text, needle


# ── 1-3. Authentication ──────────────────────────────────────────────────────
def test_missing_token_is_401_and_nothing_is_sent(client, smtp, payload):
    r = client.post('/send-email', json=payload)
    body = _err(r, 401, 'unauthorized')
    assert r.headers['www-authenticate'] == 'Bearer'
    assert 'Authorization: Bearer' in body['detail']
    assert smtp.sent == [] and smtp.logins == []


@pytest.mark.parametrize('header', [
    'Bearer wrong-token-0123456789-abcdefghij',          # invalid
    f'Bearer {TEST_EMAIL_TOKEN}x',                       # one char too many
    f'Bearer {TEST_EMAIL_TOKEN[:-1]}',                   # one char too few
    f'Bearer {TEST_EMAIL_TOKEN.upper()}',                # case matters
])
def test_invalid_token_is_401(client, smtp, payload, header):
    r = client.post('/send-email', json=payload, headers={'Authorization': header})
    _err(r, 401, 'unauthorized')
    assert smtp.sent == []
    _assert_no_secrets(r.text)


@pytest.mark.parametrize('header', [
    TEST_EMAIL_TOKEN,                                   # no scheme
    f'Basic {TEST_EMAIL_TOKEN}',                        # wrong scheme
    f'bearer{TEST_EMAIL_TOKEN}',                        # no space
    'Bearer ', 'Bearer', '   ',                         # empty token
    f'Bearer {TEST_EMAIL_TOKEN} extra',                 # trailing garbage
    f'Bearer "{TEST_EMAIL_TOKEN}"',                     # quoted
])
def test_malformed_authorization_is_401(client, smtp, payload, header):
    r = client.post('/send-email', json=payload, headers={'Authorization': header})
    _err(r, 401, 'unauthorized')
    assert smtp.sent == []


def test_token_in_other_places_is_not_accepted(client, smtp, payload):
    for kwargs in ({'headers': {'X-API-Key': TEST_EMAIL_TOKEN}},
                   {'params': {'token': TEST_EMAIL_TOKEN}},
                   {'cookies': {'token': TEST_EMAIL_TOKEN}}):
        _err(client.post('/send-email', json=payload, **kwargs), 401, 'unauthorized')


def test_all_auth_failures_get_the_same_response(client, smtp, payload):
    bodies = {client.post('/send-email', json=payload, headers=h).text for h in
              ({}, {'Authorization': 'Bearer nope-nope-nope-nope-nope'},
               {'Authorization': 'Basic abc'})}
    assert len(bodies) == 1                     # missing/invalid/malformed are indistinguishable


def test_valid_token_sends_through_smtp(client, smtp, payload, email_auth):
    r = client.post('/send-email', json=payload, headers=email_auth)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['success'] is True and out['customer_id'] == payload['customer_id']
    assert out['subject'] == 'We miss you'
    assert out['sent_to'] == 'r*************n@gmail.com'
    assert smtp.logins == [(SENDER, SMTP_PASS)]
    (msg,) = smtp.sent
    assert msg['To'] == RECEIVER and msg['Subject'] == '[ChurnIQ Demo] We miss you'
    _assert_no_secrets(r.text)


def test_unconfigured_token_fails_closed_with_503(api, client, smtp, payload, monkeypatch):
    monkeypatch.setattr(api[0], 'EMAIL_API_TOKEN', '')
    for headers in ({}, {'Authorization': 'Bearer '}, {'Authorization': f'Bearer {TEST_EMAIL_TOKEN}'}):
        _err(client.post('/send-email', json=payload, headers=headers),
             503, 'email_auth_not_configured')
    assert smtp.sent == []


def test_auth_runs_before_body_validation(client, smtp):
    # An unauthenticated caller learns nothing about the body rules
    for content in (b'{not json', b'', b'[]'):
        r = client.post('/send-email', content=content, headers={'content-type': 'application/json'})
        _err(r, 401, 'unauthorized')
    _err(client.post('/send-email', json={'customer_id': 'x' * 99}), 401, 'unauthorized')


def test_route_dependency_rejects_even_without_gate(api, payload, smtp):
    """Defence in depth: the endpoint itself also checks the token."""
    main = api[0]
    with pytest.raises(main.APIError) as e:
        main.require_email_token(_FakeRequest({}), None)
    assert e.value.status_code == 401
    main.require_email_token(_FakeRequest({'authorization': f'Bearer {TEST_EMAIL_TOKEN}'}), None)


class _FakeRequest:
    def __init__(self, headers):
        self.headers = headers


def test_cors_preflight_is_not_blocked(client, smtp):
    r = client.options('/send-email', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type'})
    assert r.status_code == 200
    assert 'authorization' in r.headers['access-control-allow-headers'].lower()


def test_401_and_429_carry_cors_headers(client, smtp, payload):
    r = client.post('/send-email', json=payload, headers={'Origin': 'http://localhost:5173'})
    assert r.status_code == 401 and 'access-control-allow-origin' in r.headers


def test_openapi_documents_bearer_auth(client):
    spec = client.get('/openapi.json').json()
    op = spec['paths']['/send-email']['post']
    assert {'EmailApiToken': []} in op['security']
    assert spec['components']['securitySchemes']['EmailApiToken']['scheme'] == 'bearer'
    assert {'401', '429'} <= set(op['responses'])


def test_other_endpoints_stay_public(client):
    assert client.get('/').status_code == 200
    assert client.get('/email-status').status_code == 200


# ── 4. Recipient: never from the request, configured value validated ─────────
@pytest.mark.parametrize('field', ['to', 'recipient', 'cc', 'bcc', 'from', 'reply_to', 'headers'])
def test_request_cannot_choose_recipient_or_headers(client, smtp, payload, email_auth, field):
    r = client.post('/send-email', json={**payload, field: 'attacker@evil.example'},
                    headers=email_auth)
    _err(r, 422, 'validation_error')
    assert smtp.sent == []


@pytest.mark.parametrize('bad', [
    '', 'not-an-email', 'a@b', '@gmail.com', 'user@', 'two@@gmail.com', 'a b@gmail.com',
    'victim@gmail.com\r\nBcc: x@evil.example', 'victim@gmail.com\nBcc: x@evil.example',
    'Name <victim@gmail.com>', 'a@gmail.com,b@evil.example', 'a@gmail.com; b@evil.example',
    'x' * 65 + '@gmail.com',
])
def test_malformed_configured_recipient_is_rejected_safely(api, client, smtp, payload,
                                                          email_auth, monkeypatch, bad):
    monkeypatch.setattr(api[0], 'DEMO_RECEIVER', bad)
    r = client.post('/send-email', json=payload, headers=email_auth)
    body = _err(r, 503, 'email_misconfigured')
    assert smtp.sent == [] and smtp.logins == []
    if bad:
        assert bad not in r.text
    _assert_no_secrets(r.text)
    assert body['detail'].endswith('The error has been logged.')


def test_malformed_configured_sender_is_rejected(api, client, smtp, payload, email_auth,
                                                monkeypatch):
    monkeypatch.setattr(api[0], 'GMAIL_SENDER', 'me@gmail.com\r\nBcc: x@evil.example')
    _err(client.post('/send-email', json=payload, headers=email_auth), 503, 'email_misconfigured')
    assert smtp.sent == []


@pytest.mark.parametrize('cid', ['', '   ', 'CUST\r\n001', "CUST'1", 'A' * 33])
def test_missing_or_malformed_customer_is_422(client, smtp, payload, email_auth, cid):
    _err(client.post('/send-email', json={**payload, 'customer_id': cid}, headers=email_auth),
         422, 'validation_error')


@pytest.mark.parametrize('missing', ['customer_id', 'subject', 'body'])
def test_missing_fields_are_422(client, smtp, payload, email_auth, missing):
    data = {k: v for k, v in payload.items() if k != missing}
    _err(client.post('/send-email', json=data, headers=email_auth), 422, 'validation_error')


# ── 5. CR/LF and header injection ────────────────────────────────────────────
@pytest.mark.parametrize('subject', [
    'Hi\r\nBcc: victim@evil.example', 'Hi\nBcc: victim@evil.example', 'Hi\rTo: x@evil.example',
    'Hi\r\n\r\n<html>body</html>', 'Hi\x0bX: 1', 'Hi\x0cX: 1', 'Hi\x85X: 1',
    'Hi X: 1', 'Hi X: 1', 'Hi\x00', 'Hi\x1b[31m', '%0d%0aBcc: x@evil.example\n',
])
def test_header_injection_in_subject_is_422(client, smtp, payload, email_auth, subject):
    r = client.post('/send-email', json={**payload, 'subject': subject}, headers=email_auth)
    _err(r, 422, 'validation_error')
    assert smtp.sent == []
    assert subject not in r.text                      # input is not echoed back


def test_encoded_crlf_text_is_harmless_literal(client, smtp, payload, email_auth):
    # Literal "%0d%0a" (no real line break) is plain text, sent as-is in one header line
    r = client.post('/send-email', json={**payload, 'subject': 'Hi %0d%0aBcc: x'}, headers=email_auth)
    assert r.status_code == 200
    (msg,) = smtp.sent
    assert msg['Bcc'] is None and '\n' not in msg['Subject'] and '\r' not in msg['Subject']


@pytest.mark.parametrize('body', ['Hi\x00there', 'Hi\x1bthere', 'Hi\x07'])
def test_control_characters_in_body_are_422(client, smtp, payload, email_auth, body):
    _err(client.post('/send-email', json={**payload, 'body': body}, headers=email_auth),
         422, 'validation_error')


def test_multiline_body_is_allowed(client, smtp, payload, email_auth):
    body = 'Hi Priya,\r\n\r\nWe miss you.\n\tThe ChurnIQ team'
    r = client.post('/send-email', json={**payload, 'body': body}, headers=email_auth)
    assert r.status_code == 200
    plain = smtp.sent[0].get_payload()[0].get_payload(decode=True).decode()
    assert 'We miss you.' in plain and 'The ChurnIQ team' in plain


@pytest.mark.parametrize('subject,body', [('x' * 201, 'b'), ('s', 'x' * 5001), ('', 'b'),
                                          ('   ', 'b'), ('s', ''), ('s', ' \n ')])
def test_subject_and_body_length_rules(client, smtp, payload, email_auth, subject, body):
    _err(client.post('/send-email', json={**payload, 'subject': subject, 'body': body},
                     headers=email_auth), 422, 'validation_error')


@pytest.mark.parametrize('subject,body', [('x' * 200, 'b'), ('s', 'x' * 5000)])
def test_maximum_lengths_are_accepted(client, smtp, payload, email_auth, subject, body):
    r = client.post('/send-email', json={**payload, 'subject': subject, 'body': body},
                    headers=email_auth)
    assert r.status_code == 200, r.text


# ── 6. HTML / script injection ───────────────────────────────────────────────
@pytest.mark.parametrize('evil', [
    '<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
    '"><svg onload=alert(1)>', "</div><a href='javascript:alert(1)'>x</a>",
    '<iframe src="https://evil.example"></iframe>',
])
def test_html_in_body_is_escaped(client, smtp, payload, email_auth, evil):
    r = client.post('/send-email', json={**payload, 'body': f'Hello {evil} & bye'},
                    headers=email_auth)
    assert r.status_code == 200, r.text
    html_part = smtp.sent[0].get_payload()[1].get_payload(decode=True).decode()
    assert evil not in html_part
    for tag in ('<script', '<img', '<svg', '<iframe', '<a href'):
        assert tag not in html_part
    assert '&lt;' in html_part and '&amp; bye' in html_part


def test_html_in_customer_fields_is_escaped(api, client, smtp, payload, email_auth, monkeypatch):
    main = api[0]
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == payload['customer_id'], 'name'] = '<script>x()</script>'
    monkeypatch.setattr(main, 'FULL_DF', df)
    r = client.post('/send-email', json=payload, headers=email_auth)
    assert r.status_code == 200, r.text
    html_part = smtp.sent[0].get_payload()[1].get_payload(decode=True).decode()
    assert '<script>' not in html_part and '&lt;script&gt;x()&lt;/script&gt;' in html_part


def test_html_in_subject_does_not_reach_html_part(client, smtp, payload, email_auth):
    r = client.post('/send-email', json={**payload, 'subject': '<b>Hi</b>'}, headers=email_auth)
    assert r.status_code == 200
    html_part = smtp.sent[0].get_payload()[1].get_payload(decode=True).decode()
    assert '<b>Hi</b>' not in html_part


# ── 7. Rate limiting ─────────────────────────────────────────────────────────
@pytest.fixture
def tight_limit(api, monkeypatch):
    main = api[0]
    monkeypatch.setattr(main, 'EMAIL_SEND_LIMITER', esec.SlidingWindowLimiter(3, 60))
    monkeypatch.setattr(main, 'EMAIL_AUTH_FAIL_LIMITER', esec.SlidingWindowLimiter(3, 60))
    return main


def test_rate_limit_exceeded_is_429(client, smtp, payload, email_auth, tight_limit):
    for _ in range(3):
        assert client.post('/send-email', json=payload, headers=email_auth).status_code == 200
    r = client.post('/send-email', json=payload, headers=email_auth)
    body = _err(r, 429, 'rate_limited')
    assert int(r.headers['retry-after']) >= 1
    assert r.headers['retry-after'] in body['detail']
    assert len(smtp.sent) == 3                          # the 4th was never sent


def test_invalid_requests_count_toward_the_limit(client, smtp, payload, email_auth, tight_limit):
    # 422s, 404s and malformed JSON all consume quota, so they cannot be used
    # to probe or to bypass the limit.
    client.post('/send-email', json={**payload, 'subject': 'a\r\nb'}, headers=email_auth)
    client.post('/send-email', json={**payload, 'customer_id': 'NOPE'}, headers=email_auth)
    client.post('/send-email', content=b'{bad', headers={**email_auth,
                                                         'content-type': 'application/json'})
    _err(client.post('/send-email', json=payload, headers=email_auth), 429, 'rate_limited')
    assert smtp.sent == []


def test_failed_auth_is_throttled_separately(client, smtp, payload, email_auth, tight_limit):
    bad = {'Authorization': 'Bearer wrong-token-0123456789-abcdef'}
    for _ in range(3):
        _err(client.post('/send-email', json=payload, headers=bad), 401, 'unauthorized')
    _err(client.post('/send-email', json=payload, headers=bad), 429, 'rate_limited')
    _err(client.post('/send-email', json=payload), 429, 'rate_limited')
    # Brute-forcers cannot use up the legitimate caller's quota
    assert client.post('/send-email', json=payload, headers=email_auth).status_code == 200


def test_limit_is_per_client(client, smtp, payload, email_auth, tight_limit):
    for _ in range(3):
        tight_limit.EMAIL_SEND_LIMITER.hit('testclient')
    _err(client.post('/send-email', json=payload, headers=email_auth), 429, 'rate_limited')
    other = TestClient(tight_limit.app, raise_server_exceptions=False, client=('10.0.0.9', 5000))
    assert other.post('/send-email', json=payload, headers=email_auth).status_code == 200


def test_x_forwarded_for_does_not_bypass_limit(client, smtp, payload, email_auth, tight_limit):
    for i in range(3):
        client.post('/send-email', json=payload, headers={**email_auth, 'X-Forwarded-For': f'1.2.3.{i}'})
    r = client.post('/send-email', json=payload, headers={**email_auth, 'X-Forwarded-For': '9.9.9.9'})
    _err(r, 429, 'rate_limited')


def test_rate_limit_response_has_cors_headers(client, smtp, payload, email_auth, tight_limit):
    for _ in range(3):
        client.post('/send-email', json=payload, headers=email_auth)
    # CHURN-54: CORS now answers only allowed origins, so use the dev frontend's origin.
    r = client.post('/send-email', json=payload, headers={**email_auth, 'Origin': 'http://localhost:5173'})
    assert r.status_code == 429 and r.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_limiter_window_slides():
    now = [1000.0]
    lim = esec.SlidingWindowLimiter(2, 60, clock=lambda: now[0])
    assert lim.hit('a') == (True, 0) and lim.hit('a') == (True, 0)
    allowed, retry = lim.hit('a')
    assert not allowed and retry == 60
    now[0] += 30
    assert lim.hit('a') == (False, 30)
    assert lim.hit('b')[0]                               # other keys unaffected
    now[0] += 30.001
    assert lim.hit('a') == (True, 0)                     # oldest aged out


def test_limiter_memory_is_bounded():
    now = [0.0]
    lim = esec.SlidingWindowLimiter(1, 10, clock=lambda: now[0], max_keys=50)
    for i in range(500):
        lim.hit(f'ip{i}')
    assert len(lim._hits) <= 50


def test_limiter_rejects_bad_config():
    with pytest.raises(ValueError):
        esec.SlidingWindowLimiter(0, 60)
    with pytest.raises(ValueError):
        esec.SlidingWindowLimiter(1, 0)


@pytest.mark.parametrize('raw,expected', [(None, 7), ('', 7), ('abc', 7), ('0', 7), ('-3', 7),
                                          (' 12 ', 12), ('1', 1)])
def test_env_int(raw, expected):
    env = {} if raw is None else {'X': raw}
    assert esec.env_int(env, 'X', 7) == expected


# ── 8-9. SMTP failure: safe errors, no credential leaks ──────────────────────
@pytest.mark.parametrize('mode,code', [('auth', 'smtp_auth_failed'), ('refused', 'smtp_error'),
                                       ('oserror', 'smtp_error')])
def test_smtp_failure_is_safe_502(client, smtp, payload, email_auth, mode, code, caplog):
    smtp.mode = mode
    with caplog.at_level(logging.DEBUG):
        r = client.post('/send-email', json=payload, headers=email_auth)
    _err(r, 502, code)
    _assert_no_secrets(r.text)
    for needle in ('535', '550', 'no such user', 'connection reset', 'OSError'):
        assert needle not in r.text
    logs = caplog.text
    assert SMTP_PASS not in logs and TEST_EMAIL_TOKEN not in logs


def test_credentials_never_logged_or_returned_on_any_path(client, smtp, payload, email_auth,
                                                         caplog, tight_limit):
    with caplog.at_level(logging.DEBUG):
        responses = [
            client.post('/send-email', json=payload),
            client.post('/send-email', json=payload,
                        headers={'Authorization': f'Bearer {TEST_EMAIL_TOKEN}-wrong'}),
            client.post('/send-email', json=payload, headers=email_auth),
            client.post('/send-email', json={**payload, 'subject': 'x\r\ny'}, headers=email_auth),
            client.post('/send-email', json=payload, headers=email_auth),
            client.post('/send-email', json=payload, headers=email_auth),   # 429
            client.get('/email-status'),
            client.get('/'),
        ]
    assert responses[5].status_code == 429
    for r in responses:
        _assert_no_secrets(r.text)
    assert TEST_EMAIL_TOKEN not in caplog.text and SMTP_PASS not in caplog.text
    assert RECEIVER not in caplog.text


def test_redact_covers_email_token_and_in_memory_smtp_password(api, smtp, email_auth):
    main = api[0]
    out = main.redact(f'token {TEST_EMAIL_TOKEN} pass {SMTP_PASS}')
    assert TEST_EMAIL_TOKEN not in out and SMTP_PASS not in out


def test_email_status_reports_auth_without_secrets(client, smtp, email_auth):
    r = client.get('/email-status')
    body = r.json()
    assert body['auth_configured'] is True
    assert body['rate_limit'].endswith('per client')
    _assert_no_secrets(r.text)


# ── 10. Existing valid behaviour is preserved ────────────────────────────────
def test_existing_email_content_is_unchanged(client, smtp, payload, email_auth, api):
    r = client.post('/send-email', json=payload, headers=email_auth)
    assert r.status_code == 200
    msg = smtp.sent[0]
    assert msg['From'] == f'ChurnIQ Pro <{SENDER}>'
    assert msg.get_content_type() == 'multipart/alternative'
    plain, html_part = (p.get_payload(decode=True).decode() for p in msg.get_payload())
    assert 'Come back!' in plain and 'Come back!' in html_part
    assert payload['customer_id'] in plain and 'Churn Risk' in html_part


def test_email_not_configured_still_503(api, client, payload, email_auth, monkeypatch):
    monkeypatch.setattr(api[0], 'EMAIL_ENABLED', False)
    _err(client.post('/send-email', json=payload, headers=email_auth), 503, 'email_not_configured')


def test_unknown_customer_still_404(client, smtp, payload, email_auth):
    _err(client.post('/send-email', json={**payload, 'customer_id': 'NOPE'}, headers=email_auth),
         404, 'customer_not_found')


# ── helpers ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('header,verdict', [
    (None, 'missing'), ('', 'missing'), ('  ', 'missing'), ('Token abc', 'malformed'),
    ('Bearer a b', 'malformed'), (f'Bearer {TEST_EMAIL_TOKEN}', 'ok'),
    (f'  Bearer {TEST_EMAIL_TOKEN}  ', 'ok'), ('Bearer abcdefghijklmnop', 'invalid'),
])
def test_check_bearer_token(header, verdict):
    assert esec.check_bearer_token(header, TEST_EMAIL_TOKEN) == verdict


def test_empty_expected_token_never_matches():
    assert esec.check_bearer_token('Bearer x', '') == 'invalid'


@pytest.mark.parametrize('raw,expected', [(None, ''), ('', ''), ('short', ''), (' ' * 20, ''),
                                          ('a' * 16, 'a' * 16), ('  ' + 'b' * 20 + '\n', 'b' * 20)])
def test_configured_token(raw, expected):
    assert esec.configured_token(raw) == expected


@pytest.mark.parametrize('addr', ['someone@gmail.com', 'first.last+tag@example.co.uk', 'a@b.io'])
def test_valid_addresses(addr):
    assert esec.is_valid_address(addr)
