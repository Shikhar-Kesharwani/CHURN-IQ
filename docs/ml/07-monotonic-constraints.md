# CHURN-45 — Monotonic constraints for What-If

**Owner:** Aryan Gupta (E2). **Script:** `backend/monotonic_experiments.py`. **Results:** [`results/monotonic_experiments.json`](results/monotonic_experiments.json). **Tests:** `backend/tests/test_monotonic_constraints.py`.

Prepared with AI-assisted development tools. Every number below comes from the results file, which the script regenerates in about 20 seconds.

## 1. Problem

`POST /whatif` reports the model faithfully, but the model is not monotonic per customer. `docs/api/README.md` §7 recorded that raising `watch_hours_per_week` to 40 *increased* predicted risk for 42% of customers.

This study re-measured the problem across each feature's whole range, not just one jump. It is much larger than that single figure suggests.

## 2. Expected direction for each What-If feature

The dataset is synthetic. Its label comes from `churn_score` in `churniq_ml_pipeline.generate_dataset`, so the true direction of each feature is known exactly.

| What-If input | Generator term | Expected direction as the value rises | Constraint |
|---|---|---|---|
| `watch_hours_per_week` | +1.5 if < 2 h, +0.5 if < 5 h | risk falls | −1 |
| `logins_last_30_days` | +1.2 if < 3 | risk falls | −1 |
| `tenure_months` | +1.2 if < 3, +0.5 if < 6, −0.8 if > 24 | risk falls | −1 |
| `payment_failures_3m` | +0.6 per failure | risk rises | +1 |
| `support_tickets` | +0.4 per ticket | risk rises | +1 |
| `monthly_charge` | none directly. It is fixed by `plan_type`; only the Basic + Mobile interaction adds +0.4 | no expectation | 0 (unconstrained) |

The engineered features that `/whatif` recomputes from these inputs get the matching sign, so a raw change stays monotone end to end:

* `engagement_score` (= watch × logins / 30): −1
* `friction_score` (= failures + tickets): +1
* `is_new_customer` (= tenure < 6): +1

All other features are unconstrained, including demographics, plan, the one-hot columns, `last_login_days_ago` and `inactivity_flag`.

## 3. Why the current model is non-monotonic

* **The true effects are step functions with long flat regions.** For example, watch hours above 5 h have no effect at all. The label also carries Gaussian noise (σ = 0.5 on the score) and is sampled from a probability.
* **Unconstrained trees fit that noise inside the flat regions.** This produces small local reversals. CHURN-15 also found 47% of the SHAP weight on features that do not drive churn.
* **Regularisation shrinks the reversals but does not remove them** (section 5). Only a hard constraint does.

## 4. Method (same as CHURN-17, `model_experiments.py`)

* **Data and split:** the committed dataset, with the same 80/20 stratified split (`random_state=42`).
* **Selection:** 5-fold stratified CV on the 4,000 training rows, with SMOTE inside the training folds where the recipe uses it.
* **Test:** each model is refit on the full training split and scored once on the 1,000 held-out customers.
* **Comparison:** paired bootstrap (1,000 resamples) of the test ROC-AUC difference.
* **Same improvement rule:** CV gain > reference CV std **and** the paired 95% CI above 0.

**Robustness:** 10 further stratified splits (seeds 1 to 10) compare the regularised model with and without the constraint.

**Per-customer What-If check:** the 1,000 held-out customers are scored on the `/whatif` code path (`churniq_core.encode_features`, so engineered features are recomputed). Each feature is swept over a grid inside its training range. A customer has a *wrong step* if risk moves against the expected direction between two neighbouring grid values.

| Model | Recipe |
|---|---|
| Committed artifact | `churniq_model.pkl` as currently served |
| A | Production recipe retrained: SMOTE + `XGB_PARAMS` |
| A + constraints | A with `monotone_constraints` |
| F | CHURN-17 regularised recipe: depth 2, lr 0.03, 400 trees, no SMOTE |
| **F + constraints** | F with `monotone_constraints` |

