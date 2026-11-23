# =============================================================================
#   ChurnIQ Pro — SHAP Explanation Validation (CHURN-15)
# =============================================================================
#   Validates the SHAP integration against the COMMITTED model on the exact
#   test split, and writes docs/ml/results/shap_validation.json.
#
#   RUN (from backend/):   python validate_shap.py
#
#   Checks:
#     1. Feature alignment: model ⇄ feature_names.pkl ⇄ encoded matrix
#     2. Additivity: expected_value + Σ SHAP == model log-odds margin
#        and sigmoid(margin) == predict_proba (explanations match predictions)
#     3. Stored top-3 reasons in customer_predictions.csv == recomputed SHAP
#     4. Global importance (mean |SHAP|) and plausibility against the known
#        data-generating features in churniq_ml_pipeline.generate_dataset()
#     5. Worked examples: 2 customers per risk level (6 customers)
# =============================================================================

import json
import os
import warnings

import numpy as np
import pandas as pd

import churniq_core as core
import evaluate_model as ev

warnings.filterwarnings('ignore')

# Features that actually drive churn in generate_dataset() (directly or as an
# engineered transform of a driver). plan_type / monthly_charge / device_type_Mobile
# matter only through the Basic + Mobile interaction.
GENERATOR_DRIVERS = {
    'watch_hours_per_week', 'logins_last_30_days', 'last_login_days_ago',
    'payment_failures_3m', 'support_tickets', 'tenure_months',
    'engagement_score', 'friction_score', 'inactivity_flag', 'is_new_customer',
    'plan_type', 'monthly_charge', 'device_type_Mobile',
}


def compute(model, X_test):
    import shap
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)
    expected = float(np.ravel(explainer.expected_value)[0])
    return explainer, shap_values, expected


