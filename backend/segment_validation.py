# =============================================================================
#   ChurnIQ Pro — Segment-level validation of the production model (CHURN-56)
# =============================================================================
#   How well does the COMMITTED production model (churniq_model.pkl,
#   config 'regularised_monotonic', CHURN-45/57) perform for each customer
#   group, and do the API risk tiers (churniq_core.RISK_MEDIUM / RISK_HIGH)
#   behave the same way in every group?
#
#   Data: only the 1,000 genuine held-out test customers, rebuilt with
#   evaluate_model.rebuild_split (80/20 stratified split, random_state=42).
#   Nothing is retrained and no committed artifact is modified.
#
#   Groups: plan_type, device_type and a provisional tenure banding.
#   Per group: counts, actual churn rate, mean predicted probability,
#   ROC-AUC (with bootstrap 95% CI), accuracy, precision, recall and F1 at
#   threshold 0.5, the calibration gap, and the risk-tier breakdown.
#
#   Only aggregates are written. No customer id, name or email is output.
#   Results → docs/ml/results/segment_validation.json
#
#   RUN (from backend/):   python segment_validation.py      (~10 s)
# =============================================================================
import json
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

import churniq_core as core
import evaluate_model as ev

warnings.filterwarnings('ignore')

# ── Configuration (PROVISIONAL — not team-approved; see docs/ml/08) ──────────
# Tenure bands in months, inclusive. Upper bound None = open-ended.
TENURE_BANDS = [
    ('0-5 months', 0, 5),
    ('6-24 months', 6, 24),
    ('25+ months', 25, None),
]
# A group is "insufficient for reliable measurement" if it has fewer than
# MIN_GROUP_SIZE customers, or fewer than MIN_CLASS_COUNT churned or retained.
MIN_GROUP_SIZE = 100
MIN_CLASS_COUNT = 30

THRESHOLD = 0.5            # classification threshold for precision/recall/F1
N_BOOTSTRAP = 1000
SEED = 42

PLAN_LEVELS = list(core.PLAN_ORDER)                       # Basic, Standard, Premium
DEVICE_LEVELS = list(core.CATEGORY_LEVELS['device_type'])  # Laptop, Mobile, Smart TV, Tablet
RISK_TIERS = ['LOW', 'MEDIUM', 'HIGH']

# Overall model baseline on the same held-out split (backend/model_metadata.json)
BASELINE_KEYS = ('roc_auc', 'accuracy', 'precision', 'recall', 'f1')


def tenure_band(months: float, bands=TENURE_BANDS) -> str:
    """Label for a tenure value. Raises if it falls outside every band."""
    for label, lo, hi in bands:
        if months >= lo and (hi is None or months <= hi):
            return label
    raise ValueError(f'tenure {months} is not covered by any tenure band')


def reliability(n: int, churned: int, retained: int,
                min_size: int = MIN_GROUP_SIZE, min_class: int = MIN_CLASS_COUNT) -> dict:
    reasons = []
    if n < min_size:
        reasons.append(f'fewer than {min_size} customers ({n})')
    if churned < min_class:
        reasons.append(f'fewer than {min_class} churned customers ({churned})')
    if retained < min_class:
        reasons.append(f'fewer than {min_class} retained customers ({retained})')
    return {'sufficient': not reasons, 'reasons': reasons}


def _r(v, nd=4):
    return None if v is None else round(float(v), nd)


def _bootstrap(y: np.ndarray, p: np.ndarray, seed: int = SEED, n: int = N_BOOTSTRAP) -> dict:
    """Percentile 95% CIs for ROC-AUC and the calibration gap (mean pred − actual rate)."""
    rng = np.random.default_rng(seed)
    aucs, gaps = [], []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        gaps.append(p[i].mean() - y[i].mean())
        if y[i].min() != y[i].max():
            aucs.append(roc_auc_score(y[i], p[i]))
    ci = lambda v: [_r(np.percentile(v, 2.5)), _r(np.percentile(v, 97.5))] if v else None
    return {'roc_auc_95ci': ci(aucs), 'calibration_gap_95ci': ci(gaps)}


def risk_breakdown(y: np.ndarray, p: np.ndarray) -> dict:
    tiers = np.array([core.get_risk_level(v) for v in p])
    out = {}
    for t in RISK_TIERS:
        m = tiers == t
        k = int(m.sum())
        out[t] = {'customers': k,
                  'share': _r(k / len(y)) if len(y) else None,
                  'actual_churn_rate': _r(y[m].mean()) if k else None,
                  'mean_predicted': _r(p[m].mean()) if k else None}
    return out


