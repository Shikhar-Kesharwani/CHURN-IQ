# =============================================================================
#   ChurnIQ Pro — Monotonic-constraint experiment (CHURN-45)
# =============================================================================
#   Question: do XGBoost monotone_constraints fix the per-customer
#   non-monotonic What-If behaviour (docs/api/README.md §7), and at what cost
#   in predictive performance?
#
#   PROTOCOL — identical to model_experiments.py (CHURN-17), fixed in advance:
#     - Same committed dataset and the same 80/20 stratified split
#       (random_state=42), rebuilt with evaluate_model.rebuild_split.
#     - 5-fold stratified CV (random_state=42) on the 4,000 training rows only;
#       SMOTE inside the training folds only where the recipe uses SMOTE.
#     - Each candidate refit on the full training split and scored ONCE on the
#       1,000 held-out test customers.
#     - Paired bootstrap (1,000 resamples) of the test ROC-AUC difference.
#     - Same improvement rule as CHURN-17: CV AUC gain > reference CV std AND
#       paired 95% CI of the test AUC difference above 0. A constrained model
#       counts as "no worse" if the paired CI of (constrained − unconstrained)
#       contains 0 or lies above it.
#
#   PER-CUSTOMER WHAT-IF CHECK (held-out test customers):
#     Raw feature values are changed exactly as /whatif does — via
#     churniq_core.encode_features, so engagement_score, friction_score and
#     is_new_customer are recomputed — and each feature is swept over a grid.
#     A customer "violates" a feature if predicted risk moves against the
#     expected direction between any two consecutive grid values.
#
#   EXPECTED DIRECTIONS come from the data-generating process
#   (churniq_ml_pipeline.generate_dataset): churn_score falls with watch hours,
#   logins and tenure, and rises with payment failures and support tickets.
#   monthly_charge has no direct effect (it is fixed by plan_type; only the
#   Basic+Mobile interaction adds risk), so it is left unconstrained.
#
#   The committed production artifacts are NOT modified.
#   Results → docs/ml/results/monotonic_experiments.json
#
#   RUN (from backend/, needs requirements-dev.txt):
#       python monotonic_experiments.py          (~1 minute)
# =============================================================================
import json
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

import churniq_core as core
import churniq_ml_pipeline as pipeline
import evaluate_model as ev
from model_experiments import (cv_scores, paired_auc_diff, test_metrics, with_smote, xgb)

warnings.filterwarnings('ignore')

# Expected direction of risk as each What-If input INCREASES
# (+1 = risk rises, -1 = risk falls, 0 = no expectation / unconstrained).
WHATIF_DIRECTIONS = {
    'watch_hours_per_week': -1,
    'logins_last_30_days':  -1,
    'tenure_months':        -1,
    'payment_failures_3m':  +1,
    'support_tickets':      +1,
    'monthly_charge':        0,
}
# Engineered features that depend on the What-If inputs get the matching sign,
# so the combined effect of a raw change stays monotone.
ENGINEERED_DIRECTIONS = {
    'engagement_score': -1,   # watch_hours × logins / 30
    'friction_score':   +1,   # payment_failures + support_tickets
    'is_new_customer':  +1,   # 1 when tenure < 6 (falls as tenure rises)
}
CONSTRAINTS = {**{k: v for k, v in WHATIF_DIRECTIONS.items() if v != 0}, **ENGINEERED_DIRECTIONS}
# The adopted production config (CHURN-57) uses the same directions.
assert CONSTRAINTS == pipeline.MONOTONE_DIRECTIONS

# Sweep grids (within the training range of each feature).
GRIDS = {
    'watch_hours_per_week': [0.5, 1, 2, 3, 5, 8, 12, 20, 30, 40],
    'logins_last_30_days':  [0, 1, 2, 3, 5, 8, 12, 16, 20, 26, 30],
    'tenure_months':        [1, 2, 3, 4, 6, 9, 12, 18, 24, 36, 48, 72],
    'payment_failures_3m':  [0, 1, 2, 3, 4],
    'support_tickets':      [0, 1, 2, 3, 4, 5],
}
# Single-step changes measured in docs/api/README.md §7 (CHURN-24).
POINT_CHANGES = [
    ('watch_hours_per_week', 40), ('watch_hours_per_week', 0.5),
    ('logins_last_30_days', 26), ('tenure_months', 72), ('tenure_months', 1),
    ('payment_failures_3m', 4), ('payment_failures_3m', 0), ('support_tickets', 5),
]
EPS = 1e-6          # any movement in the wrong direction
MATERIAL = 0.01     # a wrong-direction movement of at least 1 percentage point


