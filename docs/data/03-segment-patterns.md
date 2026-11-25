# CHURN-9 — Churn patterns by segment

**Jira:** CHURN-9 (E1, Sprint 2). **Owner:** Shimon Sarin. Prepared with AI-assisted development tools.
**Data:**
* `backend/ott_churn_dataset.csv`, observed `churn` column;
* `backend/customer_predictions.csv`, the production model's `churn_prob`, as served by the API.

Both are at `main` @ `badbdb2`, after CHURN-57 (PR #14) replaced the model.

**Reproduce:**
* `python docs/data/analysis/e1_analysis.py` writes `results/e1_results.json` → `churn9_segments`.
* `python docs/data/analysis/api_crosscheck.py` writes `results/api_crosscheck.json`. It compares with `GET /segments` and exits non-zero on any mismatch.

**Chart:** [`figures/churn9_observed_vs_predicted.png`](figures/churn9_observed_vs_predicted.png).

## 1. Two different numbers: read this first

| Measure | Meaning | Source |
|---|---|---|
| **Observed churn rate** | Share of customers in the group whose `churn` = 1 (what actually happened in the data) | this analysis |
| **Mean predicted churn probability** | Average of the model's `churn_prob` for the group × 100 | `GET /segments` → `churn_rate_pct`, which is also what the Segments and Dashboard pages show |

Both happen to be 43.1% overall, but they differ by group (up to 2.4 points, see §3). **The API's `churn_rate_pct` is a predicted probability, not an observed rate.**

## 2. Observed churn by single segment (all 5,001 customers)

Cramér's V measures association with churn (0 = none).

| Segment (V) | Groups: observed churn % (n) |
|---|---|
| **Tenure bucket (0.192)** | 0-3m **72.3%** (206) · 3-6m 57.4% (336) · 6-12m 44.8% (898) · 1-2yr 47.0% (1,622) · 2yr+ 33.5% (1,939) |
| Device (0.043) | Mobile 45.5% (1,292) · Smart TV 43.6% (1,216) · Tablet 43.6% (1,207) · Laptop 39.7% (1,286) |
| Num. profiles (0.037) | 1: 40.7% · 2: 42.9% · 3: 44.4% · 4: 45.8% · 5: 45.3% (n = 1,497 / 1,506 / 1,044 / 707 / 247) |
| Gender (0.035) | Female 45.4% (1,657) · Male 42.6% (1,661) · Other 41.3% (1,683) |
| Genre (0.033) | Documentary 46.3% (738) · Romance 43.9% · Kids 43.5% · Thriller 42.7% · Comedy 42.2% · Drama 41.8% · Action 41.1% (679) |
| Plan (0.029) | Basic 43.9% (2,226) · Standard 43.6% (1,795) · Premium 40.2% (980) |
| Country (0.020) | Singapore 45.1% (224) · USA 43.6% · India 43.3% (3,987) · Canada 42.9% · UAE 40.5% · UK 39.8% (196) |
| Age band (0.019) | 18–24 42.3% · 25–34 43.1% · 35–44 44.4% · 45+ 40.0% (n = 145) |
| Payment method (0.014) | Credit Card 44.3% · Wallet 43.1% · Debit Card 42.6% · UPI 42.4% |

**Tenure is the only demographic or account segment with a strong pattern.** The 0–3 month group churns at more than twice the 2yr+ rate.

Device, plan, genre, gender, country, age, profiles and payment method all fall within about 6 points of the 43.1% average. Most of their 95% intervals overlap (see the JSON), so these small differences should not be acted on.

## 3. Independent analysis vs `GET /segments`

For each group, the counts and the mean predicted probability were computed independently with pandas. They were then compared with the live API response (FastAPI `TestClient`, `main` @ `badbdb2`).

**All 19 rows match exactly** (count, and `churn_rate_pct` to 0.1), as does the overall 43.1%. The same tenure bins as the API are used (`pd.cut([0, 3, 6, 12, 24, 72])`, right-closed).

| Group | n | API `churn_rate_pct` (mean predicted) | Observed churn | Observed − predicted |
|---|---|---|---|---|
| Plan Basic / Standard / Premium | 2,226 / 1,795 / 980 | 43.4 / 44.0 / 40.7 | 43.9 / 43.6 / 40.2 | +0.5 / −0.4 / −0.5 |
| Device Mobile / Smart TV / Tablet / Laptop | 1,292 / 1,216 / 1,207 / 1,286 | 44.0 / 43.6 / 43.1 / 41.7 | 45.5 / 43.6 / 43.6 / 39.7 | +1.5 / 0.0 / +0.5 / −2.0 |
| Tenure 0-3m / 3-6m / 6-12m / 1-2yr / 2yr+ | 206 / 336 / 898 / 1,622 / 1,939 | 70.1 / 55.7 / 47.2 / 46.0 / 33.7 | 72.3 / 57.4 / 44.8 / 47.0 / 33.5 | +2.2 / +1.7 / −2.4 / +1.0 / −0.2 |
| Genre (7 groups) | 679–738 each | 42.0–45.4 | 41.1–46.3 | −1.5 to +0.9 |

The model's mean predictions track the observed rates closely: every gap is within ±2.4 points and inside the observed rate's 95% interval. Both agree on which group is highest in each dimension:
* tenure 0–3m;
* device Mobile;
* genre Documentary.

For **plan**, the highest group differs: Standard on predictions (44.0%) and Basic on observed churn (43.9%). The two are 0.3 points apart, within noise.

## 4. High-risk segments (combinations, n ≥ 50)

Combinations of the strongest behaviour signals (CHURN-8) with tenure. Bands: watch < 2 h, 2–5 h, 5 h+; payment failures 0, 1–2, 3–4.

| Segment | n | Observed churn | 95% CI | Mean predicted |
|---|---|---|---|---|
| **Watch < 2 h and 3–4 payment failures** | 112 | **94.6%** | 88.8–97.5 | 90.4% |
| Tenure 3-6m and watch < 2 h | 85 | 85.9% | 76.9–91.7 | 80.3% |
| Tenure 0-3m and watch < 2 h | 55 | 85.5% | 73.8–92.4 | 89.3% |
| Watch 2–5 h and 3–4 payment failures | 111 | 79.3% | 70.8–85.8 | 79.3% |
| Tenure 0-3m and 1–2 payment failures | 53 | 79.2% | 66.5–88.0 | 72.5% |
| Tenure 6-12m and 3–4 payment failures | 75 | 78.7% | 68.1–86.4 | 79.1% |
| Tenure 1-2yr and 3–4 payment failures | 196 | 78.1% | 71.8–83.3 | 78.2% |
| Watch < 2 h and 1–2 payment failures | 278 | 75.5% | 70.2–80.2 | 73.1% |

**Lowest-risk segments:**

| Segment | n | Observed churn |
|---|---|---|
| Watch 5 h+ and 0 failures | 1,618 | **23.5%** |
| Tenure 2yr+ and 0 failures | 1,165 | 23.8% |
| Tenure 2yr+ and watch 5 h+ | 1,096 | 24.7% |

**Conclusions:**

1. **The highest-risk segments combine low engagement with payment friction or a new account.**
   * Watch under 2 h plus 3–4 payment failures churns at 94.6%, about **4×** the lowest-risk segment.
   * These are the segments a retention campaign would target first.
2. **Plan × device gives only a modest lift.**
   * Basic + Mobile churns at **49.3% (n = 578)**, about 6 points above the 43.1% average. That fits the generator's small +0.4 Basic × Mobile term.
   * It is far below the behaviour-based segments above.
3. **The model's mean predictions are close to the observed rates** in every high-risk segment (within 7 points), so the Segments page ranks segments correctly.

## 5. Limitations

* **Synthetic data:** the patterns reflect the generator's scoring formula and are not evidence about real customers.
* **Association, not causation;** groups overlap, for example new customers are often low watchers.
* **Small groups:** groups with n < 100 have intervals of ±8 to ±12 points. Only combinations with n ≥ 50 are reported.
* **Predictions:** the "mean predicted" values come from out-of-fold (4,000), hold-out (1,000) and demo (1) predictions, not an in-sample fit.
