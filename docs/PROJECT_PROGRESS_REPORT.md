# CHURN-IQ — Project Progress Report

> **Final status, 25 November 2026 (evening).** Section **F** below is current, and was last updated on 25 Nov after the Jira changes of that evening (Epics E1 and E2 closed, ceremony records closed as not applicable, owners set from commit evidence). It was read live from Jira (70 issues), GitHub (`main` @ `8161a9e`, PRs #1 to #20) and the two production URLs. Prepared by Avanish Rajauria for CHURN-36, with AI-assisted development tools.
>
> **Older sections, kept unchanged for history:**
> * §0 is Aryan Gupta's Sprint 3 closeout update (25 Nov, after PR #14).
> * §1 to §14 are the 24 November snapshot (after PR #8).
>
> Where they disagree with F, F is current.

## F. Final project status (25 November 2026)

### F.1 How the sprints were used

**Sprints 1–3 are task groupings, not calendar sprints.**

* By team decision (CHURN-58, comment 10085), all three Jira sprints stay **Future with blank start and end dates** and have **never been started**.
* Sprints 1–3 only divide the work. Formal ceremony records do not apply (CHURN-35, 66, 67 and 68, comments 10108–10111).

**What happened, and what didn't:**

| Event | Status |
|---|---|
| Sprint 1 planning meeting | **Held on 20 November 2026**, all four members present, as confirmed by Avanish (CHURN-58, Done) |
| Sprint 2 and Sprint 3 planning meetings | **Not held.** Recorded on CHURN-62 and CHURN-66, which stay To Do |
| Stand-ups, sprint reviews, retrospectives | **None held or recorded.** On 25 Nov, CHURN-35, 60, 63, 64, 67 and 68 were closed as **not applicable** under the decision above: original criteria kept, rationale added, label `not-applicable`. Closing them does not mean the events happened |
| Burndown charts, sprint reports | **None exist.** Jira does not produce them for a sprint that was never started |

None of these records has been invented.

### F.2 Jira status (all 70 issues, read live on 25 Nov 2026, after today's updates)

| Type | Total | Done | In Progress | To Do |
|---|---|---|---|---|
| Epics | 6 | 5 (E1 to E5) | 1 (E6) | 0 |
| Stories | 35 | 30 (incl. CHURN-35, not applicable) | 4 (CHURN-32, 36, 54, 55) | 1 (CHURN-34) |
| Bugs | 17 | 16 | 1 (CHURN-70) | 0 |
| Tasks (sprint record tasks CHURN-58 to 69) | 12 | 9 (CHURN-58, 61, 65, 69; CHURN-60, 63, 64, 67, 68 not applicable) | 0 | 3 (CHURN-59, 62, 66) |
| **Total** | **70** | **60** (6 of them closed as not applicable) | **6** | **4** |

* **Original plan (30 Stories, CHURN-7 to CHURN-36, 103 points):** 27 of 30 Done, 96 of 103 points. CHURN-35 (2 points) is among them and was closed as not applicable.
* **Open in the original plan:**
  * CHURN-32: waiting on the team's option A/B decision;
  * CHURN-34: waiting on CHURN-70 / PR #18;
  * CHURN-36: this report, waiting on review of PR #21.

### F.3 Results by Epic

| Epic | Accountable member | Children | Done | Points Done | Epic status |
|---|---|---|---|---|---|
| E1 Customer Data & Analytics (CHURN-1) | Shimon Sarin | 6 | 6 | 21 / 21 | **Done** (25 Nov; evidence in comment 10146). Data quality, behaviour, segment patterns, Segments-page validation, dashboard re-check and data dictionary (PR #17; supporting docs from Aryan's PR #16) |
| E2 ML & Explainability (CHURN-2) | Aryan Gupta | 11 | 11 | 29 / 29 | **Done** (25 Nov; comment 10147). Pipeline, evaluation, SHAP and CLV validation, model research; monotone model adopted (PRs #12, #14); segment validation (PR #15); Bugs 37, 38 (PR #1) and 46 (PR #13) |
| E3 Backend & API (CHURN-3) | Shikhar Kesharwani | 10 | 10 | 17 / 17 | **Done** |
| E4 Similarity & What-If (CHURN-4) | Shikhar Kesharwani | 4 | 4 | 11 / 11 | **Done** |
| E5 Frontend & Dashboard (CHURN-5) | Avanish Rajauria | 12 | 12 | 22 / 22 | **Done** |
| E6 Agile & Integration (CHURN-6) | Avanish Rajauria (Epic assigned 25 Nov) + shared | 17 | 11 (6 of them not applicable) | 4 / 11 | **In Progress.** Open: CHURN-32, 34, 36, 59, 62 and 66 |
| No Epic | — | 4 | 1 (CHURN-53) | — | CHURN-54, 55 and 70 are In Progress (PRs #19, #20, #18). Epic placement is still a team decision |

### F.4 Results by sprint grouping (sprint field in Jira)

| Grouping | Goal (Jira) | Issues | Done | In Progress | To Do | Points Done |
|---|---|---|---|---|---|---|
| Sprint 1 | Establish a reliable baseline of OTT data quality, customer behaviour, and model/test readiness. | 8 | 7 (CHURN-60 not applicable) | 0 | 1 (CHURN-59) | 13 / 13 |
| Sprint 2 | Validate and fix | 9 | 6 (CHURN-63, 64 not applicable) | 2 (CHURN-54, 55) | 1 (CHURN-62) | 11 / 11 (54 and 55 are unpointed) |
| Sprint 3 | Improve, test, document | 11 | 7 (CHURN-11, 12, 33, 69; CHURN-35, 67, 68 not applicable) | 2 (CHURN-32, 36) | 2 (CHURN-34, 66) | 9 / 16 (includes CHURN-35's 2 points, not applicable) |
| Backlog (no grouping) | — | 36 | 35 | 1 (CHURN-70) | 0 | 71 / 71 |

**The 19 backlog Stories.** CHURN-13 to CHURN-31 were finished before the groupings were set up and moved to the backlog on 24 Nov (CHURN-32, comment 10070). The team has not yet confirmed option A or B for them (CHURN-32, comment 10139).

### F.5 Team contributions (Jira assignee and GitHub account actions)

| Member | Jira issues Done (as assignee) | Points Done | GitHub PRs authored | Main evidence |
|---|---|---|---|---|
| **Aryan Gupta** | 10: CHURN-13 to 17, 45, 56, 57, and Bugs CHURN-37, 38 (assignee set 25 Nov from his fix commits in PR #1) | 27 | #1, #12, #14, #15, #16 (all merged) | `docs/ml/01`–`08`; production model adoption; supporting evidence docs for CHURN-11 and 12 |
| **Shikhar Kesharwani** | 15: CHURN-18 to 25, Bugs 39 to 44, Bug 46 | 30 | #2 to #7, #13 (all merged) | `docs/api/README.md`; API hardening; CI workflow (#7); Python 3.10.13 CI (#13) |
| **Shimon Sarin** | 6: CHURN-7 to 12 | 21 | #17 (merged) | `docs/data/01`–`04`, analysis scripts and figures |
| **Avanish Rajauria** | 18: CHURN-26 to 31, Bugs 47 to 53, CHURN-33, 58, 61, 65, 69 | 24 | #8, #9, #11 (merged); #10, #18, #19, #20, #21 (open) | Frontend (E5); `docs/frontend/UI_TEST_REPORT.md`; E6 records; CHURN-54, 55 and 70 implementation (assigned 25 Nov from PR authorship); this report |
| **Unassigned** | 11 Done: Epics E1 to E5; the six not-applicable ceremony records | — | — | — |

**Reviews and merges by account:**
* PRs #12, #13 and #14 were approved by `AvanishRajauria`.
* PRs #15, #16 and #17 were approved and merged by `AvanishRajauria`. None was authored by Avanish.
* Avanish's own PRs #8, #9 and #11 were approved and merged by `Shikhar-Kesharwani`.
* **No PR was approved by its own author.**

These columns record the GitHub **account** that acted (see `docs/CONTRIBUTOR_ATTRIBUTION.md`).

### F.6 Open work

**Implementation PRs awaiting independent review** (reviews requested; reminder comments posted 25 Nov)

| PR | Jira (assignee) | Implementation | CI | Review | Merge |
|---|---|---|---|---|---|
| [#18](https://github.com/Shikhar-Kesharwani/CHURN-IQ/pull/18) | CHURN-70 (Avanish) | Segments labels now say "Average Predicted Churn Probability"; tenure ranges 1–3 / 4–6 / 7–12 / 13–24 / 25+ months; numbers unchanged; 85 frontend tests | ✅ ✅ | **None received** | **Not merged** |
| [#19](https://github.com/Shikhar-Kesharwani/CHURN-IQ/pull/19) | CHURN-54 (Avanish) | CORS restricted to production plus local dev origins; `CORS_ALLOWED_ORIGINS`; deployment doc; 30 CORS tests | ✅ ✅ | **None received** | **Not merged** |
| [#20](https://github.com/Shikhar-Kesharwani/CHURN-IQ/pull/20) | CHURN-55 (Avanish) | Fixture/API contract check; 4 Playwright smoke tests; "Browser smoke tests" CI job | ✅ ✅ ✅ (4/4) | **None received** | **Not merged** |
| [#21](https://github.com/Shikhar-Kesharwani/CHURN-IQ/pull/21) | CHURN-36 (Avanish) | This report | ✅ ✅ | **None received** | **Not merged** |

**Project-management items still open:**

* **CHURN-32 (backlog):** waits on the team's option A/B decision (comment 10139).
* **CHURN-34 (bugs and blockers, shared):**
  * all 17 Bugs now have an evidence-based assignee;
  * it waits only on CHURN-70 / PR #18 (comment 10154).
* **CHURN-36:** closes when PR #21 is approved by a teammate and merged.
* **CHURN-59, 62 and 66:** the Sprint 1 stand-up record (Shikhar) and the Sprint 2 and 3 planning records (Avanish). They are the same kind of record as the six closed today as not applicable, but are assigned and were left unchanged. The team can apply the same rule.

### F.7 Deployment status (checked live on 25 Nov 2026)

| Item | Value or status |
|---|---|
| Production frontend | `https://churn-iq-frontend-five.vercel.app`, serving bundle `assets/index-DK36Gx0B.js` |
| Production API | `https://churniq-32r3.onrender.com` |
| `VITE_API_URL` (effective) | `https://churniq-32r3.onrender.com`: the only API URL in the deployed bundle. The Vercel dashboard **setting** itself has **not** been checked; only the Vercel project owner can see it |
| `CORS_ALLOWED_ORIGINS` | Introduced by PR #19 (not merged). The default needs no variable on Render; the Render setting has not been checked |
| Deployed versions | **Both predate the team's merged PRs.** `GET /` reports `high_risk_count: 250`, the pre-PR-1/pre-PR-14 model. The bundle contains none of the PR #8 UI text |
| Redeployed after the latest merges? | **No.** Neither service has been redeployed from `main` |
| Live CORS | `Origin: https://evil.example` still receives `access-control-allow-origin: *` with `access-control-allow-credentials: true`. **The CORS fix is not live** |

**Why deployment hasn't happened:**
* No Render or Vercel access is available to this account's tooling.
* PR #19 is not merged.

The redeploy steps for the hosting account owners are in `docs/deployment/PRODUCTION_CONFIGURATION.md` §5 (on the PR #19 branch).

### F.8 CI and branch protection

* **CI on `main` @ `8161a9e`** (run 26, after PR #17): Backend tests ✅, Frontend build ✅.
* **Required checks:** "Backend tests" and "Frontend build" (branch protection on `main` since 24 Nov).
* **"Browser smoke tests" is not a required check.** PR #20 adds it as a new job. `AvanishRajauria` has **write** (not admin) access, so making it required needs the repository admin (`Shikhar-Kesharwani`).

### F.9 Test results for this report (local, on `main` @ `8161a9e` plus this documentation change)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && python -m pytest -q` (Python 3.13.18) | **552 passed** |
| Frontend tests | `cd frontend && npm test` | **82 passed** |
| Frontend build | `cd frontend && npm run build` | passes (existing chunk-size warning only) |
| Markdown links and repository paths in the two changed documents | script check | all resolve, except `docs/deployment/PRODUCTION_CONFIGURATION.md`, which exists only on the PR #19 branch until that PR is merged |

The counts on PRs #18 to #20 are higher because those PRs add tests (F.6).

### F.10 Completion summary (live data, 25 Nov 2026)

| Category | Count | Issues |
|---|---|---|
| Implementation work completed (Stories and Bugs outside E6) | 44 of 47 | All 43 under E1 to E5, plus CHURN-53. Open: CHURN-54, 55, 70 (PRs awaiting review) |
| Project-management work completed (E6, excluding ceremony records) | 5 of 8 | Done: CHURN-33, 58, 61, 65, 69. Open: CHURN-32, 34, 36 |
| Ceremony records (no event took place) | 9 | 6 closed as not applicable (CHURN-35, 60, 63, 64, 67, 68); 3 still open (CHURN-59, 62, 66) |
| Epics | 6 | 5 Done (E1 to E5); E6 In Progress |
| Awaiting independent approval | 4 PRs | #18, #19, #20, #21 (PR #10 is also still open: an old proposal, superseded by CHURN-58) |
| External dependencies | 3 | Render/Vercel redeploy and settings check (CHURN-54); making the smoke-test check required (repository admin) |

**Completion of actionable work:** 49 of 55 = **89%**.

* **Denominator, 55 issues:** the 47 implementation issues and the 8 project-management issues above.
* **Not counted:** Epics and ceremony records. Those records describe meetings that never took place, so they are reported separately and never counted as delivered work.

**All issues:** 60 of 70 are Done (86%).

* 6 of those 60 are not-applicable closures, not delivered work.
* Excluding them: 54 of 64 = 84%.

**Team workload (unresolved issues by assignee, live):**

| Assignee | Unresolved issues | Share |
|---|---|---|
| Avanish Rajauria | 8 (CHURN-6, 32, 36, 54, 55, 62, 66, 70) | 80% |
| Shikhar Kesharwani | 1 (CHURN-59) | 10% |
| Unassigned | 1 (CHURN-34, shared by design) | 10% |
| **Total** | **10** | 100% |

At the start of 25 Nov, 13 unresolved issues had no assignee. Every change since then is backed by evidence:

* **5 closed as not applicable** (the shared ceremony records);
* **2 Epics closed**, because all their children are Done;
* **4 assigned from evidence:** CHURN-54, 55 and 70 from PR authorship, and E6 from the documented workstream owner;
* **CHURN-35 closed** as not applicable.

CHURN-37 and 38 were already Done; they were assigned to Aryan from his fix commits. **CHURN-34 stays unassigned on purpose** (a shared activity).

---

# Sprint 3 closeout update (25 November 2026, Aryan Gupta), historical

## 0. Status as of PR #14 (25 November 2026)

### 0.1 How the sprints are used

**Sprints 1–3 are task groupings, not calendar sprints.**

* The team uses Sprint 1, Sprint 2 and Sprint 3 only to divide the work into three groups.
* By team decision (CHURN-58, Jira comment 10085), all three Jira sprints stay in the Future state with **no start or end dates**.
* Consequently, this report claims **no sprint dates, stand-ups, burndown charts, sprint reports, sprint reviews or retrospectives**, and none have been created.
* The only planning meeting on record is the Sprint 1 planning session on 20 November 2026 (CHURN-58).

### 0.2 Jira status (69 issues, read 25 November 2026)

| Type | Total | Done | In Progress | To Do |
|---|---|---|---|---|
| Epics | 6 | 3 (E3, E4, E5) | 1 (E6) | 2 (E1, E2) |
| Stories | 35 | 21 | 3 (CHURN-32, CHURN-33, CHURN-36) | 11 (CHURN-7 to CHURN-12, CHURN-34, CHURN-35, CHURN-54, CHURN-55, CHURN-56) |
| Bugs | 16 (CHURN-37 to CHURN-44, CHURN-46 to CHURN-53) | **16** | 0 | 0 |
| Tasks (sprint record tasks CHURN-58 to CHURN-69) | 12 | 4 (CHURN-58, CHURN-61, CHURN-65, CHURN-69) | 0 | 8 |
| **Total** | **69** | **44** | **4** | **21** |

* **Planned Stories (CHURN-7 to CHURN-36):** still 19 of 30 Done, 71 of 103 points. CHURN-11 and CHURN-12 now have evidence in an open PR (§0.4), but are **not** Done.
* **Follow-up Stories Done since the snapshot:**
  * CHURN-45: monotone constraints evaluated; decision "adopt" (PR #12).
  * CHURN-57: model adopted in production (PR #14).
* **Bugs Done since the snapshot:**
  * CHURN-46: the dev requirements install on Python 3.10.13, and CI runs on that version (PR #13).
  * CHURN-53: the Segments page uses API data (PR #11).
* **No Bug is open.**

### 0.3 Pull requests since the snapshot

| PR | Jira | Opened by | Approved by (before merge) | Merged | Merge commit |
|---|---|---|---|---|---|
| #9 | CHURN-32, CHURN-33, CHURN-36 (report update) | AvanishRajauria | Shikhar-Kesharwani | 24 Nov | `7f3e75f` |
| #10 | CHURN-33 (proposed Sprint 1 plan) | AvanishRajauria | — | **open** | — |
| #11 | CHURN-53 | AvanishRajauria | Shikhar-Kesharwani | 24 Nov | `8ea44c5` |
| #13 | CHURN-46 | Shikhar-Kesharwani | AvanishRajauria | 24 Nov | `2e093fc` |
| #12 | CHURN-45 | aryan-guptta-2007 | AvanishRajauria | 25 Nov | `e750eed` |
| #14 | CHURN-57 | aryan-guptta-2007 | AvanishRajauria | 25 Nov | `074ec94` |
| #15 | CHURN-56 (segment validation) | aryan-guptta-2007 | awaiting review | **open** | — |

* **CI:** "Backend tests" and "Frontend build" passed on PR #14's merged head (`fd8a5cb`) and on PR #15.
* **Backend CI runtime:** since PR #13, the backend job runs on Python 3.10.13, matching `runtime.txt`.

### 0.4 Production model (CHURN-45 → CHURN-57)

* **Model:** the regularised XGBoost with monotone constraints (`regularised_monotonic`: depth 2, learning rate 0.03, 400 trees, no SMOTE, seed 42) has been served since PR #14.
* **Held-out metrics (1,000 customers):** ROC-AUC **0.7597**, accuracy 0.703, precision 0.679, recall 0.589, F1 0.631.
  * The snapshot's 0.7167 belongs to the previous model.
* **What-If:** on the five constrained inputs, no customer's risk moves in the wrong direction.
* **Every served value changed with the new model.** Current dashboard values: 888 high-risk customers (17.8%), average predicted churn 43.1%, and revenue at risk ₹905,045 / month.
* **Reports:** see `docs/ml/07-monotonic-constraints.md`. CHURN-56 (segment-level validation, PR #15) is under review, not merged.

### 0.5 Sprint 3 technical evidence (this update's PR)

| Document | Jira | What it verifies |
|---|---|---|
| `docs/analytics/DASHBOARD_ANALYTICS_VALIDATION.md` | CHURN-11 | Every Dashboard and Segment Analysis value, recomputed from the CSVs, matches the API and a fresh browser run on the post-PR-14 model. No mismatch was found, so no Bug was logged. |
| `docs/data/DATA_DICTIONARY.md` | CHURN-12 | All 22 columns with type, meaning, domain and role; quality checks (0 missing, 0 duplicates, 0 invalid values); observed-churn findings; generator fields vs model outputs |

`docs/frontend/UI_TEST_REPORT.md` now carries a note that its dashboard values are historical (pre-PR-14).

### 0.6 Verified vs not verified

**Verified** (Jira status, merged PRs, CI or tests run for this update):

* E2: 5 of 5 planned Stories Done, plus CHURN-45 and CHURN-57.
* E3, E4 and E5 Done; all 16 Bugs Done.
* The dashboard numbers reconcile (CHURN-11 evidence).
* Test results (§0.7).

**Not verified or not done:**

* **E1 Stories:** CHURN-7 to CHURN-10 have not been started. CHURN-11 and CHURN-12 have evidence awaiting review; their status is unchanged, and their drafted criteria still need team approval.
* **Unstarted follow-ups:** CHURN-54 (production CORS configuration) and CHURN-55 (contract and browser smoke tests in CI) have not been started.
* **CHURN-56** is in review (PR #15).
* **CHURN-36:** this report has not yet been reviewed by the team. Its criteria ask for burndown screenshots, sprint reports and review/retrospective notes; under §0.1 those do not exist and will not be created.
* **Ceremony record tasks:** CHURN-59, CHURN-60, CHURN-62 to CHURN-64 and CHURN-66 to CHURN-68 are To Do. Each of them records an event that did not take place.
* **Deployment:** the deployed Vercel/Render site was not tested for this update.

### 0.7 Test results for this update (on `main` @ `074ec94` plus this PR's documentation changes)

All of these were run locally on Python 3.13.18 and Node 22.23.5. CI on this PR runs the backend on Python 3.10.13.

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && python -m pytest -q` | **494 passed** |
| Frontend tests | `cd frontend && npm test` | **82 passed**, 8 files |
| Frontend build | `cd frontend && npm run build` | builds; only the existing chunk-size warning |
| Independent recomputation | `python docs/analytics/recompute_analytics.py` | identical output on two runs; all values match the API |
| Browser check | Playwright and Chromium against local `uvicorn` and `vite` | Dashboard and Segment Analysis values match the API; no console or page errors |
| Markdown links | relative links and repository paths in the four changed documents | all resolve |

---

# Snapshot of 24 November 2026 (historical)

**Report date:** 24 November 2026. This version was updated after PR #8 was merged.
**Prepared by:** Avanish Rajauria, for CHURN-36 (E6 — Agile Management & Integration)
**Sources:**
* Jira project CHURN on `avanishrajauria.atlassian.net`, board 3;
* GitHub repository `Shikhar-Kesharwani/CHURN-IQ`;
* CI runs;
* `docs/api/README.md`, `docs/ml/`, `docs/frontend/UI_TEST_REPORT.md` and `docs/agile/SPRINT_PLANNING_AND_TRACKING.md`.

**Method:** every number below was read from Jira or GitHub after the PR #8 merge (`main` @ `58a98c1`). Nothing marked "pending" has happened yet, and no meeting, metric or screenshot has been invented to fill a gap. This report was prepared with AI-assisted development tools.

> **Status of this report:** draft for team review. CHURN-36 cannot be closed yet, because its acceptance criteria require burndown and sprint-report screenshots and review/retrospective notes. **None of these exist yet**, because no sprint has been started; see §8 and §13.

---

## 1. Project overview

ChurnIQ Pro is an OTT customer churn platform with three parts:

* **Backend:** FastAPI, an XGBoost churn model, SHAP explanations, CLV scoring, KNN customer similarity, a What-If simulator, and Gemini-assisted retention emails.
* **Frontend:** React and Vite.

The team runs the project in Jira as six Epics, with 30 planned Stories in three sprints.

| Epic | Area | Owner |
|---|---|---|
| CHURN-1 (E1) | Customer Data & Analytics | Shimon Sarin |
| CHURN-2 (E2) | Machine Learning & Explainability | Aryan Gupta |
| CHURN-3 (E3) | Backend & API Development | Shikhar Kesharwani |
| CHURN-4 (E4) | Customer Similarity & What-If Testing | Shikhar Kesharwani |
| CHURN-5 (E5) | Frontend & Dashboard | Avanish Rajauria |
| CHURN-6 (E6) | Agile Management & Integration | Avanish Rajauria, plus two shared Stories |

## 2. Overall progress

These figures cover the 30 planned Stories, CHURN-7 to CHURN-36.

| Measure | Value |
|---|---|
| Planned Stories | 30 Stories, **103 story points** |
| Done | **19 of 30 Stories, 71 of 103 points (69%)** |
| In Progress | 3 Stories, 7 points: CHURN-32, CHURN-33 and CHURN-36 |
| To Do | 8 Stories, 25 points: CHURN-7 to CHURN-12, CHURN-34 and CHURN-35 |
| Epics Done | 3 of 6: E3, E4 and E5 |
| Epics In Progress | 1 of 6: E6 |
| Epics To Do | 2 of 6: E1 and E2 |
| Sprints started | **0 of 3** |

**Extra follow-up work outside the 30 planned Stories** is not counted above:

* **CHURN-45** (Story): What-If predictions are not monotonic per customer.
* **CHURN-46** (Bug): the full test suite needs `requirements-dev.txt`, which cannot be installed on the declared Python 3.10.13.

Both are To Do, unassigned and unestimated, under E2. See §7 and §13.

## 3. Outcomes per Epic

| Epic | Stories | Status | Outcome |
|---|---|---|---|
| **E1 — Data & Analytics** | CHURN-7 to CHURN-12 (21 points) | To Do, 0 of 6 Done | Not started. |
| **E2 — ML & Explainability** | CHURN-13 to CHURN-17 (21 points) | 5 of 5 Done; Epic To Do | See below. |
| **E3 — Backend & API** | CHURN-18 to CHURN-22 (17 points) | 5 of 5 Done; **Epic Done** | See below. |
| **E4 — Similarity & What-If** | CHURN-23 to CHURN-25 (11 points) | 3 of 3 Done; **Epic Done** | See below. |
| **E5 — Frontend & Dashboard** | CHURN-26 to CHURN-31 (22 points) | 6 of 6 Done; **Epic Done** | See below. |
| **E6 — Agile & Integration** | CHURN-32 to CHURN-36 (11 points) | 3 In Progress, 2 To Do; **Epic In Progress** | See below. |

**E2:**
* The training/serving skew was fixed.
* Model evaluated: holdout ROC-AUC 0.7167.
* SHAP and CLV were validated.
* Genuine predictions now exist for all 5,001 customers (out-of-fold for the training split): bugs CHURN-37 and CHURN-38, both Done.
* Model research found a regularised variant scoring 0.758 test AUC.
* The Epic stays open because two follow-ups under it are open: CHURN-45 (model monotonicity) and CHURN-46 (dev requirements and Python version).

**E3:**
* All 11 endpoints were reviewed and given response models, strict input validation and one consistent JSON error format.
* The Gemini retention endpoint was hardened, with a live test recorded on CHURN-22.
* `/send-email` was secured with token authentication and rate limiting.
* Bugs CHURN-39 to CHURN-44 are Done.

**E4:**
* KNN similarity was verified against brute-force search.
* What-If routing was verified (fold model or production model, with no in-sample fallback).
* Edge-case tests were added; API-layer coverage rose from 76% to 93%.

**E5:**
* Each Story was tested against the real API, and six defects reproduced on the old `main` were logged as CHURN-47 to CHURN-52.
* All six were fixed in **PR #8**, which also added 70 frontend tests and a measured UI test report (`docs/frontend/UI_TEST_REPORT.md`).
* PR #8 was **merged on 24 November 2026** (merge commit `58a98c1`).
* All six Stories and all six Bugs are Done, and Epic CHURN-5 is Done.

**E6:**
* **CHURN-32 (backlog):** audited twice; see Jira comments 10047 and 10062.
* **CHURN-33 (sprint planning):**
  * a tracking record and proposed plan (comments 10048 and 10063);
  * a planning agenda and tracking template in `docs/agile/SPRINT_PLANNING_AND_TRACKING.md`.
* **CHURN-36:** this report.
* All three remain In Progress, because their remaining criteria depend on sprints that have not started.
* The shared Stories CHURN-34 and CHURN-35 have not yet been carried out as team activities.

## 4. Aryan Gupta — completed scope

| Item | Evidence |
|---|---|
| CHURN-13 to CHURN-17 (21 points), all Done | Jira; `docs/ml/` reports 01–06 |
| Bugs CHURN-37 and CHURN-38 (reported by Aryan, unassigned), both Done | Fixed in PR #1 |
| PR #1 "Feature/aryan e2 ml validation" | Opened and merged by `aryan-guptta-2007`; approved by `Shikhar-Kesharwani` before merge |
| Reviews | Approved PRs #2, #3, #4 and #5. #2 and #3 were approved before merge; #4 and #5 after merge |
| Merges | PRs #1, #3 and #4 |

## 5. Shikhar Kesharwani — completed scope

| Item | Evidence |
|---|---|
| CHURN-18 to CHURN-25 (28 points), all Done | Jira comments with test evidence; `docs/api/README.md` |
| Bugs CHURN-39 to CHURN-44, all Done | Linked to their Stories in Jira |
| PRs #2, #3, #4 and #5 | Opened under `Shikhar-Kesharwani`; #2 and #5 merged by Shikhar, #3 and #4 by Aryan |
| Live Gemini test | CHURN-22, comment 10026 (HTTP 200, `ai_generated: true`) |
| Review of PR #8 | Approved by the `Shikhar-Kesharwani` account before merge, then merged by it |

**Not Shikhar Jira tickets, so not credited above:**

* **Repository CI** was added in PR #7, under the `Shikhar-Kesharwani` account, through AI-assisted development tools.
* **Branch protection** on `main` was enabled on 24 November 2026 from the repository admin account.

These are account actions; see `docs/CONTRIBUTOR_ATTRIBUTION.md`.

## 6. Avanish Rajauria — scope and status

**22 of 29 story points Done; 7 points remaining** (CHURN-32, CHURN-33, CHURN-36).

| Story | Points | Status | Evidence |
|---|---|---|---|
| CHURN-26 Dashboard KPIs | 3 | **Done** | PR #8; UI test report §2; Bug CHURN-47 (Done) |
| CHURN-27 Risk table | 5 | **Done** | PR #8; report §3; Bug CHURN-48 (Done) |
| CHURN-28 Customer detail | 3 | **Done** | PR #8; report §4 (7 customers); Bug CHURN-52 (Done) |
| CHURN-29 Frontend–backend integration | 3 | **Done** | PR #8; report §5; Bug CHURN-49 (Done) |
| CHURN-30 Navigation, responsive, UX | 5 | **Done** | PR #8; report §6 (42 overflow cases); Bug CHURN-51 (Done) |
| CHURN-31 What-If and similarity UI | 3 | **Done** | PR #8; report §7 (test sheet, 19 steps); Bug CHURN-50 (Done) |
| CHURN-32 Backlog | 2 | In Progress | Jira comments 10047 and 10062 (backlog audits) |
| CHURN-33 Sprint planning and tracking | 2 | In Progress | Jira comments 10048 and 10063; `docs/agile/SPRINT_PLANNING_AND_TRACKING.md` |
| CHURN-36 Final report | 3 | In Progress | This document |

**Why the three E6 Stories are not Done:**

* **CHURN-32:** the second criterion is "backlog reviewed and updated at least once per sprint". No sprint has run, so no per-sprint review can have happened.
* **CHURN-33:** the criteria are "planning held, goal set and sprint started for each of Sprints 1–3" and "burndown and sprint-report screenshots saved for each sprint". No planning session has been held and no sprint has been started.
* **CHURN-36:** the report must include burndown screenshots, sprint reports and review/retrospective notes, and be shared with the team. None of that evidence exists yet, and the team has not reviewed the report.

## 7. Jira issue summary

| Type | Total | Done | In Progress | To Do |
|---|---|---|---|---|
| Epics | 6 | 3 (E3, E4, E5) | 1 (E6) | 2 (E1, E2) |
| Stories | 31 (30 planned + CHURN-45) | 19 | 3 (CHURN-32, CHURN-33, CHURN-36) | 9 (CHURN-7 to CHURN-12, CHURN-34, CHURN-35, CHURN-45) |
| Bugs | 15 (CHURN-37 to CHURN-44, CHURN-46 to CHURN-52) | 14 | 0 | 1 (CHURN-46) |
| **Total** | **52** | **36** | **4** | **12** |

**Bugs by area:**

| Area | Bugs | Status |
|---|---|---|
| E2 | CHURN-37, CHURN-38 | Done |
| E3 and E4 | CHURN-39 to CHURN-44 | Done |
| E5 | CHURN-47 to CHURN-52 | Done |
| E2 follow-up | CHURN-46 | To Do, unassigned |

## 8. Sprints

| Sprint | Goal | Stories | Points | Done | In Progress | To Do | Jira state |
|---|---|---|---|---|---|---|---|
| Sprint 1 (id 1) | Understand the system and baseline everything | 12 | 36 | 20 | 4 | 12 | **Future: never started** |
| Sprint 2 (id 2) | Validate and fix | 10 | 38 | 30 | 0 | 8 | **Future: never started** |
| Sprint 3 (id 3) | Improve, test, document | 8 | 29 | 21 | 3 | 5 | **Future: never started** |

**No sprint evidence exists yet.** All three sprints are in the Future state, with no start or end dates. Jira only produces a burndown chart and sprint report for a started sprint, so:

* there are **no burndown screenshots**;
* there are **no sprint-report screenshots**;
* there are **no sprint review or retrospective records**.

None are included, and none have been created.

**Work happened outside sprints.** All 19 Done Stories (71 points) were delivered between 22 and 24 November 2026, before any sprint was started. They include 13 Stories that were planned for Sprints 2 and 3.

**For the next planning session.** The team needs to decide how these Done Stories are treated when the first sprint is started. The agenda and options are in `docs/agile/SPRINT_PLANNING_AND_TRACKING.md`.

## 9. Story point distribution

| Owner | Planned | Done | In Progress | To Do |
|---|---:|---:|---:|---:|
| Shimon Sarin | 21 | 0 | 0 | 21 |
| Aryan Gupta | 21 | 21 | 0 | 0 |
| Shikhar Kesharwani | 28 | 28 | 0 | 0 |
| Avanish Rajauria | 29 | 22 | 7 | 0 |
| Shared (CHURN-34, CHURN-35) | 4 | 0 | 0 | 4 |
| **Total** | **103** | **71** | **7** | **25** |

CHURN-45 and CHURN-46 have no story points and are not included.

## 10. Test results

| Suite | Command | Result | Where recorded |
|---|---|---|---|
| Backend | `cd backend && python -m pytest -q` | **481 passed** (Python 3.13.18, with dev requirements) | CHURN-25 comment; PR #8 |
| Backend API-layer coverage | `pytest --cov=main --cov=customer_similarity --cov=churniq_core --cov-branch` | 93% | CHURN-25 |
| Frontend | `cd frontend && npm test` | **70 passed** (added in PR #8) | PR #8; CI |
| Frontend build | `npm run build` | passes | CI |
| UI checks in a real browser | Playwright scripts against the local backend | 41/41 value checks, 7/7 customers, 19/19 test-sheet steps, 42/42 layout cases | `docs/frontend/UI_TEST_REPORT.md` |

**Known test gap:** with only `requirements.txt` installed, 9 ML tests fail on a missing `imblearn` package (CHURN-46).

## 11. Pull requests and merge status

| PR | Title (short) | Opened by | Merged by | Approval | Status |
|---|---|---|---|---|---|
| #1 | Feature/aryan e2 ml validation | aryan-guptta-2007 | aryan-guptta-2007 | Shikhar, before merge | Merged 23 Nov |
| #2 | E3 + E4 API quality | Shikhar-Kesharwani | Shikhar-Kesharwani | Aryan, before merge | Merged 23 Nov |
| #3 | Configurable Gemini model | Shikhar-Kesharwani | aryan-guptta-2007 | Aryan, before merge | Merged 23 Nov |
| #4 | Secure email endpoint | Shikhar-Kesharwani | aryan-guptta-2007 | Aryan, **after** merge | Merged 23 Nov |
| #5 | Live Gemini test docs | Shikhar-Kesharwani | Shikhar-Kesharwani | Aryan, **after** merge | Merged 23 Nov |
| #6 | Student contribution attribution report | Shikhar-Kesharwani | Shikhar-Kesharwani | none | Merged 24 Nov |
| #7 | CI workflow | Shikhar-Kesharwani | Shikhar-Kesharwani | none (CI passed) | Merged 24 Nov |
| #8 | E5 frontend and E6 report | AvanishRajauria | Shikhar-Kesharwani | Shikhar-Kesharwani, **before** merge (two approvals on head `2feb096`, 11:41 and 11:43 UTC) | **Merged 24 Nov, 11:44 UTC, commit `58a98c1`** |

**About these columns:** they record the GitHub account that performed each action, not necessarily the person operating it. Several PRs were opened or merged through AI-assisted development tools acting on a student's account (see `docs/CONTRIBUTOR_ATTRIBUTION.md`).

**This report update** is delivered in a separate documentation PR from branch `docs/avanish-e6-post-merge-status`. It awaits a teammate's review.

**Branch protection:** `main` has been protected since 24 November 2026, set up after PR #7 was merged. Merging needs a pull request, one approval, and passing **Backend tests** and **Frontend build** checks.

## 12. CI results

| Run | Trigger | Commit | Backend tests | Frontend build |
|---|---|---|---|---|
| #1 | PR #7 | `a85565e` | ✅ | ✅ |
| #2 | push to `main` after PR #7 | `e95b65b` | ✅ | ✅ |
| #3 | PR #8 (code commit) | `3b91b2a` | ✅ | ✅ (includes `npm test`) |
| #4 | PR #8 | `722df03` | ✅ | ✅ |
| #5 | PR #8 (merged head) | `2feb096` | ✅ | ✅ |
| #6 | push to `main` after PR #8 | `58a98c1` | ✅ | ✅ |

## 13. Outstanding work and blockers

| Item | Who acts | Blocks |
|---|---|---|
| Hold a real sprint-planning session; agree scope, dates and how to treat already-Done Stories (agenda in `docs/agile/SPRINT_PLANNING_AND_TRACKING.md`) | Whole team | CHURN-33 |
| Start the agreed sprint in Jira on its real start date (not backdated) | Avanish, after the team agrees | CHURN-32, CHURN-33, CHURN-36 |
| Record stand-ups and blockers during the sprint | Whole team (CHURN-34) | CHURN-34 |
| At sprint end: save the burndown and sprint report, hold the review and retrospective, complete the sprint | Whole team; notes on CHURN-35 | CHURN-33, CHURN-35, CHURN-36 |
| Review the backlog once per sprint | Avanish | CHURN-32 |
| Review this report | A teammate | CHURN-36 |
| E1 (CHURN-7 to CHURN-12) not started | Shimon | E1 |
| CHURN-45 and CHURN-46 unassigned | Project lead; suggested owner E2 (Aryan) | E2 |
| Segments page has hard-coded `REVENUE` and `INSIGHTS` that contradict `/segments` | Shimon, as part of CHURN-10 | CHURN-10 |
| `/segments` `monthly_trend` is simulated, not real data | Team decision; the UI labels it as simulated | — |
| Confirm whether Vercel sets `VITE_API_URL`; otherwise production uses `frontend/.env.production` | Whoever manages the Vercel project | — |
| 22 Stories still have acceptance criteria marked "drafted — awaiting team approval" | Team, at planning | All of them |

## 14. Recommendations

1. **Hold sprint planning now.** Use the agenda in `docs/agile/SPRINT_PLANNING_AND_TRACKING.md`. Confirm the drafted acceptance criteria, decide where the already-Done Stories belong, and start the sprint in Jira with real dates. Do not backdate it.
2. **Start E1.** It is the largest untouched area (21 points). CHURN-26's dashboard checks can be reused for CHURN-11.
3. **Assign CHURN-45 and CHURN-46**, and fix CHURN-46 so the full test suite installs on the declared Python version.
4. **Keep the review gate.** Avoid approvals after merge (as happened on PRs #4 and #5) and unreviewed merges (PRs #6 and #7). Branch protection now enforces this.
5. **Finish CHURN-36 at the end of each sprint.** Add the burndown and sprint-report screenshots and the review and retrospective notes once they exist.
