# ChurnIQ — API Quality (Epics CHURN-3 / CHURN-4: E3 Backend & API, E4 Similarity & What-If)

This report covers Jira Stories **CHURN-18 to CHURN-25**. It documents the FastAPI backend in `backend/main.py`: every endpoint, its contract, input validation, error handling, the Gemini retention flow, the KNN similarity and What-If endpoints, and edge-case coverage.

Everything here was measured on branch `feature/shikhar-e3-e4-api-quality`, built on `main` @ `7d605c5` (Aryan's E2 merge). Environment: **Python 3.10.13** (as in `backend/runtime.txt`), Linux, FastAPI 0.115.12, Pydantic 2.11.3, pandas 2.3.3, numpy 2.2.0, scikit-learn 1.6.1, xgboost 2.1.4.

| Story | Section | Tests |
|---|---|---|
| CHURN-18 Review all FastAPI endpoints | [§1](#1-endpoint-inventory-churn-18) | `tests/test_api_contracts.py` (inventory), `test_api_endpoints.py` |
| CHURN-19 Validate API response formats | [§2](#2-response-format-validation-churn-19) | `tests/test_api_contracts.py` |
| CHURN-20 Improve input validation | [§3](#3-input-validation-rules-churn-20) | `tests/test_api_validation.py` |
| CHURN-21 Handle backend errors | [§4](#4-error-handling-strategy-churn-21) | `tests/test_api_errors.py` |
| CHURN-22 Gemini retention API integration test | [§5](#5-gemini-retention-api-churn-22) | `tests/test_retention_gemini.py` |
| CHURN-23 KNN similarity testing | [§6](#6-knn-similarity-churn-23) | `tests/test_similarity_api.py`, `test_similarity_engine.py` |
| CHURN-24 What-If prediction testing | [§7](#7-what-if-prediction-churn-24) | `tests/test_whatif_api.py` |
| CHURN-25 Edge cases + coverage | [§8](#8-edge-cases-and-coverage-churn-25), [§9](#9-test-commands-and-results) | all of the above |

Bugs found and fixed: **CHURN-39 to CHURN-44** ([§10](#10-bugs-found)). Known limitations are in [§11](#11-known-limitations-and-unresolved-issues).

---

## 1. Endpoint inventory (CHURN-18)

Every route in `backend/main.py`. Each one was exercised with valid data through FastAPI's `TestClient` (the automated suite) and over real HTTP against `uvicorn` ([§9.3](#93-end-to-end-http-run)). `/docs` (Swagger) and `/redoc` both render. `tests/test_api_contracts.py::test_route_inventory_matches_documentation` fails if a route is added or removed without updating this table.

| Method | Path | Purpose | Inputs | Output (response model) | Status | External dependency |
|---|---|---|---|---|---|---|
| GET | `/` | Health check + component status | — | `HealthResponse` | ✅ Works | — |
| GET | `/customers` | Risk table + KPI summary | query `risk_level`, `plan_type`, `limit` (1–10000, default 500), `sort_by` | `CustomersResponse` | ✅ Works (validation fixed, CHURN-40) | — |
| GET | `/customer/{customer_id}` | One customer: profile, churn probability, SHAP reasons, CLV | path `customer_id` | `CustomerDetailResponse` | ✅ Works | — |
| POST | `/whatif` | Live re-prediction with changed features | body `WhatIfRequest` | `WhatIfResponse` | ✅ Works (validation fixed, CHURN-39) | — |
| POST | `/api/customer-similarity` | KNN look-alike customers | body `CustomerSimilarityRequest` | `CustomerSimilarityResponse` | ✅ Works (CHURN-41) | — |
| POST | `/customer-similarity` | Alias of the above (identical output) | same | same | ✅ Works | — |
| GET | `/retention/{customer_id}` | Retention email + 2 actions | path `customer_id` | `RetentionResponse` | ✅ Works. Gemini mocked in tests; rule-based fallback verified live (CHURN-42) | **Google Gemini** (optional, `GEMINI_API_KEY`) |
| POST | `/send-email` | Send the retention email to the demo inbox | body `SendEmailRequest` | `SendEmailResponse` | ⚠️ Works with SMTP mocked; returns 503 when not configured (CHURN-44) | **Gmail SMTP** (`GMAIL_SENDER`, `GMAIL_APP_PASS`) |
| GET | `/email-status` | Is email sending configured? | — | `EmailStatusResponse` | ✅ Works (addresses now masked) | — |
| GET | `/segments` | Churn by plan, device, tenure, genre, CLV; 12-month trend | — | `SegmentsResponse` | ✅ Works | — |
| GET | `/dashboard/summary` | All dashboard KPIs + top 5 priority customers | — | `DashboardResponse` | ✅ Works | — |
| GET | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, OpenAPI schema | — | HTML / JSON | ✅ Works | Swagger/ReDoc assets load from a CDN in the browser |

**Status codes used.** 200 success. 404 unknown customer or route. 405 wrong method. 409 customer not scored, or its fold model unavailable. 422 malformed or out-of-range input. 500 unexpected error. 502 SMTP failure. 503 optional component not configured (email, similarity engine).

**Externally dependent endpoints.** `/retention` calls Gemini only when `GEMINI_API_KEY` is set. No key was available in this environment, so **no live Gemini call was made**. All Gemini behaviour was verified with a mocked client ([§5](#5-gemini-retention-api-churn-22)). `/send-email` needs Gmail credentials. It was tested with a mocked `smtplib.SMTP_SSL`, and **no email was sent**.

---

## 2. Response format validation (CHURN-19)

Every endpoint now declares a Pydantic `response_model`, so FastAPI validates each response at runtime. Field names did not change, so existing frontend code keeps working. `tests/test_api_contracts.py` additionally checks:

- **Types and nulls.** `churn_prob` is `null` **if and only if** the customer is NOT_SCORED. Otherwise it is in [0, 1], and `risk_level` is HIGH, MEDIUM or LOW and matches `get_risk_level(churn_prob)`. `scored` and `clv_score` agree with it. No NaN or Infinity appears anywhere in any response.
- **Consistency across endpoints.** For one customer, `churn_prob` is identical in `/customers`, `/customer/{id}`, `/retention/{id}`, `/whatif` (`original_churn_prob`) and the similarity `selected_customer`.
- **Derived fields.** `churn_percent == f"{churn_prob*100:.1f}%"`. In What-If: `change ≈ new − original`, `change_percent` is formatted from `change`, and `improved == (change < 0)`.
- **No undeclared fields** on `/customer/{id}`, `/whatif` and `/retention`.
- **OpenAPI.** Every operation has a `$ref` response schema, and the `ErrorResponse` schema is published.

### Inconsistencies found and fixed

| # | Inconsistency | Fix | Frontend impact |
|---|---|---|---|
| 1 | `/retention` `churn_prob` was a **percentage** (`99.6`); every other endpoint uses 0–1 (`0.9958`) | Now 0–1. Added `churn_percent` and `risk_level` (CHURN-42) | None. The frontend doesn't read this field |
| 2 | `/retention` `generated_by` claimed `gemini-1.5-flash` while a different model was called | Reports the configured `GEMINI_MODEL_NAME` (CHURN-42; configurable since the model fix, see §5.1) | None |
| 3 | Fallback content identifiable only by `generated_by` | Added `ai_generated: bool` and `fallback_reason` | None (additive) |
| 4 | 422 errors had a **list** in `detail`; every other error had a string | Every error: `detail` is a string, plus `error`, `status_code`, `errors[]` (CHURN-43) | **Fixes** `CustomerSimilarity.jsx`, which renders `data.detail` and couldn't render a list |
| 5 | Unhandled errors were `text/plain` | JSON `ErrorResponse` with `request_id` | None |
| 6 | `/` reported `model_loaded: true` as a constant | Real status, plus `fold_models_loaded`, `similarity_ready`, `email_enabled` | None (additive) |
| 7 | `/email-status` and `/send-email` returned full Gmail addresses | Masked, e.g. `r*************n@gmail.com` (CHURN-44) | The "Email sent to …" message shows the masked address |

Fields that are legitimately `null`: `churn_prob`, `clv_score`, `prediction_source` and `clv_breakdown.retention_factor` for NOT_SCORED customers; `historical_churn` for customers with no label; `avg_churn_probability` and `avg_churn_rate_pct` when nobody is scored; `fallback_reason` when Gemini output was used.

---

## 3. Input validation rules (CHURN-20)

| Input | Rule | Invalid → |
|---|---|---|
| `customer_id` (path and body, every endpoint) | Surrounding whitespace ignored. 1–32 characters of `A–Z a–z 0–9 _ -` | malformed → **422**; well-formed but unknown → **404** `customer_not_found` |
| `/whatif` body | `extra='forbid'`: unknown fields are rejected (a typo used to be a silent no-op) | 422 |
| `watch_hours_per_week` | number, finite, 0–168 (training range 0.5–40) | 422 |
| `tenure_months` | strict integer, 1–240 (training 1–72) | 422 |
| `payment_failures_3m` | strict integer, 0–20 (training 0–4) | 422 |
| `support_tickets` | strict integer, 0–100 (training 0–5) | 422 |
| `logins_last_30_days` | strict integer, 0–300 (training 1–26) | 422 |
| `monthly_charge` | strict integer, 1–5000 (training {199, 499, 799}) | 422 |
| any What-If field = `null` / omitted | keeps the customer's actual value (unchanged behaviour) | — |
| NaN, ±Infinity, `"12"`, `true`, arrays, objects | rejected. NaN used to be **silently replaced by 5.0 h/week** (CHURN-39) | 422 |
| `n_neighbors` | strict integer 1–50. `null` or omitted → 5. Used to silently rewrite 0 or negative values to 5 and accept 5000 (CHURN-41) | 422 |
| `/customers?limit` | 1–10000 (`limit=-1` used to drop the last row) | 422 |
| `/customers?risk_level` | HIGH / MEDIUM / LOW / NOT_SCORED, case-insensitive (used to be silently ignored) | 422 |
| `/customers?plan_type` | Basic / Standard / Premium, case-insensitive (used to be silently ignored) | 422 |
| `/customers?sort_by` | allow-list: `churn_prob, clv_score, monthly_charge, tenure_months, watch_hours_per_week, logins_last_30_days, payment_failures_3m, support_tickets, customer_id, name, plan_type, risk_level`. **Blocks** the generator oracle `churn_probability` and the label `churn` (CHURN-40) | 422 |
| `/send-email` `subject` | 1–200 characters, single line (CR/LF rejected: header injection) | 422 |
| `/send-email` `body` | 1–5000 characters, not blank; HTML-escaped in the HTML part | 422 |
| Empty body, malformed JSON, `[]`, `null`, wrong content type | — | 422 |

**Bounds and the model.** The What-If bounds are physically plausible limits, not the training range. Between the training maximum and the bound, XGBoost does not extrapolate: the prediction stays flat at the edge value. A value such as 100 h/week is accepted and answered, but it carries no more signal than 40 h/week.

**Preserved behaviour.** A customer with no out-of-sample prediction (NOT_SCORED, Aryan's CHURN-37) still gets **409** on `/whatif` and `/retention`, now with `error: customer_not_scored`. That customer is still shown as `NOT_SCORED` with `null` probability and CLV elsewhere. They can be filtered with `/customers?risk_level=NOT_SCORED`.

---

## 4. Error-handling strategy (CHURN-21)

**One JSON shape for every error**, whether it is raised by our code, by FastAPI validation, by routing or by a crash:

```json
{
  "detail": "Customer 'NOPE' not found. Total customers: 5001. Example valid ID: CUST00001",
  "error": "customer_not_found",
  "status_code": 404,
  "errors": [{"field": "watch_hours_per_week", "message": "Input should be a finite number", "type": "finite_number"}],
  "request_id": "3f2c9a1b7d4e"
}
```

`errors` appears only on 422, and `request_id` only on unexpected 500s. `detail` is always a human-readable string, so the frontend's `data?.detail` keeps working.

| Situation | Status / `error` | What the client sees | What is logged (`churniq.api` logger) |
|---|---|---|---|
| Unknown customer | 404 `customer_not_found` | message with an example ID | — |
| Malformed input | 422 `validation_error` | field + message, **input value not echoed** | — |
| Customer not scored | 409 `customer_not_scored` | message (unchanged wording) | — |
| Fold models missing or mismatched | 409 `fold_model_unavailable` | message. **Never** falls back to the in-sample production model | warning at startup |
| Similarity engine unavailable | 503 `similarity_unavailable` | message | error at startup / request |
| Email not configured | 503 `email_not_configured` | message | warning |
| SMTP auth failure / delivery error | 502 `smtp_auth_failed` / `smtp_error` (auth was **401**, which wrongly implied the *client's* credentials) | generic message | SMTP code / exception class, redacted |
| What-If model failure or non-finite output | 500 `prediction_failed` | generic message | redacted traceback + customer ID |
| Similarity crash | 500 `similarity_failed` | generic message | redacted traceback |
| Anything else | 500 `internal_error` + `request_id` | generic message | request_id, method, path, redacted traceback |
| Gemini failure | 200 with labelled fallback (§5) | `ai_generated:false`, `fallback_reason` | warning, redacted |

**No leaks.** Exception text, stack traces, file paths and SMTP server replies never reach the client. Log messages and tracebacks pass through `redact()`, which removes the configured `GEMINI_API_KEY` and `GMAIL_APP_PASS` values, any `AIza…` key and `key=` / `token=` / `password=` query values. A test found that `logger.exception` printed the raw exception message in the traceback, so tracebacks are now formatted and redacted explicitly.

**Startup failures.**

- **Required artifacts** (`churniq_model.pkl`, `feature_names.pkl`, `customer_predictions.csv`, `ott_churn_dataset.csv`): if one is missing or corrupt, `ArtifactLoadError` is raised with a one-line reason and the server refuses to start. Tested in a subprocess.
- **Optional artifacts** (`oof_fold_models.pkl`, `similarity_*.joblib`) degrade to 409 or 503. The fold-bundle feature check is now an explicit check instead of an `assert`, which `python -O` strips.

`/segments` used to call `np.random.seed(42)` on every request, re-seeding NumPy's global RNG. It now uses a local `RandomState(42)`, which gives identical numbers.

---

## 5. Gemini retention API (CHURN-22)

`GET /retention/{id}` builds a prompt from the customer's profile, model churn probability, CLV and top 3 SHAP reasons. It then calls Gemini (model `GEMINI_MODEL_NAME`, default `gemini-3.5-flash`; timeout `GEMINI_TIMEOUT_SECONDS`, default 20 s) and validates the reply. On any failure it returns rule-based content that is **always labelled as fallback**.

| Scenario | Result | Test |
|---|---|---|
| 6 customers: 2 HIGH, 2 MEDIUM, 2 LOW; holdout + out-of-fold | 200, `ai_generated: true`, `generated_by` equal to the configured model (default `"gemini-3.5-flash"`), `fallback_reason: null`. The prompt contains that customer's churn % and all 3 SHAP reasons | `test_gemini_output_for_customers_across_risk_levels` |
| Same 6 customers, **no API key** | 200, `generated_by: "rule-based-fallback"`, `ai_generated: false`, `fallback_reason: "gemini_not_configured"`, `priority == risk_level` | `test_missing_api_key_uses_labelled_rule_based_fallback` |
| Timeout (`DeadlineExceeded`, `TimeoutError`) | labelled fallback, `gemini_timeout` | `test_upstream_failures_fall_back_without_crashing` |
| Quota 429, 503, 403 bad key, network error, unexpected exception | labelled fallback, `gemini_api_error` | same |
| Non-JSON, truncated JSON, JSON array, empty `email`, missing `subject`, `actions` not a non-empty list of strings, blocked response | labelled fallback, `gemini_invalid_response`. **Never** passed off as AI output | `test_unusable_gemini_output_is_never_passed_off_as_ai` |
| Markdown-fenced JSON | accepted as Gemini output | `test_markdown_fenced_json_is_accepted` |
| Invalid `priority` from Gemini | replaced by the customer's risk tier | `test_invalid_gemini_priority_falls_back_to_risk_tier` |
| Unknown / NOT_SCORED customer | 404 / 409; **Gemini is not called** | `test_unknown_and_not_scored_customers_do_not_call_gemini` |
| 403 error whose text contains the key | key absent from the response **and** from all logs (`[REDACTED]`) | `test_api_key_never_appears_in_logs_or_response` |
| Server start with no key / empty / placeholder / fake key (subprocess) | `GEMINI_ENABLED` false / false / false / true; no crash; key never printed | `test_startup_gemini_configuration` |
| Each rule-based template (billing, engagement, tenure, generic) | complete email, 2 actions, matching offer | `test_every_rule_based_template_is_reachable_and_complete` |

No API key is hard-coded. The key is read only from the `GEMINI_API_KEY` environment variable, and `.env` files are git-ignored.

### 5.1 Gemini configuration

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | *(unset)* | Google AI Studio key. Unset, empty or the placeholder `YOUR_GEMINI_API_KEY` disables Gemini, and every response is the labelled rule-based fallback. Read from the environment only; never commit it (`.env` files are git-ignored). |
| `GEMINI_MODEL_NAME` | `gemini-3.5-flash` | Model used for `generate_content` and reported in `generated_by`. Surrounding whitespace is stripped; unset or blank falls back to the default. |
| `GEMINI_TIMEOUT_SECONDS` | `20` | Upper bound on one Gemini call. |

**Why the default is `gemini-3.5-flash`.** The project's direct Google REST API test showed that `gemini-2.5-flash` returns **404** for the project's API key, while `gemini-3.5-flash` generates content. Until the model fix, the name was hard-coded, so every call 404'd and the API silently served the rule-based fallback (`fallback_reason: "gemini_api_error"`).

**To use a different model**, set the variable before starting the server. No code change is needed:

```bash
export GEMINI_MODEL_NAME=gemini-3.5-pro
```

On Render, add `GEMINI_MODEL_NAME` under the service's **Environment** settings next to `GEMINI_API_KEY`. At startup the server prints `✓ Gemini API configured — model <name>`; it never prints the key.

Tests (`tests/test_retention_gemini.py`):
- the default is `gemini-3.5-flash`
- the override works, including blank and whitespace-only values
- the real `google.generativeai` client sends `models/<selected model>` on the wire (only the network transport is stubbed)
- `generated_by` always equals the configured model when Gemini output is used, and is never a model name for fallback content

### 5.2 Manual live smoke test

The automated tests mock Gemini, so a real call needs a valid key. Run this locally and never paste the key into chat, logs or commits. Reading it with `read -s` keeps it out of your shell history:

```bash
cd backend
```

```bash
read -rs GEMINI_API_KEY && export GEMINI_API_KEY
```

```bash
uvicorn main:app --port 8000
```

In a second terminal:

```bash
curl -s localhost:8000/retention/CUST00001 | python -c "import sys,json; d=json.load(sys.stdin); print({k: d[k] for k in ('generated_by','ai_generated','fallback_reason')})"
```

Expected on success: `{'generated_by': 'gemini-3.5-flash', 'ai_generated': True, 'fallback_reason': None}`, or your `GEMINI_MODEL_NAME` if you overrode it. If `ai_generated` is `False`, `fallback_reason` and the server log (redacted) give the cause. For example, `gemini_api_error` with a 404 in the log means the key can't access that model.

---

## 6. KNN similarity (CHURN-23)

`POST /customer-similarity` (and `/api/customer-similarity`) was checked against an **independent brute-force Euclidean search** over the engine's own standardised feature space. The tests do not just re-read the engine's output.

| Property | Result |
|---|---|
| Neighbours ordered closest first (`distance` ascending, `similarity_score` descending) | ✅ for 21 customers (holdout, out-of-fold, demo) × k ∈ {1, 3, 5, 10, 50} |
| Requested count respected | ✅ k = 1…50. k > dataset returns all other customers (engine level) |
| Customer never returned as their own neighbour; no duplicates | ✅ |
| Distances equal brute-force distances (±1e-4); same neighbour set | ✅ 21 customers, k = 10 |
| `similarity_score == round(100 / (1 + distance), 1)` | ✅ |
| Smaller k is a prefix of larger k; results deterministic; alias identical | ✅ |
| **Normalisation preserved:** numeric features StandardScaled (mean 0, sd 1 over the dataset) | ✅ |
| **Leakage protection preserved:** `churn`, `churn_probability`, `clv_score`, `clv_segment`, IDs, `churn_prob`, `risk_level` are not features. Scrambling `churn_probability` and `churn_prob` leaves neighbours unchanged | ✅ |
| `historical_churn` / `historical_outcome` = dataset label | ✅ |
| Neighbour `churn_prob` = served model prediction, not the generator value (Aryan's CHURN-37) | ✅ |
| Unscored neighbour → `churn_prob: null`, `risk_level: "NOT_SCORED"` | ✅ |
| First insight's churn count matches the returned neighbours | ✅ |
| Invalid k (0, −1, 51, 5000, 2.5, "5", true) | 422 (API), ValueError (engine) |

`test_similarity_engine.py` was extended with counts 1/3/10/50, invalid k and k > dataset. It now writes its artifacts to a temporary directory; it used to overwrite the committed `similarity_*.joblib` files, so it is now part of the default `pytest` run.

---

## 7. What-If prediction (CHURN-24)

| Property | Result |
|---|---|
| **No-op reproduces the served probability** | Max \|change\| = **0.0** over **all 5,001 customers** (measured). Tests cover about 300 customers across holdout, out-of-fold and demo with tolerance 1e-4 (both values are rounded to 4 dp). Setting fields to their current values is also a no-op |
| **Out-of-fold customers use their own fold model** | Replaced each fold model with a sentinel; every OOF customer got exactly its fold's sentinel value. The production model raised if touched |
| **Test and demo customers use the production model** | Sentinel production model used; fold models raised if touched |
| **No in-sample fallback** | With fold models missing, OOF customers get **409** `fold_model_unavailable`. The production model is never called |
| **No generator-oracle fallback** | Overwriting `churn_probability` and flipping `churn` changes no What-If output |
| Model input | Exact `FEATURE_NAMES` order. Only the changed feature and its engineered dependents (`friction_score`) differ from the customer's feature row. One-hot columns are intact (CHURN-13 regression guard) |
| Response matches `WhatIfResponse` | ✅ validated with the Pydantic model; field set exact; derived fields consistent |
| NOT_SCORED customer | 409 `customer_not_scored` (preserved) |
| Invalid input | 422 (see §3); a 150-request fuzz test produced no 500s |

**Direction of key features**, measured over 400 customers (200 holdout + 200 OOF):

| Change | Mean Δ churn prob | Share ↑ | Share ↓ | Test asserts |
|---|---|---|---|---|
| `payment_failures_3m` → 4 | +0.352 | 96% | 3% | mean > 0.1, ≥ 90% ↑ |
| `support_tickets` → 5 | +0.341 | 96% | 1% | mean > 0.1, ≥ 90% ↑ |
| `tenure_months` → 1 | +0.370 | 95% | 2% | mean > 0.1, ≥ 90% ↑ |
| `watch_hours_per_week` → 0.5 | +0.289 | 88% | 7% | mean > 0.1, ≥ 80% ↑ |
| `payment_failures_3m` → 0 | −0.085 | 1% | 39% (60% already 0) | mean < 0, ≤ 2% rise > 0.01 |
| `tenure_months` → 72 | −0.061 | 35% | 62% | mean < 0 |
| `watch_hours_per_week` → 40 | −0.061 | **42%** | 56% | mean < 0 |
| `logins_last_30_days` → 26 | −0.052 | 32% | 68% | mean < 0 |

**Model observation (not an API defect).** Engagement and loyalty improvements lower risk on average, but **not monotonically per customer**. Raising watch hours to 40 increases predicted risk for 42% of customers. The XGBoost model has no monotonic constraints, and E2's research (docs/ml/05) found 47% of SHAP weight on noise features. The What-If simulator faithfully reports this behaviour, so analysts should read single-customer What-If results as "what the model says", not causal effects. Raised for the ML owners in §11.

---

## 8. Edge cases and coverage (CHURN-25)

| Edge case | Where tested |
|---|---|
| Unknown customer IDs (incl. lower-case, too long, look-alike) on all 4 customer endpoints | `test_api_validation.py`, `test_api_endpoints.py` §8 |
| Malformed IDs (spaces, quotes/SQL, unicode, path traversal, NUL, newline inside, non-string types) | `test_api_validation.py` |
| Empty body, malformed / truncated JSON, `[]`, `null`, bare string, wrong content type | `test_api_validation.py` |
| Boundary values exactly at every What-If bound (accepted) and one step outside (422) | `test_api_validation.py` |
| Extreme values (1e308, −1e308), NaN, ±Infinity (incl. a raw `NaN` JSON token) | `test_api_validation.py` |
| Missing optional fields and explicit `null` (keep actual values; `n_neighbors` → 5) | `test_api_validation.py` |
| `/customers` limits 1 and 10000, every sort field, case-insensitive filters | `test_api_validation.py` |
| NOT_SCORED customers on every endpoint | `test_api_validation.py`, `test_similarity_api.py` |
| Backend failures: model exception, NaN model output, similarity crash / stale index / unavailable, missing / corrupt artifacts, missing fold models, unhandled exception | `test_api_errors.py`, `test_whatif_api.py` |
| External-service failures: Gemini (timeout, quota, auth, network, bad output), SMTP (auth, disconnect) | `test_retention_gemini.py`, `test_api_errors.py` |
| Randomised What-If fuzz (150 requests): only 200 or 422 | `test_api_validation.py` |

### Coverage before and after

The same commands were run before (on `main` @ `7d605c5`) and after (this branch), with Python 3.10.13 and pytest-cov 7.1.0.

**API layer**: `pytest --cov=main --cov=customer_similarity --cov=churniq_core --cov-branch`

| File | Before | After |
|---|---|---|
| `main.py` | 71% (423 stmts, 112 missed) | **93%** (767 stmts, 52 missed) |
| `customer_similarity.py` | 70% (172 stmts, 43 missed) | **92%** (174 stmts, 10 missed) |
| `churniq_core.py` | 97% | 97% (unchanged) |
| **Total (branch-aware)** | **76%** | ****93%**** |

**Whole backend**: `pytest --cov=.` (statement coverage; includes training scripts and test files)

| | Before | After |
|---|---|---|
| Total | 61% (2129 stmts) | **82%** (3399 stmts; includes the new test files) |

`main.py` grew from 423 to 767 statements: response models, error handlers, validation, Gemini handling. Coverage rose even though the denominator grew.

**Remaining uncovered critical paths** (from `--cov-report=term-missing`):

- Import-time branches for optional or misconfigured artifacts: fold-bundle feature mismatch, similarity engine failing to load *and* fit, `email_config.json` fallback, an invalid `GEMINI_TIMEOUT_SECONDS`. The runtime behaviour of each degraded state is tested by monkeypatching (409/503), but the module-level `except` blocks themselves only run on a fresh import with broken files.
- Similarity-engine first-run fit and save when artifacts are absent (`main.py`). The engine's `fit`/`save` are covered directly.
- `if __name__ == "__main__":` uvicorn launcher.
- `build_feature_row` defaults for missing raw values and unknown plan names. These can't be reached through the API now that inputs are validated, and are kept for safety.

---

## 9. Test commands and results

### 9.1 Setup

`requirements-dev.txt` pins `matplotlib==3.11.2`, which requires Python ≥ 3.11. It **cannot be installed on Python 3.10.13** (pre-existing; see §11). The 3.10.13 environment was built with:

```bash
cd backend
```

```bash
pip install -r requirements.txt imbalanced-learn==0.14.2 Faker pytest==9.2.0 httpx==0.28.1 pytest-cov matplotlib seaborn
```

### 9.2 Run

```bash
python -m pytest
```

```bash
python -m pytest --cov=main --cov=customer_similarity --cov=churniq_core --cov-branch --cov-report=term-missing
```

```bash
python test_api_endpoints.py
```

```bash
python test_similarity_engine.py
```

**Results (Python 3.10.13):** **354 passed, 0 failed, 0 skipped** (`python -m pytest`, 1 min 52 s) after the Gemini model fix (`fix/gemini-model-config`). It was 345 when PR #2 merged; both coverage runs below were taken then, and 345 passed each time.

| Suite | Tests |
|---|---|
| Existing ML suite (`tests/test_clv.py`, `test_model_*`, `test_pipeline_preprocessing.py`, `test_prediction_coverage.py`, `test_shap_validation.py`) | 95 — all pass, unchanged |
| `tests/test_api_contracts.py` | 25 |
| `tests/test_api_validation.py` | 117 |
| `tests/test_api_errors.py` | 22 |
| `tests/test_retention_gemini.py` | 47 (38 at PR #2; +9 for model configuration) |
| `tests/test_similarity_api.py` | 26 |
| `tests/test_whatif_api.py` | 20 |
| `test_api_endpoints.py`, `test_similarity_engine.py` (now collected by pytest) | 2 |

Baseline before changes: **95 passed** (the two script tests were run separately and passed).

### 9.3 End-to-end HTTP run

`uvicorn main:app` was started with no Gemini key and exercised with `curl` along the frontend's flow:

1. Health, then `/customers?risk_level=high&limit=1` returns the top customer (CUST02633, out-of-fold).
2. `/dashboard/summary` 200, `/segments` 200, `/customer/CUST02633` 200.
3. `/whatif` (failures 0, tickets 0): 0.9965 → 0.7991 (−19.7%, `improved: true`), scored with the customer's fold model.
4. `/api/customer-similarity` (k=3) 200.
5. `/retention` 200, `rule-based-fallback`, `ai_generated: false`, `fallback_reason: gemini_not_configured`, `churn_prob: 0.9965`.
6. `/send-email` 503 `email_not_configured`.

Raw `NaN` in a body returned 422. A malformed body returned 422. An unknown ID returned 404. The CORS preflight returned 200. The server log had no errors.

### 9.4 Frontend

No frontend file was changed. `npm ci && npm run build` (Node 22, Vite 6.4.1) **succeeded**. The only warning is the pre-existing "chunk larger than 500 kB". The frontend reads `detail` (still a string), `new_churn_prob`, `new_risk`, `improved`, `change_percent`, `subject`, `email` and `sent_to`, all unchanged in type.

---

## 10. Bugs found

All six were found in this review, fixed on this branch, and linked to their stories in Jira.

| Bug | Summary | Story |
|---|---|---|
| CHURN-39 | `/whatif` accepted negative, out-of-range, NaN/Infinity and unknown fields; NaN silently became 5 h/week | CHURN-20, CHURN-24 |
| CHURN-40 | `/customers` ignored invalid filters, `limit=-1` dropped a row, sorting by the generator oracle was allowed | CHURN-18, CHURN-20 |
| CHURN-41 | `n_neighbors` silently rewritten to 5, no upper bound (5000 took about 3 s) | CHURN-23 |
| CHURN-42 | `/retention` mislabelled the model, used a 0–100 scale, had no timeout, could pass empty Gemini output as AI | CHURN-19, CHURN-22 |
| CHURN-43 | Inconsistent error shapes (list `detail`, plain-text 500), exception text leaked | CHURN-19, CHURN-21 |
| CHURN-44 | `/send-email` HTML/header injection, a constant "HIGH RISK" label, SMTP text leaked, Gmail addresses exposed | CHURN-18, CHURN-21 |

---

## 11. Known limitations and unresolved issues

1. **No live Gemini test yet.** No API key was available in the CI/agent environment. The Gemini host is reachable and answers 403 without a key. All Gemini paths are verified with a mock and with the real client library (transport stubbed). Run the manual smoke test in §5.2 with a valid key before closing CHURN-22.
2. **No live SMTP test.** SMTP was mocked; no email was sent.
3. **`/send-email` has no authentication or rate limit** (noted on CHURN-44, out of scope). Anyone who can reach the API can trigger demo emails. The whole API is unauthenticated with `allow_origins=["*"]`.
4. **What-If is not monotonic per customer** (§7). This is a model property for the E2/ML owners: consider XGBoost `monotone_constraints` or the regularised configuration from docs/ml/05.
5. **`requirements-dev.txt` cannot be installed on Python 3.10.13** (`matplotlib==3.11.2` needs ≥ 3.11), while `runtime.txt` says 3.10.13. This is pre-existing and not changed here, because it belongs to the E2 tooling. The 3.10-compatible install is in §9.1.
6. **`GET /customers` defaults to `limit=500`**, so the Risk Table page shows only 500 of 5,001 customers (pre-existing UI behaviour, unchanged).
7. **What-If bounds are wider than the training data**, and the model is flat beyond the training range (§3).
8. Import-time degraded-artifact branches are only partly covered (§8).
