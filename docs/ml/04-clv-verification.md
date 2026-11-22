# CHURN-16 — CLV Calculation and Tier Verification

**Code:** `backend/churniq_core.py` (`calc_clv`, `get_clv_segment`), used by both the pipeline and the API
**Tests:** `backend/tests/test_clv.py`

## Verified formula

```
CLV = monthly_charge × max(tenure_months, 6) × (1 − churn_probability)
```

| Input | Unit / range in data | Source |
|---|---|---|
| `monthly_charge` | ₹ per month: 199 / 499 / 799 (Basic / Standard / Premium) | dataset |
| `tenure_months` | months, 1–72. Floored at 6 in the formula. | dataset |
| `churn_probability` | 0–1 | **API:** model probability (`customer_predictions.csv`). **Dataset `clv_score`:** the generator's true probability. |

The result is in ₹ and rounded to 2 dp. It's identical in `churniq_ml_pipeline.py` (Part A and Part H) and `main.py`.

## Tier definitions

| Tier | Rule | Boundary behaviour |
|---|---|---|
| High | CLV > 8,000 | 8,000.00 → Medium; 8,000.01 → High |
| Medium | 3,000 < CLV ≤ 8,000 | 3,000.00 → Low; 3,000.01 → Medium |
| Low | CLV ≤ 3,000 | |
| Unknown | CLV missing | Added by this Story; see below |

No customer has a CLV exactly equal to 3,000 or 8,000.

## Hand recomputation (API values, `GET /customer/{id}`)

These are customers on either side of both boundaries, plus the highest and lowest CLV.

| Customer | Charge | Tenure | max(t, 6) | Churn prob | Hand CLV | API CLV | API tier | Correct tier |
|---|---|---|---|---|---|---|---|---|
| CUST02582 | 499 | 42 | 42 | 0.6173 | 8,020.63 | 8,021.64 | High | ✅ High |
| CUST01546 | 799 | 16 | 16 | 0.3773 | 7,960.60 | 7,960.06 | Medium | ✅ Medium |
| CUST01199 | 799 | 6 | 6 | 0.3737 | 3,002.48 | 3,002.54 | Medium | ✅ Medium |
| CUST03159 | 799 | 21 | 21 | 0.8214 | 2,996.73 | 2,996.84 | Low | ✅ Low |
| CUST02849 | 799 | 72 | 72 | 0.0638 | 53,857.71 | 53,855.07 | High | ✅ High |
| CUST01033 | 499 | 2 | **6** | 0.9958 | 12.57 | 12.53 | Low | ✅ Low (tenure floor applied) |

The small differences, at most ₹2.6, come from the API showing `churn_prob` rounded to 4 dp while CLV was computed from the unrounded probability. The maximum possible rounding error is 799 × 72 × 0.00005 ≈ ₹2.9.

**Across all 1,000 scored customers:** CLV matches the formula within rounding, and every tier is correct. The dataset's own `clv_score` and `clv_segment` columns also match the formula and tiers for all 5,000 rows (max difference ₹2.76, 0 tier mismatches).

## Mismatches found

### Fixed in this branch

1. **The same customer could get two different tiers (156 of 1,001 scored customers).** `/customer/{id}` and `/customers` work out the tier from the **model** CLV. `GET /segments` (`by_clv`) and the dashboard's `high_value_at_risk` used the dataset's `clv_segment`, which comes from the **generator's true** probability (an oracle value the model never sees).
   - **Fix:** `main.py` now derives `clv_segment` from the model CLV for every scored customer.
   - **Visible effects:**
     - `/segments.by_clv` High/Medium/Low counts go from 1268/2140/1593 to 1266/2170/1565.
     - `dashboard.kpis.high_value_at_risk` goes from **11 to 0**. Under the model's own CLV, no HIGH-risk customer reaches the High tier: p ≥ 0.70 caps CLV at 0.30 × charge × tenure.
2. **The displayed formula was wrong.** `clv_breakdown.formula` said `monthly_charge × tenure × (1 − churn_probability)` but the code applies `max(tenure, 6)`. The string now matches the code.
3. **No input validation.** `calc_clv` now:
   - returns `None` for missing inputs (None/NaN) instead of a NaN or a misleading value;
   - raises `ValueError` for negative charge, negative tenure, a probability outside [0, 1], non-numeric or infinite values.

   `get_clv_segment` returns `"Unknown"` for a missing CLV. API callers never pass a missing value, so existing responses don't change.

### Open — needs a team decision (not changed here)

> **Follow-up audit (`06-followup-audit.md` §1–3):**
> - The root cause is confirmed: the unscored customers are exactly the training split.
> - The impact is larger than "₹0 CLV". For all 4,000 of them, `/whatif` and `/retention` return HTTP 500, and every `/customers?plan_type=` filter returns 500. These are pre-existing on `origin/main`.
> - The demo row's SHAP reasons are hand-written, not computed.
> - Draft Bug descriptions (A and B) and the proposed fixes are in that document.

1. **4,000 of 5,001 customers have no model prediction.** The pipeline scores only the 20% test split. For everyone else, `GET /customer/{id}` returns `churn_prob 0.0`, risk `LOW`, CLV **₹0** and tier `Low`. That's misleading: by the formula, an unknown churn probability doesn't mean CLV = 0, and 0% risk isn't a prediction. `/segments.by_clv` keeps the dataset (oracle) tier for these customers.
   - **Proposed fix:** score every customer with out-of-fold predictions (5-fold CV, SMOTE inside folds) so that no customer is scored by a model that trained on them. Then regenerate `customer_predictions.csv`.
   - This changes every dashboard KPI, so the team should agree before it's done.
2. **The demo customer's CLV is hard-coded.** `CUST99999` (added by `add_emails.py` / `fix_cust99999.py`) has CLV fixed at ₹500 in both the CSV and `main.py`. The formula gives 199 × 6 × (1 − 0.96) = ₹47.76. It's in the Low tier either way. This is demo data, so I left it unchanged.

## Business assumptions that can't be confirmed from the code

- **Tenure is the customer's past tenure, not future lifetime.** The original pipeline comment says "expected_tenure_remaining", but the code multiplies by months already subscribed. So this CLV is closer to "risk-adjusted historical revenue" than a forward-looking lifetime value.
- **The 6-month floor** is described only as "to avoid near-zero CLV for very new customers". Nothing in the repo justifies it from the business side.
- **The tier cut-offs (₹3,000 / ₹8,000)** have no documented source.
- **No discounting, margin or acquisition cost** is applied; CLV is gross revenue.
- **Using (1 − p) as a retention factor** assumes p is a calibrated probability. CHURN-14 found the model over-confident at the extremes, which biases CLV for HIGH-risk customers downwards.

These should be confirmed by the product owner. They are documented here, not changed.
