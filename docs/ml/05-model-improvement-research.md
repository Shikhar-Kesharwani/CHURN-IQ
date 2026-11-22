# CHURN-17 — Model Improvement Research

**Reproduce:** `cd backend && python model_experiments.py` (about 40 s; writes `docs/ml/results/model_experiments.json`)
**Baseline:** CHURN-14 (`02-model-evaluation.md`)

## Protocol (fixed before looking at test results)

1. Same dataset and the same 80/20 stratified split (`random_state=42`) as the pipeline and CHURN-14.
2. **Every selection decision uses only the 4,000 training rows.** That means 5-fold stratified CV, with SMOTE applied **inside each training fold** (imblearn `Pipeline`) and never to validation folds.
3. Each shortlisted candidate is refit on the full training split and scored **once** on the held-out test split.
4. Test comparisons with the baseline use a **paired bootstrap** (1,000 resamples) of ROC-AUC on the same 1,000 test customers.
5. **Improvement rule:** CV ROC-AUC gain > the baseline's CV standard deviation **and** the 95% CI of the paired test-AUC difference lies entirely above 0.

**Baseline for comparison:** the production recipe (SMOTE + XGBoost 200/5/0.1) retrained in this environment. It scores test AUC 0.7239, against 0.7167 for the committed artifact, which can't be reproduced exactly (`01-pipeline-review.md`, Issue 3). Retraining keeps the comparison fair: same environment, same code, only the recipe changes.

## Candidates and results

| Candidate | Features | CV AUC (mean ± sd) | Test AUC | Acc | Prec | Recall | F1 | Brier | Δ test AUC vs baseline (95% CI) | Meets rule |
|---|---|---|---|---|---|---|---|---|---|---|
| **A. Baseline:** SMOTE + XGB(200, depth 5, lr 0.1) | 33 | 0.7467 ± 0.0202 | 0.7239 | 0.669 | 0.628 | 0.571 | 0.598 | 0.2157 | — | — |
| B. XGB, no SMOTE | 33 | 0.7510 ± 0.0200 | 0.7229 | 0.662 | 0.621 | 0.552 | 0.585 | 0.2155 | [−0.014, +0.011] | ❌ |
| C. XGB + `scale_pos_weight` | 33 | 0.7494 ± 0.0200 | 0.7163 | 0.656 | 0.603 | 0.592 | 0.597 | 0.2193 | [−0.021, +0.006] | ❌ |
| D. Logistic regression | 33 | 0.7279 ± 0.0210 | 0.7096 | 0.674 | 0.659 | 0.506 | 0.572 | 0.2127 | [−0.043, +0.010] | ❌ |
| E. Logistic regression, behavioural features | 16 | 0.7306 ± 0.0216 | 0.7110 | 0.670 | 0.654 | 0.497 | 0.565 | 0.2123 | [−0.042, +0.013] | ❌ |
| **F. Regularised XGB (CV-tuned), no SMOTE** | 33 | **0.7744 ± 0.0214** | **0.7581** | **0.707** | **0.687** | 0.589 | **0.634** | **0.1963** | **[+0.018, +0.052]** | ✅ |
| G. Regularised XGB, behavioural features | 16 | 0.7739 ± 0.0209 | 0.7590 | 0.706 | 0.688 | 0.582 | 0.631 | 0.1962 | [+0.018, +0.054] | ✅ |
| *Reference: committed artifact* | 33 | — | 0.7167 | 0.667 | 0.623 | 0.578 | 0.599 | 0.2189 | — | — |
| *Reference: oracle (true probability)* | — | — | 0.7941 | 0.746 | 0.736 | 0.640 | 0.685 | 0.1810 | — | — |

**Hyperparameter search (F):** a CV-only grid of 24 configurations:

| Parameter | Values tried |
|---|---|
| `max_depth` | {2, 3, 4} |
| `learning_rate` | {0.03, 0.1} |
| `n_estimators` | {150, 400} |
| `min_child_weight` | {1, 10} |

The other XGBoost settings were kept from production. The selected configuration is `max_depth=2, learning_rate=0.03, n_estimators=400, min_child_weight=1`, with CV AUC 0.7744. The top 5 configurations are all depth 2–3 and lie within 0.002 AUC of each other, so the result isn't sensitive to the exact choice.

"Behavioural features" means dropping age, gender, country, genre and payment method. The hypothesis came from CHURN-15, where 47% of SHAP importance sat on these.

## What the results show

1. **Overfitting was the main problem, not class imbalance.**
   - Shallower trees with a slower learning rate gained about +0.028 CV AUC and +0.034 test AUC.
   - That closes 49% of the gap between the baseline (0.724) and the oracle ceiling (0.794).
