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
| POST | `/send-email` | Send the retention email to the demo inbox | header `Authorization: Bearer <EMAIL_API_TOKEN>`, body `SendEmailRequest` | `SendEmailResponse` | ✅ Works with SMTP mocked. Bearer token + rate limit; 503 when not configured (CHURN-44, [§12](#12-email-endpoint-security-churn-44)) | **Gmail SMTP** (`GMAIL_SENDER`, `GMAIL_APP_PASS`) |
| GET | `/email-status` | Is email sending configured? | — | `EmailStatusResponse` | ✅ Works (addresses now masked) | — |
| GET | `/segments` | Churn by plan, device, tenure, genre, CLV; 12-month trend | — | `SegmentsResponse` | ✅ Works | — |
| GET | `/dashboard/summary` | All dashboard KPIs + top 5 priority customers | — | `DashboardResponse` | ✅ Works | — |
| GET | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, OpenAPI schema | — | HTML / JSON | ✅ Works | Swagger/ReDoc assets load from a CDN in the browser |

**Status codes used.** 200 success. 404 unknown customer or route. 405 wrong method. 409 customer not scored, or its fold model unavailable. 422 malformed or out-of-range input. 500 unexpected error. 502 SMTP failure. 503 optional component not configured (email, similarity engine).

**Externally dependent endpoints.** `/retention` calls Gemini only when `GEMINI_API_KEY` is set. During the PR #2 work no key was available, so the automated tests verify all Gemini behaviour with a mocked client ([§5](#5-gemini-retention-api-churn-22)). A **live Gemini call was made later**, after PR #3, and succeeded ([§5.3](#53-live-gemini-test-result)). `/send-email` needs Gmail credentials. It was tested only with a mocked or fake SMTP server, and **no email was sent**.

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

### 5.3 Live Gemini test result

The Gemini work was tested in two stages. Keep them apart when reading this report.

| Stage | What was tested | Real Gemini API? |
|---|---|---|
| PR #2 (`feature/shikhar-e3-e4-api-quality`) | All Gemini paths in `tests/test_retention_gemini.py`, using a mocked client or the real client library with the network transport stubbed | **No.** No API key was available |
| PR #3 (`fix/gemini-model-config`) | Model made configurable, default `gemini-3.5-flash` (the old `gemini-2.5-flash` returned 404 for the project key). Still mocked in automated tests | **No** |
| Manual smoke test (§5.2), after PR #3 was merged | `GET /retention/{id}` against the real Google Gemini API | **Yes, it passed** |

**Live result**, recorded on 23 November 2026 in Jira [CHURN-22 comment 10026](https://avanishrajauria.atlassian.net/browse/CHURN-22?focusedCommentId=10026):

- HTTP **200 OK**
- `ai_generated: true`
- `generated_by: "gemini-3.5-flash"`
- `fallback_reason: null`
- Python 3.10.13
- Tested on merged `main` at commit `39c1aa2` (PR #3 merge)

The automated suite still mocks Gemini, so CI never needs a real key. The live check was manual and is not repeated automatically. Re-run §5.2 after changing the model or the key.

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
| `payment_failures_3m` → 4 | +0.364 | 97% | 0% | mean > 0.1, ≥ 90% ↑ |
| `support_tickets` → 5 | +0.328 | 97% | 0% | mean > 0.1, ≥ 90% ↑ |
| `tenure_months` → 1 | +0.330 | 97% | 0% | mean > 0.1, ≥ 90% ↑ |
| `watch_hours_per_week` → 0.5 | +0.294 | 92% | 0% | mean > 0.1, ≥ 80% ↑ |
| `payment_failures_3m` → 0 | −0.077 | 0% | 39% (61% already 0) | mean < 0, ≤ 2% rise > 0.01 |
| `tenure_months` → 72 | −0.100 | 0% | 85% | mean < 0 |
| `watch_hours_per_week` → 40 | −0.113 | **0%** | 88% | mean < 0 |
| `logins_last_30_days` → 26 | −0.037 | **0%** | 99% | mean < 0 |

The remaining share in each row is customers already at that value, whose risk does not change. Re-measured on 24 Nov 2026 with the CHURN-57 production model, through `POST /whatif`, on the same 400-customer sample as `tests/test_whatif_api.py`.

**Monotonic per customer since CHURN-57.**

* **Before:** the earlier production model was not monotonic. Raising watch hours to 40 increased predicted risk for **42%** of customers. Across the full value range, about 99% of held-out customers had a wrong-direction step for watch hours, logins and tenure.
* **Now:** the production recipe (`regularised_monotonic`) applies XGBoost monotone constraints. Risk can only fall as watch hours, logins and tenure rise, and only rise with payment failures and support tickets. That holds for every customer, on both the production model and the out-of-fold fold models. See [docs/ml/07-monotonic-constraints.md](../ml/07-monotonic-constraints.md).
* **Tests:** `tests/test_monotonic_constraints.py` asserts this per customer through this endpoint.
* **`monthly_charge` is unconstrained**, because it has no monotone effect in the data.
* **Interpretation is unchanged:** What-If results describe the model, not causal effects.

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

**Update (CHURN-46):** `requirements-dev.txt` now pins `matplotlib==3.10.9` and installs on Python 3.10.13, so the full environment is simply `pip install -r requirements.txt -r requirements-dev.txt`. The text below records how the environment was built at the time of PR #2.

At that time, `requirements-dev.txt` pinned `matplotlib==3.11.2`, which requires Python ≥ 3.11. It **could not be installed on Python 3.10.13** (see §11). The 3.10.13 environment was built with:

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

**Results by stage.** The backend suite grew with each PR. Each total below is the full-suite result recorded at that stage. A later total includes everything before it.

| Stage | Backend result | Python | What was added |
|---|---|---|---|
| Baseline: `main` @ `7d605c5`, before this work | 95 passed | 3.10.13 | ML suite only (the two script tests were run separately and passed) |
| PR #2 merged (API quality, CHURN-18..25) | **345 passed**, 0 failed | 3.10.13 | contract, validation, error, Gemini (38), KNN and What-If suites. The coverage runs in §8 were taken at this point |
| PR #3 merged (Gemini model configuration, CHURN-22) | **354 passed**, 0 failed, 0 skipped (`python -m pytest`, 1 min 52 s) | 3.10.13 | 9 Gemini model-configuration tests (47 in total) |
| PR #4 merged (email endpoint security, CHURN-44) | **481 passed**, 0 failed | 3.13.18 | 127 tests in `tests/test_email_security.py` (§12.5) |

**Final result: 481 passed**, as reported by PR #4. PR #4 also reports a successful frontend build (`npm run build`). Its SMTP checks used a mocked or fake SMTP server, and **no real email was sent**. Gemini is mocked in every automated run; the separate live Gemini check is in §5.3.

PR #4 ran on Python 3.13.18 because `requirements-dev.txt` does not install on Python 3.10.13 (§11). Running the same 354 tests there gave the same 354 passed before PR #4's changes were applied.

The table below breaks down the 354-test suite after PR #3. PR #4 then added `tests/test_email_security.py` (127 tests) and changed only how the existing `/send-email` tests authenticate.

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

1. **Gemini live testing is manual.** The automated tests mock Gemini, so they need no API key. A manual live test after PR #3 succeeded (200, `ai_generated: true`, `generated_by: gemini-3.5-flash`; §5.3). It is not repeated automatically.
2. **No live SMTP test.** SMTP was mocked; no email was sent.
3. **`/send-email` is now protected by a bearer token and a rate limit** (CHURN-44, [§12](#12-email-endpoint-security-churn-44)). The limiter is in-memory and per process. The other endpoints are still unauthenticated with `allow_origins=["*"]`. They are read-only or compute-only and send nothing.

4. ~~**What-If is not monotonic per customer** (§7).~~ **Resolved** by CHURN-45 (evaluation and decision) and CHURN-57 (adoption): the production model now uses XGBoost monotone constraints. See §7 and docs/ml/07-monotonic-constraints.md.

5. **`requirements-dev.txt` cannot be installed on Python 3.10.13** (`matplotlib==3.11.2` needs ≥ 3.11), while `runtime.txt` says 3.10.13. This is pre-existing and not changed here, because it belongs to the E2 tooling. The 3.10-compatible install is in §9.1. **Resolved later by CHURN-46** (matplotlib pinned to 3.10.9; CI runs on 3.10.13).

6. **`GET /customers` defaults to `limit=500`**, so the Risk Table page shows only 500 of 5,001 customers (pre-existing UI behaviour, unchanged).
7. **What-If bounds are wider than the training data**, and the model is flat beyond the training range (§3).
8. Import-time degraded-artifact branches are only partly covered (§8).

---

## 12. Email endpoint security (CHURN-44)

CHURN-44 first fixed HTML/header injection, the "HIGH RISK" label, SMTP error leaks and the unmasked addresses (§10). What it did not fix was authentication and a rate limit on `POST /send-email`. That is added here. The code is in `backend/email_security.py` and the `email_endpoint_gate` middleware in `backend/main.py`. The tests are in `backend/tests/test_email_security.py`.

### 12.1 Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `EMAIL_API_TOKEN` | **yes**, to send | — | Shared secret, at least 16 characters. Unset or shorter → `/send-email` returns **503** `email_auth_not_configured` (fails closed). Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `EMAIL_RATE_LIMIT_MAX` | no | `5` | Requests allowed per window, per client |
| `EMAIL_RATE_LIMIT_WINDOW_SECONDS` | no | `600` | Window length (sliding) |
| `GMAIL_SENDER`, `GMAIL_APP_PASS`, `DEMO_RECEIVER` | yes, to send | — | Unchanged. Sender and receiver must be plain `local@domain.tld` addresses, otherwise **503** `email_misconfigured` |

Set them on the backend host (Render → Environment) or in your shell. Never commit them. `.env.example` lists the names only. `GET /email-status` reports `auth_configured` (true/false, never the token) and the active `rate_limit`.

### 12.2 Authentication

* The client sends `Authorization: Bearer <EMAIL_API_TOKEN>`. No other location is accepted: not `X-API-Key`, not a query string, not a cookie.
* The token is compared in constant time (`hmac.compare_digest`).
* A missing, malformed (wrong scheme, extra words, quotes) or wrong token always gets the **same** response: **401**, `{"error": "unauthorized", ...}` with `WWW-Authenticate: Bearer`.
* The check runs in a middleware **before routing and body parsing**. An unauthenticated caller learns nothing about the body rules, and even malformed JSON gets 401. The route also checks the token itself, as defence in depth, and `/docs` shows the lock (`EmailApiToken` bearer scheme).
* The token is never logged or returned. `redact()` also strips it, along with the Gmail App Password loaded from `email_config.json`, from logged tracebacks.
* **Frontend.** On the first *Send Email* click, the Customer Detail page asks the operator for the token. It keeps it in `sessionStorage` for that tab only, and clears it again after a 401. The token is deliberately **not** read from a `VITE_*` variable: Vite compiles those into the public JavaScript bundle. API clients just add the header:

```bash
curl -X POST "$API/send-email" -H "Authorization: Bearer $EMAIL_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"customer_id":"CUST00001","subject":"We miss you","body":"Hi ..."}'
```

### 12.3 Rate limiting

* The default is 5 requests per 600 s (sliding window) per client IP. Exceeding it returns **429** `rate_limited` with a `Retry-After` header (seconds).
* **Authenticated** attempts all count, whether they succeed, fail validation (422), name an unknown customer (404) or have malformed JSON. Invalid requests therefore cannot bypass the limit.
* **Failed authentication** attempts are counted in a separate bucket with the same limits. Brute-forcing the token is throttled to 5 guesses per 10 minutes, but it cannot use up the quota of the legitimate caller.
* `X-Forwarded-For` is **not** trusted, because a client can set it to anything. The key is the direct peer address.
* No new dependency is needed. It is a small, thread-safe in-memory limiter with bounded memory.

**Deployment limitations**

1. **Per process.** The project runs a single `uvicorn main:app` process (no `--workers`, no gunicorn config). With *N* workers the effective limit becomes *N* × `EMAIL_RATE_LIMIT_MAX`. The server prints a warning at start-up when `WEB_CONCURRENCY > 1`. If you scale out, move the limiter to a shared store (for example Redis). A shared store was not added because this demo has no shared backend.
2. **Resets on restart.** Counters live in memory.
3. **Behind a reverse proxy** (Render), every request arrives from the proxy's address, so all clients share one bucket. That works as a global limit, which is the safe direction for a demo. For per-user limits, run `uvicorn main:app --proxy-headers --forwarded-allow-ips=<proxy IP>` so `request.client` is the real client.
4. A shared token identifies "someone who knows the token", not an individual user. Rotate it by changing `EMAIL_API_TOKEN` and restarting.

### 12.4 Validation and injection

* **Recipient.** It is never taken from the request. `to`, `recipient`, `cc`, `bcc`, `from`, `reply_to` and `headers` are rejected with 422 (`extra='forbid'`), so there is no open relay. The configured `DEMO_RECEIVER` and `GMAIL_SENDER` are validated before use: no CR/LF, spaces, display names or lists. An invalid value returns 503 `email_misconfigured`, the address is not echoed, and SMTP is not contacted.
* **Subject.** One line of 1–200 characters. Every line break (CR, LF, VT, FF, NEL, U+2028/U+2029) and every control character is rejected, not only CR/LF.
* **Body.** 1–5000 characters, not blank. Newlines and tabs are allowed. Other control characters (NUL, ESC, BEL …) are rejected.
* **HTML.** The body and the customer name, plan and id are `html.escape`d in the HTML part. The plain-text part is unchanged.
* **SMTP errors.** 502 `smtp_auth_failed` / `smtp_error` with a generic message. The SMTP server's text, codes and credentials are logged only in redacted form and never returned. Responses and logs never contain the full sender or receiver address. Responses show the masked address.

### 12.5 Tests

`backend/tests/test_email_security.py` has 127 tests, with SMTP replaced by a fake, so no email is sent. They cover missing, invalid and malformed tokens (401), a valid token (full send), a server with no token (503), auth before body parsing, CORS preflight and CORS headers on 401/429, the OpenAPI security scheme, attempts to choose a recipient (422), malformed configured addresses (503), CR/LF/Unicode-line-break/control-character injection (422), HTML/script escaping in the body and customer fields, 429 with `Retry-After`, invalid requests consuming quota, the separate auth-failure bucket, per-client buckets, `X-Forwarded-For` not bypassing the limit, SMTP auth/refused/OS errors (502, no leaks), no token, password or address in any response or log, and unchanged email content for valid sends. Existing `/send-email` tests in `test_api_errors.py` and `test_api_validation.py` now send the test token.

Full backend suite (Python 3.13, `cd backend && python -m pytest -q`): **481 passed** (354 on `main` before this change + 127 new). Mutation check: disabling the gate, the limiter, HTML escaping or address validation makes 10, 6, 5 and 14 of the new tests fail respectively.

