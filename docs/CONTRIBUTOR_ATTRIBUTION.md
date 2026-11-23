# CHURN-IQ — Student Contribution Attribution

This report records which student is responsible for each piece of work in this
repository. It is built from three sources: the Jira project, GitHub pull-request
records, and the Git commit history. Everything below can be checked against those
sources.

**Student contributors:** Aryan Gupta and Shikhar Kesharwani.

Audited state: `main` at `eb7f75b75fcf28d43d80805a3896fe05e52ea5dd`. It contains 23
commits, and every branch in the repository has been merged into it. This report does
not change any commit, author field or merge record.

---

## 1. How to read this report

These columns mean different things, so keep them separate:

| Term | Meaning | Source |
|---|---|---|
| **Student Responsible** | The student accountable for the work. For implementation commits this is the Jira assignee and PR owner. For merge commits it is the person who performed the merge. | Jira assignee, GitHub PR `user` / `merged_by` |
| **PR Owner** | The GitHub account that opened the pull request. | GitHub PR `user` |
| **Recorded Git author** | The author identity stored in the commit. It is shown in full and is **not** changed by this report. | `git log` |

**"Student Responsible" is not a claim of personal Git authorship.** For several
commits the Git author is an identity used by AI-assisted development tools, not a
student account. Those rows say so in the Verification Evidence column.

**Use of AI-assisted development tools:** both students used AI-assisted development
tools. Every commit produced with them carries a co-author trailer in its commit
message, and the evidence column flags each one. The Git records can't show how the
work was split between a student and a tool inside a single commit. This report
doesn't try to.

---

## 2. Jira task allocation, checked against GitHub

Every Story was reported by **Avanish Rajauria**, who is not a student contributor.
"Status" is the current Jira status; all tasks below are **Done**.

### 2.1 Stories

| Jira | Summary | Jira assignee | Assignee history | Delivered in |
|---|---|---|---|---|
| CHURN-13 | Review XGBoost pipeline | Aryan Gupta | Reassigned 22 Nov from an earlier Jira account `aryanguptta.s` to "Aryan Gupta" (by Avanish Rajauria) | PR #1 |
| CHURN-14 | Evaluate model performance | Aryan Gupta | Same reassignment as CHURN-13 | PR #1 |
| CHURN-15 | Validate SHAP explanations | Aryan Gupta | Same reassignment as CHURN-13 | PR #1 |
| CHURN-16 | Verify CLV calculation and tiers | Aryan Gupta | Same reassignment as CHURN-13 | PR #1 |
| CHURN-17 | Model improvement research | Aryan Gupta | Same reassignment as CHURN-13 | PR #1 |
| CHURN-18 | Review all FastAPI endpoints | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-19 | Validate API response formats | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-20 | Improve input validation | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-21 | Handle backend errors | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-22 | Gemini retention API integration test | Shikhar Kesharwani | Never reassigned | PR #2, PR #3, PR #5 (docs) |
| CHURN-23 | Test KNN similarity results | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-24 | Test What-If prediction endpoint | Shikhar Kesharwani | Never reassigned | PR #2 |
| CHURN-25 | Edge-case tests + test coverage | Shikhar Kesharwani | Never reassigned | PR #2, PR #5 (docs) |

### 2.2 Bugs

| Jira | Summary (short) | Assignee | Reporter | Fixed in |
|---|---|---|---|---|
| CHURN-37 | 4,000 unscored customers shown as 0% risk; HTTP 500s | **Unassigned** | Aryan Gupta | PR #1 (`1be47ea`, `ffde7ed`, `55192ca`) |
| CHURN-38 | CUST99999 demo customer with hard-coded values | **Unassigned** | Aryan Gupta | PR #1 (`1be47ea`, "Bug B"; `3646fed` records "CHURN-37/38 resolved") |
| CHURN-39 | `/whatif` accepts invalid / NaN input | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 |
| CHURN-40 | `/customers` ignores invalid filters; leakage sort | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 |
| CHURN-41 | `/customer-similarity` rewrites invalid `n_neighbors` | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 |
| CHURN-42 | `/retention` model label, scale, timeout | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 |
| CHURN-43 | Inconsistent error responses | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 |
| CHURN-44 | `/send-email` injection and data exposure | Shikhar Kesharwani | Shikhar Kesharwani | PR #2 (partial), PR #4 (auth + rate limiting) |

