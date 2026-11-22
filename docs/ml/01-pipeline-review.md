# CHURN-13 — XGBoost Pipeline Review

**Scope:** `backend/churniq_ml_pipeline.py` end to end, plus the inference path in `backend/main.py` that has to apply the same preprocessing.
**Epic:** CHURN-2 (E2 — Machine Learning & Explainability)

## 1. Pipeline as implemented

| Stage | What happens | Where |
|---|---|---|
| A. Data | 5,000 synthetic customers, all seeds = 42. Churn label is sampled from `sigmoid(churn_score − 1.5)` | `generate_dataset()` |
| B. EDA | 6-panel PNG dashboard | `save_eda_dashboard()` |
| C. Preprocessing | Drops identifiers and leakage columns, adds 4 engineered features, ordinal-encodes `plan_type`, one-hot encodes 5 nominal columns (`drop_first=True`) | `churniq_core.encode_features()` |
| C. Split | 80/20 `train_test_split(stratify=y, random_state=42)`: 4,000 train / 1,000 test | `split_data()` |
| D. SMOTE | `SMOTE(k_neighbors=5, random_state=42)` on the **training split only**: 4,000 → 4,554 rows (2,277 / 2,277) | `apply_smote()` |
| E. Training | `XGBClassifier` (parameters below) | `train_model()` |
| F. Evaluation | Accuracy, Precision, Recall, F1, ROC-AUC, confusion matrix on the test split | `evaluate()` |
| G. SHAP | `TreeExplainer` on the test split | `compute_shap()` |
| H. Predictions | `customer_predictions.csv`: test customers only, with probability, risk level, top-3 SHAP reasons and CLV | `build_predictions()` |

### Preprocessing details

- **Dropped as identifiers:** `customer_id`, `name`, `email`.
- **Dropped as target leakage:** `churn_probability`, `clv_score` and `clv_segment`. All three are derived from the generator's true churn probability.
- **Engineered features:**
  - `engagement_score = watch_hours × logins / 30`
  - `friction_score = payment_failures_3m + support_tickets`
  - `inactivity_flag = last_login_days_ago > 14`
  - `is_new_customer = tenure_months < 6`
- **Encoding:**
  - `plan_type` is ordinal: Basic=0, Standard=1, Premium=2.
  - `gender`, `country`, `preferred_genre`, `device_type` and `payment_method` are one-hot encoded with `drop_first=True`. The baseline levels are Female, Canada, Action, Laptop and Credit Card.
- **Scaling:** none, by design. Tree splits don't depend on feature scale.
- **Feature selection:** none. All 33 encoded features are used.
- **Missing values:** the generator produces none. At inference, missing raw values get the defaults in `main.build_feature_row`, and an unknown category level encodes as the baseline level.

### Training configuration (recorded)

| Parameter | Value |
|---|---|
| `n_estimators` | 200 |
| `max_depth` | 5 |
| `learning_rate` | 0.1 |
| `subsample` | 0.8 |
| `colsample_bytree` | 0.8 |
| `eval_metric` | logloss |
| `random_state` | 42 |
| SMOTE | `k_neighbors=5`, `random_state=42`, training split only |
| Committed artifact | trained with XGBoost **2.1.4** (read from the booster config) |

## 2. Verification results

| Check | Result |
|---|---|
| SMOTE applied only to training data | ✅ Called only on the training split. The test split keeps the real class ratio (43.1% churn). No test row appears in the resampled training data. Original training rows are preserved unchanged. |
| Train/test overlap | ✅ None (disjoint indices, no duplicated feature rows) |
| Stratification | ✅ 43.08% churn in train vs 43.10% in test |
| Leakage columns excluded | ✅ None of the identifier, leakage or target columns reach the model |
| Committed artifacts consistent | ✅ `churniq_model.pkl` + `feature_names.pkl` reproduce `customer_predictions.csv` (max difference 5×10⁻⁵, i.e. 4-dp rounding) |
| Split reproducible | ✅ The rebuilt test split is exactly the 1,000 customers in `customer_predictions.csv` |
| Dataset reproducible | ✅ `generate_dataset(seed=42)` reproduces every non-name column of the committed CSV. Names come from an unseeded Faker. |
| Training deterministic in a fixed environment | ✅ Two full pipeline runs gave identical predictions |
| `eval_set=[(X_test, y_test)]` | Didn't change the model: predictions were identical with and without it, because there's no early stopping. Removed anyway, since monitoring on the test set encourages test-set tuning. |

## 3. Issues found

