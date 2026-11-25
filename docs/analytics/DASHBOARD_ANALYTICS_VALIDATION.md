# CHURN-11 — Dashboard analytics validation

**Jira:** CHURN-11 (E1; assignee Shimon Sarin). Evidence prepared by Aryan Gupta for the Sprint 3 closeout, with AI-assisted development tools.
**Checked against:** `main` @ `074ec94`, after PR #14 (CHURN-57, the regularised monotone-constrained model) was merged.
**Script:** [`recompute_analytics.py`](recompute_analytics.py). **Output:** [`results/recomputed_values.json`](results/recomputed_values.json). **Screenshots:** [`evidence/dashboard.png`](evidence/dashboard.png), [`evidence/segments.png`](evidence/segments.png).

## 1. Result

All dashboard and Segment Analysis numbers were checked three ways, and every one agrees:

1. recomputed independently from the two CSV files;
2. returned by the API;
3. shown in a real browser.

**No mismatch was found, so no Bug was logged.**

## 2. Source snapshot

| File | Rows × columns | Git blob SHA (`git hash-object`) |
|---|---|---|
| `backend/ott_churn_dataset.csv` | 5,001 × 22 | `1975eeab8c4dfc8f75a3da5a20c010e11612c564` |
| `backend/customer_predictions.csv` | 5,001 × 10 | `575d24b92fafef8808ceace4c85ef1cfe001b2a7` |

* **Join on `customer_id`:** 5,001 matched, 5,001 scored, 0 unscored.
* **Prediction sources:**
  * 1,000 `holdout_test`;
  * 4,000 `cv_out_of_fold`;
  * 1 `demo` (CUST99999).

If either blob SHA changes, the values below are stale and the script should be re-run.

## 3. Method

1. **Independent recomputation.** `recompute_analytics.py` uses pandas only and does **not** import `backend/main.py`.
   * Risk tiers are recomputed from `churn_prob` with literal cut-offs: HIGH ≥ 0.70, MEDIUM ≥ 0.40, LOW below.
   * CLV tiers are recomputed from the model `clv_score`: High > 8,000, Medium > 3,000, Low otherwise.
   * These cut-offs match `churniq_core.RISK_HIGH`, `RISK_MEDIUM` and `get_clv_segment`. The stored `risk_level` was also cross-checked: it gives identical counts.
2. **API.** `GET /dashboard/summary` and `GET /segments` were called both through FastAPI's `TestClient` and on a live `uvicorn main:app` (port 8000).
3. **Browser.** The Vite dev server (port 5173) was pointed at that live API, and Chromium (Playwright 1.63.0, Node 22.23.5) opened the Dashboard (`/`) and Segment Analysis (`/segments`) pages.
   * KPI and table values were read from the page text.
   * Chart values were read from the Recharts tooltips by hovering each bar or point.
   * No console errors or page errors were recorded.
   * Python 3.13.18 was used for the backend.

## 4. Semantics: what the numbers mean

* **Prediction-based figures.** `/dashboard/summary` and `/segments` use the **production model's `churn_prob`** from `customer_predictions.csv`.
  * Every Segment Analysis `churn_rate_pct` is a **mean predicted probability × 100**, not an observed churn rate.
  * The page subtitle says so ("Predicted churn breakdown").
* **Raw dataset fields, not model outputs:**
  * `churn` is the observed (synthetic) outcome.
  * `churn_probability` is the **generator's** probability. It is a leakage column and never a model input or output.
  * `clv_score` and `clv_segment` in the raw dataset are also generator-side. The API overwrites `clv_segment` from the model `clv_score` (`backend/main.py` around line 233). The raw tiers (High 1,268 / Medium 1,593 / Low 2,140) are therefore **not** what the dashboard shows.
* **Revenue at risk** = Σ `monthly_charge × churn_prob` over scored customers (a monthly figure).
* **Model CLV** = `monthly_charge × max(tenure_months, 6) × (1 − churn_prob)` (`churniq_core.calc_clv`).
  * Recomputing it from the 4-decimal `churn_prob` in the CSV matches the stored value to within ₹2.85.
  * That gap is rounding, because the artifact was computed from unrounded probabilities.

## 5. Dashboard KPIs (`GET /dashboard/summary` → `frontend/src/pages/Dashboard.jsx`)

| UI element | API field | Recomputed | API | Browser |
|---|---|---|---|---|
| Total Customers | `kpis.total_customers` | 5,001 | 5,001 | 5,001 ("5,001 scored by the model") |
| High Risk Count | `kpis.high_risk_count` | 888 | 888 | 888 |
| High-risk share (sub-label) | `kpis.high_risk_pct` | 17.8% | 17.8 | "17.8% of scored · ≥70% churn probability" |
| Medium / Low risk | `kpis.medium_risk_count`, `low_risk_count` | 1,445 / 2,668 | 1,445 / 2,668 | not displayed |
| Revenue at Risk / mo | `kpis.revenue_at_risk_formatted` | ₹905,045.48 | ₹905,045 (raw 905045.48) | ₹905,045 |
| Avg Churn Probability | `kpis.avg_churn_percent` | 43.1% (0.4309) | 43.1% | 43.1% |
| High-value at risk (HIGH risk and High model CLV) | `kpis.high_value_at_risk` | 3 | 3 | not displayed as a number |
| Signal: low engagement (< 3 watch h/week) | `churn_reasons_breakdown.low_engagement` | 1,449 | 1,449 | 1,449 (tooltip) |
| Signal: payment failures (> 0 in 3 months) | `…payment_issues` | 2,000 | 2,000 | 2,000 (tooltip) |
| Signal: new customers (tenure < 6 months) | `…new_customers` | 433 | 433 | 433 (tooltip) |
| Signal: more than 1 support ticket | `…support_issues` | 1,237 | 1,237 | 1,237 (tooltip) |

