# CHURN-56 — Segment-level validation of the production model

**Owner:** Aryan Gupta (E2). **Script:** `backend/segment_validation.py`. **Results:** [`results/segment_validation.json`](results/segment_validation.json). **Tests:** `backend/tests/test_segment_validation.py`.

Prepared with AI-assisted development tools. Every number below comes from the results file, which the script regenerates in about 10 seconds with identical output each time.

## 1. Question

CHURN-14 measured the model overall. CHURN-56 asks two things about the **final** production model, the regularised XGBoost with monotone constraints adopted in CHURN-45 and CHURN-57:

* How well does it perform **for each customer group**?
* Do the API risk tiers behave the same way in every group?

## 2. Method

* **Model:** the committed `backend/churniq_model.pkl` (`model_config: regularised_monotonic`, seed 42), loaded with `evaluate_model.load_artifacts()`. It is **not retrained**, and no artifact is modified.
* **Customers:** only the **1,000 genuine held-out customers** (431 churned, 569 retained). They are rebuilt with `evaluate_model.rebuild_split()`: an 80/20 stratified split with `random_state=42`, excluding the demo row.
* **Sanity checks** (recorded in the results file):
  * the split is exactly the 1,000 `holdout_test` rows in `customer_predictions.csv`;
  * the probabilities match the stored ones within rounding (5×10⁻⁵);
  * the overall metrics match `model_metadata.json`;
  * no leakage or identifier column is a model feature.
* **Groups:**
  * plan type: Basic, Standard, Premium;
  * device type: Laptop, Mobile, Smart TV, Tablet;
  * tenure: 0–5, 6–24 and 25+ months.
* **Metrics per group:** customers, retained and churned counts, actual churn rate, mean predicted probability, ROC-AUC with a bootstrap 95% CI, and accuracy, precision, recall and F1 at threshold 0.5.
* **Risk tiers:** the production cut-offs from `churniq_core`: LOW < 0.40, MEDIUM ≥ 0.40 and < 0.70, HIGH ≥ 0.70. For every group the report gives the count, share, actual churn rate and mean prediction per tier.
* **Undefined metrics are `null`, with the reason recorded in `not_calculable`:**
  * ROC-AUC for a single-class group;
  * precision when nobody is predicted to churn;
  * recall when there are no churners.
* **Weak segment (a statistical rule, not an invented margin):** the group's bootstrap 95% CI for ROC-AUC lies **entirely below** the overall 0.7597. Bootstrap: 1,000 resamples, seed 42.
* **Miscalibrated (same approach):** the bootstrap 95% CI of the gap between mean predicted probability and actual churn rate excludes 0.

### Provisional settings: not team-approved

| Setting | Value | Where |
|---|---|---|
| Tenure bands | 0–5, 6–24, 25+ months | `TENURE_BANDS` |
| Minimum group size for a reliable measurement | 100 customers | `MIN_GROUP_SIZE` |
| Minimum count of each class (churned and retained) | 30 | `MIN_CLASS_COUNT` |

These are starting values chosen for this report. They are configurable, both as module constants and as arguments to `run()`, and need team confirmation. A group below them is still reported, but is flagged *insufficient for reliable measurement*.

## 3. Results (1,000 held-out customers)

**Overall baseline:** ROC-AUC **0.7597**, accuracy 0.7030, precision 0.6791, recall 0.5893, F1 0.6311. Actual churn rate 43.1%, mean predicted 43.5%.

| Segment | n | Churned | Actual churn | Mean predicted | ROC-AUC [95% CI] | Precision | Recall | F1 | Flags |
|---|---|---|---|---|---|---|---|---|---|
| Plan: Basic | 450 | 198 | 44.0% | 43.8% | 0.773 [0.733, 0.816] | 0.686 | 0.596 | 0.638 | — |
| Plan: Standard | 343 | 153 | 44.6% | 44.6% | 0.738 [0.680, 0.787] | 0.676 | 0.601 | 0.637 | — |
| Plan: Premium | 207 | 80 | 38.6% | 40.7% | 0.763 [0.690, 0.832] | 0.667 | 0.550 | 0.603 | — |
| Device: Laptop | 250 | 102 | 40.8% | 42.2% | 0.778 [0.715, 0.834] | 0.681 | 0.608 | 0.642 | — |
| Device: Mobile | 265 | 130 | 49.1% | 45.2% | 0.777 [0.716, 0.827] | 0.750 | 0.623 | 0.681 | — |
| Device: Smart TV | 239 | 102 | 42.7% | 44.5% | **0.708** [0.643, 0.773] | 0.609 | 0.549 | 0.577 | — |
| Device: Tablet | 246 | 97 | 39.4% | 41.9% | 0.767 [0.701, 0.824] | 0.663 | 0.567 | 0.611 | — |
| Tenure: 0–5 months | 88 | 58 | 65.9% | 61.6% | 0.736 [0.632, 0.843] | 0.772 | 0.759 | 0.765 | **insufficient** (n < 100) |
| Tenure: 6–24 months | 543 | 244 | 44.9% | 46.2% | **0.724** [0.681, 0.766] | 0.661 | 0.598 | 0.628 | — |
| Tenure: 25+ months | 369 | 129 | 35.0% | 35.0% | 0.781 [0.734, 0.828] | 0.667 | **0.496** | 0.569 | — |