### 🔴 Bug 1 — Training/serving skew in `POST /whatif` (fixed)

`main.build_feature_row()` called `pd.get_dummies(..., drop_first=True)` on a **single row**. With only one row, each categorical column has exactly one level, and `drop_first` removes it. As a result, **all 19 one-hot columns were always 0** at inference, so the model saw every customer as Female / Canada / Action / Laptop / Credit Card.

I measured this on the 1,000 test customers by sending a no-change `/whatif` request, which should return the original probability:

| | Mean \|Δ prob\| | Max \|Δ prob\| | Risk tier changed |
|---|---|---|---|
| Before fix | **0.157** | **0.568** | **327 / 1000** |
| After fix | 0.00002 | 0.0001 | 0 / 1000 |

**Fix:** a new shared module, `backend/churniq_core.py`. Its `encode_features()` encodes categoricals against the fixed training category levels, so one row and the full table encode identically. Both the pipeline and `main.build_feature_row()` now call it, so there's a single preprocessing implementation. Tests: `test_single_row_encoding_equals_batch_encoding`, `test_api_build_feature_row_matches_training_encoding` and `test_noop_whatif_returns_original_probability`. All three fail on the old code.

The demo customer `CUST99999` still shows a 0.96 → 0.98 change. Its 0.96 probability was hand-written into the CSV by `fix_cust99999.py` rather than produced by the model.

### 🟠 Issue 2 — Running the pipeline destroyed committed data (fixed)

The whole pipeline ran at import time and wrote to `./`. That overwrote `ott_churn_dataset.csv`, removing the `email` column and the `CUST99999` demo row added by `add_emails.py`, and overwrote `customer_predictions.csv`. It also couldn't be imported or tested.

**Fix:** the pipeline is now a set of functions plus `main()`, guarded by `if __name__ == "__main__"`.
- Output goes to `--output-dir`, which defaults to `pipeline_outputs/` (git-ignored).
- Heavy optional imports (Faker, matplotlib, seaborn, SHAP) happen only where they're used.
- The original teaching comments and VIVA tips are kept.

### 🟡 Issue 3 — The committed model can't be reproduced bit-for-bit (documented, not fixed)

Retraining with the pinned versions (Linux, XGBoost 2.1.4, scikit-learn 1.6.1) gives a different model: max probability difference 0.39, test AUC 0.7239 vs 0.7167. I ruled out:
- the train/test split: it matches exactly;
- the dataset: it matches exactly;
- `eval_set`: no effect;
- the imbalanced-learn version: 0.12.4, 0.13.0 and 0.14.2 all give the same result;
- float vs integer SMOTE input: the committed model's split thresholds are integers, which matches integer SMOTE output.

The remaining likely cause is XGBoost's row/column subsampling RNG differing by platform. The codebase has Windows-specific handling, so the model may have been trained on Windows. **This is unconfirmed.**

**Mitigation:** evaluation uses the committed artifact (`evaluate_model.py`) rather than a retrain. CHURN-17 compares candidates against a baseline retrained in the same environment.

### 🟡 Issue 4 — Dependencies needed for training are missing from requirements (fixed)

`requirements.txt` is the deployment set. It doesn't include `imbalanced-learn`, `faker`, `matplotlib` or `seaborn`, which the pipeline needs, or `pytest`/`httpx` for tests. `imbalanced-learn` was never pinned anywhere. Added `backend/requirements-dev.txt` with the versions used for this validation, and left the deployment requirements unchanged.

### ℹ Observations (no change made)

- Only the 1,000 **test** customers (plus the demo row) get predictions. The other 4,000 appear in the API with `churn_prob` 0, LOW risk and CLV ₹0. See `04-clv-verification.md`, open issue 1.
- SHAP values are in **log-odds** units, not probability. The original comments said "pushed churn probability up by +2.17"; the comments are now corrected.
- The original comment said the base churn rate was "~30-35%". The actual rate is 43.1%.

## 4. Changes made

| File | Change |
|---|---|
| `backend/churniq_core.py` (new) | Shared feature engineering, encoding, risk thresholds, SHAP-reason formatting and CLV |
| `backend/churniq_ml_pipeline.py` | Restructured into functions; uses the shared core; removed test `eval_set`; `--output-dir`; `--model-config` (CHURN-17) |
| `backend/main.py` | `build_feature_row` uses the shared encoder (Bug 1); helpers delegate to the core |
| `backend/requirements-dev.txt` (new) | Training and test dependencies |
| `backend/tests/test_pipeline_preprocessing.py` (new) | 14 tests covering the checks above |