2. **SMOTE adds nothing here.** The imbalance is mild (43% churn). Removing SMOTE (B) or replacing it with `scale_pos_weight` (C) changed AUC within noise. SMOTE does inflate the predicted probabilities: the baseline's mean prediction is 0.451 against a true rate of 0.431.
3. **Calibration improves too.** Brier score drops from 0.216 to 0.196, and the mean prediction (0.434) is close to the actual rate (0.431). This matters because the API feeds probabilities directly into CLV and revenue-at-risk.
4. **Explanations become more trustworthy.** Measured with SHAP on the test set:

   | Model | Share of SHAP importance on non-driver features | Customers whose #1 reason is a non-driver |
   |---|---|---|
   | Committed / baseline | 47% | 398 / 1000 |
   | F (regularised) | 10.8% | 121 / 1000 |
   | G (regularised, behavioural) | 5.3% | 105 / 1000 |

5. **Logistic regression** is simpler and well calibrated, but it can't express the generator's threshold effects and interactions without hand-made features. It scored significantly lower in CV.
6. **Behavioural-only features (G)** match F's accuracy with half the features and cleaner explanations. But the evidence that demographics don't matter comes from this synthetic generator. Real data may differ.

## Threshold tuning

The threshold is chosen on out-of-fold **training** predictions to maximise F1, then applied once to the test set.

| Model | CV-chosen threshold | Test precision | Test recall | Test F1 |
|---|---|---|---|---|
| A. Baseline | 0.35 | 0.582 | 0.749 | 0.655 |
| F. Regularised | 0.32 | 0.585 | **0.796** | **0.675** |
| F at the default 0.50 | 0.50 | 0.687 | 0.589 | 0.634 |

Lowering the threshold to about 0.32 lets model F catch **80% of churners instead of 59%**, at the cost of more false alarms. Whether that's worth it depends on the cost of a retention offer relative to a lost customer's CLV, which the repository doesn't state. It's a **business decision**, so the threshold isn't changed.

## Recommendations (in priority order)

| # | Recommendation | Expected benefit | Drawbacks / risks | Complexity | Status |
|---|---|---|---|---|---|
| 1 | **Adopt the regularised XGBoost without SMOTE (config F)** for production | +0.034 test AUC (CI +0.018 to +0.052), better calibration, explanations far less driven by noise | All API numbers change (probabilities, risk tiers, CLV, KPIs). The demo row must be re-added. Frontend copy that quotes metrics should be checked. | Low: `python churniq_ml_pipeline.py --model-config regularised --output-dir .`, then re-run `add_emails.py` / `fix_cust99999.py` | **Implemented as an option** (`MODEL_CONFIGS['regularised']`); the production artifact is **not replaced**. Needs team sign-off. |
| 2 | **Score all customers with out-of-fold predictions** | Removes the 4,000 customers showing 0% risk and ₹0 CLV (CHURN-16 open issue 1) | Dashboard KPIs change substantially | Medium | Proposed |
| 3 | **Decide the operating threshold from business costs** (cost of an offer vs CLV lost) | Up to +21 points of recall at ~0.32 | More false-alarm offers | Low, once costs are known | Needs product input |
| 4 | Consider dropping demographic/preference features (config G) | Same AUC, half the features, the cleanest explanations | May drop real signal in production data. Re-test on real data first. | Low | Not recommended until real data is available |
| 5 | Probability calibration (isotonic or Platt on a validation fold) | More accurate CLV and revenue-at-risk | Adds a component; little gain once #1 is adopted | Medium | Optional |
| 6 | Widen the CV search (depth 1, `n_estimators` > 400, lr < 0.03) | Possibly a small gain: the selected configuration sits at the edge of the grid | Selection on the same CV folds; small expected effect | Low | Follow-up |
| — | Replace SMOTE with `scale_pos_weight`, or switch to logistic regression | none measured | | | **Not recommended** (no measurable benefit) |

## Implemented

- `churniq_ml_pipeline.MODEL_CONFIGS` has `'baseline'` (the default, unchanged) and `'regularised'` (config F), selected with `--model-config`. Running the regularised config reproduces this report's numbers: test AUC 0.7581, F1 0.6342.
- `backend/model_experiments.py` runs the full experiment.
- `backend/tests/test_model_improvement.py` guards the baseline vs regularised comparison and the recorded results.

## Limitations

- **Synthetic data:** the generator is an additive score with thresholds, which shallow trees model well. Gains may differ on real data.
- **Single test split:** I've reported CV and bootstrap intervals, but there's only one held-out split.
- **Garden of forking paths:** I looked at the test results for all seven candidates. The adopted candidate also has the best CV score, chosen before testing, which limits this concern.
- **Baseline difference:** the comparison baseline is the same-environment retrain (0.7239), not the committed artifact (0.7167). Compared with the committed artifact, the gain is larger (+0.041).
