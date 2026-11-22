"""CHURN-14 — Model evaluation on the held-out test split (committed artifact)."""
import json
import os

import pytest

import evaluate_model as ev


@pytest.fixture(scope='module')
def results():
    return ev.run(write=False)


def test_sanity_checks(results):
    assert results['sanity_checks']['split_matches_customer_predictions_csv'] is True
    assert results['sanity_checks']['max_abs_diff_vs_stored_churn_prob'] <= 1e-4


def test_class_distribution(results):
    cd = results['class_distribution']
    assert cd['test']['retained'] + cd['test']['churned'] == 1000
    assert cd['train']['retained'] + cd['train']['churned'] == 4000
    assert cd['train_after_smote']['churn_rate'] == 0.5
    # Test set keeps the real-world class ratio (SMOTE not applied)
    assert abs(cd['test']['churn_rate'] - cd['full']['churn_rate']) < 0.005


def test_metrics_are_valid_and_confusion_matrix_consistent(results):
    m, cm = results['metrics'], results['confusion_matrix']
    for k in ('accuracy', 'precision', 'recall', 'f1', 'roc_auc'):
        assert 0.0 <= m[k] <= 1.0
        lo, hi = results['metrics_95ci'][k]
        assert lo <= m[k] <= hi
    assert sum(cm.values()) == 1000
    assert m['accuracy'] == pytest.approx((cm['tp'] + cm['tn']) / 1000, abs=1e-4)
    assert m['precision'] == pytest.approx(cm['tp'] / (cm['tp'] + cm['fp']), abs=1e-4)
    assert m['recall'] == pytest.approx(cm['tp'] / (cm['tp'] + cm['fn']), abs=1e-4)


def test_model_beats_majority_baseline_and_stays_below_oracle(results):
    m, ref = results['metrics'], results['reference']
    assert m['roc_auc'] > 0.5
    assert m['accuracy'] > ref['majority_class']['accuracy']
    assert m['roc_auc'] < ref['oracle_true_probability']['roc_auc']


def test_results_match_recorded_report(results):
    """Guards the numbers quoted in docs/ml/02-model-evaluation.md."""
    path = os.path.join(ev.RESULTS_DIR, 'evaluation_results.json')
    with open(path) as f:
        recorded = json.load(f)
    assert results['metrics'] == recorded['metrics']
    assert results['confusion_matrix'] == recorded['confusion_matrix']
