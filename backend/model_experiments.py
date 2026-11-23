# =============================================================================
#   ChurnIQ Pro — Model Improvement Experiments (CHURN-17)
# =============================================================================
#   Controlled comparison of candidate improvements against the baseline.
#
#   PROTOCOL (fixed before looking at test results):
#     - Same dataset and the same 80/20 stratified split (random_state=42)
#       as churniq_ml_pipeline.py / evaluate_model.py.
#     - Model/threshold SELECTION uses only the 4,000 training rows:
#       5-fold stratified CV (random_state=42), SMOTE applied INSIDE each
#       training fold only (imblearn Pipeline) — never on validation folds.
#     - Each shortlisted candidate is refit on the full training split and
#       scored ONCE on the held-out test split.
#     - Test differences vs the baseline use a paired bootstrap (1,000
#       resamples) of ROC-AUC on the same test customers.
#     - A candidate counts as an improvement only if its CV ROC-AUC beats the
#       baseline by more than one CV standard deviation AND the paired test
#       ROC-AUC difference has a 95% CI above 0.
#
#   The committed production artifact is NOT modified.
#   Results → docs/ml/results/model_experiments.json
#
#   RUN (from backend/):   python model_experiments.py      (~1-2 minutes)
# =============================================================================

import itertools
import json
import os
import warnings

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, f1_score, log_loss,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

import churniq_ml_pipeline as pipeline
import evaluate_model as ev

warnings.filterwarnings('ignore')

SEED = pipeline.SEED
CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

# Demographic / preference features — hypothesis from CHURN-15: the model
# spends ~47% of its SHAP mass on these, and they rarely carry churn signal.
DEMOGRAPHIC_PREFIXES = ('age', 'gender_', 'country_', 'preferred_genre_', 'payment_method_')


def behavioural_columns(cols):
    return [c for c in cols if not c.startswith(DEMOGRAPHIC_PREFIXES)]


def xgb(**overrides):
    params = dict(pipeline.XGB_PARAMS)
    params.update(overrides)
    return XGBClassifier(**params)


def with_smote(model):
    return ImbPipeline([('smote', SMOTE(**pipeline.SMOTE_PARAMS)), ('model', model)])


def logistic(cols):
    num = [c for c in cols if not c.startswith(('gender_', 'country_', 'preferred_genre_',
                                                'device_type_', 'payment_method_'))]
    pre = ColumnTransformer([('num', StandardScaler(), num)], remainder='passthrough')
    from sklearn.pipeline import Pipeline
    return Pipeline([('pre', pre), ('lr', LogisticRegression(max_iter=2000, C=1.0))])


def cv_scores(estimator, X, y):
    """Out-of-fold probabilities + per-fold ROC-AUC on the training split."""
    oof = cross_val_predict(estimator, X, y, cv=CV, method='predict_proba')[:, 1]
    folds = [roc_auc_score(y.iloc[va], oof[va]) for _, va in CV.split(X, y)]
    return oof, float(np.mean(folds)), float(np.std(folds))


def test_metrics(y, prob, threshold=0.5):
    pred = (prob >= threshold).astype(int)
    return {
        'threshold': round(float(threshold), 3),
        'accuracy':  round(float(accuracy_score(y, pred)), 4),
        'precision': round(float(precision_score(y, pred, zero_division=0)), 4),
        'recall':    round(float(recall_score(y, pred, zero_division=0)), 4),
        'f1':        round(float(f1_score(y, pred, zero_division=0)), 4),
        'roc_auc':   round(float(roc_auc_score(y, prob)), 4),
        'brier':     round(float(brier_score_loss(y, prob)), 4),
        'log_loss':  round(float(log_loss(y, prob)), 4),
        'mean_pred': round(float(prob.mean()), 4),
    }


def paired_auc_diff(y, prob_a, prob_b, n=1000, seed=SEED):
    """95% CI of AUC(b) − AUC(a) over paired bootstrap resamples of the test set."""
    rng = np.random.default_rng(seed)
    y, prob_a, prob_b = np.asarray(y), np.asarray(prob_a), np.asarray(prob_b)
    diffs = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        diffs.append(roc_auc_score(y[i], prob_b[i]) - roc_auc_score(y[i], prob_a[i]))
    return [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)]


def best_f1_threshold(y, oof):
    grid = np.round(np.arange(0.20, 0.71, 0.01), 2)
    scores = [f1_score(y, (oof >= t).astype(int)) for t in grid]
    return float(grid[int(np.argmax(scores))])


