"""CHURN-56 — segment-level validation of the committed production model."""
import json
import os

import numpy as np
import pytest

import churniq_core as core
import segment_validation as sv
import evaluate_model as ev


@pytest.fixture(scope='module')
def result():
    return sv.run(write=False)


@pytest.fixture(scope='module')
def held_out():
    return sv.held_out()


# ── Held-out split, leakage, artifacts ──────────────────────────────────────

def test_uses_exactly_the_genuine_held_out_split(result, held_out):
    rows, y, prob, X_test = held_out
    assert len(rows) == len(y) == len(prob) == 1000
    _, _, dataset, predictions = ev.load_artifacts()
    holdout = set(predictions.loc[predictions['prediction_source'] == 'holdout_test', 'customer_id'])
    assert set(dataset.loc[X_test.index, 'customer_id']) == holdout
    assert not set(dataset.loc[X_test.index, 'customer_id']) & {'CUST99999'}   # demo row excluded
    assert result['sanity_checks']['split_matches_holdout_test_rows_in_customer_predictions_csv']
    assert result['data'] == {**result['data'], 'customers': 1000, 'churned': 431, 'retained': 569}


def test_probabilities_are_the_production_model_output(result):
    # customer_predictions.csv stores the same probabilities rounded to 4 dp
    assert result['sanity_checks']['max_abs_diff_vs_stored_churn_prob'] <= 5e-5 + 1e-9
    assert result['artifact']['model_config'] == 'regularised_monotonic'


def test_overall_baseline_matches_recorded_production_metrics(result):
    with open(ev._path('model_metadata.json')) as f:
        recorded = json.load(f)['test_metrics']
    for k in sv.BASELINE_KEYS:
        assert result['overall'][k] == pytest.approx(recorded[k], abs=5e-4), k
    assert result['overall']['roc_auc'] == 0.7597


def test_no_target_leakage(result, held_out):
    _, _, _, X_test = held_out
    forbidden = set(core.LEAKAGE_COLS + core.ID_COLS + [core.TARGET_COL])
    assert not forbidden & set(X_test.columns)
    assert result['sanity_checks']['feature_set_excludes_leakage_and_identifier_columns']


def test_report_contains_no_customer_identifiers(result):
    _, _, dataset, _ = ev.load_artifacts()
    text = json.dumps(result)
    assert 'CUST' not in text and '@' not in text
    for name in dataset['name'].head(200):
        assert name not in text


# ── Groups ───────────────────────────────────────────────────────────────────

def test_every_plan_and_device_group_is_reported(result):
    assert list(result['segments']['plan_type']) == ['Basic', 'Standard', 'Premium']
    assert list(result['segments']['device_type']) == ['Laptop', 'Mobile', 'Smart TV', 'Tablet']
    for dim in ('plan_type', 'device_type', 'tenure_band'):
        for level, g in result['segments'][dim].items():
            for key in ('customers', 'retained', 'churned', 'actual_churn_rate', 'roc_auc',
                        'precision', 'recall', 'f1', 'mean_predicted_probability', 'risk_tiers'):
                assert key in g, (dim, level, key)


@pytest.mark.parametrize('dim', ['plan_type', 'device_type', 'tenure_band'])
def test_group_counts_add_up(result, dim):
    groups = result['segments'][dim].values()
    assert sum(g['customers'] for g in groups) == 1000
    assert sum(g['churned'] for g in groups) == 431
    for g in groups:
        assert g['retained'] + g['churned'] == g['customers']
        assert sum(t['customers'] for t in g['risk_tiers'].values()) == g['customers']


def test_group_metrics_match_direct_calculation(result, held_out):
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    rows, y, prob, _ = held_out
    for level, g in result['segments']['device_type'].items():
        m = (rows['device_type'] == level).values
        yy, pp = y.values[m], prob[m]
        assert g['customers'] == m.sum()
        assert g['actual_churn_rate'] == pytest.approx(yy.mean(), abs=5e-5)
        assert g['mean_predicted_probability'] == pytest.approx(pp.mean(), abs=5e-5)
        assert g['roc_auc'] == pytest.approx(roc_auc_score(yy, pp), abs=5e-5)
        pred = (pp >= 0.5).astype(int)
        assert g['precision'] == pytest.approx(precision_score(yy, pred), abs=5e-5)
        assert g['recall'] == pytest.approx(recall_score(yy, pred), abs=5e-5)
        assert g['f1'] == pytest.approx(f1_score(yy, pred), abs=5e-5)


# ── Tenure bands ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('months,band', [
    (0, '0-5 months'), (1, '0-5 months'), (5, '0-5 months'),
    (6, '6-24 months'), (24, '6-24 months'),
    (25, '25+ months'), (72, '25+ months'),
])
def test_tenure_band_boundaries(months, band):
    assert sv.tenure_band(months) == band


