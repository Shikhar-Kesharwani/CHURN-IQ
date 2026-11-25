# CHURN-7 — Dataset quality analysis

**Jira:** CHURN-7 (E1, Sprint 1). **Owner:** Shimon Sarin. Prepared with AI-assisted development tools.
**Data:** `backend/ott_churn_dataset.csv` (git blob `1975eeab8c4dfc8f75a3da5a20c010e11612c564`), and `backend/customer_predictions.csv` (blob `575d24b92fafef8808ceace4c85ef1cfe001b2a7`), both at `main` @ `badbdb2`.
**Reproduce:** `python docs/data/analysis/e1_analysis.py`. Every number below is in `docs/data/analysis/results/e1_results.json` → `churn7_quality` and `churn7_predictions_join`.
**Regression test:** `backend/tests/test_dataset_quality.py` (23 tests, collected by `python -m pytest`, so CI fails if the data ever breaks these rules).

## 1. Result

**The dataset is clean.** There are no missing values, no duplicates, no out-of-range values, no unknown categories, no plan–price mismatches and no invalid labels. **No cleaning or fix is needed before modelling or analysis.**

There is one known, documented inconsistency in a generator-side column, for the demo row CUST99999 (§5). It does not reach the model or the API.

## 2. Missing values and duplicates

| Check | Result |
|---|---|
| Shape | 5,001 rows × 22 columns |
| Missing values, **per column** | **0 in every one of the 22 columns** |
| Blank or whitespace-only text cells | 0 |
| Duplicate full rows | 0 |
| Duplicate rows ignoring `customer_id` (same customer under two IDs) | 0 |
| Duplicate `customer_id` | 0 (also 0 after trimming and upper-casing) |
| `customer_id` not matching `CUST` + 5 digits | 0 |
| Repeated `name` / `email` | 53 / 3. These are **not errors**: generated names collide. They do mean neither column can be used as a key |

## 3. Numeric ranges (domain = what the generator in `churniq_ml_pipeline.generate_dataset` allows)

| Column | Allowed | Observed min–max | Out of range |
|---|---|---|---|
| `age` | 18–65 | 18–57 | 0 |
| `monthly_charge` | 199–799 | 199–799 | 0 |
| `tenure_months` | 1–72 | 1–72 | 0 |
| `watch_hours_per_week` | 0.5–40.0 | 0.5–40.0 | 0 |
| `num_profiles` | 1–5 | 1–5 | 0 |
| `logins_last_30_days` | 0–60 | **1–26** | 0 |
| `last_login_days_ago` | 0–90 | **0–43** | 0 |
| `payment_failures_3m` | 0–4 | 0–4 | 0 |
| `support_tickets` | 0–5 | 0–5 | 0 |
| `churn_probability` | 0–1 | 0.0272–0.9940 | 0 |
| `clv_score` | ≥ 0 | 17.86–53,645.69 | 0 |

* All integer columns hold whole numbers, and `watch_hours_per_week` has at most 1 decimal place.
* **Note, not an error:** logins (max 26 of 60), last login (max 43 of 90) and age (max 57 of 65) use only part of their allowed range. They come from Poisson, exponential and normal draws. This matters for CHURN-8: the generator only raises churn risk for **fewer than 3 logins**, and just **3 of 5,001** customers are in that range.

## 4. Categories, prices and labels

| Column | Values (count) | Unknown values |
|---|---|---|
| `gender` | Other 1,683 · Male 1,661 · Female 1,657 | 0 |
| `country` | India 3,987 · Singapore 224 · UAE 215 · UK 196 · Canada 191 · USA 188 | 0 |
| `plan_type` | Basic 2,226 · Standard 1,795 · Premium 980 | 0 |
| `preferred_genre` | Documentary 738 · Comedy 732 · Kids 727 · Drama 723 · Thriller 708 · Romance 694 · Action 679 | 0 |
| `device_type` | Mobile 1,292 · Laptop 1,286 · Smart TV 1,216 · Tablet 1,207 | 0 |
| `payment_method` | Wallet 1,305 · UPI 1,270 · Debit Card 1,254 · Credit Card 1,172 | 0 |
| `clv_segment` | Low 2,140 · Medium 1,593 · High 1,268 | 0 |

* No category value has leading or trailing spaces.
* **Plan–price consistency:** `monthly_charge` equals the plan price (Basic 199, Standard 499, Premium 799) for all 5,001 rows. **0 mismatches.**
* **Churn label:** values {0: 2,846, 1: 2,155}; **0 non-binary values**.
* **Generator-side consistency:**
  * `clv_segment` matches the documented cut-offs (High > 8,000, Medium > 3,000) on all rows.
  * `clv_score` matches `monthly_charge × max(tenure, 6) × (1 − churn_probability)` within ₹2.76 (rounding) on every row except the demo row.
* **Email format:** 0 malformed addresses.

## 5. Finding: demo row CUST99999 (known, no fix needed)

* `backend/add_emails.py` added CUST99999 with hand-set generator values: `churn_probability` 0.96, `churn` 1 and **`clv_score` 500**.
* The CLV formula gives **₹47.76** for that row, so its raw `clv_score` and `clv_segment` are inconsistent with the rest of the file.
* **Impact:** none on the product.
  * These are generator-side leakage columns, so the model never reads them.
  * The serving artifact scores CUST99999 with the real model (`prediction_source = demo`, CHURN-38).
  * The API recomputes CLV and its tier from the model probability.
* **Recommendation:** keep it as documented. Exclude CUST99999 from any analysis of the raw `clv_score` (it's 1 row of 5,001).

## 6. Dataset ↔ predictions join

| Check | Result |
|---|---|
| Dataset rows / prediction rows | 5,001 / 5,001 |
| Matched on `customer_id` | 5,001 (0 only-in-dataset, 0 only-in-predictions) |
| `churn_prob` missing or outside [0, 1] | 0 |
| `actual_churn` equals the dataset `churn` | yes, for every row |
| Prediction source | 4,000 `cv_out_of_fold` · 1,000 `holdout_test` · 1 `demo` |

## 7. Recommended fixes

**None are required.** To keep it that way, `backend/tests/test_dataset_quality.py` now asserts the rules in §2–§4 and §6 on every CI run. If the dataset or the predictions are regenerated and break a rule, the build fails.

## 8. Limitations

* The data is **synthetic** (seeded generator plus `add_emails.py`). A clean result here shows the generator works as designed; it says nothing about real-world data quality.
* The domains in §3 come from the generator code. A real dataset would need domain rules agreed with the business.
