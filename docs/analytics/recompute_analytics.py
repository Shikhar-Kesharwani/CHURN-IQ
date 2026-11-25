"""Independent recomputation for CHURN-11 (dashboard numbers) and CHURN-12 (data findings).

Uses pandas/numpy only and deliberately does NOT import backend/main.py, so the
numbers can be compared with the API instead of being produced by it.

    python docs/analytics/recompute_analytics.py > /tmp/recomputed.json

Output contains aggregates only: no customer names, emails or IDs
(except the documented demo id CUST99999 in the quality section).
"""
import json
import os
import subprocess

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATASET = os.path.join(ROOT, 'backend', 'ott_churn_dataset.csv')
PREDICTIONS = os.path.join(ROOT, 'backend', 'customer_predictions.csv')

# Literal copies of the production cut-offs (churniq_core.RISK_MEDIUM / RISK_HIGH
# and get_clv_segment), so a change there would show up as a mismatch here.
RISK_MEDIUM, RISK_HIGH = 0.40, 0.70
CLV_HIGH, CLV_MEDIUM = 8000, 3000
PLAN_PRICE = {'Basic': 199, 'Standard': 499, 'Premium': 799}
CATEGORIES = {
    'plan_type': ['Basic', 'Standard', 'Premium'],
    'device_type': ['Mobile', 'Laptop', 'Smart TV', 'Tablet'],
    'payment_method': ['UPI', 'Credit Card', 'Debit Card', 'Wallet'],
    'preferred_genre': ['Action', 'Drama', 'Comedy', 'Thriller', 'Kids', 'Documentary', 'Romance'],
    'gender': ['Male', 'Female', 'Other'],
    'country': ['India', 'UAE', 'USA', 'UK', 'Singapore', 'Canada'],
    'clv_segment': ['High', 'Medium', 'Low'],
}
NUMERIC_DOMAINS = {  # (min, max or None)
    'age': (0, 120), 'monthly_charge': (0, None), 'tenure_months': (0, None),
    'watch_hours_per_week': (0, 168), 'num_profiles': (1, None), 'logins_last_30_days': (0, None),
    'last_login_days_ago': (0, None), 'payment_failures_3m': (0, None), 'support_tickets': (0, None),
    'clv_score': (0, None), 'churn_probability': (0, 1),
}


def blob_sha(path):
    return subprocess.check_output(['git', '-C', ROOT, 'hash-object', path]).decode().strip()


def pct(x):
    return round(float(x) * 100, 1)