def test_tenure_bands_are_configurable_and_reject_gaps():
    bands = [('short', 0, 11), ('long', 12, None)]
    assert sv.tenure_band(11, bands) == 'short' and sv.tenure_band(12, bands) == 'long'
    with pytest.raises(ValueError):
        sv.tenure_band(3, [('late', 6, None)])


def test_custom_tenure_bands_flow_through_run():
    r = sv.run(write=False, tenure_bands=[('short', 0, 11), ('long', 12, None)])
    assert list(r['segments']['tenure_band']) == ['short', 'long']
    assert sum(g['customers'] for g in r['segments']['tenure_band'].values()) == 1000


# ── Risk tiers ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('p,tier', [(0.0, 'LOW'), (0.3999, 'LOW'), (0.40, 'MEDIUM'),
                                    (0.6999, 'MEDIUM'), (0.70, 'HIGH'), (1.0, 'HIGH')])
def test_risk_thresholds_follow_production_constants(p, tier):
    assert core.RISK_MEDIUM == 0.40 and core.RISK_HIGH == 0.70
    out = sv.risk_breakdown(np.array([1]), np.array([p]))
    assert out[tier]['customers'] == 1


def test_risk_tier_breakdown_matches_get_risk_level(result, held_out):
    _, y, prob, _ = held_out
    tiers = np.array([core.get_risk_level(v) for v in prob])
    for t in sv.RISK_TIERS:
        assert result['overall']['risk_tiers'][t]['customers'] == int((tiers == t).sum())
        assert result['overall']['risk_tiers'][t]['actual_churn_rate'] == pytest.approx(
            y.values[tiers == t].mean(), abs=5e-5)


# ── Small groups and undefined metrics ───────────────────────────────────────

def test_small_group_is_flagged_insufficient():
    y = np.array([1] * 10 + [0] * 15)
    p = np.linspace(0.1, 0.9, 25)
    g = sv.group_metrics(y, p, min_size=100, min_class=30, bootstrap=False)
    assert g['reliability']['sufficient'] is False
    assert len(g['reliability']['reasons']) == 3
    assert g['roc_auc'] is not None          # still reported, just flagged


def test_reliability_settings_are_configurable():
    y = np.array([1] * 10 + [0] * 15)
    p = np.linspace(0.1, 0.9, 25)
    assert sv.group_metrics(y, p, min_size=20, min_class=10, bootstrap=False)['reliability']['sufficient']


def test_tenure_0_5_is_flagged_under_provisional_settings(result):
    g = result['segments']['tenure_band']['0-5 months']
    assert g['customers'] == 88 and not g['reliability']['sufficient']
    assert 'tenure_band=0-5 months' in result['flagged']['insufficient_for_reliable_measurement']
    assert 'PROVISIONAL' in result['settings']['status']


@pytest.mark.parametrize('label', [0, 1])
def test_single_class_group_has_null_auc_with_reason(label):
    y = np.full(40, label)
    p = np.linspace(0.05, 0.95, 40)
    g = sv.group_metrics(y, p, min_size=10, min_class=5)
    assert g['roc_auc'] is None and 'only one class' in g['not_calculable']['roc_auc']
    assert g['roc_auc_95ci'] is None and g['calibration_gap_95ci'] is None
    assert g['reliability']['sufficient'] is False
    if label == 0:
        assert g['recall'] is None and g['f1'] is None


def test_no_predicted_churners_gives_null_precision():
    g = sv.group_metrics(np.array([0, 1, 0, 1]), np.array([0.1, 0.2, 0.3, 0.4]), bootstrap=False)
    assert g['precision'] is None and 'no customer predicted' in g['not_calculable']['precision']
    assert g['recall'] == 0.0


def test_comparison_rule_uses_confidence_interval():
    base = {'roc_auc': 0.76, 'accuracy': 0.7, 'precision': 0.68, 'recall': 0.59, 'f1': 0.63}
    g = {k: base[k] for k in base}
    assert sv.compare_with_baseline({**g, 'roc_auc_95ci': [0.70, 0.75]}, base)['roc_auc_clearly_below_baseline']
    assert not sv.compare_with_baseline({**g, 'roc_auc_95ci': [0.70, 0.77]}, base)['roc_auc_clearly_below_baseline']


# ── Determinism and recorded results ─────────────────────────────────────────

def test_results_are_deterministic(result):
    assert sv.run(write=False) == result


def test_recorded_json_matches_a_fresh_run(result):
    with open(os.path.join(ev.RESULTS_DIR, 'segment_validation.json')) as f:
        assert json.load(f) == json.loads(json.dumps(result))
