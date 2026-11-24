# CHURN-15 — SHAP Explanation Validation

> **Model update, 24 Nov 2026 (CHURN-57).** The production model has been replaced by the regularised recipe with monotone constraints (`regularised_monotonic`, [07-monotonic-constraints.md](07-monotonic-constraints.md)). The analysis below describes the **previous** committed model and is kept as the historical record. Its script has been re-run on the new model, and the current figures are in `results/shap_validation.json`: additivity error 2×10⁻⁶; 12.5% of mean |SHAP| on non-driver features (previously 47%); 128 of 1,000 customers have a non-driver top reason (previously 398).

**Reproduce:** `cd backend && python validate_shap.py` (writes `docs/ml/results/shap_validation.json`)
**Tests:** `backend/tests/test_shap_validation.py`

## How SHAP is used

1. The pipeline (Part G) runs `shap.TreeExplainer(model)` on the 1,000 test customers.
2. Part H stores the top 3 **positive** SHAP features per customer in `customer_predictions.csv` as `"feature (impact: +X.XX)"`.
3. `main.py` turns these into plain-English text for `GET /customers`, `GET /customer/{id}` and `GET /retention/{id}`. The `/retention` text also goes into the Gemini prompt.

**Units:** for `XGBClassifier`, SHAP values are in **log-odds**. The expected value is +0.0027, and `sigmoid(expected_value + Σ SHAP)` is the churn probability.

## Validation results

| Check | Result |
|---|---|
| Feature alignment: model booster names = `feature_names.pkl` = encoded matrix columns | ✅ 33 features, same order |
| SHAP matrix shape | ✅ 1000 × 33 |
| Additivity: `expected + Σ SHAP` = model margin | ✅ max error 2.4×10⁻⁶ |
| Consistent with predictions: `sigmoid(margin)` = `predict_proba` | ✅ max error 1.2×10⁻⁷ |
| Stored top-3 reasons = recomputed SHAP | ✅ 1000 / 1000. One customer (`CUST00173`) has only 2 positive features; the CSV stores `N/A`, which pandas reads as NaN, and the API renders it as "No significant risk factor identified". |
| `GET /customer/{id}` reasons match SHAP | ✅ Tested for 20 customers across HIGH, MEDIUM and LOW |

## All customers (after CHURN-37)

Every customer's reasons are now checked against SHAP from **the model that produced its probability** (`python validate_shap.py`, `results/shap_validation.json`):

| Source | Customers | Reasons match recomputed SHAP | Max additivity error |
|---|---|---|---|
| holdout_test (committed model) | 1,000 | 1,000 | 2.4×10⁻⁶ |
| cv_out_of_fold (own fold model) | 4,000 | 4,000 | 3.1×10⁻⁶ |
| demo (committed model) | 1 | 1 | 2.4×10⁻⁶ |

**Display fix:** the Customer Detail page showed impacts as "++0.46", because it added a "+" to a value that already carried its sign. This was pre-existing on `main` and is now fixed.

## Worked examples (2 per risk level)

Values are log-odds contributions; the top 4 by |SHAP| are shown. In every case `expected + Σ SHAP` equals the model margin exactly.

| Customer | Risk | Actual | Prob | Top contributions (feature = value → SHAP) |
|---|---|---|---|---|
| CUST01033 | HIGH | churned | 0.996 | friction_score=7 → +2.19, tenure_months=2 → +1.39, watch_hours=1.4 → +0.80, device_Mobile=1 → +0.38 |
| CUST03969 | HIGH | churned | 0.830 | last_login_days_ago=25 → +1.10, device_Tablet=1 → +0.54, watch_hours=2.5 → +0.29, payment_Debit Card=1 → +0.23 |
| CUST04935 | MEDIUM | churned | 0.697 | watch_hours=0.5 → +1.10, country_India=0 → −0.81, device_Mobile=1 → +0.53, engagement=0.18 → +0.52 |
| CUST03929 | MEDIUM | churned | 0.542 | friction_score=3 → +0.69, country_Singapore=1 → +0.61, country_India=0 → −0.43, watch_hours=11.1 → −0.42 |
| CUST02155 | LOW | retained | 0.398 | watch_hours=0.8 → +0.93, tenure_months=50 → −0.92, friction_score=0 → −0.67, genre_Romance=1 → +0.56 |
| CUST01688 | LOW | retained | 0.216 | friction_score=0 → −0.82, genre_Drama=1 → +0.37, age=46 → −0.24, gender_Male=1 → +0.21 |

