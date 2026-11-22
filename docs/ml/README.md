# ChurnIQ — ML Validation (Epic CHURN-2, E2: Machine Learning & Explainability)

Validation of the churn model, its explanations and the CLV logic. Covers Jira Stories CHURN-13 to CHURN-17.

| Story | Report | Script / code | Tests |
|---|---|---|---|
| CHURN-13 Review XGBoost pipeline | [01-pipeline-review.md](01-pipeline-review.md) | `backend/churniq_ml_pipeline.py`, `backend/churniq_core.py` | `tests/test_pipeline_preprocessing.py` |
| CHURN-14 Evaluate model performance | [02-model-evaluation.md](02-model-evaluation.md) | `backend/evaluate_model.py` | `tests/test_model_evaluation.py` |
| CHURN-15 Validate SHAP explanations | [03-shap-validation.md](03-shap-validation.md) | `backend/validate_shap.py` | `tests/test_shap_validation.py` |
| CHURN-16 Verify CLV calculation and tiers | [04-clv-verification.md](04-clv-verification.md) | `backend/churniq_core.py` | `tests/test_clv.py` |
| CHURN-17 Model improvement research | [05-model-improvement-research.md](05-model-improvement-research.md) | `backend/model_experiments.py` | `tests/test_model_improvement.py` |

| Follow-up audit (CHURN-16 bugs, re-verification, Git audit) | [06-followup-audit.md](06-followup-audit.md) | `backend/verify_model_improvement.py` | — |

Machine-readable results are in [`results/`](results/): `evaluation_results.json`, `shap_validation.json`, `model_experiments.json` and `model_improvement_verification.json`.

## Headline findings

- **Bug fixed: what-if predictions ignored every categorical feature.** A single-row `get_dummies(drop_first=True)` zeroed all 19 one-hot columns. A no-change `/whatif` moved churn probability by 0.157 on average and changed the risk tier for 327 of 1,000 customers. After the fix: Δ ≤ 0.0001 and 0 tier changes.
- **Committed model on the held-out test set:** ROC-AUC **0.717**, accuracy 0.667, precision 0.623, recall 0.578, F1 0.599. The ceiling set by the data's own label noise is about 0.794.
- **SHAP is computed correctly** (additivity error < 3×10⁻⁶). However, 47% of the explanation weight sits on features that don't drive churn. The plain-English reason text also contradicted customers' actual values (fixed).
- **The CLV formula is correct.** Tier assignment was inconsistent between endpoints for 156 customers (fixed). 4,000 unscored customers show CLV ₹0 (open, needs a team decision).
- **A regularised XGBoost without SMOTE improves test ROC-AUC from 0.724 to 0.758** (paired 95% CI of the gain +0.018 to +0.052). It also improves calibration and cuts noise-driven explanations from 47% to 11%. It's available as `--model-config regularised`; the production artifact is unchanged pending team sign-off.

## How to run

```bash
cd backend
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

```bash
python evaluate_model.py
```

```bash
python validate_shap.py
```

```bash
python model_experiments.py
```

```bash
python churniq_ml_pipeline.py --output-dir pipeline_outputs --model-config baseline
```

- `python -m pytest` runs the ML validation suite (about 15 s).
- `evaluate_model.py` (CHURN-14), `validate_shap.py` (CHURN-15) and `model_experiments.py` (CHURN-17, about 40 s) each regenerate their file in `docs/ml/results/`.
- The last command retrains the model into a scratch folder. It never overwrites the committed files unless you pass `--output-dir .`.

The older script-style checks still run directly: `python test_api_endpoints.py`. `python test_similarity_engine.py` rewrites the committed `.joblib` similarity artifacts, so run it in a copy of `backend/`.

## Test results (this branch)

| Suite | Result |
|---|---|
| `python -m pytest` (new ML suite) | **85 passed**, 0 failed, 1 xfailed (Bug A full fix pending, `tests/test_unscored_and_demo_customers.py`) |
| `npm run build` (frontend) | builds successfully (only the existing chunk-size advisory) |
| `python test_api_endpoints.py` (existing) | passed |
| `python test_similarity_engine.py` (existing, run in a copy of `backend/`) | passed |
| Regression check: the bug-specific tests run against the original `main.py` | 5 failed (as expected, proving the tests detect the bugs) |
| API response structure, old vs new code (11 endpoints/calls) | identical keys and types. Only the intended values change (see `03` and `04`) |

Environment: Python 3.13, Linux. Pinned versions from `requirements.txt` (numpy 2.2.0, pandas 2.3.3, scikit-learn 1.6.1, xgboost 2.1.4, shap 0.46.0, fastapi 0.115.12) plus `requirements-dev.txt`. The frontend wasn't run, because no frontend code changed and every API field it reads keeps its name and type.

## Open issues requiring a team decision

1. Whether to adopt the `regularised` model for production. That means regenerating the committed artifacts and re-adding the demo customer (CHURN-17, rec. 1).
2. Out-of-fold scoring for the 4,000 customers with no prediction (CHURN-16, Bug A full fix). The interim fix is in place: they're now reported as NOT_SCORED instead of 0 % / ₹0, and the HTTP 500s are gone. Bug B (the demo customer's hard-coded CLV and hand-written reasons) is fixed. See `06`.
3. The operating threshold for "flag for retention", based on business costs (CHURN-17, rec. 3).
4. Confirming the CLV business assumptions: past vs remaining tenure, the 6-month floor, and the ₹3k/₹8k tiers (CHURN-16).
5. The committed model can't be reproduced bit-for-bit. Its booster records `seed: 0`, not the pipeline's 42, so its exact training provenance is unknown (CHURN-13; see `06` §6).