def constraint_tuple(columns):
    return tuple(int(CONSTRAINTS.get(c, 0)) for c in columns)


def predict_raw(model, raw: pd.DataFrame, feature_names, dtypes) -> np.ndarray:
    X = core.encode_features(raw, feature_names).astype(dtypes)
    return model.predict_proba(X)[:, 1]


def whatif_behaviour(model, raw: pd.DataFrame, feature_names, dtypes) -> dict:
    """Per-customer direction checks on the given raw rows."""
    base_prob = predict_raw(model, raw, feature_names, dtypes)
    out = {'point_changes': {}, 'grid_sweeps': {}}
    for feat, value in POINT_CHANGES:
        changed = raw.copy()
        changed[feat] = value
        delta = predict_raw(model, changed, feature_names, dtypes) - base_prob
        moved = raw[feat].values != value
        d = delta[moved]
        out['point_changes'][f'{feat} -> {value}'] = {
            'n_customers_changed': int(moved.sum()),
            'mean_delta': round(float(d.mean()), 4),
            'share_up': round(float((d > EPS).mean()), 4),
            'share_down': round(float((d < -EPS).mean()), 4),
        }
    for feat, grid in GRIDS.items():
        sign = WHATIF_DIRECTIONS[feat]
        probs = []
        for value in grid:
            changed = raw.copy()
            changed[feat] = value
            probs.append(predict_raw(model, changed, feature_names, dtypes))
        steps = np.diff(np.vstack(probs), axis=0) * sign   # >0 = expected direction
        any_wrong = (steps < -EPS).any(axis=0)
        material_wrong = (steps < -MATERIAL).any(axis=0)
        out['grid_sweeps'][feat] = {
            'expected_direction': 'risk falls as value rises' if sign < 0 else 'risk rises as value rises',
            'grid': grid,
            'share_customers_with_any_wrong_step': round(float(any_wrong.mean()), 4),
            'share_customers_with_wrong_step_over_1pp': round(float(material_wrong.mean()), 4),
            'largest_wrong_step': round(float(max(0.0, -steps.min())), 4),
        }
    return out


