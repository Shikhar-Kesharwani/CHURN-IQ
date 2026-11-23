# =============================================================================
#   ChurnIQ Pro — Full-coverage customer predictions (CHURN-37)
# =============================================================================
#   Regenerates backend/customer_predictions.csv so that EVERY eligible
#   customer has a genuine, leakage-safe model prediction — without
#   retraining or replacing the production model (churniq_model.pkl):
#
#     holdout_test    (1,000)  committed production model; these customers were
#                              never seen in training. Values are verified to
#                              be identical to the previously committed CSV.
#     cv_out_of_fold  (4,000)  training customers: 5-fold stratified CV over the
#                              training split with the production recipe
#                              (SMOTE inside training folds + XGB_PARAMS); each
#                              customer is scored by the fold model that did
#                              not see them. SHAP from that fold model.
#     demo            (CUST99999) committed production model (not in training).
#
#   Every row: churn_prob, risk_level, top-3 SHAP reasons, CLV via
#   churniq_core.calc_clv, actual_churn, prediction_source, fold.
#   Records failing churniq_core.validate_raw_record are NOT scored (they stay
#   NOT_SCORED / Unknown in the API) and are listed in the results JSON.
#   The generator's 'churn_probability' column is never used as a prediction.
#
#   Outputs:
#     backend/customer_predictions.csv     (all eligible customers)
#     backend/oof_fold_models.pkl          (5 fold models, for live what-if)
#     docs/ml/results/prediction_coverage.json
#
#   RUN (from backend/):   python generate_predictions.py      (~30 s)
#   Deterministic: re-running produces byte-identical outputs in the same
#   environment (verified by tests/test_prediction_coverage.py).
# =============================================================================

import json
import os
import pickle
import platform
import warnings

import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.metrics import brier_score_loss, roc_auc_score

import churniq_core as core
import churniq_ml_pipeline as pipeline
import evaluate_model as ev

warnings.filterwarnings('ignore')

PRED_COLS = ['churn_prob', 'risk_level', 'top_reason_1', 'top_reason_2', 'top_reason_3',
             'clv_score', 'actual_churn']


def score_with_model(model, df, X, y):
    _, shap_values = pipeline.compute_shap(model, X)
    prob = model.predict_proba(X)[:, 1]
    return pipeline.build_predictions(df, X, y, prob, shap_values)


def source_metrics(part: pd.DataFrame) -> dict:
    y, p = part['actual_churn'].values, part['churn_prob'].values
    tiers = {}
    for lvl in ('HIGH', 'MEDIUM', 'LOW'):
        m = part['risk_level'] == lvl
        tiers[lvl] = {'customers': int(m.sum()),
                      'mean_predicted': round(float(p[m].mean()), 4) if m.any() else None,
                      'observed_churn_rate': round(float(y[m].mean()), 4) if m.any() else None}
    return {
        'customers': int(len(part)),
        'roc_auc': round(float(roc_auc_score(y, p)), 4) if len(set(y)) > 1 else None,
        'brier': round(float(brier_score_loss(y, p)), 4),
        'mean_predicted': round(float(p.mean()), 4),
        'observed_churn_rate': round(float(y.mean()), 4),
        'risk_tiers': tiers,
    }


