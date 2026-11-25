"""CHURN-45 — monotone constraints fix per-customer What-If direction at no material AUC cost.

Fast checks (a few seconds): the constraint vector matches the documented
expected directions, a constrained model trained with the same recipe never
moves risk the wrong way for any test customer, and the recorded experiment
supports the adopt decision.
"""
import json
import os

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

import churniq_ml_pipeline as pipeline
import evaluate_model as ev
import monotonic_experiments as mx


def test_expected_directions_match_the_data_generator():
    # churn_score in generate_dataset falls with watch hours, logins and tenure,
    # and rises with payment failures and support tickets; monthly_charge has no
    # direct term (it is fixed by plan_type), so it is left unconstrained.
    assert mx.WHATIF_DIRECTIONS == {
        'watch_hours_per_week': -1, 'logins_last_30_days': -1, 'tenure_months': -1,
        'payment_failures_3m': +1, 'support_tickets': +1, 'monthly_charge': 0,
    }
    assert mx.ENGINEERED_DIRECTIONS == {'engagement_score': -1, 'friction_score': +1,
                                        'is_new_customer': +1}


def test_constraint_vector_follows_feature_order(artifacts):
    cols = list(artifacts['X'].columns)
    vec = mx.constraint_tuple(cols)
    assert len(vec) == len(cols)
    named = dict(zip(cols, vec))
    for feat, sign in {**mx.WHATIF_DIRECTIONS, **mx.ENGINEERED_DIRECTIONS}.items():
        assert named[feat] == sign, feat
    # Everything else (demographics, plan, one-hot columns) is unconstrained
    assert sum(1 for v in vec if v != 0) == 8


@pytest.fixture(scope='module')
def constrained_model(artifacts):
    reg = pipeline.MODEL_CONFIGS['regularised']['xgb_params']
    params = dict(reg, monotone_constraints=mx.constraint_tuple(list(artifacts['X'].columns)))
    return pipeline.train_model(artifacts['X_train'].astype(float), artifacts['y_train'], params)


def test_constrained_model_never_moves_risk_the_wrong_way(artifacts, constrained_model):
    raw = artifacts['base'].loc[artifacts['X_test'].index[:200]].copy()
    dtypes = artifacts['X_test'].astype(float).dtypes
    result = mx.whatif_behaviour(constrained_model, raw, artifacts['feature_names'], dtypes)
    for feat, sweep in result['grid_sweeps'].items():
        assert sweep['share_customers_with_any_wrong_step'] == 0.0, feat
        assert sweep['largest_wrong_step'] == 0.0, feat


def test_constrained_model_keeps_regularised_performance(artifacts, constrained_model):
    auc = roc_auc_score(artifacts['y_test'],
                        constrained_model.predict_proba(artifacts['X_test'].astype(float))[:, 1])
    # Unconstrained regularised recipe scores ~0.758 on this split (CHURN-17)
    assert 0.750 <= auc <= 0.770


def test_recorded_experiment_supports_adoption():
    with open(os.path.join(ev.RESULTS_DIR, 'monotonic_experiments.json')) as f:
        r = json.load(f)
    behaviour = r['whatif_behaviour']
    # Unconstrained models violate direction for most customers on engagement features
    for name in ('committed_production_artifact', 'A_baseline_smote_xgb', 'F_regularised_xgb'):
        assert behaviour[name]['grid_sweeps']['watch_hours_per_week'][
            'share_customers_with_any_wrong_step'] > 0.9
    # Constrained models: zero violations on every constrained What-If feature
    for name in ('A_mono_baseline_smote_xgb', 'F_mono_regularised_xgb'):
        for sweep in behaviour[name]['grid_sweeps'].values():
            assert sweep['share_customers_with_any_wrong_step'] == 0.0
    cmp = r['comparisons']
    # Constraint costs nothing measurable on the reference split ...
    assert cmp['F_mono vs F (constraints on CHURN-17 regularised recipe)']['no_worse_than_reference']
    # ... and the adopted recipe still beats the production recipe significantly
    assert cmp['F_mono vs A (constrained regularised vs production recipe)']['meets_improvement_rule']
    # Across 10 other splits the cost is negligible
    rob = r['robustness_10_splits']
    assert abs(rob['mean_diff_F_mono_minus_F']) < 0.005 and rob['min_diff'] > -0.01
