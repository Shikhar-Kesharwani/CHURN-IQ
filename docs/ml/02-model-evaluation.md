# CHURN-14 — Model Performance Evaluation

> **Model update, 24 Nov 2026 (CHURN-57).** The production model has been replaced by the regularised recipe with monotone constraints (`regularised_monotonic`, [07-monotonic-constraints.md](07-monotonic-constraints.md)). The analysis below describes the **previous** committed model and is kept as the historical record. Its script has been re-run on the new model, and the current figures are in `results/evaluation_results.json`: ROC-AUC 0.7597 (95% CI 0.728 to 0.791), accuracy 0.703, precision 0.679, recall 0.589, F1 0.631, Brier 0.196.

**Artifact evaluated:** `backend/churniq_model.pkl`, the committed production model, **not retrained**.
**Reproduce:** `cd backend && python evaluate_model.py` (writes `docs/ml/results/evaluation_results.json`)

## Methodology

- **Dataset:** `backend/ott_churn_dataset.csv`, 5,000 rows. The demo row `CUST99999` is excluded because it was appended after training and was never part of the split.
- **Test data:** the pipeline's held-out split, rebuilt exactly (`train_test_split(test_size=0.2, stratify=y, random_state=42)`). This is verified: the rebuilt test set is the same 1,000 customers stored in `customer_predictions.csv`, and the artifact reproduces the stored probabilities to within 5×10⁻⁵.
- **Threshold:** 0.5, the value `model.predict` uses.
- **Which rows:** only `prediction_source == 'holdout_test'` rows are evaluation data. Since CHURN-37, `customer_predictions.csv` also contains out-of-fold predictions for the 4,000 training customers (AUC 0.746, reported in `04-clv-verification.md`). Those come from fold models, not the committed artifact, and aren't mixed into these metrics.
- **Uncertainty:** percentile 95% confidence intervals from 1,000 bootstrap resamples of the test set (seed 42).

## Class balance

| Split | Retained | Churned | Churn rate |
|---|---|---|---|
| Full dataset | 2,846 | 2,154 | 43.1% |
| Train | 2,277 | 1,723 | 43.1% |
| Train after SMOTE | 2,277 | 2,277 | 50.0% |
| **Test (evaluated)** | **569** | **431** | **43.1%** |

The imbalance is mild (57/43). The test set keeps the real distribution because SMOTE isn't applied to it.

## Results (test set, n = 1,000)

| Metric | Value | 95% CI |
|---|---|---|
| Accuracy | **0.6670** | 0.637 – 0.697 |
| Precision (churn) | **0.6225** | 0.577 – 0.670 |
| Recall (churn) | **0.5777** | 0.528 – 0.626 |
| F1 (churn) | **0.5993** | 0.559 – 0.640 |
| ROC-AUC | **0.7167** | 0.681 – 0.748 |

These are consistent with the "ROC-AUC: 0.72" quoted in `backend/README.md`.

### Confusion matrix (threshold 0.5)

| | Predicted retained | Predicted churn |
|---|---|---|
| **Actually retained** | TN = 418 | FP = 151 |
| **Actually churned** | FN = 182 | TP = 249 |

### Classification report

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Retained | 0.6967 | 0.7346 | 0.7151 | 569 |
| Churned | 0.6225 | 0.5777 | 0.5993 | 431 |
| Macro avg | 0.6596 | 0.6562 | 0.6572 | 1000 |
| Weighted avg | 0.6647 | 0.6670 | 0.6652 | 1000 |

## Reference points (same test set)

| Reference | Accuracy | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| Majority class (always "retained") | 0.569 | 0.000 | 0.000 | 0.500 |
| **Committed model** | 0.667 | 0.578 | 0.599 | 0.717 |
| Oracle: the generator's true churn probability | 0.746 | 0.640 | 0.685 | **0.794** |

The labels are *sampled* from a probability, so even a perfect model can't exceed about 0.79 ROC-AUC on this data. The model reaches 0.717, so there is headroom; CHURN-17 tries to use it.

## Why these metrics

- **ROC-AUC** measures ranking quality at every threshold. It's the right primary metric because the API ranks customers by risk and splits them into tiers at 0.40 and 0.70, not at a single cut-off.
- **Recall** is reported because a missed churner (false negative) loses that customer's CLV. **Precision** is reported because every false alarm costs a retention offer. **F1** balances the two.
- **Accuracy** is reported but shouldn't be relied on alone. The majority-class baseline already scores 0.569.
- **Calibration** matters here because the API uses the probability directly, not just the ranking. It feeds CLV (`× (1 − p)`), revenue-at-risk and the risk tiers.

## Calibration

| Predicted probability bin | n | Mean predicted | Observed churn rate |
|---|---|---|---|
| 0.0 – 0.2 | 225 | 0.127 | 0.209 |
| 0.2 – 0.4 | 287 | 0.294 | 0.310 |
| 0.4 – 0.6 | 164 | 0.496 | 0.512 |
| 0.6 – 0.8 | 170 | 0.708 | 0.588 |
| 0.8 – 1.0 | 154 | 0.886 | 0.721 |

- **Brier score:** 0.219 (oracle: 0.181).
- **Mean predicted:** 0.451 vs an actual rate of 0.431.
- The model is **over-confident at both extremes**. Customers it labels HIGH average 0.834 predicted but only 0.699 actually churn.

| Risk level | Customers | Mean predicted | Observed churn |
|---|---|---|---|
| HIGH (≥ 0.70) | 249 | 0.834 | 0.699 |
| MEDIUM (0.40–0.70) | 239 | 0.545 | 0.506 |
| LOW (< 0.40) | 512 | 0.221 | 0.266 |

The risk tiers do separate customers well: observed churn is 70% / 51% / 27% across HIGH / MEDIUM / LOW.

## Threshold sweep (same model)

| Threshold | Precision | Recall | F1 | Customers flagged |
|---|---|---|---|---|
| 0.30 | 0.544 | 0.784 | 0.643 | 621 |
| 0.40 | 0.605 | 0.685 | 0.642 | 488 |
| **0.50** | 0.623 | 0.578 | 0.599 | 400 |
| 0.60 | 0.651 | 0.490 | 0.559 | 324 |
| 0.70 | 0.699 | 0.404 | 0.512 | 249 |

This sweep is shown for information. Choosing a threshold uses the training data in CHURN-17, not the test set.

## Limitations

- The data is **synthetic**. Absolute numbers describe this generator, not a real OTT platform.
- The test set has 1,000 customers. The width of the confidence intervals (about ±0.03 AUC) should be considered before comparing models.
- The committed model can't be retrained bit-for-bit in this environment (see `01-pipeline-review.md`, Issue 3). These numbers are for the committed artifact itself.

**These results are the baseline for CHURN-17** (the "Story 11" in the Jira description). The 0.7167 AUC is for the committed artifact; a same-environment retrain of the same recipe scores 0.7239.