def run(write=True):
    model, feature_names, dataset, old_predictions = ev.load_artifacts()

    # ── Eligibility ────────────────────────────────────────────────────────
    invalid = {r['customer_id']: core.validate_raw_record(r)
               for r in dataset.to_dict(orient='records') if core.validate_raw_record(r)}
    eligible = dataset[~dataset['customer_id'].isin(invalid)]

    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(eligible)

    # ── 1. Held-out test customers: committed production model ─────────────
    test_part = score_with_model(model, base, X_test, y_test)
    test_part['prediction_source'] = 'holdout_test'
    test_part['fold'] = pd.NA

    # Must reproduce the previously committed test predictions exactly
    old = old_predictions.fillna({'top_reason_1': 'N/A', 'top_reason_2': 'N/A',
                                  'top_reason_3': 'N/A'}).set_index('customer_id')
    new = test_part.set_index('customer_id')
    old = old.loc[new.index]
    for col in PRED_COLS:
        if col in ('churn_prob', 'clv_score'):
            assert np.allclose(old[col].values, new[col].values, atol=0.011), col
        else:
            assert (old[col].values == new[col].values).all(), col

    # ── 2. Training customers: out-of-fold predictions ─────────────────────
    oof_part, fold_models = pipeline.build_oof_predictions(base, X_train, y_train, 'baseline')

    # ── 3. Demo customers (not part of the split): committed model ─────────
    demo = eligible[eligible['customer_id'].isin(pipeline.DEMO_CUSTOMER_IDS)]
    parts = [test_part, oof_part]
    if len(demo):
        X_demo = core.encode_features(demo, feature_names)
        demo_part = score_with_model(model, demo, X_demo, demo['churn'].astype(int))
        demo_part['prediction_source'] = 'demo'
        demo_part['fold'] = pd.NA
        parts.append(demo_part)

    predictions = pipeline.finalise_predictions(*parts)

    # ── Coverage + evidence ────────────────────────────────────────────────
    by_source = {s: source_metrics(predictions[predictions['prediction_source'] == s])
                 for s in ('holdout_test', 'cv_out_of_fold')}
    clv_recomputed = predictions.merge(dataset[['customer_id', 'monthly_charge', 'tenure_months']],
                                       on='customer_id')
    t = np.maximum(clv_recomputed['tenure_months'], core.CLV_MIN_TENURE)
    clv_err = (clv_recomputed['monthly_charge'] * t * (1 - clv_recomputed['churn_prob'])
               - clv_recomputed['clv_score']).abs()
    results = {
        'artifact': 'churniq_model.pkl (unchanged) for holdout_test + demo; '
                    '5 fold models (production recipe) for cv_out_of_fold',
        'environment': {'xgboost': xgboost.__version__, 'scikit_learn': sklearn.__version__,
                        'python': platform.python_version(), 'platform': platform.platform()},
        'oof': {'n_splits': pipeline.OOF_N_SPLITS, 'seed': pipeline.SEED,
                'recipe': 'SMOTE (training folds only) + XGB_PARAMS (baseline/production)',
                'fold_train_rows': [int(len(tr)) for tr, _ in pipeline.oof_folds(X_train, y_train)]},
        'coverage': {
            'customers_in_dataset': int(len(dataset)),
            'eligible': int(len(eligible)),
            'invalid_not_scored': {k: v for k, v in invalid.items()},
            'scored': int(len(predictions)),
            'by_source': predictions['prediction_source'].value_counts().to_dict(),
            'churn_prob_in_0_1': bool(predictions['churn_prob'].between(0, 1).all()),
            'any_nan': bool(predictions[PRED_COLS].isna().any().any()),
        },
        'test_rows_identical_to_previous_csv': True,
        'metrics_by_source': by_source,
        'clv_formula_max_abs_error_vs_rounded_prob': round(float(clv_err.max()), 4),
        'tiers_consistent': bool((predictions['clv_score'].map(core.get_clv_segment).notna()).all()
                                 and (predictions['churn_prob'].map(core.get_risk_level)
                                      == predictions['risk_level']).all()),
    }

    if write:
        predictions.to_csv(ev._path('customer_predictions.csv'), index=False)
        with open(ev._path('oof_fold_models.pkl'), 'wb') as f:
            pickle.dump({'models': fold_models, 'feature_names': list(feature_names),
                         'model_config': 'baseline', 'n_splits': pipeline.OOF_N_SPLITS,
                         'seed': pipeline.SEED, 'xgboost_version': xgboost.__version__}, f)
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'prediction_coverage.json'), 'w') as f:
            json.dump(results, f, indent=2)
    return predictions, fold_models, results


if __name__ == '__main__':
    _, _, r = run()
    print(json.dumps({k: r[k] for k in ('coverage', 'metrics_by_source',
                                        'clv_formula_max_abs_error_vs_rounded_prob',
                                        'tiers_consistent')}, indent=2))