def run(write=True):
    committed, feature_names, dataset, _ = ev.load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(dataset)
    assert list(X.columns) == list(feature_names), 'feature order differs from FEATURE_NAMES'
    X_train_f, X_test_f = X_train.astype(float), X_test.astype(float)
    mono = constraint_tuple(list(X.columns))

    reg = dict(pipeline.MODEL_CONFIGS['regularised']['xgb_params'])
    reg_overrides = {k: reg[k] for k in ('max_depth', 'learning_rate', 'n_estimators', 'min_child_weight')}

    # name -> (estimator, use original dtypes [SMOTE recipe] or float)
    candidates = {
        'A_baseline_smote_xgb':          (with_smote(xgb()), True),
        'A_mono_baseline_smote_xgb':     (with_smote(xgb(monotone_constraints=mono)), True),
        'F_regularised_xgb':             (xgb(**reg_overrides), False),
        'F_mono_regularised_xgb':        (xgb(**reg_overrides, monotone_constraints=mono), False),
    }

    results, test_probs, fitted = {}, {}, {}
    for name, (est, orig) in candidates.items():
        Xtr, Xte = (X_train, X_test) if orig else (X_train_f, X_test_f)
        oof, mean, std = cv_scores(est, Xtr, y_train)
        est.fit(Xtr, y_train)
        prob = est.predict_proba(Xte)[:, 1]
        test_probs[name], fitted[name] = prob, (est, Xte.dtypes)
        results[name] = {
            'cv_auc_mean': round(mean, 4), 'cv_auc_std': round(std, 4),
            'cv_brier': round(float(brier_score_loss(y_train, oof)), 4),
            'test': test_metrics(y_test, prob),
        }

    committed_prob = committed.predict_proba(X_test)[:, 1]
    test_probs['committed_production_artifact'] = committed_prob

    def compare(a, b):
        ci = paired_auc_diff(y_test, test_probs[a], test_probs[b])
        rec = {'test_auc_diff_95ci': ci,
               'test_auc_diff_point': round(float(results.get(b, {}).get('test', {}).get('roc_auc', 0)
                                                  - results.get(a, {}).get('test', {}).get('roc_auc', 0)), 4)
               if a in results and b in results else None}
        if a in results and b in results:
            rec['cv_auc_gain'] = round(results[b]['cv_auc_mean'] - results[a]['cv_auc_mean'], 4)
            rec['meets_improvement_rule'] = bool(rec['cv_auc_gain'] > results[a]['cv_auc_std'] and ci[0] > 0)
            rec['no_worse_than_reference'] = bool(ci[0] <= 0 <= ci[1] or ci[0] > 0)
        return rec

    comparisons = {
        'A_mono vs A (constraints on production recipe)':
            compare('A_baseline_smote_xgb', 'A_mono_baseline_smote_xgb'),
        'F_mono vs F (constraints on CHURN-17 regularised recipe)':
            compare('F_regularised_xgb', 'F_mono_regularised_xgb'),
        'F_mono vs A (constrained regularised vs production recipe)':
            compare('A_baseline_smote_xgb', 'F_mono_regularised_xgb'),
        'F vs A (CHURN-17 result, re-measured)':
            compare('A_baseline_smote_xgb', 'F_regularised_xgb'),
        'F_mono vs committed artifact':
            compare('committed_production_artifact', 'F_mono_regularised_xgb'),
        'A_mono vs committed artifact':
            compare('committed_production_artifact', 'A_mono_baseline_smote_xgb'),
    }

    # Robustness: 10 fresh stratified splits (seeds 1-10), as in the CHURN-17
    # follow-up audit — does the constraint cost AUC on other splits?
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    robustness = []
    for seed in range(1, 11):
        Xa, Xb, ya, yb = train_test_split(X.astype(float), y, test_size=pipeline.TEST_SIZE,
                                          random_state=seed, stratify=y)
        aucs = {}
        for name, mc in (('F', None), ('F_mono', mono)):
            extra = {} if mc is None else {'monotone_constraints': mc}
            m = xgb(**reg_overrides, **extra).fit(Xa, ya)
            aucs[name] = float(roc_auc_score(yb, m.predict_proba(Xb)[:, 1]))
        robustness.append({'split_seed': seed, 'F_auc': round(aucs['F'], 4),
                           'F_mono_auc': round(aucs['F_mono'], 4),
                           'diff': round(aucs['F_mono'] - aucs['F'], 4)})
    diffs = np.array([r['diff'] for r in robustness])
    robustness_summary = {
        'splits': robustness,
        'mean_diff_F_mono_minus_F': round(float(diffs.mean()), 4),
        'sd_diff': round(float(diffs.std(ddof=1)), 4),
        'min_diff': round(float(diffs.min()), 4), 'max_diff': round(float(diffs.max()), 4),
        'F_mono_better_or_equal_on': int((diffs >= 0).sum()),
    }

    raw_test = base.loc[X_test.index].copy()
    behaviour = {'committed_production_artifact': whatif_behaviour(committed, raw_test, feature_names,
                                                                   X_test.dtypes)}
    for name, (est, dtypes) in fitted.items():
        behaviour[name] = whatif_behaviour(est, raw_test, feature_names, dtypes)

    out = {
        'protocol': {
            'split': '80/20 stratified, random_state=42 (same as pipeline and model_experiments.py)',
            'selection': '5-fold stratified CV on training split only, SMOTE inside folds where used',
            'test_usage': 'one evaluation per candidate',
            'paired_bootstrap': '1,000 resamples of the 1,000 test customers, seed 42',
            'improvement_rule': 'CV AUC gain > reference CV std AND paired 95% CI of test AUC '
                                'difference > 0',
            'whatif_population': f'{len(raw_test)} held-out test customers',
            'wrong_step_thresholds': {'any': EPS, 'material': MATERIAL},
        },
        'expected_directions': {'whatif_inputs': WHATIF_DIRECTIONS,
                                'engineered_features': ENGINEERED_DIRECTIONS,
                                'source': 'churniq_ml_pipeline.generate_dataset churn_score terms'},
        'monotone_constraints_vector': dict(zip(X.columns, mono)),
        'committed_production_artifact': {'test': test_metrics(y_test, committed_prob)},
        'candidates': results,
        'comparisons': comparisons,
        'robustness_10_splits': robustness_summary,
        'whatif_behaviour': behaviour,
    }
    if write:
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'monotonic_experiments.json'), 'w') as f:
            json.dump(out, f, indent=2)
    return out


if __name__ == '__main__':
    res = run()
    print(json.dumps({k: res[k] for k in ('committed_production_artifact', 'candidates', 'comparisons')},
                     indent=2))