### 2.3 Pull requests

| PR | Title (short) | PR Owner (opened by) | Merged by | Approved by (time vs merge) | Jira scope |
|---|---|---|---|---|---|
| #1 | Feature/aryan e2 ml validation | Aryan Gupta (`aryan-guptta-2007`) | Aryan Gupta | Shikhar Kesharwani, before merge | CHURN-13 to CHURN-17, CHURN-37, CHURN-38 |
| #2 | E3 + E4: API review, validation, error handling, tests | Shikhar Kesharwani (`Shikhar-Kesharwani`) | Shikhar Kesharwani | Aryan Gupta, before merge | CHURN-18 to CHURN-25, CHURN-39 to CHURN-44 |
| #3 | fix(gemini): configurable model | Shikhar Kesharwani | Aryan Gupta | Aryan Gupta, before merge | CHURN-22 |
| #4 | Fix CHURN-44: secure email endpoint | Shikhar Kesharwani | Aryan Gupta | Aryan Gupta, **after** merge | CHURN-44 |
| #5 | docs(api): live Gemini test, test chronology | Shikhar Kesharwani | Shikhar Kesharwani | Aryan Gupta, **after** merge | CHURN-22, CHURN-25 (documentation) |

Each Jira key above was checked against the commit messages in that PR. PR #1's
description reads "Complete Aryan E2 ML Tasks — CHURN-13 to CHURN-17".

---

## 3. Commit-level contribution table (all 23 commits)

Rows are in chronological order. Abbreviations in the evidence column:
- **AI-assisted:** the commit message carries a co-author trailer for AI-assisted development tools.
- **Tool identity:** the Git author is the account used by those tools, not a student account.

