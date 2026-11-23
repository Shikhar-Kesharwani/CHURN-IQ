# =============================================================================
#   ChurnIQ Pro — Reproducible Model Evaluation (CHURN-14)
# =============================================================================
#   Evaluates the COMMITTED production artifact (churniq_model.pkl) on the
#   exact held-out test split used by churniq_ml_pipeline.py.
#
#   The script does not retrain anything and does not modify any committed
#   file. Results are written to docs/ml/results/evaluation_results.json.
#
#   RUN (from backend/):
#     python evaluate_model.py
#
#   What it reports:
#     - Class distribution (full / train / SMOTE-train / test)
#     - Accuracy, Precision, Recall, F1, ROC-AUC + bootstrap 95% CIs
#     - Confusion matrix and classification report (threshold 0.5)
#     - Reference points: majority-class baseline and the "oracle" ceiling
#       (the generator's true churn probability, which no model can beat)
#     - Threshold sweep, calibration (Brier score, mean predicted vs actual)
#     - Observed churn rate per risk level (HIGH / MEDIUM / LOW)
#     - Sanity checks: split reproduces customer_predictions.csv, and the
#       artifact reproduces the stored probabilities
# =============================================================================

import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

import churniq_core as core
import churniq_ml_pipeline as pipeline

warnings.filterwarnings('ignore')

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BACKEND_DIR, '..', 'docs', 'ml', 'results')
N_BOOTSTRAP = 1000


def _path(name):
    return os.path.join(BACKEND_DIR, name)


def load_artifacts():
    with open(_path('churniq_model.pkl'), 'rb') as f:
        model = pickle.load(f)
    with open(_path('feature_names.pkl'), 'rb') as f:
        feature_names = pickle.load(f)
    dataset = pd.read_csv(_path('ott_churn_dataset.csv'))
    predictions = pd.read_csv(_path('customer_predictions.csv'))
    return model, feature_names, dataset, predictions


def rebuild_split(dataset: pd.DataFrame):
    """Rebuild the pipeline's exact train/test split from the committed dataset."""
    base = dataset[~dataset['customer_id'].isin(pipeline.DEMO_CUSTOMER_IDS)].copy()
    X, y = pipeline.preprocess(base)
    X_train, X_test, y_train, y_test = pipeline.split_data(X, y)
    return base, X, y, X_train, X_test, y_train, y_test


def metrics_at(y_true, prob, threshold=0.5):
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    pred = (prob >= threshold).astype(int)
    return {
        'threshold': threshold,
        'accuracy':  float(accuracy_score(y_true, pred)),
        'precision': float(precision_score(y_true, pred, zero_division=0)),
        'recall':    float(recall_score(y_true, pred, zero_division=0)),
        'f1':        float(f1_score(y_true, pred, zero_division=0)),
        'flagged':   int(pred.sum()),
    }


def bootstrap_ci(y_true, prob, n=N_BOOTSTRAP, seed=42, threshold=0.5):
    """Percentile 95% CI of each metric over bootstrap resamples of the test set."""
    rng = np.random.default_rng(seed)
    y_true, prob = np.asarray(y_true), np.asarray(prob)
    keys = ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']
    samples = {k: [] for k in keys}
    for _ in range(n):
        idx = rng.integers(0, len(y_true), len(y_true))
        yt, pb = y_true[idx], prob[idx]
        if yt.min() == yt.max():
            continue
        m = metrics_at(yt, pb, threshold)
        m['roc_auc'] = roc_auc_score(yt, pb)
        for k in keys:
            samples[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
            for k, v in samples.items()}


def class_counts(y):
    y = pd.Series(y)
    return {'retained': int((y == 0).sum()), 'churned': int((y == 1).sum()),
            'churn_rate': round(float(y.mean()), 4)}