def run(write=True):
    model, feature_names, dataset, predictions = ev.load_artifacts()
    base, X, y, X_train, X_test, y_train, y_test = ev.rebuild_split(dataset)
    _, sv, expected = compute(model, X_test)
    margin = model.predict(X_test, output_margin=True)
    prob = model.predict_proba(X_test)[:, 1]
    ids = base.loc[X_test.index, 'customer_id'].values
    cols = list(X_test.columns)

    # 1. Alignment
    alignment = {
        'n_features': len(feature_names),
        'model_booster_names_equal_feature_names_pkl':
            list(model.get_booster().feature_names) == list(feature_names),
        'encoded_matrix_columns_equal_feature_names_pkl': cols == list(feature_names),
        'shap_matrix_shape': list(sv.shape),
    }

    # 2. Additivity / consistency with predictions
    additivity = {
        'expected_value_log_odds': round(expected, 6),
        'max_abs_error_expected_plus_sum_shap_vs_margin':
            float(np.abs(expected + sv.sum(axis=1) - margin).max()),
        'max_abs_error_sigmoid_margin_vs_predict_proba':
            float(np.abs(1 / (1 + np.exp(-margin)) - prob).max()),
        'units': 'log-odds (margin); sigmoid(expected + sum(shap)) = churn probability',
    }

    # 3. Stored reasons vs recomputed
    stored = predictions.fillna({f'top_reason_{k}': 'N/A' for k in (1, 2, 3)}).set_index('customer_id')
    matches, mismatches = 0, []
    for i, cid in enumerate(ids):
        rec = core.get_top_shap_reasons(sv[i], cols)
        rec += ['N/A'] * (3 - len(rec))
        got = [stored.loc[cid, f'top_reason_{k}'] for k in (1, 2, 3)]
        if rec == got:
            matches += 1
        else:
            mismatches.append(cid)
    reasons_check = {'customers': len(ids), 'match': matches, 'mismatched_ids': mismatches[:20],
                     'note': "customer_predictions.csv stores 'N/A'; pandas reads it as NaN "
                             "(compare after fillna('N/A'))."}

    # 3b. Out-of-fold and demo rows (CHURN-37): each row's SHAP must come from
    # the model that produced its probability — the fold model / committed model.
    by_source = {'holdout_test': {'customers': len(ids), 'reasons_match': matches,
                                  'max_additivity_error': additivity[
                                      'max_abs_error_expected_plus_sum_shap_vs_margin']}}
    if 'prediction_source' in predictions.columns:
        import pickle
        with open(ev._path('oof_fold_models.pkl'), 'rb') as f:
            fold_models = pickle.load(f)['models']
        full_X = core.encode_features(dataset, feature_names)
        full_X.index = dataset['customer_id'].values

        def check(model_, cids):
            Xc = full_X.loc[cids]
            exp_, sv_ = compute(model_, Xc)[1:][::-1]
            marg = model_.predict(Xc, output_margin=True)
            p_ = model_.predict_proba(Xc)[:, 1]
            ok = 0
            for j, cid in enumerate(cids):
                rec = core.get_top_shap_reasons(sv_[j], list(feature_names))
                rec += ['N/A'] * (3 - len(rec))
                ok += rec == [stored.loc[cid, f'top_reason_{k}'] for k in (1, 2, 3)]
            return (ok, float(np.abs(exp_ + sv_.sum(axis=1) - marg).max()),
                    float(np.abs(np.round(p_, 4) - stored.loc[cids, 'churn_prob'].values).max()))

        oof = stored[stored['prediction_source'] == 'cv_out_of_fold']
        tot_ok, worst_add, worst_p = 0, 0.0, 0.0
        for fold, grp in oof.groupby('fold'):
            ok, add_err, p_err = check(fold_models[int(fold)], list(grp.index))
            tot_ok += ok
            worst_add, worst_p = max(worst_add, add_err), max(worst_p, p_err)
        by_source['cv_out_of_fold'] = {'customers': int(len(oof)), 'reasons_match': int(tot_ok),
                                       'max_additivity_error': worst_add,
                                       'max_prob_diff_vs_csv': worst_p}
        demo_ids = list(stored[stored['prediction_source'] == 'demo'].index)
        if demo_ids:
            ok, add_err, p_err = check(model, demo_ids)
            by_source['demo'] = {'customers': len(demo_ids), 'reasons_match': int(ok),
                                 'max_additivity_error': add_err, 'max_prob_diff_vs_csv': p_err}
    reasons_check['by_source'] = by_source

    # 4. Global importance + plausibility
    imp = pd.Series(np.abs(sv).mean(axis=0), index=cols).sort_values(ascending=False)
    total = float(imp.sum())
    noise = [f for f in cols if f not in GENERATOR_DRIVERS]
    reason_feats = []
    for cid in ids:
        for k in (1, 2, 3):
            r = stored.loc[cid, f'top_reason_{k}']
            if r != 'N/A':
                reason_feats.append((k, r.split(' (impact')[0]))
    rf = pd.DataFrame(reason_feats, columns=['rank', 'feature'])
    rf['noise'] = ~rf['feature'].isin(GENERATOR_DRIVERS)
    plausibility = {
        'top10_mean_abs_shap': [{'feature': f, 'mean_abs_shap': round(float(v), 4),
                                 'generator_driver': f in GENERATOR_DRIVERS}
                                for f, v in imp.head(10).items()],
        'share_of_mean_abs_shap_on_non_driver_features': round(float(imp[noise].sum()) / total, 4),
        'displayed_reasons_total': int(len(rf)),
        'displayed_reasons_citing_non_driver_features': int(rf['noise'].sum()),
        'customers_whose_top_reason_is_non_driver': int(rf[(rf['rank'] == 1) & rf['noise']].shape[0]),
    }

    # 5. Worked examples: 2 per risk level (highest-probability first in each)
    risk = np.array([core.get_risk_level(p) for p in prob])
    examples = []
    for lvl in ['HIGH', 'MEDIUM', 'LOW']:
        idxs = np.where(risk == lvl)[0]
        idxs = idxs[np.argsort(-prob[idxs])]
        for i in [idxs[0], idxs[len(idxs) // 2]]:
            top = np.argsort(-np.abs(sv[i]))[:4]
            examples.append({
                'customer_id': ids[i], 'risk_level': lvl, 'actual_churn': int(y_test.iloc[i]),
                'churn_prob': round(float(prob[i]), 4),
                'expected_plus_sum_shap': round(expected + float(sv[i].sum()), 4),
                'margin': round(float(margin[i]), 4),
                'top_contributions': [{'feature': cols[j],
                                       'value': float(X_test.iloc[i, j]),
                                       'shap': round(float(sv[i, j]), 4)} for j in top],
                'stored_reasons': [stored.loc[ids[i], f'top_reason_{k}'] for k in (1, 2, 3)],
            })

    results = {'alignment': alignment, 'additivity': additivity,
               'stored_reasons_vs_recomputed': reasons_check,
               'global_importance_plausibility': plausibility,
               'mean_abs_shap_all_features': {f: round(float(v), 4) for f, v in imp.items()},
               'examples': examples}
    if write:
        os.makedirs(ev.RESULTS_DIR, exist_ok=True)
        with open(os.path.join(ev.RESULTS_DIR, 'shap_validation.json'), 'w') as f:
            json.dump(results, f, indent=2)
    return results


if __name__ == '__main__':
    r = run()
    print(json.dumps({k: r[k] for k in ('alignment', 'additivity', 'global_importance_plausibility')},
                     indent=2))
    print(f"stored reasons match: {r['stored_reasons_vs_recomputed']['match']}"
          f"/{r['stored_reasons_vs_recomputed']['customers']}")
