# CHURN-IQ — Project Progress Report

**Report date:** 24 November 2026
**Prepared by:** Avanish Rajauria, for CHURN-36 (E6 — Agile Management & Integration)
**Sources:**
* Jira project CHURN on `avanishrajauria.atlassian.net`, board 3;
* GitHub repository `Shikhar-Kesharwani/CHURN-IQ`;
* CI runs;
* `docs/api/README.md`, `docs/ml/` and `docs/frontend/UI_TEST_REPORT.md`.

**Method:** every number below was read from Jira or GitHub on the report date. Nothing marked "pending" has happened yet, and no meeting, metric or screenshot has been invented to fill a gap. This report was prepared with AI-assisted development tools.

> **Status of this report:** draft for team review in PR #8. CHURN-36 cannot be closed yet, because its acceptance criteria require burndown and sprint-report screenshots and review/retrospective notes. None of these exist yet; see §8 and §13.

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

| Measure | Value |
|---|---|
| Planned Stories (CHURN-7 to CHURN-36) | 30 Stories, **103 story points** |
| Stories Done | 13 of 30, **49 of 103 points (48%)** |
| Stories In Progress | 9 (CHURN-26 to CHURN-33 and CHURN-36), 29 points; the E5 code is in PR #8, awaiting review |
| Stories To Do | 8 (CHURN-7 to CHURN-12, CHURN-34, CHURN-35), 25 points |
| Epics Done | 2 of 6 (E3, E4) |
| Sprints started | **0 of 3** |

## 3. Outcomes per Epic

| Epic | Stories | Status | Outcome |
|---|---|---|---|
| **E1 — Data & Analytics** | CHURN-7 to CHURN-12 (21 points) | To Do, 0 of 6 | Not started. |
| **E2 — ML & Explainability** | CHURN-13 to CHURN-17 (21 points) | 5 of 5 Done; Epic still To Do | See below. |
| **E3 — Backend & API** | CHURN-18 to CHURN-22 (17 points) | 5 of 5 Done; Epic Done | See below. |
| **E4 — Similarity & What-If** | CHURN-23 to CHURN-25 (11 points) | 3 of 3 Done; Epic Done | See below. |
| **E5 — Frontend & Dashboard** | CHURN-26 to CHURN-31 (22 points) | 6 In Progress | See below. |
| **E6 — Agile & Integration** | CHURN-32 to CHURN-36 (11 points) | 3 In Progress, 2 To Do | See below. |

**E2:**
* The training/serving skew was fixed.
* Model evaluated: holdout ROC-AUC 0.7167.
* SHAP and CLV were validated.
* Genuine predictions now exist for all 5,001 customers (out-of-fold for the training split): bugs CHURN-37 and CHURN-38, both Done.
* Model research found a regularised variant scoring 0.758 test AUC.
* The Epic stays open because two follow-ups under it are open: CHURN-45 (model monotonicity) and CHURN-46 (dev-requirements and Python version).

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
* Each Story was tested against the real API, and six defects were reproduced and logged as CHURN-47 to CHURN-52.
* All six are fixed in **PR #8**, with 70 frontend tests and a measured UI test report.
* The Stories cannot be closed until a teammate approves and merges PR #8.

**E6:**
* Backlog audit done (CHURN-32), sprint tracking record done (CHURN-33), this report drafted (CHURN-36).
* Shared Stories CHURN-34 and CHURN-35 have not been carried out as team activities.

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

**Not Shikhar Jira tickets, so not credited above:**

* **Repository CI** was added in PR #7, under the `Shikhar-Kesharwani` account, through AI-assisted development tools.
* **Branch protection** on `main` was enabled on 24 November 2026 from the repository admin account.

These are account actions; see `docs/CONTRIBUTOR_ATTRIBUTION.md`.

## 6. Avanish Rajauria — scope and status

