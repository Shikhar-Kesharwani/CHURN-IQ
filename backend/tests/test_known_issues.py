"""Open CHURN-16 issues found in the follow-up audit (docs/ml/06-followup-audit.md).

The xfail(strict=True) tests describe the EXPECTED behaviour once the
proposed Bugs are fixed. They currently fail; once a fix lands they will
pass, and strict mode then fails the run as a reminder to remove the marker.
"""
import pytest

import churniq_core as core


def test_unscored_customers_are_exactly_the_training_split(api, artifacts):
    main, _ = api
    unscored = set(main.FULL_DF.loc[main.FULL_DF['churn_prob'].isna(), 'customer_id'])
    train_ids = set(artifacts['base'].loc[artifacts['X_train'].index, 'customer_id'])
    assert unscored == train_ids and len(unscored) == 4000


@pytest.mark.xfail(strict=True, reason='Bug A: unscored customers shown as 0% risk / ₹0 CLV')
def test_bug_a_unscored_customer_not_reported_as_zero_risk(api):
    _, client = api
    body = client.get('/customer/CUST00002').json()
    assert not (body['churn_prob'] == 0.0 and body['clv_score'] == 0.0)


@pytest.mark.xfail(strict=True, reason='Bug A: /whatif returns HTTP 500 for unscored customers')
def test_bug_a_whatif_works_for_unscored_customer(api):
    main, _ = api
    from fastapi.testclient import TestClient
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post('/whatif', json={'customer_id': 'CUST00002'}).status_code != 500


@pytest.mark.xfail(strict=True, reason='Bug A: /customers?plan_type=... returns HTTP 500 (NaN rows)')
def test_bug_a_plan_filter_does_not_500(api):
    main, _ = api
    from fastapi.testclient import TestClient
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.get('/customers?plan_type=Basic').status_code == 200


@pytest.mark.xfail(strict=True, reason='Bug B: CUST99999 CLV hard-coded to ₹500')
def test_bug_b_demo_customer_clv_matches_formula(api):
    _, client = api
    body = client.get('/customer/CUST99999').json()
    expected = core.calc_clv(body['monthly_charge'], body['tenure_months'], body['churn_prob'])
    assert abs(body['clv_score'] - expected) < 3
