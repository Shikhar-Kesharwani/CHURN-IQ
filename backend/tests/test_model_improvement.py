"""CHURN-17 — the recommended 'regularised' config vs the baseline on the same split."""
import json
import os

import pytest
from sklearn.metrics import roc_auc_score

import churniq_ml_pipeline as pipeline
import evaluate_model as ev


def _test_auc(artifacts, config_name):
    cfg = pipeline.MODEL_CONFIGS[config_name]
    X_train, y_train = artifacts['X_train'], artifacts['y_train']
    if cfg['smote']:
        X_train, y_train = pipeline.apply_smote(X_train, y_train)
    model = pipeline.train_model(X_train, y_train, cfg['xgb_params'])
    return roc_auc_score(artifacts['y_test'], model.predict_proba(artifacts['X_test'])[:, 1])


def test_regularised_config_beats_baseline_on_same_split(artifacts):
    base_auc = _test_auc(artifacts, 'baseline')
    reg_auc = _test_auc(artifacts, 'regularised')
    assert base_auc == pytest.approx(0.7239, abs=1e-3)
    assert reg_auc == pytest.approx(0.7581, abs=1e-3)
    assert reg_auc > base_auc


def test_default_pipeline_config_is_unchanged_baseline():
    assert pipeline.MODEL_CONFIGS['baseline']['xgb_params'] == pipeline.XGB_PARAMS
    assert pipeline.MODEL_CONFIGS['baseline']['smote'] is True
    assert pipeline.XGB_PARAMS['max_depth'] == 5 and pipeline.XGB_PARAMS['n_estimators'] == 200


def test_recorded_experiments_support_recommendation():
    with open(os.path.join(ev.RESULTS_DIR, 'model_experiments.json')) as f:
        r = json.load(f)
    reg = r['candidates']['F_xgb_regularised_cv_tuned']
    assert reg['meets_improvement_rule'] is True
    assert reg['test_auc_diff_vs_baseline_95ci'][0] > 0
    for name in ('B_xgb_no_smote', 'C_xgb_scale_pos_weight', 'D_logistic_regression'):
        assert r['candidates'][name]['meets_improvement_rule'] is False