| Story | Points | Status | Evidence |
|---|---|---|---|
| CHURN-26 Dashboard KPIs | 3 | In Progress | PR #8; UI test report §2; Bug CHURN-47 |
| CHURN-27 Risk table | 5 | In Progress | PR #8; report §3; Bug CHURN-48 |
| CHURN-28 Customer detail | 3 | In Progress | PR #8; report §4 (7 customers); Bug CHURN-52 |
| CHURN-29 Frontend–backend integration | 3 | In Progress | PR #8; report §5; Bug CHURN-49 |
| CHURN-30 Navigation, responsive, UX | 5 | In Progress | PR #8; report §6 (42 overflow cases); Bug CHURN-51 |
| CHURN-31 What-If and similarity UI | 3 | In Progress | PR #8; report §7 (test sheet, 19 steps); Bug CHURN-50 |
| CHURN-32 Backlog | 2 | In Progress | Jira comment 10047 (backlog audit) |
| CHURN-33 Sprint planning and tracking | 2 | In Progress | Jira comment 10048 (tracking record and proposed plan) |
| CHURN-36 Final report | 3 | In Progress | This document |

**Why none of these is Done yet:**

* **CHURN-26 to CHURN-31:** the work, tests and evidence are complete, but the code is not merged. Branch protection requires a teammate's approval.
* **CHURN-32:** its second criterion is "reviewed every sprint", and no sprint has run.
* **CHURN-33 and CHURN-36:** they need started sprints, sprint reports, and real review and retrospective sessions.

## 7. Jira issue summary

