# CHURN-10 — Segment Analysis page validation

**Jira:** CHURN-10 (E1, Sprint 2). **Owner:** Shimon Sarin. Prepared with AI-assisted development tools.
**Code checked:** `frontend/src/pages/SegmentAnalysis.jsx` at `main` @ `badbdb2`. This is after CHURN-53 (PR #11), which removed the hard-coded values. That Bug blocked this Story and is Done.
**Compared with:**
1. `GET /segments`;
2. the independent analysis in [CHURN-9](03-segment-patterns.md).

**Screenshot:** [`evidence/churn10_segments_page.png`](evidence/churn10_segments_page.png).

## 1. Result

* **Values: every value on the page is correct.** All 19 chart and table values, the 3 revenue figures, the total and the average match `GET /segments`. They also match the independent recomputation of the mean predicted probability (CHURN-9 §3).
* **Labels: one genuine mismatch, logged as Bug [CHURN-70](https://avanishrajauria.atlassian.net/browse/CHURN-70).**
  * The page labels the **mean predicted churn probability** as **"Churn Rate"** in its chart titles, tooltips and genre table header.
  * The actual (observed) churn rate for the same groups differs by up to 2.4 points.
  * The Dashboard already labels the same metric correctly: "Average Churn Probability by Plan Type".

## 2. Method

* **Servers:**
  * Backend: `cd backend && uvicorn main:app --port 8000`, on Python 3.10.13 (the production runtime).
  * Frontend: `cd frontend && VITE_API_URL=http://127.0.0.1:8000 npx vite --port 5173`.
* **Browser:** Chromium via Playwright opened `/segments`.
  * Chart titles, axis tick labels, the genre table and the revenue cards were read from the DOM.
  * Chart values were read from the Recharts tooltip, by hovering every bar and line point.
* **API values** come from `docs/data/analysis/api_crosscheck.py` (FastAPI `TestClient`).
* **Console:** 0 console errors and 0 page errors.

## 3. Values: page vs API vs CHURN-9

| Chart | Page (tooltip / table) | `GET /segments` `churn_rate_pct` | Independent mean predicted (CHURN-9) | Observed churn (CHURN-9) |
|---|---|---|---|---|
| Plan: Basic / Premium / Standard | 43.4% / 40.7% / 44% | 43.4 / 40.7 / 44.0 | 43.4 / 40.7 / 44.0 | 43.9 / 40.2 / 43.6 |
| Device: Mobile / Smart TV / Tablet / Laptop | 44% / 43.6% / 43.1% / 41.7% | 44.0 / 43.6 / 43.1 / 41.7 | same | 45.5 / 43.6 / 43.6 / 39.7 |
| Tenure: 0-3m / 3-6m / 6-12m / 1-2yr / 2yr+ | 70.1% / 55.7% / 47.2% / 46% / 33.7% | 70.1 / 55.7 / 47.2 / 46.0 / 33.7 | same | 72.3 / 57.4 / 44.8 / 47.0 / 33.5 |
| Genre table (7 rows) | Documentary 45.4 · Romance 43.4 · Thriller 42.9 · Kids 42.9 · Action 42.6 · Drama 42.3 · Comedy 42 | identical | same | 41.1–46.3 |
| Genre "vs Average" | header "(43.1%)"; Above for Documentary and Romance only | `overall.avg_churn_rate_pct` 43.1 | 43.1 | — |
| Revenue at risk / mo: Basic / Premium / Standard | ₹192,348 / ₹318,690 / ₹394,007 | `by_plan[].revenue_at_risk` 192,348.19 / 318,689.94 / 394,007.36 | — | — |
| Revenue total | "₹905,045 / month" | `overall.total_revenue_at_risk` 905,045.48 | — | — |
| Insights (5 sentences) | quote the same extremes, for example "0-3m … 70.1% … 36.4 points above … 2yr+ (33.7%)" | consistent | — | — |

**Display notes:**
* The page drops a trailing ".0" ("44%" for 44.0). That's display rounding only, with no loss.
* The revenue values are rounded to whole rupees. The three plans add up to the total (905,045.49 against 905,045.48; the 1-paisa gap is rounding).

## 4. Labels, axes, legends and units

| Element | What the page shows | Correct? |
|---|---|---|
| Page heading and subtitle | "Segment Analysis" · "Predicted churn breakdown by key customer segments" | ✅ |
| Chart titles | "Churn Rate by Plan Type / Device Type / Tenure Bucket / Preferred Genre" | ❌ **Mislabel (CHURN-70):** the values are mean *predicted* probability, not an observed rate |
| Tooltip series name | "Churn Rate : x%" | ❌ same |
| Genre table header | "CHURN RATE" · "VS AVERAGE (43.1%)" | ❌ same, for the first header; the second is correct |
| Y axis, plan and device charts | 0%, 15%, 30%, 45%, 60% | ✅ starts at 0, % unit shown |
| Y axis, tenure chart | 0%, 20%, 40%, 60%, 80% | ✅ |
| X axis categories | Basic · Premium · Standard; Mobile · Smart TV · Tablet · Laptop; 0-3m · 3-6m · 6-12m · 1-2yr · 2yr+ | ✅ match the API; ⚠️ see below |
| Revenue chart | Y axis ₹0K–₹400K; tooltip "Revenue at Risk / mo"; footnote "monthly charge × predicted churn probability" | ✅ unit and period stated |
| Legends | none | ✅ every chart has a single series, so no legend is needed |
| Insights | "…highest **predicted** churn rate…" | ✅ |

⚠️ **Tenure bucket labels.** The API bins are right-closed (`pd.cut([0, 3, 6, 12, 24, 72])`). So "3-6m" means 4–6 months and "6-12m" means 7–12 months, but the labels read as if neighbouring buckets overlap. This is recorded as a secondary point in CHURN-70; the numbers are correct.

## 5. Bug logged

[**CHURN-70**](https://avanishrajauria.atlassian.net/browse/CHURN-70) (Bug, Low): *Segments page labels mean predicted churn probability as "Churn Rate" (titles, tooltips, genre table)*.

* It's reproducible with the steps in the ticket.
* It's linked to CHURN-10 and CHURN-53.
* It's left unassigned for the team to give to the frontend (E5) owner. This Story does not change the frontend.

## 6. Limitations

* Tested on a local dev server (Vite dev mode) at 1400 px width. The deployed site and mobile widths were not re-tested here; responsiveness was covered by CHURN-30.
* The values are a snapshot of the data blobs in [CHURN-7](01-data-quality.md). Retraining the model changes every figure.
