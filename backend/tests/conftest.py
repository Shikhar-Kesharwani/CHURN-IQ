"""Shared fixtures for the ChurnIQ ML validation test suite (CHURN-13..17).

Run from backend/:   python -m pytest
"""
import os
import sys
import warnings

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

warnings.filterwarnings('ignore')


@pytest.fixture(scope='session')
def artifacts():
    import evaluate_model as ev
    model, feature_names, dataset, predictions = ev.load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(dataset)
    return {
        'model': model, 'feature_names': feature_names, 'dataset': dataset,
        'predictions': predictions, 'base': base, 'X': X, 'y': y,
        'X_train': X_train, 'X_test': X_test, 'y_train': y_train, 'y_test': y_test,
    }


@pytest.fixture(scope='session')
def api():
    """Import the FastAPI app once (loads model + data) and return (main, client)."""
    from fastapi.testclient import TestClient
    import main
    return main, TestClient(main.app)


@pytest.fixture(scope='session')
def scored_ids(api):
    main, _ = api
    # Held-out test customers (scored by the committed production model)
    p = main.PREDICTIONS_DF
    return list(p.loc[p['prediction_source'] == 'holdout_test', 'customer_id'])


@pytest.fixture(scope='session')
def oof_ids(api):
    # Training customers scored out-of-fold (CHURN-37)
    p = api[0].PREDICTIONS_DF
    return list(p.loc[p['prediction_source'] == 'cv_out_of_fold', 'customer_id'])


# ── /send-email auth + rate limit (CHURN-44) ─────────────────────────────────
# A test-only token (not a real secret). Tests that call /send-email use the
# `email_auth` fixture and send EMAIL_AUTH_HEADERS.
TEST_EMAIL_TOKEN = 'test-token-0123456789-abcdefghij'
EMAIL_AUTH_HEADERS = {'Authorization': f'Bearer {TEST_EMAIL_TOKEN}'}


@pytest.fixture(autouse=True)
def _reset_email_rate_limits():
    """Every test starts with empty /send-email rate-limit buckets."""
    main = sys.modules.get('main')
    for name in ('EMAIL_SEND_LIMITER', 'EMAIL_AUTH_FAIL_LIMITER'):
        if main is not None and hasattr(main, name):
            getattr(main, name).reset()
    yield


@pytest.fixture
def email_auth(api, monkeypatch):
    """Configure the server-side EMAIL_API_TOKEN; returns the request headers."""
    monkeypatch.setattr(api[0], 'EMAIL_API_TOKEN', TEST_EMAIL_TOKEN)
    return dict(EMAIL_AUTH_HEADERS)
