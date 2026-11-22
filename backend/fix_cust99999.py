"""
Add / refresh the CUST99999 demo customer row in customer_predictions.csv.

Bug B (CHURN-16 audit): this script used to write hand-typed values —
churn_prob 0.96, CLV ₹500 and "SHAP" reasons copied from an illustrative
comment. It now computes every value from the trained model:
  - churn_prob  = model.predict_proba on the shared feature encoding
  - risk_level  = churniq_core.get_risk_level
  - top reasons = real SHAP TreeExplainer values
  - clv_score   = churniq_core.calc_clv (verified formula)

main.py also scores demo customers live at startup, so the API is correct even
if this script has not been re-run.

Run from backend/ (after add_emails.py):   python fix_cust99999.py
"""
import pickle

import pandas as pd
import shap

import churniq_core as core

DEMO_ID = 'CUST99999'

with open('churniq_model.pkl', 'rb') as f:
    model = pickle.load(f)
with open('feature_names.pkl', 'rb') as f:
    feature_names = pickle.load(f)

dataset = pd.read_csv('ott_churn_dataset.csv')
demo = dataset[dataset['customer_id'] == DEMO_ID]
if demo.empty:
    raise SystemExit(f'{DEMO_ID} not found in ott_churn_dataset.csv — run add_emails.py first.')

X = core.encode_features(demo, feature_names)
prob = float(model.predict_proba(X)[0][1])
reasons = core.get_top_shap_reasons(shap.TreeExplainer(model).shap_values(X)[0], list(feature_names))
reasons += ['N/A'] * (3 - len(reasons))
row = demo.iloc[0]

new_row = {
    'customer_id':  DEMO_ID,
    'churn_prob':   round(prob, 4),
    'risk_level':   core.get_risk_level(prob),
    'top_reason_1': reasons[0],
    'top_reason_2': reasons[1],
    'top_reason_3': reasons[2],
    'clv_score':    core.calc_clv(row['monthly_charge'], row['tenure_months'], prob),
    'actual_churn': int(row['churn']),
}

pred = pd.read_csv('customer_predictions.csv')
pred = pred[pred['customer_id'] != DEMO_ID]
pred = pd.concat([pred, pd.DataFrame([new_row])], ignore_index=True)
pred.to_csv('customer_predictions.csv', index=False)
print(f'Done! {DEMO_ID} scored by the model: {new_row}')