The behavioural signals point the right way: low watch hours, high friction, short tenure and long absence raise risk; long tenure and zero friction lower it.

## Global importance (mean |SHAP|, test set)

| Rank | Feature | Mean \|SHAP\| | Drives churn in the generator? |
|---|---|---|---|
| 1 | watch_hours_per_week | 0.575 | ✅ |
| 2 | friction_score | 0.493 | ✅ |
| 3 | tenure_months | 0.387 | ✅ |
| 4 | device_type_Tablet | 0.252 | ❌ |
| 5 | device_type_Mobile | 0.252 | ✅ (only together with the Basic plan) |
| 6 | device_type_Smart TV | 0.212 | ❌ |
| 7 | payment_failures_3m | 0.187 | ✅ |
| 8 | country_India | 0.168 | ❌ |
| 9 | engagement_score | 0.168 | ✅ |
| 10 | preferred_genre_Documentary | 0.139 | ❌ |

**Plausibility:** the top 3 match the strongest drivers built into `generate_dataset()`. However:

- **47% of total SHAP importance** sits on features that have **no effect** in the data generator: device Tablet/Smart TV, country, genre, gender, age, payment method and num_profiles.
- **1,665 of the 2,999 reasons shown to users (55.5%)** cite one of those features.
- For **398 of 1,000 customers**, the #1 reason is one of them.

SHAP is reporting the model faithfully. The model itself is fitting noise, because depth-5 trees with 200 rounds overfit. That's a model problem, handled in CHURN-17: a regularised model brings this share down to **10.8%**, and 5.3% with behavioural features only.

## Issue found and fixed — reason text contradicted the customer's data

`main.format_reason()` attached a fixed sentence to each feature name whatever the customer's actual value was. Since only positive-SHAP features are shown, it assumed a direction that often wasn't true. Measured on the 1,000 stored predictions:

| Fixed text shown | When shown | How often the text was true |
|---|---|---|
| "Short subscription tenure — still in high-risk early phase" | tenure 1–24 months | 37% (tenure < 6) |
| "Infrequent logins — rarely opening the app" | 3–23 logins | 27% |
| "Has not logged in recently — going inactive" | last login 0–41 days ago | 32% (> 14 days) |
| "Low profile usage — subscription underutilized" | 2–5 profiles | **0%** |
| "New customer — within the high-churn 0-6 month window" | is_new_customer = 0 | **0%** |
| One-hot features, e.g. "Device Type Tablet" | value 0 or 1 | ambiguous |

**Fix** (`churniq_core.describe_reason`, `main.explain_reason`):
- The API looks up the customer's actual model-feature value.
- The strong statement is shown **only when it's true**, and it includes the number, e.g. "Short subscription tenure — 2 months…" or "High friction score — 7 combined payment failures + support tickets".
- Otherwise a neutral, factual description is shown, e.g. "Subscription tenure of 18 months — raises predicted churn risk".
- One-hot features read "Device: Tablet" or "Device: not Tablet".

After the fix, **0 contradictions remain across all 3,003 reasons** served for the 1,001 scored customers.

- The `[SHAP: +X.XX]` suffix is unchanged, so the frontend's `split('[')` still works.
- `format_reason(str)` with no value behaves as before.
- The rule-based retention fallback still keys on the raw reason string, so its behaviour is unchanged.

## Limitations

- Reasons exist only for the 1,000 test customers plus the demo row. The other 4,000 show "No significant risk factor identified".
- The text describes the model's associations; it doesn't establish cause and effect.
- SHAP is computed with SHAP 0.46.0, pinned in requirements.