def group_metrics(y, p, threshold: float = THRESHOLD, min_size: int = MIN_GROUP_SIZE,
                  min_class: int = MIN_CLASS_COUNT, bootstrap: bool = True) -> dict:
    """All metrics for one group. Metrics that are undefined are None, with a reason."""
    y, p = np.asarray(y).astype(int), np.asarray(p, dtype=float)
    n, churned = int(len(y)), int(y.sum())
    retained = n - churned
    pred = (p >= threshold).astype(int)
    not_calculable = {}

    if n == 0:
        raise ValueError('empty group')
    if churned == 0 or retained == 0:
        auc = None
        not_calculable['roc_auc'] = ('only one class present '
                                     f'({"all churned" if retained == 0 else "no churners"}); '
                                     'ROC-AUC needs both churned and retained customers')
    else:
        auc = roc_auc_score(y, p)
    if pred.sum() == 0:
        precision = None
        not_calculable['precision'] = 'no customer predicted to churn at the threshold'
    else:
        precision = precision_score(y, pred, zero_division=0)
    if churned == 0:
        recall = None
        not_calculable['recall'] = 'no actual churners in the group'
    else:
        recall = recall_score(y, pred, zero_division=0)
    if precision is None or recall is None:
        f1 = None
        not_calculable['f1'] = 'precision or recall is undefined'
    else:
        f1 = f1_score(y, pred, zero_division=0)

    actual = y.mean()
    mean_pred = p.mean()
    out = {
        'customers': n, 'retained': retained, 'churned': churned,
        'actual_churn_rate': _r(actual),
        'mean_predicted_probability': _r(mean_pred),
        'calibration_gap': _r(mean_pred - actual),
        'roc_auc': _r(auc), 'accuracy': _r(accuracy_score(y, pred)),
        'precision': _r(precision), 'recall': _r(recall), 'f1': _r(f1),
        'predicted_churners': int(pred.sum()),
        'not_calculable': not_calculable,
        'reliability': reliability(n, churned, retained, min_size, min_class),
        'risk_tiers': risk_breakdown(y, p),
    }
    if bootstrap:
        out.update(_bootstrap(y, p) if auc is not None else
                   {'roc_auc_95ci': None, 'calibration_gap_95ci': None})
    return out


def compare_with_baseline(g: dict, baseline: dict) -> dict:
    diff = {k: (_r(g[k] - baseline[k]) if g[k] is not None else None) for k in BASELINE_KEYS}
    ci = g.get('roc_auc_95ci')
    gap_ci = g.get('calibration_gap_95ci')
    return {
        'difference_vs_baseline': diff,
        # Statistical, not an invented margin: the whole bootstrap CI of the
        # group's ROC-AUC lies below the overall model's ROC-AUC.
        'roc_auc_clearly_below_baseline': bool(ci is not None and ci[1] < baseline['roc_auc']),
        'roc_auc_clearly_above_baseline': bool(ci is not None and ci[0] > baseline['roc_auc']),
        # Mean prediction differs from the actual churn rate beyond resampling noise.
        'miscalibrated': bool(gap_ci is not None and (gap_ci[0] > 0 or gap_ci[1] < 0)),
    }


def held_out(model=None, dataset=None):
    """(raw test rows, y_test, production probabilities, X_test) for the genuine held-out split."""
    if model is None or dataset is None:
        model, _, dataset, _ = ev.load_artifacts()
    base, _, _, _, X_test, _, y_test = ev.rebuild_split(dataset)
    prob = model.predict_proba(X_test)[:, 1]
    rows = base.loc[X_test.index, ['plan_type', 'device_type', 'tenure_months']].copy()
    return rows, y_test, prob, X_test


