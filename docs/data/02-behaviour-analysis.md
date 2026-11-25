# CHURN-8 — Customer behaviour analysis

**Jira:** CHURN-8 (E1, Sprint 1). **Owner:** Shimon Sarin. Prepared with AI-assisted development tools.
**Data:** `backend/ott_churn_dataset.csv`, all 5,001 rows, **observed** outcome `churn` (not model predictions). The data quality was checked first in [CHURN-7](01-data-quality.md): no cleaning was needed.
**Reproduce:** `python docs/data/analysis/e1_analysis.py`. The numbers are in `docs/data/analysis/results/e1_results.json` → `churn8_behaviour`.
**Charts:**
* [`figures/churn8_churn_rate_by_variable.png`](figures/churn8_churn_rate_by_variable.png): churn rate by group, with 95% confidence intervals and group sizes.
* [`figures/churn8_distributions.png`](figures/churn8_distributions.png): distributions by outcome.

**Overall:** 2,155 of 5,001 customers churned, **43.1%**.

## 1. Strongest associations with churn

Ranked by Cramér's V, which compares variables on the same grouped scale (0 = no association). For the numeric variables, the univariate ROC-AUC shows the direction (0.5 = no signal).

| Rank | Variable | Cramér's V | AUC | Direction | Size of effect (observed churn) |
|---|---|---|---|---|---|
| 1 | **Watch hours / week** | **0.297** | 0.355 | more watching → less churn | 70.1% (< 2 h, n = 1,074) vs 31.9% (20–40 h, n = 448) |
| 2 | **Payment failures (3 months)** | **0.257** | 0.620 | more failures → more churn | 35.0% (0, n = 3,001) vs 80.1% (4, n = 156) |
| 3 | **Tenure** | **0.187** | 0.407 | longer tenure → less churn | 65.4% (1–5 months, n = 433) vs 33.0% (25–48 months, n = 1,493) |
| 4 | Support tickets | 0.175 | 0.584 | more tickets → more churn | 36.9% (0, n = 2,527) vs 80.4% (5, n = 92) |
| 5 | Logins (30 days) | 0.039 | **0.504** | **no meaningful association** | 41.9%–52.7% across groups; overlapping intervals |
| 6 | Plan | 0.029 | — | very weak | Basic 43.9% · Standard 43.6% · Premium 40.2% |

**The three strongest are watch hours, payment failures and tenure,** followed by support tickets. Logins and plan show little or no association.

## 2. Each variable: distribution and churn rate

The 95% intervals are Wilson score intervals. *n* is the number of customers in the group.

### Watch hours per week

The distribution is skewed: mean 8.33, median 5.8, quartiles 2.5–11.5, range 0.5–40. Churned customers average 6.73 h; retained customers average 9.54 h.

| Hours | n | Churned | Observed churn | 95% CI |
|---|---|---|---|---|
| 0.5–2 | 1,074 | 753 | **70.1%** | 67.3–72.8 |
| 2–5 | 1,178 | 501 | 42.5% | 39.7–45.4 |
| 5–10 | 1,240 | 398 | 32.1% | 29.6–34.7 |
| 10–20 | 1,061 | 360 | 33.9% | 31.1–36.8 |
| 20–40 | 448 | 143 | 31.9% | 27.8–36.4 |

The effect is concentrated **below 5 hours**. Above 5 hours, churn is flat at about 32–34%.

### Payment failures (last 3 months)

Mean 0.73. 60% of customers (3,001) have none.

| Failures | n | Observed churn | 95% CI |
|---|---|---|---|
| 0 | 3,001 | 35.0% | 33.3–36.7 |
| 1 | 996 | 45.5% | 42.4–48.6 |
| 2 | 498 | 54.0% | 49.6–58.3 |
| 3 | 350 | 74.0% | 69.2–78.3 |
| 4 | 156 | **80.1%** | 73.2–85.6 |

Churn rises with every extra failure.

### Tenure (months)

Mean 23.5, median 20, range 1–72. Churned customers average 20.9 months; retained customers average 25.4.

| Months | n | Observed churn | 95% CI |
|---|---|---|---|
| 1–5 | 433 | **65.4%** | 60.8–69.7 |
| 6–12 | 1,007 | 45.8% | 42.7–48.9 |
| 13–24 | 1,622 | 47.0% | 44.6–49.4 |
| 25–48 | 1,493 | 33.0% | 30.7–35.4 |
| 49–72 | 446 | 35.0% | 30.7–39.5 |

There are two steps: after the first 5 months, and after 24 months.

### Support tickets

Mean 0.94. Half of customers (2,527) have none.

| Tickets | n | Observed churn | 95% CI |
|---|---|---|---|
| 0 | 2,527 | 36.9% | 35.0–38.8 |
| 1 | 1,237 | 43.6% | 40.8–46.4 |
| 2 | 610 | 48.4% | 44.4–52.3 |
| 3 | 354 | 58.2% | 53.0–63.2 |
| 4 | 181 | 60.2% | 52.9–67.1 |
| 5 | **92** | **80.4%** | 71.2–87.3 |

Churn rises steadily. The 5-ticket group is small (n = 92), so its exact rate is uncertain (±8 points).

### Logins (last 30 days)

Mean 11.9, sd 3.4, range 1–26, close to a Poisson(12) distribution. Churned customers average 11.91 logins; retained customers average 11.88.

| Logins | n | Observed churn | 95% CI |
|---|---|---|---|
| 0–5 | 91 | 52.7% | 42.6–62.7 |
| 6–10 | 1,709 | 43.1% | 40.7–45.4 |
| 11–15 | 2,474 | 41.9% | 39.9–43.8 |
| 16–20 | 681 | 46.3% | 42.5–50.0 |
| 21+ | 46 | 43.5% | 30.2–57.8 |

**There is no meaningful association: AUC 0.504, point-biserial r = 0.004.**

* The generator's formula only adds churn risk when **logins < 3**, and only **3 customers** fall below that threshold (all 3 churned).
* So logins are effectively a non-signal in this dataset, even though the formula includes them.
* The small groups at the extremes (n = 91 and n = 46) have wide intervals that overlap the overall rate.

### Plan

Basic 2,226 · Standard 1,795 · Premium 980.

| Plan | n | Observed churn | 95% CI |
|---|---|---|---|
| Basic | 2,226 | 43.9% | 41.9–46.0 |
| Standard | 1,795 | 43.6% | 41.3–45.9 |
| Premium | 980 | 40.2% | 37.2–43.3 |

The differences are small. Basic and Standard intervals overlap, and Premium is about 3.5 points lower. In the generator, plan matters only through a Basic × Mobile interaction (+0.4 to the score), which fits this weak pattern. See CHURN-9 for the combination.

## 3. Interpretation and limitations

* **Correlation is not causation.** These are associations in observed data. A customer who watches less might churn because of something else that also lowers their watching.
* **Synthetic data.** The churn label was sampled from a known scoring formula (`generate_dataset`). The ranking above largely **recovers that formula**: low watching, payment failures, short tenure and tickets all add to the score. That validates the data pipeline, but says nothing about real OTT customers.
* **One variable at a time.** Variables overlap; for example, a new customer can also be a low watcher. CHURN-9 looks at combinations.
* **Bin choices.** The groupings above were chosen for readability. AUC and point-biserial r are computed on the raw values and don't depend on the bins.
* **Small groups.** The intervals for 4 payment failures (n = 156), 5 tickets (n = 92) and the logins extremes (n = 91 and n = 46) are wide; treat those exact rates with caution.