def main():
    d, p = pd.read_csv(DATASET), pd.read_csv(PREDICTIONS)
    f = d.merge(p[['customer_id', 'churn_prob', 'risk_level', 'clv_score', 'prediction_source']],
                on='customer_id', how='left', suffixes=('_raw', ''))
    tier = np.where(f.churn_prob >= RISK_HIGH, 'HIGH', np.where(f.churn_prob >= RISK_MEDIUM, 'MEDIUM', 'LOW'))
    clv_tier = np.where(f.clv_score > CLV_HIGH, 'High', np.where(f.clv_score > CLV_MEDIUM, 'Medium', 'Low'))
    f['tenure_bucket'] = pd.cut(f.tenure_months, [0, 3, 6, 12, 24, 72],
                                labels=['0-3m', '3-6m', '6-12m', '1-2yr', '2yr+']).astype(str)

    def predicted(col):
        g = f.groupby(col).churn_prob.agg(['mean', 'size'])
        return {k: {'predicted_rate_pct': pct(v['mean']), 'customers': int(v['size'])} for k, v in g.iterrows()}

    plan_clv = f.groupby('plan_type').clv_score.agg(['mean', 'size'])
    dashboard = {
        'dataset': {'rows': len(d), 'columns': d.shape[1], 'git_blob_sha': blob_sha(DATASET)},
        'predictions': {'rows': len(p), 'git_blob_sha': blob_sha(PREDICTIONS),
                        'prediction_source': p.prediction_source.value_counts().to_dict()},
        'join': {'matched': int(d.customer_id.isin(p.customer_id).sum()),
                 'scored': int(f.churn_prob.notna().sum()), 'unscored': int(f.churn_prob.isna().sum())},
        'risk_counts_from_probability': pd.Series(tier).value_counts().to_dict(),
        'risk_counts_stored_risk_level': f.risk_level.value_counts().to_dict(),
        'high_risk_pct': pct((tier == 'HIGH').mean()),
        'avg_churn_prob': round(float(f.churn_prob.mean()), 4),
        'revenue_at_risk_monthly': round(float((f.monthly_charge * f.churn_prob).sum()), 2),
        'model_clv_mean': round(float(f.clv_score.mean()), 2),
        'dashboard_avg_clv_weighted_from_rounded_plan_means': round(float(
            (plan_clv['mean'].round(0) * plan_clv['size']).sum() / plan_clv['size'].sum()), 2),
        'model_clv_tiers': pd.Series(clv_tier).value_counts().to_dict(),
        'generator_clv_segment_not_used_by_dashboard': d.clv_segment.value_counts().to_dict(),
        'high_risk_and_high_model_clv': int(((tier == 'HIGH') & (clv_tier == 'High')).sum()),
        'churn_signals': {
            'low_engagement_watch_lt_3h': int((f.watch_hours_per_week < 3).sum()),
            'payment_issues_failures_gt_0': int((f.payment_failures_3m > 0).sum()),
            'new_customers_tenure_lt_6m': int((f.tenure_months < 6).sum()),
            'support_issues_tickets_gt_1': int((f.support_tickets > 1).sum()),
        },
        'predicted_rate_segments': {c: predicted(c) for c in
                                    ['plan_type', 'device_type', 'tenure_bucket', 'preferred_genre']},
    }

    invalid = {c: int(((d[c] < lo) | ((d[c] > hi) if hi is not None else False)).sum())
               for c, (lo, hi) in NUMERIC_DOMAINS.items()}
    invalid.update({c: int((~d[c].isin(v)).sum()) for c, v in CATEGORIES.items()})
    quality = {
        'missing_values': int(d.isna().sum().sum()),
        'duplicate_customer_id': int(d.customer_id.duplicated().sum()),
        'duplicate_full_rows': int(d.duplicated().sum()),
        'invalid_values_by_column': invalid,
        'invalid_values_total': int(sum(invalid.values())),
        'plan_price_mismatches': int((d.plan_type.map(PLAN_PRICE) != d.monthly_charge).sum()),
        'non_binary_churn': int((~d.churn.isin([0, 1])).sum()),
        'churn_probability_outside_0_1': int(((d.churn_probability < 0) | (d.churn_probability > 1)).sum()),
        'duplicate_names': int(d.name.duplicated().sum()),
        'duplicate_emails': int(d.email.duplicated().sum()),
    }

    def observed(mask):
        return {'observed_churn_pct': pct(d.churn[mask].mean()), 'customers': int(mask.sum())}

    findings = {
        'overall': {'churned': int(d.churn.sum()), 'customers': len(d), 'observed_churn_pct': pct(d.churn.mean())},
        'plan_type': {k: observed(d.plan_type == k) for k in CATEGORIES['plan_type']},
        'device_type': {k: observed(d.device_type == k) for k in CATEGORIES['device_type']},
        'tenure': {'0-5 months': observed(d.tenure_months <= 5),
                   '6-24 months': observed(d.tenure_months.between(6, 24)),
                   '25+ months': observed(d.tenure_months >= 25)},
        'watch_hours_per_week': {'<2': observed(d.watch_hours_per_week < 2),
                                 '2 to <5': observed(d.watch_hours_per_week.between(2, 5, inclusive='left')),
                                 '5+': observed(d.watch_hours_per_week >= 5)},
        'payment_failures_3m': {int(k): observed(d.payment_failures_3m == k) for k in sorted(d.payment_failures_3m.unique())},
        'support_tickets': {int(k): observed(d.support_tickets == k) for k in sorted(d.support_tickets.unique())},
    }
    print(json.dumps({'dashboard': dashboard, 'quality': quality, 'observed_findings': findings}, indent=1))


if __name__ == '__main__':
    main()