## 5. Results

### Predictive performance (held-out test set, threshold 0.5)

| Model | CV AUC (mean ± sd) | Test ROC-AUC | Precision | Recall | F1 | Accuracy | Brier |
|---|---|---|---|---|---|---|---|
| Committed artifact | — | 0.7167 | 0.6225 | 0.5777 | 0.5993 | 0.667 | 0.2189 |
| A | 0.7467 ± 0.0202 | 0.7239 | 0.6276 | 0.5708 | 0.5978 | 0.669 | 0.2157 |
| A + constraints | 0.7551 ± 0.0184 | 0.7270 | 0.6312 | 0.6195 | 0.6253 | 0.680 | 0.2155 |
| F | 0.7744 ± 0.0214 | 0.7581 | 0.6865 | 0.5893 | 0.6342 | 0.707 | 0.1963 |
| **F + constraints** | **0.7748 ± 0.0206** | **0.7597** | 0.6791 | 0.5893 | 0.6311 | 0.703 | **0.1958** |

The retrained A (0.7239) and F (0.7581) reproduce the CHURN-17 figures (0.724 and 0.758), so the protocol is consistent.

| Comparison | Test AUC difference | Paired 95% CI | Meets improvement rule? |
|---|---|---|---|
| A + constraints vs A | +0.0031 | [−0.0122, +0.0183] | No; no worse |
| F + constraints vs F | +0.0016 | [−0.0021, +0.0054] | No; no worse |
| **F + constraints vs A** (production recipe) | **+0.0358** | **[+0.0192, +0.0539]** | **Yes** |
| F + constraints vs committed artifact | — | [+0.0265, +0.0587] | — |

**Robustness over 10 other splits** (F + constraints minus F):

* Mean difference: **−0.0006 AUC**, sd 0.0026, range −0.0035 to +0.0052.
* F + constraints was better or equal on 3 of the 10 splits.

So the constraint has a **negligible cost, not a gain**. The difference is well inside split-to-split noise.

### Per-customer What-If direction (1,000 held-out customers)

Share of customers with **any** wrong-direction step / with a wrong step **over 1 percentage point** / the largest wrong step:

| Feature | Committed artifact | A | A + constraints | F | F + constraints |
|---|---|---|---|---|---|
| `watch_hours_per_week` | 99.4% / 98.6% / 0.574 | 98.8% / 96.8% / 0.425 | **0 / 0 / 0** | 99.9% / 59.4% / 0.178 | **0 / 0 / 0** |
| `logins_last_30_days` | 99.1% / 95.9% / 0.414 | 99.5% / 96.6% / 0.357 | **0 / 0 / 0** | 100% / 91.3% / 0.226 | **0 / 0 / 0** |
| `tenure_months` | 99.6% / 97.8% / 0.395 | 99.8% / 98.5% / 0.286 | **0 / 0 / 0** | 98.2% / 56.6% / 0.045 | **0 / 0 / 0** |
| `payment_failures_3m` | 37.2% / 23.5% / 0.133 | 23.2% / 15.6% / 0.128 | **0 / 0 / 0** | 0.9% / 0.1% / 0.010 | **0 / 0 / 0** |
| `support_tickets` | 41.4% / 30.6% / 0.189 | 42.7% / 32.0% / 0.174 | **0 / 0 / 0** | 4.4% / 2.3% / 0.033 | **0 / 0 / 0** |

Single-step changes from `docs/api/README.md` §7: share of changed customers whose risk went **up**.

| Change | Committed | F | F + constraints |
|---|---|---|---|
| `watch_hours_per_week` → 40 | 41% | 38% | **0%** |
| `logins_last_30_days` → 26 | 34% | 32% | **0%** |
| `tenure_months` → 72 | 38% | 28% | **0%** |

(For the committed artifact, the 41% here reproduces the 42% in §7 on a different customer sample.)