def run(write: bool = True, tenure_bands=TENURE_BANDS, min_size: int = MIN_GROUP_SIZE,
        min_class: int = MIN_CLASS_COUNT) -> dict:
    model, feature_names, dataset, predictions = ev.load_artifacts()
    rows, y_test, prob, X_test = held_out(model, dataset)
    y = y_test.values

    # Sanity: the split and the probabilities are exactly the served holdout predictions
    stored = predictions.set_index('customer_id')
    holdout_ids = set(stored.index[stored['prediction_source'] == 'holdout_test'])
    test_ids = dataset.loc[X_test.index, 'customer_id']
    split_ok = set(test_ids) == holdout_ids and len(test_ids) == 1000
    max_diff = float(np.abs(prob - stored.loc[test_ids, 'churn_prob'].values).max())

    with open(ev._path('model_metadata.json')) as f:
        meta = json.load(f)

    overall = group_metrics(y, prob, min_size=min_size, min_class=min_class)
    baseline = {k: overall[k] for k in BASELINE_KEYS}

    rows = rows.assign(tenure_band=rows['tenure_months'].map(lambda m: tenure_band(m, tenure_bands)))
    dims = {
        'plan_type': ('plan_type', PLAN_LEVELS),
        'device_type': ('device_type', DEVICE_LEVELS),
        'tenure_band': ('tenure_band', [b[0] for b in tenure_bands]),
    }
    segments = {}
    for dim, (col, levels) in dims.items():
        segments[dim] = {}
        for level in levels:
            m = (rows[col] == level).values
            if not m.any():
                segments[dim][level] = {'customers': 0, 'note': 'no held-out customers in this group'}
                continue
            g = group_metrics(y[m], prob[m], min_size=min_size, min_class=min_class)
            g['comparison'] = compare_with_baseline(g, baseline)
            segments[dim][level] = g

    flagged = {
        'roc_auc_clearly_below_baseline': [f'{d}={k}' for d, gs in segments.items() for k, g in gs.items()
                                           if g.get('comparison', {}).get('roc_auc_clearly_below_baseline')],
        'miscalibrated': [f'{d}={k}' for d, gs in segments.items() for k, g in gs.items()
                          if g.get('comparison', {}).get('miscalibrated')],
        'insufficient_for_reliable_measurement': [
            f'{d}={k}' for d, gs in segments.items() for k, g in gs.items()
            if g.get('customers', 0) and not g['reliability']['sufficient']],
    }

    results = {
        'artifact': {'file': 'backend/churniq_model.pkl (committed, not retrained)',
                     'model_config': meta['model_config'], 'seed': meta['seed']},
        'data': {'population': 'held-out test split only (never seen in training)',
                 'split': '80/20 stratified, random_state=42 (evaluate_model.rebuild_split)',
                 'customers': int(len(y)), 'churned': int(y.sum()), 'retained': int(len(y) - y.sum())},
        'sanity_checks': {
            'split_matches_holdout_test_rows_in_customer_predictions_csv': bool(split_ok),
            'max_abs_diff_vs_stored_churn_prob': round(max_diff, 6),
            'overall_metrics_match_model_metadata': all(
                abs(baseline[k] - meta['test_metrics'][k]) < 5e-4 for k in BASELINE_KEYS),
            'feature_set_excludes_leakage_and_identifier_columns': not (
                set(feature_names) & set(core.LEAKAGE_COLS + core.ID_COLS + [core.TARGET_COL])),
        },
        'settings': {
            'threshold': THRESHOLD,
            'risk_tiers': {'LOW': f'< {core.RISK_MEDIUM}', 'MEDIUM': f'>= {core.RISK_MEDIUM} and < {core.RISK_HIGH}',
                           'HIGH': f'>= {core.RISK_HIGH}', 'source': 'churniq_core.RISK_MEDIUM / RISK_HIGH'},
            'tenure_bands_months': [{'label': l, 'min': lo, 'max': hi} for l, lo, hi in tenure_bands],
            'min_group_size': min_size, 'min_class_count': min_class,
            'bootstrap': {'resamples': N_BOOTSTRAP, 'seed': SEED, 'interval': 'percentile 95%'},
            'status': 'PROVISIONAL: tenure bands and reliability minimums are not team-approved',
            'weak_segment_rule': 'bootstrap 95% CI of segment ROC-AUC entirely below the overall ROC-AUC',
            'miscalibration_rule': 'bootstrap 95% CI of (mean predicted − actual churn rate) excludes 0',
        },
        'overall': overall,
        'segments': segments,
        'flagged': flagged,
    }
    if write:
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'segment_validation.json'), 'w') as f:
            json.dump(results, f, indent=2)
    return results


if __name__ == '__main__':
    r = run()
    print('Sanity checks:', json.dumps(r['sanity_checks']))
    print(f"\nOverall (n={r['overall']['customers']}): " +
          ', '.join(f"{k} {r['overall'][k]}" for k in BASELINE_KEYS))
    hdr = f"{'segment':<26}{'n':>5}{'churn%':>8}{'pred%':>7}{'AUC':>7}  {'AUC 95% CI':<16}{'prec':>6}{'rec':>6}{'F1':>6}  flags"
    print('\n' + hdr)
    for dim, groups in r['segments'].items():
        for level, g in groups.items():
            if not g.get('customers'):
                print(f"{dim + '=' + level:<26}{0:>5}  (no customers)")
                continue
            c = g['comparison']
            flags = [f for f, on in (('AUC↓', c['roc_auc_clearly_below_baseline']),
                                     ('AUC↑', c['roc_auc_clearly_above_baseline']),
                                     ('miscal', c['miscalibrated']),
                                     ('small', not g['reliability']['sufficient'])) if on]
            fmt = lambda v: '—' if v is None else f'{v:.3f}'
            print(f"{dim + '=' + level:<26}{g['customers']:>5}{g['actual_churn_rate']*100:>7.1f}%"
                  f"{g['mean_predicted_probability']*100:>6.1f}%{fmt(g['roc_auc']):>7}  "
                  f"{str(g['roc_auc_95ci']):<16}{fmt(g['precision']):>6}{fmt(g['recall']):>6}{fmt(g['f1']):>6}  "
                  f"{' '.join(flags)}")
    print('\nFlagged:', json.dumps(r['flagged']))
