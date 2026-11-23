# =============================================================================
#   ChurnIQ Pro — Independent verification of the CHURN-17 result (audit)
# =============================================================================
#   Re-checks the claim "regularised XGBoost (no SMOTE) beats the baseline"
#   with tests that were NOT used to select it:
#     1. DeLong test for correlated ROC-AUCs on the original test split,
#        vs the retrained baseline and vs the committed artifact, with a
#        Bonferroni correction for the 6 candidates compared in CHURN-17.
#     2. 10 fresh stratified train/test splits (seeds 1-10): the AUC gain on
#        each, and a sign test.
#     3. Repeated 5x3 stratified CV on the training split with a new seed.
#   Production artifacts are not touched. Writes
#   docs/ml/results/model_improvement_verification.json
#
#   RUN (from backend/):   python verify_model_improvement.py   (~1 minute)
# =============================================================================

import json
import os
import warnings

import numpy as np
from scipy import stats
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score, train_test_split

import churniq_ml_pipeline as pipeline
import evaluate_model as ev
import model_experiments as mx

warnings.filterwarnings('ignore')

REG = pipeline.MODEL_CONFIGS['regularised']['xgb_params']
N_COMPARISONS = 6   # candidates B-G compared against the baseline in CHURN-17


def delong(y, prob_a, prob_b):
    """DeLong (1988) test of AUC(b) − AUC(a) for two scores on the same samples."""
    y = np.asarray(y)
    pos, neg = y == 1, y == 0

    def components(p):
        p = np.asarray(p)
        P, N = p[pos], p[neg]
        v10 = np.array([((x > N).sum() + 0.5 * (x == N).sum()) / len(N) for x in P])
        v01 = np.array([((P > x).sum() + 0.5 * (P == x).sum()) / len(P) for x in N])
        return v10.mean(), v10, v01

    auc_a, a10, a01 = components(prob_a)
    auc_b, b10, b01 = components(prob_b)
    s10, s01 = np.cov(np.vstack([a10, b10])), np.cov(np.vstack([a01, b01]))
    var = ((s10[0, 0] + s10[1, 1] - 2 * s10[0, 1]) / pos.sum()
           + (s01[0, 0] + s01[1, 1] - 2 * s01[0, 1]) / neg.sum())
    z = (auc_b - auc_a) / np.sqrt(var)
    return float(auc_b - auc_a), float(z), float(2 * stats.norm.sf(abs(z)))


def fit_baseline(X, y):
    Xs, ys = pipeline.apply_smote(X, y)
    return pipeline.train_model(Xs, ys)


def fit_regularised(X, y):
    return pipeline.train_model(X, y, REG)


def run(write=True):
    model, _, dataset, _ = ev.load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(dataset)

    p_base = fit_baseline(X_train, y_train).predict_proba(X_test)[:, 1]
    p_reg = fit_regularised(X_train, y_train).predict_proba(X_test)[:, 1]
    p_committed = model.predict_proba(X_test)[:, 1]

    delong_results = {}
    for name, ref in (('vs_retrained_baseline', p_base), ('vs_committed_artifact', p_committed)):
        d, z, p = delong(y_test, ref, p_reg)
        delong_results[name] = {'auc_gain': round(d, 4), 'z': round(z, 2), 'p_value': p,
                                'bonferroni_alpha': round(0.05 / N_COMPARISONS, 4),
                                'significant_after_bonferroni': p < 0.05 / N_COMPARISONS}

    gains = []
    for seed in range(1, 11):
        a, b, c, d = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)
        auc_r = roc_auc_score(d, fit_regularised(a, c).predict_proba(b)[:, 1])
        auc_b = roc_auc_score(d, fit_baseline(a, c).predict_proba(b)[:, 1])
        gains.append({'split_seed': seed, 'baseline_auc': round(auc_b, 4),
                      'regularised_auc': round(auc_r, 4), 'gain': round(auc_r - auc_b, 4)})
    g = np.array([r['gain'] for r in gains])
    wins = int((g > 0).sum())

    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=7)
    cv_base = cross_val_score(mx.with_smote(mx.xgb()), X_train, y_train, cv=rcv, scoring='roc_auc')
    reg_params = {k: REG[k] for k in ('max_depth', 'learning_rate', 'n_estimators', 'min_child_weight')}
    cv_reg = cross_val_score(mx.xgb(**reg_params), X_train.astype(float), y_train, cv=rcv,
                             scoring='roc_auc')

    out = {
        'delong_original_split': delong_results,
        'fresh_splits': {
            'per_split': gains,
            'mean_gain': round(float(g.mean()), 4), 'sd_gain': round(float(g.std(ddof=1)), 4),
            'min_gain': round(float(g.min()), 4), 'max_gain': round(float(g.max()), 4),
            'regularised_wins': wins, 'sign_test_p': float(stats.binomtest(wins, len(g)).pvalue),
        },
        'repeated_cv_5x3_seed7': {
            'baseline_mean': round(float(cv_base.mean()), 4), 'baseline_sd': round(float(cv_base.std()), 4),
            'regularised_mean': round(float(cv_reg.mean()), 4), 'regularised_sd': round(float(cv_reg.std()), 4),
            'regularised_better_folds': int((cv_reg > cv_base).sum()), 'folds': int(len(cv_reg)),
        },
    }
    if write:
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'model_improvement_verification.json'), 'w') as f:
            json.dump(out, f, indent=2)
    return out


if __name__ == '__main__':
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != 'fresh_splits'}, indent=2))
    fs = r['fresh_splits']
    print(f"fresh splits: mean gain {fs['mean_gain']:+.4f} (sd {fs['sd_gain']:.4f}, "
          f"range {fs['min_gain']:+.4f}..{fs['max_gain']:+.4f}), wins {fs['regularised_wins']}/10, "
          f"sign test p={fs['sign_test_p']:.4f}")
