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


# ── Adopted production artifacts (CHURN-57) ─────────────────────────────────

def test_production_config_is_the_adopted_constrained_recipe():
    assert pipeline.PRODUCTION_CONFIG == 'regularised_monotonic'
    cfg = pipeline.MODEL_CONFIGS['regularised_monotonic']
    assert cfg['monotone'] is True and cfg['smote'] is False
    assert cfg['xgb_params'] == pipeline.MODEL_CONFIGS['regularised']['xgb_params']
    assert pipeline.MONOTONE_DIRECTIONS == mx.CONSTRAINTS


def test_committed_artifacts_carry_the_constraints(artifacts):
    import pickle
    expected = pipeline.monotone_constraint_tuple(artifacts['feature_names'])

    def constraints_of(model):
        cfg = json.loads(model.get_booster().save_config())
        raw = cfg['learner']['gradient_booster']['tree_train_param']['monotone_constraints']
        return tuple(int(v) for v in raw.strip('()').split(','))

    assert constraints_of(artifacts['model']) == expected
    with open(os.path.join(os.path.dirname(ev.RESULTS_DIR), '..', '..', 'backend',
                           'oof_fold_models.pkl'), 'rb') as f:
        bundle = pickle.load(f)
    assert bundle['model_config'] == pipeline.PRODUCTION_CONFIG and bundle['seed'] == pipeline.SEED
    for m in bundle['models']:
        assert constraints_of(m) == expected
    with open(os.path.join(os.path.dirname(ev.RESULTS_DIR), '..', '..', 'backend',
                           'model_metadata.json')) as f:
        meta = json.load(f)
    assert meta['model_config'] == pipeline.PRODUCTION_CONFIG and meta['seed'] == pipeline.SEED
    assert tuple(meta['xgb_params']['monotone_constraints']) == expected
    assert meta['test_metrics']['roc_auc'] == 0.7597


@pytest.mark.parametrize('field,values,sign', [
    ('watch_hours_per_week', [0.5, 2.0, 5.0, 12.0, 40.0], -1),
    ('logins_last_30_days', [0, 2, 8, 26], -1),
    ('tenure_months', [1, 5, 12, 72], -1),
    ('payment_failures_3m', [0, 1, 2, 4], +1),
    ('support_tickets', [0, 2, 5], +1),
])
def test_served_whatif_is_monotonic_for_every_sampled_customer(api, field, values, sign):
    """Through POST /whatif: holdout (production model) and out-of-fold (fold models)."""
    from fastapi.testclient import TestClient
    main, _ = api
    client = TestClient(main.app)
    p = main.PREDICTIONS_DF
    ids = (list(p.loc[p['prediction_source'] == 'holdout_test', 'customer_id'][::25])
           + list(p.loc[p['prediction_source'] == 'cv_out_of_fold', 'customer_id'][::100]))
    for cid in ids:
        probs = []
        for v in values:
            r = client.post('/whatif', json={'customer_id': cid, field: v})
            assert r.status_code == 200, r.text
            probs.append(r.json()['new_churn_prob'])
        steps = np.diff(probs) * sign
        # Responses are rounded to 4 dp, so allow one rounding unit
        assert (steps >= -1e-4).all(), (cid, field, probs)