| Commit SHA | Student Responsible | PR Number | PR Owner | Work Description | Verification Evidence |
|---|---|---|---|---|---|
| `4fad66925c3e61af8e39a52606211687dec476b9` | **Pending verification** | None (direct push to `main`) | N/A | Initial full-stack platform with KNN similarity finder (37 files, +15,411 lines) | Recorded Git author "Shikhar Kesharwani" with a placeholder email `@example.com`. Not linked to any GitHub account. No trailer either way. |
| `3f348b015b9d04c90eebc18ffd9f25b5ad3b0c9d` | **Pending verification** | None (direct push to `main`) | N/A | Read Gmail credentials from environment variables | Same placeholder email; not linked to any GitHub account. |
| `97f8cae060c6702be577dabcb75518a74a48acbc` | **Pending verification** | None (direct push to `main`) | N/A | Harden `.gitignore`, add `.env.example` templates | Same placeholder email; not linked to any GitHub account. |
| `59f96058db4aef8d66a81279ac28684ef7807320` | Aryan Gupta | #1 | Aryan Gupta | E2 ML validation: serving-skew fix, evaluation, SHAP, CLV, model research (CHURN-13 to CHURN-17) | Git author Aryan Gupta, linked to `aryan-guptta-2007`. Jira assignee: Aryan. AI-assisted. Committer is the tool identity. |
| `95f61e83e5b5ec47bf328cbd003ab55858b8f166` | Aryan Gupta | #1 | Aryan Gupta | CHURN-16 follow-up audit: unscored customers, demo CLV | Git author Aryan, linked to `aryan-guptta-2007`. AI-assisted. Committer is the tool identity. |
| `1be47ea901eef7484980edfe28e84301e0e66ee2` | Aryan Gupta | #1 | Aryan Gupta | Unscored-customer handling and demo-customer fix (CHURN-16, CHURN-37 interim, CHURN-38) | Git author Aryan, linked to `aryan-guptta-2007`. AI-assisted. Committer is the tool identity. |
| `ffde7ed78553d4310f7cc75d39b2d5c265e94e44` | Aryan Gupta | #1 | Aryan Gupta | Out-of-fold predictions for all customers (CHURN-37) | Git author and committer Aryan, linked to `aryan-guptta-2007`. AI-assisted. |
| `55192ca7838c14ef424ec4d6e4ee1c0d714ee005` | Aryan Gupta | #1 | Aryan Gupta | Serve out-of-fold predictions; what-if routing (CHURN-37) | Git author and committer Aryan, linked to `aryan-guptta-2007`. AI-assisted. |
| `3646fed158311a8a5f72987e27c90ca5e5bf740b` | Aryan Gupta | #1 | Aryan Gupta | Prediction-coverage docs, SHAP sign display fix (CHURN-37/38) | Git author and committer Aryan, linked to `aryan-guptta-2007`. AI-assisted. |
| `c5d23da2649ddd395224ac7c3e2d6bc048ceb777` | **Pending verification** | #1 | Aryan Gupta | Cross-platform fixes to ML validation tests (2 files) | Recorded Git author "Shikhar Kesharwani" with the placeholder `@example.com` email. Not linked to any GitHub account. Not credited to the PR owner by default. |
| `013a068e109beabf7fff0d7842dc0e131cd6fc72` | **Pending verification** | #1 | Aryan Gupta | Mark out-of-fold coverage implemented in ML docs (1 file) | Same placeholder email; not linked to any GitHub account. |
| `7d605c58616608ecb4001991b3664e56ddf06cb2` | Aryan Gupta (merge) | #1 | Aryan Gupta | Merge PR #1 | Merge author Aryan Gupta, linked to `aryan-guptta-2007`. GitHub `merged_by: aryan-guptta-2007`. |
| `bf8accc87db9be673f677d048df689bf09ae050e` | Shikhar Kesharwani | #2 | Shikhar Kesharwani | API validation, consistent JSON errors, response models, safe Gemini handling (CHURN-19 to CHURN-22, CHURN-39 to CHURN-44) | Jira assignee: Shikhar. **Recorded Git author: tool identity (not a student account).** Produced under Shikhar's task ownership. |
| `64488ac4f032d137a421896b3b27f27264f3b38e` | Shikhar Kesharwani | #2 | Shikhar Kesharwani | Contract, validation, error, Gemini, KNN and What-If test suites (CHURN-18 to CHURN-25) | Jira assignee: Shikhar. **Recorded Git author: tool identity.** |
| `1d184a2c10d260c8c92a3090e44740f465f20fee` | Shikhar Kesharwani | #2 | Shikhar Kesharwani | API documentation: endpoint inventory, validation, error strategy (CHURN-18 to CHURN-25) | Jira assignee: Shikhar. **Recorded Git author: tool identity.** |
| `54dcd92af05617f1dcd479e23aa764904552cdbe` | Shikhar Kesharwani (merge) | #2 | Shikhar Kesharwani | Merge PR #2 | Merge author Shikhar Kesharwani, linked to `Shikhar-Kesharwani`. GitHub `merged_by: Shikhar-Kesharwani`. |
| `279ad5f9441c89f976424d91d917fd7d061472fb` | Shikhar Kesharwani | #3 | Shikhar Kesharwani | Configurable Gemini model (CHURN-22) | Jira assignee: Shikhar. **Recorded Git author: tool identity.** |
| `4b1da04c3c1eafc60c0dbf12c6f3e074736a7d5e` | Shikhar Kesharwani | #3 | Shikhar Kesharwani | Document Gemini model configuration (CHURN-22) | Jira assignee: Shikhar. **Recorded Git author: tool identity.** |
| `39c1aa2c6e72a76122957189a9d60aec9d1f6e4b` | Aryan Gupta (merge) | #3 | Shikhar Kesharwani | Merge PR #3 | Merge author Aryan, linked to `aryan-guptta-2007`. `merged_by: aryan-guptta-2007`. PR opened by Shikhar, merged by Aryan. |
| `a9bb485ced8bebdcd720412912c81c9a6f0de60e` | Shikhar Kesharwani | #4 | Shikhar Kesharwani | Secure `/send-email`: token auth and rate limiting (CHURN-44) | Jira assignee: Shikhar. **Recorded Git author name shows "Shikhar Kesharwani", but the email and GitHub link belong to the tool identity.** This is not personal Git authorship. AI-assisted. |
| `4f414d2b037081ff9d544e7718c05da3bd5cca5f` | Aryan Gupta (merge) | #4 | Shikhar Kesharwani | Merge PR #4 | Merge author Aryan, linked to `aryan-guptta-2007`. `merged_by: aryan-guptta-2007`. PR opened by Shikhar, merged by Aryan. |
| `a79ba50bf014fd1b07677c09880d9963c382a673` | Shikhar Kesharwani | #5 | Shikhar Kesharwani | Record live Gemini test; clarify test chronology (CHURN-22, CHURN-25 docs) | Jira assignee: Shikhar. **Recorded Git author name shows "Shikhar Kesharwani", but the email and GitHub link belong to the tool identity.** This is not personal Git authorship. AI-assisted. |
| `eb7f75b75fcf28d43d80805a3896fe05e52ea5dd` | Shikhar Kesharwani (merge) | #5 | Shikhar Kesharwani | Merge PR #5 | Merge author Shikhar, linked to `Shikhar-Kesharwani`. `merged_by: Shikhar-Kesharwani`. |