The dashboard also uses `/segments` for its CLV panel and plan chart:

| UI element | Source | Recomputed | Browser |
|---|---|---|---|
| Avg CLV | `weightedAvgClv(by_plan)`: Σ `avg_clv × count` / Σ `count` | ₹6,233.31 from the API's whole-rupee plan means; exact model-CLV mean ₹6,233.52 | ₹6,233 |
| High / Medium / Low CLV tier | `by_clv[].count` | 1,241 / 1,635 / 2,125 | 1,241 / 1,635 / 2,125 |
| Avg churn probability by plan | `by_plan[].churn_rate_pct` | Basic 43.4%, Standard 44.0%, Premium 40.7% | 43.4%, 44%, 40.7% (tooltips) |
| Monthly churn trend | `monthly_trend` | not checked: **simulated** by the API | titled "(simulated)" and captioned "Illustrative only" |
| Top priority table | `priority_customers`: top 5 HIGH by model CLV | 5 rows, all HIGH | 5 rows, all HIGH |

**Code paths.**
* Backend: `backend/main.py`, where `FULL_DF` is built (about line 223) and the `/dashboard/summary` handler starts at about line 2240.
* Frontend: the API client is `frontend/src/api/churniq.js` (`getDashboard` → `/dashboard/summary`, `getSegments` → `/segments`). The page is `frontend/src/pages/Dashboard.jsx`, with the KPI cards at about lines 119–125 and `weightedAvgClv` at line 38.

## 6. Segment Analysis (`GET /segments` → `frontend/src/pages/SegmentAnalysis.jsx`)

All values are **mean predicted churn probability** (customers in brackets). Recomputed = API = browser for every row.

| Dimension | Values |
|---|---|
| Plan | Basic 43.4% (2,226); Standard 44.0% (1,795); Premium 40.7% (980) |
| Device | Mobile 44.0% (1,292); Smart TV 43.6% (1,216); Tablet 43.1% (1,207); Laptop 41.7% (1,286) |
| Tenure bucket (`pd.cut` bins 0, 3, 6, 12, 24, 72, right-closed) | 0–3m 70.1% (206); 3–6m 55.7% (336); 6–12m 47.2% (898); 1–2yr 46.0% (1,622); 2yr+ 33.7% (1,939) |
| Genre | Documentary 45.4% (738); Romance 43.4% (694); Kids 42.9% (727); Thriller 42.9% (708); Action 42.6% (679); Drama 42.3% (723); Comedy 42.0% (732) |
| Revenue at risk by plan | Basic ₹192,348; Premium ₹318,690; Standard ₹394,007; total ₹905,045 / month |

**How the browser shows them:**

* The browser prints whole-number percentages without a decimal (44%, 46%, 42%). The underlying values are 44.0, 46.0 and 42.0.
* The genre table compares each genre with the overall 43.1%.
* Plan, device and tenure values come from the chart tooltips.
* The generated insight sentences on the page quote the same figures, for example "0-3m … 70.1% … 2yr+ (33.7%)".

## 7. Historical values in older documents

`docs/frontend/UI_TEST_REPORT.md` §2 (CHURN-26, PR #8) recorded a high-risk count of 1,201, an average of 44.8%, revenue at risk of ₹941,958 and an average CLV of ₹6,089.

* Those values were correct for the **model served before PR #14**.
* PR #14 (CHURN-57) replaced the model and regenerated `customer_predictions.csv`, so every served value changed.
* That report has been labelled as historical. **This document holds the current values.**

## 8. Limitations

* **Synthetic data.** The dataset is synthetic, so these are internal-consistency checks: data ↔ API ↔ UI. They say nothing about real customers.
* **Predictions, not observations.** Segment and KPI figures are model predictions. 4,000 of the 5,001 probabilities are out-of-fold predictions, 1,000 are hold-out predictions and 1 is the demo row; none is an in-sample fit.
* **Simulated trend.** `monthly_trend` is generated by the API around the current average. It was not validated, because there is no monthly history in the data.
* **Local test only.** The browser check ran against a local dev server (Vite dev mode). The deployed Vercel/Render site was not tested.
* **Snapshot.** The values are a snapshot of the two blob SHAs above. Retraining or regenerating predictions requires re-running the script and the browser check.

## 9. Reproduce

```bash
python docs/analytics/recompute_analytics.py          # pandas + numpy only
cd backend && uvicorn main:app --port 8000            # terminal 1
cd frontend && npm ci && npx vite --port 5173         # terminal 2, then open / and /segments
```
