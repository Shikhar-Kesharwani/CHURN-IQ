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
    return [c for c in main.PREDICTIONS_DF['customer_id'] if c != 'CUST99999']