## 6. Decision: **adopt F + constraints** (regularised recipe + monotone constraints)

1. **It removes the defect completely.** Across all five constrained What-If features, no customer's risk moves in the wrong direction. Regularisation alone leaves about 99% of customers with reversals on the engagement features.
2. **It costs nothing material in accuracy.** The paired CI against F contains 0, and over 10 splits the mean cost is −0.0006 AUC.
3. **It carries the CHURN-17 gain.** Against the production recipe it adds +0.036 AUC (CI +0.019 to +0.054), meeting the improvement rule. It also has better calibration (Brier 0.1958 vs 0.2157).

Constraining the current production recipe (A + constraints) would also fix the direction, but without the accuracy and calibration gain. It is therefore not recommended.

**What adoption involves (CHURN-57).** Every probability, risk tier, CLV and KPI changes. The production model, the out-of-fold fold models, `customer_predictions.csv` (including the demo row) and the docs must all be regenerated by the committed code with a recorded seed and config. CHURN-57's criteria require the team to be told before that change is merged.

## 7. Adoption (CHURN-57)

The decision was implemented on branch `feature/churn-57-adopt-monotonic-model`, stacked on the CHURN-45 branch.

* **Production recipe:** `churniq_ml_pipeline.PRODUCTION_CONFIG = 'regularised_monotonic'`. The constraint directions are defined once, in `MONOTONE_DIRECTIONS`, and the experiment asserts it uses the same ones.
* **Retrained from the committed dataset:**

  ```bash
  python churniq_ml_pipeline.py --from-dataset ott_churn_dataset.csv --output-dir .
  ```

  The dataset, its names and emails, and the demo row are unchanged. The command writes `churniq_model.pkl`, `feature_names.pkl` (byte-identical to before) and `model_metadata.json`. The metadata records the config, seed 42, the XGBoost parameters including the constraint vector, the split and the test metrics.
* **Predictions and fold models regenerated:** `python generate_predictions.py` rebuilds `customer_predictions.csv` (1,000 hold-out, 4,000 out-of-fold and 1 demo row) and `oof_fold_models.pkl`. The 5 fold models use the same constrained recipe, so What-If is monotonic for out-of-fold customers too.
* **Deterministic:** both steps give byte-identical artifacts when re-run.
* **New metrics on the held-out split:**
  * test ROC-AUC 0.7597 (95% CI 0.728 to 0.791), accuracy 0.703, precision 0.679, recall 0.589, F1 0.631, Brier 0.196;
  * out-of-fold ROC-AUC 0.7737.
* **Explanations are cleaner as a side effect:** 12.5% of mean |SHAP| is now on non-driver features, down from 47%.
* **Every served value changes:**
  * Hold-out probabilities move by 0.094 on average, and by up to 0.506. Risk tiers, CLV, the dashboard KPIs and segment figures change with them.
  * The frontend unit tests use recorded fixtures (`frontend/src/test/fixtures/`), which still hold values from the previous model. They test page behaviour, not live numbers, and were not regenerated here.
* **Tests:**
  * 494 backend tests pass.
  * Tests were changed only where the model change explains it:
    * `test_prediction_coverage.py`: the expected config is now `regularised_monotonic` and the hold-out AUC 0.7597. The out-of-fold provenance check now compares at half a rounding unit (see the comment in the test).
    * `test_clv.py`: the tier-boundary customers were re-selected.
  * `docs/ml/results/evaluation_results.json`, `shap_validation.json` and `prediction_coverage.json` were regenerated by their own scripts.

## 8. Limitations

* **The directions come from the synthetic generator,** which is the ground truth for this dataset. They should be revisited if the model is ever trained on real data.
* **`monthly_charge` is left unconstrained.** Its effect is not monotone in the generator: it acts only through the Basic + Mobile interaction.
* **The check covers the five constrained inputs over their training ranges.** XGBoost guarantees monotonicity by construction for constrained features, and the sweep confirms it empirically.