def run(write=True):
    model, feature_names, dataset, predictions = load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = rebuild_split(dataset)

    # ── Sanity checks ──────────────────────────────────────────────────────
    assert list(X.columns) == list(feature_names), 'feature order mismatch'
    test_ids = base.loc[X_test.index, 'customer_id']
    stored = predictions.set_index('customer_id')
    # Only the held-out test rows are evaluation data (CHURN-37 added
    # out-of-fold rows for training customers and a demo row).
    if 'prediction_source' in stored.columns:
        stored_real = stored[stored['prediction_source'] == 'holdout_test']
    else:
        stored_real = stored.drop(index=[i for i in pipeline.DEMO_CUSTOMER_IDS if i in stored.index])
    split_matches = set(test_ids) == set(stored_real.index)

    prob = model.predict_proba(X_test)[:, 1]
    max_diff = float(np.abs(prob - stored.loc[test_ids, 'churn_prob'].values).max())

    _, y_train_sm = pipeline.apply_smote(X_train, y_train)

    # ── Core metrics at the production threshold (0.5) ─────────────────────
    ev = pipeline.evaluate(model, X_test, y_test)

    # ── Reference points ───────────────────────────────────────────────────
    oracle = base.loc[X_test.index, 'churn_probability'].values   # generator truth
    oracle_metrics = metrics_at(y_test.values, oracle)
    oracle_metrics['roc_auc'] = float(roc_auc_score(y_test, oracle))
    majority = metrics_at(y_test.values, np.zeros(len(y_test)))
    majority['roc_auc'] = 0.5

    # ── Threshold sweep, calibration, risk levels ──────────────────────────
    sweep = [metrics_at(y_test.values, prob, t) for t in np.round(np.arange(0.30, 0.71, 0.05), 2)]
    risk = pd.Series([core.get_risk_level(p) for p in prob], index=X_test.index)
    by_risk = {
        lvl: {'customers': int((risk == lvl).sum()),
              'mean_predicted': round(float(prob[(risk == lvl).values].mean()), 4)
              if (risk == lvl).any() else None,
              'observed_churn_rate': round(float(y_test[risk == lvl].mean()), 4)
              if (risk == lvl).any() else None}
        for lvl in ['HIGH', 'MEDIUM', 'LOW']
    }
    bins = pd.cut(prob, [0, .2, .4, .6, .8, 1.0], include_lowest=True)
    calib = (pd.DataFrame({'bin': bins, 'p': prob, 'y': y_test.values})
             .groupby('bin', observed=True).agg(n=('y', 'size'), mean_pred=('p', 'mean'),
                                                observed=('y', 'mean')).reset_index())
    calib['bin'] = calib['bin'].astype(str)

    results = {
        'artifact': 'backend/churniq_model.pkl (committed, not retrained)',
        'dataset': {
            'file': 'backend/ott_churn_dataset.csv',
            'rows_total': int(len(dataset)),
            'rows_used': int(len(base)),
            'excluded_demo_rows': sorted(pipeline.DEMO_CUSTOMER_IDS & set(dataset['customer_id'])),
            'n_features': int(X.shape[1]),
        },
        'methodology': {
            'split': '80/20 stratified train_test_split, random_state=42',
            'smote': 'training split only (k_neighbors=5, random_state=42)',
            'threshold': 0.5,
            'bootstrap_resamples': N_BOOTSTRAP,
        },
        'class_distribution': {
            'full': class_counts(y), 'train': class_counts(y_train),
            'train_after_smote': class_counts(y_train_sm), 'test': class_counts(y_test),
        },
        'sanity_checks': {
            'split_matches_customer_predictions_csv': bool(split_matches),
            'max_abs_diff_vs_stored_churn_prob': round(max_diff, 6),
        },
        'metrics': {k: round(ev[k], 4) for k in ('accuracy', 'precision', 'recall', 'f1', 'roc_auc')},
        'metrics_95ci': {k: [round(a, 4), round(b, 4)] for k, (a, b) in
                         bootstrap_ci(y_test.values, prob).items()},
        'confusion_matrix': ev['confusion_matrix'],
        'classification_report': {
            k: {m: round(v, 4) for m, v in d.items()} if isinstance(d, dict) else round(d, 4)
            for k, d in ev['classification_report'].items()},
        'reference': {
            'majority_class': {k: round(v, 4) for k, v in majority.items()},
            'oracle_true_probability': {k: round(v, 4) for k, v in oracle_metrics.items()},
        },
        'calibration': {
            'brier_score': round(float(brier_score_loss(y_test, prob)), 4),
            'oracle_brier_score': round(float(brier_score_loss(y_test, oracle)), 4),
            'mean_predicted_probability': round(float(prob.mean()), 4),
            'actual_churn_rate': round(float(y_test.mean()), 4),
            'bins': [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                     for r in calib.to_dict(orient='records')],
        },
        'risk_levels': by_risk,
        'threshold_sweep': [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                            for r in sweep],
    }

    if write:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(os.path.join(RESULTS_DIR, 'evaluation_results.json'), 'w') as f:
            json.dump(results, f, indent=2)
    return results


if __name__ == '__main__':
    r = run()
    print(json.dumps({k: r[k] for k in ('sanity_checks', 'class_distribution', 'metrics',
                                        'metrics_95ci', 'confusion_matrix', 'reference',
                                        'calibration', 'risk_levels')}, indent=2))
    sys.exit(0)