---

## 4. Student summaries

### 4.1 Aryan Gupta

**Jira responsibility**
- Assignee of Stories CHURN-13 to CHURN-17 (Epic CHURN-2, ML validation).
- Reporter of Bugs CHURN-37 and CHURN-38. Both are unassigned in Jira and were fixed in Aryan's PR #1.

**Pull requests**
- Opened and merged PR #1, which delivers CHURN-13 to CHURN-17, CHURN-37 and CHURN-38.

**Commits credited (6 implementation commits)**
- `59f9605`, `95f61e8`, `1be47ea`, `ffde7ed`, `55192ca`, `3646fed`.
- Each one is recorded with Aryan's own Git identity, linked to `aryan-guptta-2007`.
- All six were produced with AI-assisted development tools, as their commit trailers show.

**Personal GitHub activity that can be checked directly**
- Merged PRs #1, #3 and #4 (merge commits `7d605c5`, `39c1aa2`, `4f414d2`).
- Approved PRs #2, #3, #4 and #5. The approvals on #4 and #5 were submitted after those PRs had already merged.

### 4.2 Shikhar Kesharwani

**Jira responsibility**
- Assignee of Stories CHURN-18 to CHURN-25 (Epics CHURN-3 and CHURN-4, API quality and testing).
- Assignee and reporter of Bugs CHURN-39 to CHURN-44.

**Pull requests**
- Opened PRs #2, #3, #4 and #5.
- Merged #2 and #5. Aryan merged #3 and #4.

**Commits credited for task ownership (7 implementation and documentation commits)**
- `bf8accc`, `64488ac`, `1d184a2`, `279ad5f`, `4b1da04`, `a9bb485`, `a79ba50`.
- For all seven, the recorded Git author is the AI-assisted development tool identity, not Shikhar's account.
- Shikhar is credited as the student responsible through Jira assignment and PR ownership, not as the personal Git author.
- `a9bb485` and `a79ba50` display Shikhar's name in the author field, but their email and GitHub link belong to the tool identity.

**Personal GitHub activity that can be checked directly**
- Merged PRs #2 and #5 (merge commits `54dcd92`, `eb7f75b`).
- Approved PR #1 before it was merged.
- Opened PRs #2 to #5.

---

## 5. Historical authorship pending verification

The five commits listed below show the author name "Shikhar Kesharwani" but use the
placeholder email `shikhar.kesharwani@example.com`. An `example.com` address can't be
verified on any GitHub account, so GitHub doesn't link these commits to anyone. Their
messages contain no trailer that indicates how they were produced.

| Commit SHA | PR | PR Owner | Status |
|---|---|---|---|
| `4fad66925c3e61af8e39a52606211687dec476b9` | None (direct push) | N/A | Pending verification |
| `3f348b015b9d04c90eebc18ffd9f25b5ad3b0c9d` | None (direct push) | N/A | Pending verification |
| `97f8cae060c6702be577dabcb75518a74a48acbc` | None (direct push) | N/A | Pending verification |
| `c5d23da2649ddd395224ac7c3e2d6bc048ceb777` | #1 | Aryan Gupta | Pending verification |
| `013a068e109beabf7fff0d7842dc0e131cd6fc72` | #1 | Aryan Gupta | Pending verification |

None of these is credited to either student in this report. To resolve them, the
actual author should confirm authorship, for example by stating it in a review comment
on the PR that adds this file. This report can then be updated to match. The commits
themselves will not be rewritten.

---

## 6. What this report does not change

- No commit was rewritten, amended or rebased. All 23 SHAs on `main` are unchanged.
- The recorded Git author fields remain exactly as shown in `git log`, including the
  two whose name field doesn't match their email.
- Merge records, PR ownership and review records on GitHub are unchanged.
- This file is the only change, added through a separate pull request for review.