def run(write=True):
    model_art, _, dataset, _ = ev.load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(dataset)
    X_train_f, X_test_f = X_train.astype(float), X_test.astype(float)
    beh = behavioural_columns(list(X.columns))

    # ── Candidate definitions ──────────────────────────────────────────────
    candidates = {
        'A_baseline_smote_xgb':        (with_smote(xgb()), None),
        'B_xgb_no_smote':              (xgb(), None),
        'C_xgb_scale_pos_weight':      (xgb(scale_pos_weight=float((y_train == 0).sum() / (y_train == 1).sum())), None),
        'D_logistic_regression':       (logistic(list(X.columns)), None),
        'E_logistic_behavioural':      (logistic(beh), beh),
    }

    # Small, CV-only hyper-parameter search for a regularised XGBoost
    grid = list(itertools.product([2, 3, 4], [0.03, 0.1], [150, 400], [1, 10]))
    search = []
    for depth, lr, n_est, mcw in grid:
        est = xgb(max_depth=depth, learning_rate=lr, n_estimators=n_est, min_child_weight=mcw)
        _, mean, std = cv_scores(est, X_train_f, y_train)
        search.append({'max_depth': depth, 'learning_rate': lr, 'n_estimators': n_est,
                       'min_child_weight': mcw, 'cv_auc_mean': round(mean, 4), 'cv_auc_std': round(std, 4)})
    search.sort(key=lambda r: -r['cv_auc_mean'])
    best = search[0]
    best_params = {k: best[k] for k in ('max_depth', 'learning_rate', 'n_estimators', 'min_child_weight')}
    candidates['F_xgb_regularised_cv_tuned'] = (xgb(**best_params), None)
    candidates['G_xgb_regularised_behavioural'] = (xgb(**best_params), beh)

    # ── CV on training split, then one test evaluation per candidate ───────
    results, test_probs, oofs = {}, {}, {}
    for name, (est, cols) in candidates.items():
        if name == 'A_baseline_smote_xgb':
            # Exactly the production recipe, incl. original dtypes (SMOTE keeps
            # integer/bool columns integer/bool, as in churniq_ml_pipeline.py)
            Xtr, Xte = X_train, X_test
        else:
            Xtr = X_train_f if cols is None else X_train_f[cols]
            Xte = X_test_f if cols is None else X_test_f[cols]
        oof, mean, std = cv_scores(est, Xtr, y_train)
        est.fit(Xtr, y_train)
        prob = est.predict_proba(Xte)[:, 1]
        oofs[name], test_probs[name] = oof, prob
        results[name] = {
            'n_features': int(Xtr.shape[1]),
            'cv_auc_mean': round(mean, 4), 'cv_auc_std': round(std, 4),
            'cv_brier': round(float(brier_score_loss(y_train, oof)), 4),
            'test': test_metrics(y_test, prob),
        }

    # Paired comparison against the (retrained) baseline
    base_name = 'A_baseline_smote_xgb'
    for name in results:
        if name == base_name:
            continue
        r = results[name]
        r['test_auc_diff_vs_baseline_95ci'] = paired_auc_diff(y_test, test_probs[base_name], test_probs[name])
        r['meets_improvement_rule'] = bool(
            r['cv_auc_mean'] - results[base_name]['cv_auc_mean'] > results[base_name]['cv_auc_std']
            and r['test_auc_diff_vs_baseline_95ci'][0] > 0)

    # Threshold tuning on OOF predictions (training split only)
    threshold_tuning = {}
    for name in (base_name, 'F_xgb_regularised_cv_tuned', 'G_xgb_regularised_behavioural'):
        t = best_f1_threshold(y_train, oofs[name])
        threshold_tuning[name] = {'f1_optimal_threshold_from_cv': t,
                                  'test_at_0.5': test_metrics(y_test, test_probs[name], 0.5),
                                  'test_at_tuned': test_metrics(y_test, test_probs[name], t)}

    # Reference points on the same test split
    committed_prob = model_art.predict_proba(X_test)[:, 1]
    oracle = base.loc[X_test.index, 'churn_probability'].values
    reference = {
        'committed_production_artifact': test_metrics(y_test, committed_prob),
        'oracle_true_generator_probability': test_metrics(y_test, oracle),
    }

    out = {
        'protocol': {
            'split': '80/20 stratified, random_state=42 (same as pipeline)',
            'selection': '5-fold stratified CV on training split only, SMOTE inside folds',
            'test_usage': 'one evaluation per candidate after selection',
            'improvement_rule': 'CV AUC gain > baseline CV std AND paired bootstrap 95% CI of '
                                'test AUC difference > 0',
        },
        'reference': reference,
        'hyperparameter_search_top5': search[:5],
        'hyperparameter_search_size': len(search),
        'selected_regularised_params': best_params,
        'candidates': results,
        'threshold_tuning': threshold_tuning,
    }
    if write:
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'model_experiments.json'), 'w') as f:
            json.dump(out, f, indent=2)
    return out


if __name__ == '__main__':
    r = run()
    rows = [{'candidate': k, 'n_feat': v['n_features'], 'cv_auc': f"{v['cv_auc_mean']:.4f}±{v['cv_auc_std']:.4f}",
             **{m: v['test'][m] for m in ('roc_auc', 'accuracy', 'precision', 'recall', 'f1', 'brier', 'mean_pred')},
             'auc_diff_ci': v.get('test_auc_diff_vs_baseline_95ci', '-'),
             'improves': v.get('meets_improvement_rule', '-')}
            for k, v in r['candidates'].items()]
    pd.set_option('display.width', 250)
    print(pd.DataFrame(rows).to_string(index=False))
    print('\nselected regularised params:', r['selected_regularised_params'])
    print('reference:', json.dumps(r['reference'], indent=1))
    print('threshold tuning:', json.dumps(r['threshold_tuning'], indent=1))
