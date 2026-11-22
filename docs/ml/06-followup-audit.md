# Follow-up Audit (before publishing `feature/aryan-e2-ml-validation`)

**Scope:** remaining CHURN-16 issues, re-verification of CHURN-17 and of the reproducibility limitation, and a Git and diff audit.
**Ground rules:** nothing pushed or merged; no production artifact (`*.pkl`, `*.csv`, `*.joblib`) changed; no Jira issue created or transitioned.

Every number below was measured in this audit. "Original" means `origin/main` at `97f8cae`, run from a separate worktree.

---

## 1. Why 4,000 customers have no prediction

**Root cause, confirmed:** Part H of the pipeline builds `customer_predictions.csv` by looping over `X_test` only. That's `churniq_ml_pipeline.py:642` (`build_predictions`), and line 1024 in the original script. The 4,000 unscored customers are **exactly the training split** (set equality checked). The 1,001 scored rows are the 1,000-customer test split plus the hand-added demo row `CUST99999`.

This was deliberate in the pipeline design ("SHAP for the test set"), but `main.py` merges these predictions onto all 5,001 customers with a left join, which leaves NaN for 80% of them.

**How unscored customers behave in the API:**

| Endpoint | Behaviour for unscored customers | Pre-existing on `origin/main`? |
|---|---|---|
| `GET /customer/{id}` | `churn_prob 0.0`, risk `LOW`, CLV `₹0`, tier `Low`, "No significant risk factor identified". This is **fabricated zero risk.** | Yes |
| `POST /whatif` | **HTTP 500** for 4,000 / 4,000 (NaN original probability can't be serialised to JSON) | Yes |
| `GET /retention/{id}` | **HTTP 500** for 4,000 / 4,000 | Yes |
| `GET /customers` (default `limit=500`) | 200. Sorting by `churn_prob` puts NaN last, so only scored customers are returned. | Yes |
| `GET /customers?limit>1001`, or any `plan_type=` filter | **HTTP 500** ("Out of range float values are not JSON compliant: nan"). All three plan filters fail at the default limit, because each plan has fewer than 500 scored customers (451 / 343 / 207). | Yes |
| `GET /dashboard/summary`, `/customers` summary | `total_customers` = 5,001, but HIGH+MEDIUM+LOW = 1,001. Averages are taken over the 1,001 scored customers only. | Yes |
| `GET /segments` `by_clv` | The 4,000 are counted under the **generator's** tier (1,032 High / 1,264 Medium / 1,704 Low), while `/customer` shows each of them as `Low`. | Partly. My branch made scored customers consistent; unscored still use the generator tier. |
| `POST /api/customer-similarity` | Shows the generator's **true** `churn_probability` as the model `churn_prob` (`customer_similarity.py:268, 316`). Example: 4 of CUST01033's 5 neighbours. That's an oracle value labelled as a prediction. | Yes |

The frontend gets `/customers` with the default limit and opens `/customer/{id}` for whoever is clicked. So today the user-visible symptoms are: (a) unscored customers appear as 0% / LOW / ₹0, and (b) the what-if sliders and "Generate email" fail for them.

### Options considered

| Option | Assessment |
|---|---|
| Fill with 0 / LOW (current behaviour) | ❌ Fabricated risk. Rejected. |
| Score training customers with the production model | ❌ Over-optimistic. The model's AUC on its own training rows is **0.958**, vs **0.717** on held-out data. 1,059 customers would be called HIGH. |
| Show the generator's `churn_probability` | ❌ That's the oracle value the model is trying to estimate. Label leakage, not a prediction. |
| **A. Out-of-fold (OOF) scoring of the training split** | ✅ **Recommended.** Each training customer is scored by a model fitted on the other 4 folds (5-fold stratified CV, SMOTE inside folds), so no customer is scored by a model that saw them. Measured on the 4,000 with the production recipe: AUC **0.746**, Brier 0.204, which is comparable to the test set (0.717 / 0.219). SHAP reasons come from the fold model, and CLV from the OOF probability. Add a `prediction_source` column (`holdout_test` / `cv_out_of_fold` / `demo`) so provenance stays visible. |
| **B. Interim: mark as unscored, never zero** | ✅ Safe stop-gap if A isn't approved yet. The API returns `churn_prob: null`, `risk_level: "NOT_SCORED"`, `clv_score: null`, `clv_segment: "Unknown"`; `/whatif` and `/retention` return 409 with a clear message instead of 500; NaN is never serialised. **This changes the API contract**: the frontend formats `Number(clv_score)` and shows `risk_level`, so it needs matching changes. |

**Proposal:** do B immediately, because it removes the HTTP 500s and the fake zeros. Then do A, which regenerates `customer_predictions.csv` and needs approval because every dashboard KPI changes. Separately, `customer_similarity.py` should stop falling back to the generator's `churn_probability`; that's another developer's module, so I'm flagging it rather than changing it.

---

## 2. CUST99999's hard-coded ₹500 CLV

**Where it's set (three places):**

| Location | What it sets |
|---|---|
| `backend/add_emails.py:106-108` | Dataset row: `clv_score 500.0`, `clv_segment "Low"`, `churn_probability 0.96`, `churn 1` |
| `backend/fix_cust99999.py:7-12` | Predictions row: `churn_prob 0.96`, `risk_level HIGH`, `clv_score 500.0`, and **hand-written SHAP reasons** |
| `backend/main.py:736-739` | `/customer/{id}` override: `churn_prob` taken from the dataset, **`clv = 500.0`** |

**Measured against the verified formula and the model:**

| Quantity | Stored / served | Computed |
|---|---|---|
| Churn probability | 0.96 (typed by hand) | **0.9836** (committed model, after the encoding fix) |
| CLV | ₹500.00 | ₹199 × max(2, 6) × (1 − p): **₹19.60** at p = 0.9836, ₹47.76 at p = 0.96 |
| Tier | Low | Low (no tier change) |
| Top-3 reasons | friction +2.17, tenure +1.35, watch hours +1.05 | **tenure +0.85, watch hours +0.71, friction +0.67** (real SHAP) |

The hand-written impacts are copied from an illustrative comment in the original pipeline's SHAP section. **This row's "SHAP reasons" were never computed by SHAP**, even though `/customer` and the Gemini prompt present them as model output. The CHURN-15 validation checked the 1,000 test customers and excluded this demo row, so it missed this.

**Proposed correction** (not applied; touches committed data and another developer's scripts):
1. Score demo rows with the model instead of typing values in. A small `score_demo_customers.py` (or a step in `fix_cust99999.py`) builds the features with `churniq_core.encode_features` and writes `churn_prob` = model output (0.9836), `risk_level` from `get_risk_level`, the real top-3 SHAP reasons, and `clv_score = churniq_core.calc_clv(199, 2, p)` = ₹19.60.
2. Remove the override in `main.py:736-739`, so the API reads the demo row like any other.
3. In `add_emails.py`, compute `clv_score`/`clv_segment` with `churniq_core.calc_clv`/`get_clv_segment` instead of the literal `500.0`/`"Low"`.

If the team wants to keep "96%" for the demo story, the minimum consistent fix is CLV **₹47.76** with the 0.96 kept, plus a visible "demo data" label, since the probability wouldn't be a model output.

---

## 3. Proposed Jira Bugs (drafts — NOT created)

### Bug A — Missing predictions: 4,000 customers shown as 0% risk / ₹0 CLV, and HTTP 500 on what-if, retention and filtered lists

- **Summary:** 4,000 customers (the training split) have no model prediction. The API presents them as zero risk and zero CLV, and several endpoints return HTTP 500 for them.
- **Component / Epic:** Backend API, ML pipeline / CHURN-2 (E2)
- **Found in:** `origin/main` `97f8cae` (pre-existing); still present on `feature/aryan-e2-ml-validation`.
- **Root cause:** `churniq_ml_pipeline.py` Part H writes predictions only for the 20% test split. `main.py` left-joins them onto all 5,001 customers, and the endpoints then coerce NaN to 0 or try to serialise it.
- **Steps to reproduce:**
  1. `GET /customer/CUST00002` → `churn_prob 0.0`, `risk_level LOW`, `clv_score 0.0`, `clv_segment Low`.
  2. `POST /whatif {"customer_id":"CUST00002"}` → HTTP 500.
  3. `GET /retention/CUST00002` → HTTP 500.
  4. `GET /customers?plan_type=Basic` → HTTP 500 (also for Standard and Premium, and for any `limit` > 1001).
- **Expected:** every customer either has a genuine out-of-sample prediction, or is explicitly marked as not scored. No zero risk is ever invented, and no endpoint returns 500.
- **Actual:**
  - 4,000 of 5,001 customers (80%) show 0% risk and ₹0 CLV.
  - `/whatif` and `/retention` fail for all 4,000.
  - All `plan_type` filters fail.
  - Dashboard tier counts sum to 1,001 while `total_customers` is 5,001.
  - `/segments` tiers come from the generator, not the model.
  - The similarity finder shows the generator's true probability as a model prediction.
- **Impact:** misleading risk and CLV for most customers; broken what-if and email generation for them; an oracle value shown as a model output.
- **Proposed fix:**
  1. Interim: represent unscored customers explicitly (`null` / `NOT_SCORED` / `Unknown`), return 409 instead of 500, never serialise NaN (backend + frontend).
  2. Then score the training split with 5-fold out-of-fold predictions (measured AUC 0.746 vs test 0.717), regenerate `customer_predictions.csv` with a `prediction_source` column, and remove the similarity fallback to `churn_probability`.
- **Rejected alternatives:** filling with zero; scoring with the production model in-sample (AUC 0.958 on its own training rows, over-optimistic); using the generator's `churn_probability` (label leakage).
- **Acceptance criteria:**
  - No API response contains a fabricated 0 risk/CLV or NaN.
  - `/whatif`, `/retention` and `/customers?plan_type=*` return non-500 for every customer.
  - Dashboard tier counts reconcile with `total_customers` (or exclude unscored customers explicitly).
  - Tests cover scored, unscored and demo customers.
- **Evidence:** `docs/ml/06-followup-audit.md` §1; `docs/ml/04-clv-verification.md`.

### Bug B — CUST99999 demo customer: hard-coded CLV ₹500, probability 0.96 and SHAP reasons not computed by the model

- **Summary:** the demo customer's CLV is hard-coded at ₹500, which is inconsistent with the CLV formula. Its probability and "SHAP" reasons are hand-written rather than model outputs.
- **Component / Epic:** Backend API, demo data / CHURN-2 (E2)
- **Found in:** `origin/main` `97f8cae`.
- **Locations:** `backend/main.py:736-739` (`clv = 500.0` override); `backend/fix_cust99999.py:7-12`; `backend/add_emails.py:106-108`.
- **Steps to reproduce:** `GET /customer/CUST99999` → `clv_score 500.0`, `churn_prob 0.96`, reasons with impacts +2.17 / +1.35 / +1.05.
- **Expected:** `clv_score = monthly_charge × max(tenure, 6) × (1 − churn_prob)`, i.e. 199 × 6 × (1 − p). Probability and reasons should come from the model and SHAP.
- **Actual:**
  - CLV ₹500, where the formula gives ₹47.76 at the stored 0.96 and ₹19.60 at the model's 0.9836.
  - The probability is typed by hand.
  - The reasons copy an illustrative comment; real SHAP is tenure +0.85, watch hours +0.71, friction +0.67.
  - The tier (Low) is unaffected.
- **Impact:** the demo customer is the one used in live demos and for the Gemini email prompt, so it presents made-up numbers as model output. It also contradicts the formula shown in `clv_breakdown`.
- **Proposed fix:** score demo rows with the model (`churniq_core.encode_features` + SHAP + `calc_clv`), remove the `main.py` override, and compute the dataset row's `clv_score`/`clv_segment` with `churniq_core`. If "96%" must stay for the demo narrative, use CLV ₹47.76 and label the row as demo data.
- **Acceptance criteria:**
  - The demo row's `clv_score` matches the formula within rounding.
  - Its reasons match recomputed SHAP.
  - No hard-coded CLV remains in `main.py`.
  - A test covers the demo customer.
- **Evidence:** `docs/ml/06-followup-audit.md` §2.

---

## 4. CLV formula and tiers across all records

Tolerance: probabilities are stored to 4 dp, so the allowed difference is `charge × max(tenure, 6) × 0.00005 + 0.005`.

| Record set | Rows | Formula mismatches | Tier mismatches | Within rounding of a boundary |
|---|---|---|---|---|
| Dataset `clv_score` (generator probability), excl. demo | 5,000 | **0** | **0** | 0 |
| Dataset, demo row `CUST99999` | 1 | **1** (₹500 vs ₹47.76) | 0 | 0 |
| **Scored**: predictions `clv_score` (model probability), excl. demo | 1,000 | **0** | **0** (API `/customer`) | 0 |
| Scored: demo row | 1 | **1** (₹500 vs ₹19.60 / ₹47.76) | 0 | 0 |
| **Unscored** (training split) | 4,000 | n/a: **no model CLV exists**. The API shows ₹0 / Low; `/segments` uses the generator tier. | inconsistent between endpoints | n/a |

Tier boundaries (High > 8,000; Medium > 3,000; otherwise Low) are applied identically by `churniq_core`, `main.get_clv_segment` and `pipeline.clv_segment`; this is unit-tested at 3,000 / 3,000.01 / 8,000 / 8,000.01.

---

## 5. CHURN-17 regularised model — re-verification

Reproduce with `python backend/verify_model_improvement.py`, which writes `results/model_improvement_verification.json`. The production model is untouched; `regularised` is only an opt-in pipeline config.

| Check | Result |
|---|---|
| Re-running `model_experiments.py` | Byte-identical `model_experiments.json` |
| Leakage | Selection used training-split CV only, with SMOTE inside folds; the test split was scored once per candidate; leakage columns are excluded by the shared encoder |
| DeLong test, original split, vs retrained baseline | ΔAUC **+0.0342**, z = 4.12, **p = 3.7×10⁻⁵** |
| DeLong test vs committed artifact | ΔAUC **+0.0413**, z = 5.06, **p = 4.1×10⁻⁷** |
| Multiple comparisons (6 candidates) | Bonferroni α = 0.0083; both remain significant |
| 10 fresh train/test splits (seeds 1–10) | Regularised wins **10/10**. Mean gain **+0.024** (sd 0.005, range +0.017 to +0.034); sign test p = 0.002. |
| Repeated 5×3 CV (new seed) | Baseline 0.745 ± 0.014 vs regularised 0.775 ± 0.017; better in **15/15** folds |

**Conclusion:** the improvement is statistically well supported. **Correction to the CHURN-17 report:** the +0.034 gain on the original split is at the **upper end** of what fresh splits show. The expected gain is about **+0.024 AUC** (range +0.017 to +0.034). It is still recommended, and still needs team sign-off before it replaces production.

---

## 6. Reproducibility limitation — known vs unconfirmed

**Known (measured):**
- The pipeline is deterministic in a fixed environment. Two full runs give identical predictions, and retraining without subsampling is also deterministic.
- The dataset, train/test split and SMOTE output are reproduced exactly.
- The committed artifact reproduces its own stored predictions (max difference 5×10⁻⁵).
- The committed artifact was saved by **XGBoost 2.1.4** (`tree_method=auto`, `grow_quantile_histmaker`, `base_score=0.5`, 200 trees, 33 features).
- **New:** the committed booster's config records **`seed: 0`**, while its scikit-learn wrapper says `random_state=42`. In this environment, training with `random_state=42` always records `seed: 42`, including after a pickle round-trip. So **the committed artifact wasn't produced by the committed pipeline code exactly as it runs with these versions.**
- Retraining with seed 0 doesn't reproduce it either (max difference 0.286; seeds 1, 7, 42, 123 and 2024: 0.32–0.41). The seed isn't the only difference.
- imbalanced-learn 0.12.4 / 0.13.0 / 0.14.2 all give identical SMOTE output and identical retrains.

**Unconfirmed:**
- How the artifact was actually produced: a different script or notebook, parameters set after fitting, a different random state, or a different OS/CPU. My earlier statement that it was "likely platform-dependent subsampling" is **weakened**: an OS difference wouldn't explain the recorded seed of 0.
- Whether a Windows run of the current pipeline would reproduce it. This can't be tested here.

**Mitigation (unchanged):** evaluate the committed artifact directly (`evaluate_model.py`). For model comparisons, use same-environment retrains. If the team regenerates artifacts (e.g. adopting the regularised config), record `xgboost.__version__`, the platform and the booster seed alongside the artifact.

---

## 7. Git and diff audit

| Check | Result |
|---|---|
| Branch `feature/aryan-e2-ml-validation` exists, working tree clean | ✅ |
| Commit `926f632` exists on the branch | ✅ (`926f6326afacb2f5724e9324a0bd5c1d3f8db6f4`) |
| Based on the latest `origin/main` | ✅ Fetched; `origin/main` = `97f8cae` = merge-base; branch is 0 behind, 1 ahead (before this audit's commit) |
| Other developers' work overwritten | ✅ None. Only files related to E2 changed (26 in `926f632`). Committed `*.pkl`/`*.csv`/`*.joblib`, frontend and similarity engine untouched. `main.py` and the pipeline changes are scoped to the documented fixes. |
| Secrets | ✅ None (scanned added lines for keys, tokens, passwords, private keys) |
| Personal data | ✅ No customer names/emails in docs/results; no account emails |
| Binary or large files | ✅ None added |
| Missing files | ✅ Every module, test and doc path referenced exists and is tracked |
| Remote branches | Only `main` exists on `origin`; nothing has been pushed |
| Note | `926f632`'s author is recorded as `Claude <noreply@anthropic.com>`. If the team requires Aryan as author, amend before pushing (only with approval). |