| Type | Total | Done | In Progress | To Do |
|---|---|---|---|---|
| Epics | 6 | 2 (E3, E4) | 0 | 4 (E1, E2, E5, E6) |
| Stories | 31 (30 planned + CHURN-45) | 13 | 9 | 9 |
| Bugs | 15 (CHURN-37 to CHURN-44, CHURN-46 to CHURN-52) | 8 | 6 (CHURN-47 to CHURN-52, fixed in PR #8) | 1 (CHURN-46) |
| **Total** | **52** | **23** | **15** | **14** |

## 8. Sprints

| Sprint | Goal | Stories | Points | Done points | Jira state | Burndown / sprint report |
|---|---|---|---|---|---|---|
| Sprint 1 (id 1) | Understand the system and baseline everything | 12 | 36 | 17 | future (never started) | **Not available** |
| Sprint 2 (id 2) | Validate and fix | 10 | 38 | 19 | future (never started) | **Not available** |
| Sprint 3 (id 3) | Improve, test, document | 8 | 29 | 13 | future (never started) | **Not available** |

* **No reports exist.** Jira only produces a burndown chart and sprint report for a started sprint. Because no sprint has been started, **no burndown or sprint-report screenshots exist**. None are included, and none have been created.
* **Work happened outside sprints.** All 49 completed points were delivered outside a running sprint (22–24 November 2026), including Stories planned for Sprints 2 and 3.
* **Next step.** A proposed planning record is on CHURN-33 for the team to agree.

## 9. Story point distribution

| Owner | Planned | Done | In Progress | To Do |
|---|---|---|---|---|
| Shimon Sarin | 21 | 0 | 0 | 21 |
| Aryan Gupta | 21 | 21 | 0 | 0 |
| Shikhar Kesharwani | 28 | 28 | 0 | 0 |
| Avanish Rajauria | 29 | 0 | 29 | 0 |
| Shared (CHURN-34, CHURN-35) | 4 | 0 | 0 | 4 |
| **Total** | **103** | **49** | **29** | **25** |

## 10. Test results

| Suite | Command | Result | Where recorded |
|---|---|---|---|
| Backend | `cd backend && python -m pytest -q` | **481 passed** on `main` and on the PR #8 branch (Python 3.13.18, with dev requirements) | CHURN-25 comment; PR #8 |
| Backend API-layer coverage | `pytest --cov=main --cov=customer_similarity --cov=churniq_core --cov-branch` | 93% | CHURN-25 |
| Frontend | `cd frontend && npm test` | **70 passed** (new in PR #8) | PR #8 |
| Frontend build | `npm run build` | passes | CI |
| UI checks in a real browser | Playwright scripts against the local backend | All checks pass after the fixes; failures before them are logged as CHURN-47 to CHURN-52 | `docs/frontend/UI_TEST_REPORT.md` |

**Known test gap:** with only `requirements.txt` installed, 9 ML tests fail on a missing `imblearn` package (CHURN-46).

## 11. Pull requests and merge status

| PR | Title (short) | Opened by | Merged by | Approval | Status |
|---|---|---|---|---|---|
| #1 | Feature/aryan e2 ml validation | aryan-guptta-2007 | aryan-guptta-2007 | Shikhar, before merge | Merged |
| #2 | E3 + E4 API quality | Shikhar-Kesharwani | Shikhar-Kesharwani | Aryan, before merge | Merged |
| #3 | Configurable Gemini model | Shikhar-Kesharwani | aryan-guptta-2007 | Aryan, before merge | Merged |
| #4 | Secure email endpoint | Shikhar-Kesharwani | aryan-guptta-2007 | Aryan, **after** merge | Merged |
| #5 | Live Gemini test docs | Shikhar-Kesharwani | Shikhar-Kesharwani | Aryan, **after** merge | Merged |
| #6 | Student contribution attribution report | Shikhar-Kesharwani | Shikhar-Kesharwani | none | Merged |
| #7 | CI workflow | Shikhar-Kesharwani | Shikhar-Kesharwani | none (CI passed) | Merged |
| #8 | E5 frontend and E6 report | AvanishRajauria | — | **awaiting review** | Open |

**About these columns:** they record the GitHub account that performed each action, not necessarily the person operating it. Several PRs were opened or merged through AI-assisted development tools acting on a student's account (see `docs/CONTRIBUTOR_ATTRIBUTION.md`).

**Branch protection:** `main` has been protected since 24 November 2026, set up after PR #7 was merged. Merging needs a pull request, one approval, and passing **Backend tests** and **Frontend build** checks.

## 12. CI results

| Run | Trigger | Backend tests | Frontend build |
|---|---|---|---|
| PR #7 | pull request | ✅ | ✅ |
| `main` after PR #7 | push | ✅ | ✅ |
| PR #8 | pull request | see the PR's checks | ✅ (now includes `npm test`) |

## 13. Known defects and blockers

| Item | Owner / action needed |
|---|---|
| PR #8 needs one approving review | A teammate (Aryan, Shikhar or Shimon) reviews and approves it; then it can be merged and CHURN-26 to CHURN-31 and CHURN-47 to CHURN-52 closed |
| No sprint started, so there are no burndown or sprint reports | Team planning session, then the project lead (Avanish) starts the agreed sprint with real dates |
| Review and retrospective not held (CHURN-35) | Whole team at the end of each sprint; notes go on CHURN-35 |
| E1 (CHURN-7 to CHURN-12) not started | Shimon |
| CHURN-45 (What-If monotonicity) unassigned | Lead to assign; suggested owner E2 (Aryan) |
| CHURN-46 (dev requirements and Python version) unassigned | Lead to assign; suggested owner E2 tooling (Aryan) |
| Segments page has hard-coded `REVENUE` and `INSIGHTS` that contradict `/segments` | Shimon, as part of CHURN-10 |
| `/segments` `monthly_trend` is simulated, not real data | Team decision; the UI labels it as simulated |
| 22 Stories still have acceptance criteria marked "drafted — awaiting team approval" | Team confirms at planning |

**Review and retrospective evidence:** none recorded. No sprint review or retrospective has taken place in Jira or in the repository. The CHURN-35 notes are pending.

## 14. Recommendations

1. **Hold Sprint planning now.** Confirm the drafted acceptance criteria, decide where the already-Done Stories belong, and start the sprint in Jira with real dates. Do not backdate it.
2. **Review and merge PR #8.** That closes most of E5 (22 points) and six bugs.
3. **Start E1.** It is the largest untouched area (21 points). CHURN-26's dashboard checks can be reused for CHURN-11.
4. **Assign CHURN-45 and CHURN-46**, and fix CHURN-46 so the full test suite installs on the declared Python version.
5. **Keep the review gate.** Avoid approvals after merge (as happened on PRs #4 and #5) and unreviewed merges (PRs #6 and #7). Branch protection now enforces this.
6. **Finish CHURN-36 at the end of each sprint.** Add the burndown and sprint-report screenshots and the review and retrospective notes once they exist.