### Risk tiers within each group: actual churn rate (share of the group)

| Segment | LOW (< 0.40) | MEDIUM (0.40–0.70) | HIGH (≥ 0.70) |
|---|---|---|---|
| Overall | 24.6% (52%) | 54.7% (31%) | 78.8% (17%) |
| Plan: Basic | 25.3% (52%) | 52.2% (30%) | 83.1% (18%) |
| Plan: Standard | 26.0% (49%) | 56.9% (34%) | 74.1% (17%) |
| Plan: Premium | 21.0% (57%) | 55.9% (28%) | 75.9% (14%, n = 29) |
| Device: Laptop | 20.7% (54%) | 57.9% (30%) | 76.9% (16%) |
| Device: Mobile | 28.8% (50%) | 59.5% (32%) | 85.7% (18%) |
| Device: Smart TV | 26.1% (48%) | 49.4% (35%) | 75.6% (17%) |
| Device: Tablet | 23.0% (56%) | 51.5% (27%) | 75.6% (17%) |
| Tenure: 0–5 months | 47.4% (22%, n = 19) | 54.5% (38%) | 86.1% (41%) |
| Tenure: 6–24 months | 27.7% (49%) | 54.7% (31%) | 72.6% (20%) |
| Tenure: 25+ months | 19.1% (64%) | 54.7% (29%) | 92.9% (8%, n = 28) |

## 4. Findings

1. **No segment performs clearly worse than the model overall.** No group's ROC-AUC CI lies entirely below 0.7597, and no group is miscalibrated. The model ranks customers about equally well across plans, devices and tenure.
2. **The weakest point estimates are Smart TV (0.708) and tenure 6–24 months (0.724).** Their CIs still include the baseline, with upper bounds of 0.773 and 0.766. That makes them worth watching, but this data does not show them to be worse. Smart TV also has the lowest F1 (0.577).
3. **Model accuracy is not the same as churn rate.**
   * **Mobile** has the highest churn rate among devices (49.1%), yet the model ranks Mobile customers well (ROC-AUC 0.777, F1 0.681). A high churn rate makes a group a retention priority; it does not make the model weak there.
   * The same holds for **tenure 0–5 months**, which has the highest churn rate (65.9%).
4. **Long-tenure customers: good ranking, lower recall at 0.5.** Tenure 25+ months has the highest ROC-AUC (0.781) but the lowest recall (0.496). The model finds fewer of them at threshold 0.5 because their probabilities are lower overall (mean 35.0%, which exactly matches their actual churn rate). This is a threshold effect, not a ranking failure.
5. **Risk tiers behave consistently.** In every group, actual churn rises from LOW to MEDIUM to HIGH. Two tier estimates rest on small counts:
   * **HIGH for 25+ months** (92.9%) has n = 28.
   * **LOW for 0–5 months** (47.4%) has n = 19. In that group even "LOW" customers churn at about twice the overall LOW rate.
6. **Tenure 0–5 months is too small to measure reliably** under the provisional settings (88 customers, 30 retained). Its wide CI (0.632 to 0.843) reflects that.

## 5. Recommendations

* **No segment-specific model or recalibration is needed:** nothing is clearly weaker, and nothing is miscalibrated.
* **Keep the global 0.5 threshold and tiers for now.** If the business wants more long-tenure churners caught (recall 0.496 in 25+ months), consider a lower threshold for that group, or treat MEDIUM-tier long-tenure customers (54.7% actual churn) as actionable. That is a business trade-off: more contacts for more caught churners. It is not a model fix.
* **New customers (0–5 months) need care in the UI.** Their "LOW" tier churns at 47.4% (n = 19). Retention teams should not read a LOW tier as safe for new customers. Re-measure once more data is available.
* **Monitor Smart TV and tenure 6–24 months** when the model is next retrained (for example, CHURN-17-style experiments). Their point estimates are the lowest, but not significantly so.
* **The team should confirm the provisional tenure bands and the reliability minimums.** If they change, re-run the script; the results are deterministic.

## 6. Limitations

* **One held-out split of 1,000 customers.** Segment CIs are wide (half-widths of about ±0.04 to ±0.07 AUC for groups of 200 to 450 customers, and about ±0.1 for the 88-customer group), so only large differences would be detectable.
* **The data is synthetic.** Plan and device have almost no direct effect in the generator (only the Basic + Mobile interaction does), so similar performance across them is expected. Real data could differ.
* **Single dimensions only.** Combinations such as plan × tenure are not analysed; several cells would be too small (for example, Premium × 0–5 months has 15 customers).
* **The settings are provisional** (section 2).

## 7. Reproduce

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python segment_validation.py
python -m pytest -q tests/test_segment_validation.py
```
