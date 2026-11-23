"""CHURN-15 — SHAP explanations: alignment, additivity, API consistency, wording."""
import numpy as np
import pytest

import churniq_core as core
import validate_shap as vs


@pytest.fixture(scope='module')
def shap_data(artifacts):
    _, sv, expected = vs.compute(artifacts['model'], artifacts['X_test'])
    return sv, expected


def test_shap_matrix_aligned_with_features(artifacts, shap_data):
    sv, _ = shap_data
    assert sv.shape == (len(artifacts['X_test']), len(artifacts['feature_names']))


def test_shap_additivity_matches_model_output(artifacts, shap_data):
    sv, expected = shap_data
    margin = artifacts['model'].predict(artifacts['X_test'], output_margin=True)
    prob = artifacts['model'].predict_proba(artifacts['X_test'])[:, 1]
    assert np.abs(expected + sv.sum(axis=1) - margin).max() < 1e-4
    assert np.abs(1 / (1 + np.exp(-(expected + sv.sum(axis=1)))) - prob).max() < 1e-4


def test_stored_reasons_match_recomputed_shap(artifacts, shap_data):
    sv, _ = shap_data
    stored = artifacts['predictions'].fillna('N/A').set_index('customer_id')
    ids = artifacts['base'].loc[artifacts['X_test'].index, 'customer_id'].values
    cols = list(artifacts['X_test'].columns)
    for i, cid in enumerate(ids):
        rec = core.get_top_shap_reasons(sv[i], cols)
        rec += ['N/A'] * (3 - len(rec))
        assert rec == [stored.loc[cid, f'top_reason_{k}'] for k in (1, 2, 3)], cid


def test_api_reasons_match_shap_for_customers_across_risk_levels(api, artifacts, shap_data):
    main, client = api
    sv, _ = shap_data
    prob = artifacts['model'].predict_proba(artifacts['X_test'])[:, 1]
    ids = artifacts['base'].loc[artifacts['X_test'].index, 'customer_id'].values
    cols = list(artifacts['X_test'].columns)
    checked = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for i in np.argsort(-prob)[::50]:          # spread across the risk range
        cid = ids[i]
        body = client.get(f'/customer/{cid}').json()
        rec = core.get_top_shap_reasons(sv[i], cols)
        for k in range(3):
            shown = body[f'top_reason_{k + 1}']
            if k < len(rec):
                assert shown == main.explain_reason(cid, rec[k])
                assert f"[SHAP: {rec[k].split('impact: ')[1].rstrip(')')}]" in shown
            else:
                assert shown == 'No significant risk factor identified'
        checked[body['risk_level']] += 1
    assert all(v >= 2 for v in checked.values()), checked


def test_top_reasons_are_positive_and_sorted():
    reasons = core.get_top_shap_reasons([0.1, -2.0, 0.5, 0.3, 0.0], list('abcde'))
    assert reasons == ['c (impact: +0.50)', 'd (impact: +0.30)', 'a (impact: +0.10)']
    assert core.get_top_shap_reasons([-1.0, 0.0], ['a', 'b']) == []


@pytest.mark.parametrize('feature,value,must_not_start', [
    ('tenure_months', 18, 'Short subscription tenure'),
    ('num_profiles', 4, 'Only 1 profile'),
    ('last_login_days_ago', 0, 'Has not logged in'),
    ('logins_last_30_days', 15, 'Infrequent logins'),
    ('is_new_customer', 0, 'New customer'),
])
def test_reason_text_never_contradicts_actual_value(feature, value, must_not_start):
    assert not core.describe_reason(feature, value).startswith(must_not_start)


@pytest.mark.parametrize('feature,value,expected_start', [
    ('tenure_months', 2, 'Short subscription tenure — 2 months'),
    ('watch_hours_per_week', 1.4, 'Very low content engagement — only 1.4'),
    ('device_type_Tablet', 1, 'Device: Tablet'),
    ('device_type_Tablet', 0, 'Device: not Tablet'),
    ('plan_type', 0, 'Plan: Basic'),
])
def test_reason_text_describes_actual_value(feature, value, expected_start):
    assert core.describe_reason(feature, value).startswith(expected_start)


def test_format_reason_backward_compatible(api):
    main, _ = api
    assert main.format_reason('N/A') == 'No significant risk factor identified'
    assert main.format_reason('nan') == 'No significant risk factor identified'
    assert main.format_reason('friction_score (impact: +2.17)').endswith('[SHAP: +2.17]')
