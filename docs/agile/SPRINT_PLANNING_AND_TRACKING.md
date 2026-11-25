# CHURN-IQ — Sprint Planning and Tracking (CHURN-33)

**Owner:** Avanish Rajauria (E6). **Board:** CHURN board, id 3, on `avanishrajauria.atlassian.net`.

> **Update, 25 November 2026 (Avanish Rajauria, AI-assisted).** This note is current. The rest of the document is the original agenda and templates from 24 Nov, kept unchanged for history. Statements there such as "no planning meeting … has taken place yet" were true when written.
>
> **What happened:**
> * **Sprint 1 planning was held on 20 November 2026,** with all four members present, as confirmed by Avanish. It is recorded on CHURN-58 (Done, comments 10083–10085).
> * **No planning meeting was held for Sprint 2 or Sprint 3.** This is recorded on CHURN-62 and CHURN-66, which stay To Do.
> * **No stand-ups, sprint reviews or retrospectives were held.** No burndown chart or sprint report exists.
>
> **Team decisions that replaced the process below:**
> 1. **Blank dates, never started.** Sprints 1–3 keep blank start and end dates and are never started (CHURN-58, comment 10085).
> 2. **Task groupings.** Sprints 1–3 are task groupings, not calendar Scrum events (comments 10108–10111 on CHURN-35, 66, 67 and 68).
>
> **Consequences:**
> * The §4.1–§4.5 templates were used only for Sprint 1 planning.
> * The backlog reviews (§4.6) were done before execution for all three groupings: CHURN-61, 65 and 69, all Done.
>
> **Treatment of the 19 Stories completed before planning (§2):** they are in the backlog (CHURN-32, comment 10070), which is option B in practice. **The team has not yet confirmed option A or B** (CHURN-32, comment 10139).
>
> **§5, Definition of Done, as now applied:**
>
> | Story | Status (25 Nov 2026) |
> |---|---|
> | CHURN-32 | In Progress. Reviews for all three groupings are Done; it waits only on the option A/B confirmation |
> | CHURN-33 | **Done.** Criteria amended to the two decisions; original wording kept in the description; evidence in comment 10138 |
> | CHURN-36 | In Progress. Criteria amended the same way; `docs/PROJECT_PROGRESS_REPORT.md` section F is the final report, and it closes once a teammate approves and merges it |
>
> **Later on 25 Nov:** under the same two decisions, the shared ceremony records CHURN-35, 60, 63, 64, 67 and 68 were closed as **not applicable**.
> * Their original Definitions of Done are kept in the descriptions, and each carries the label `not-applicable`.
> * Closing them does not mean any review, retrospective or stand-up took place.
> * CHURN-59, 62 and 66 (assigned records of the same kind) are unchanged.
>
> **Current issue status** is in `docs/PROJECT_PROGRESS_REPORT.md`, section F.

This document is a **planning agenda and a set of blank tracking templates**. It records the current Jira state, and gives the team a process to follow once sprints actually run.

**No planning meeting, stand-up, sprint review or retrospective is recorded here.** None has taken place yet. Fill in the templates only with what really happens, on the day it happens. Prepared with AI-assisted development tools.

---

## 1. Current state (read from Jira, 24 November 2026)

| Sprint | Goal | Jira state | Start / end dates | Stories | Points | Done | In Progress | To Do |
|---|---|---|---|---|---|---|---|---|
| CHURN Sprint 1 (id 1) | Understand the system and baseline everything | Future | not set | 12 | 36 | 20 | 4 | 12 |
| CHURN Sprint 2 (id 2) | Validate and fix | Future | not set | 10 | 38 | 30 | 0 | 8 |
| CHURN Sprint 3 (id 3) | Improve, test, document | Future | not set | 8 | 29 | 21 | 3 | 5 |

**Issues per sprint**

| Sprint | Done | In Progress | To Do |
|---|---|---|---|
| Sprint 1 | CHURN-13, 14 (Aryan); CHURN-18, 19, 23 (Shikhar); CHURN-26 (Avanish) | CHURN-32, 33 (Avanish) | CHURN-7, 8 (Shimon); CHURN-34, 35 (shared) |
| Sprint 2 | CHURN-15, 16 (Aryan); CHURN-20, 21, 24 (Shikhar); CHURN-27, 28, 29 (Avanish) | — | CHURN-9, 10 (Shimon) |
| Sprint 3 | CHURN-17 (Aryan); CHURN-22, 25 (Shikhar); CHURN-30, 31 (Avanish) | CHURN-36 (Avanish) | CHURN-11, 12 (Shimon) |

**Not in any sprint, and unestimated:**

* Bugs CHURN-37 to CHURN-44 and CHURN-47 to CHURN-52, all Done.
* Follow-ups CHURN-45 (Story) and CHURN-46 (Bug), both To Do and unassigned.

## 2. Completed Stories the team must decide on at planning

All 19 Done Stories (71 points) were completed **before any sprint was started**:

* CHURN-13 to CHURN-31, all Done;
* 13 of them are planned for Sprints 2 and 3: CHURN-15, 16, 17, 20, 21, 22, 24, 25, 27, 28, 29, 30, 31.

Jira's burndown and sprint report only count work that changes status **during** a started sprint. These Stories will therefore not appear as burned-down work in any sprint report. Options for the team to choose from:

| Option | What it means | Effect on reports |
|---|---|---|
| A. Record the early delivery as it is | Leave the Done Stories where they are and note in the first sprint's planning record that 71 points were delivered before Sprint 1 started | Honest; the sprint report will not show this work as burned down during the sprint |
| B. Re-plan the remaining work | Move only unfinished Stories into the first sprint to be started (Sprint 1 or a renamed sprint), and keep Done Stories out of the sprint commitment | Sprint reports reflect only work actually done during the sprint |

**Do not use dates that make past work appear to have happened inside a sprint.** Either way:

* do not set a sprint start date in the past;
* do not reopen and re-close Done Stories to make them show up.

## 3. Planning agenda (for the team's first real planning session)

Planned duration: about 1 hour. Attendees: all four members.

1. **Review the state above (5 min).** Confirm the Done, In Progress and To Do figures in Jira.
2. **Decide how to treat the 19 completed Stories (10 min).** Choose option A or B in §2.
3. **Confirm acceptance criteria (10 min).** 22 Stories still say "drafted — proposed, awaiting team approval". Approve or amend them.
4. **Agree the sprint scope (15 min).** Candidates:
   * E1, Shimon: CHURN-7 to CHURN-12 (21 points);
   * the recurring E6 Stories: CHURN-32 and CHURN-33 (Avanish), and the shared CHURN-34 and CHURN-35;
   * CHURN-36 (Avanish);
   * the follow-ups CHURN-45 and CHURN-46, which need an owner and an estimate first.
5. **Set the sprint goal and real dates (5 min).** Use today or a future date as the start date, and agree the length.
6. **Assign owners (5 min).** Assign CHURN-45 and CHURN-46. CHURN-34 and CHURN-35 stay shared.
7. **Risks and dependencies (5 min).**
   * CHURN-10 needs the Segments page's hard-coded `REVENUE` and `INSIGHTS` corrected.
   * CHURN-11 can reuse the CHURN-26 dashboard checks in `docs/frontend/UI_TEST_REPORT.md`.
8. **Start the sprint in Jira (5 min).** Board 3 → Backlog → Start sprint, with the agreed goal and dates.

## 4. Templates

Copy each template into a Jira comment on the Story shown. Leave fields blank until they are real.

### 4.1 Sprint planning record (comment on CHURN-33)

```
Sprint planning — <sprint name>
Date held: <YYYY-MM-DD>            Attendees: <names of people actually present>
Treatment of already-Done Stories: <option A / B and why>
Sprint goal: <goal>
Start date: <YYYY-MM-DD>           End date: <YYYY-MM-DD>
Committed Stories (key · owner · points): <...>
Total committed points: <n>
Acceptance criteria approved for: <keys>
Risks / dependencies: <...>
```

### 4.2 Daily stand-up / blocker log (comment on CHURN-34)

```
Stand-up — <YYYY-MM-DD>            Present: <names>
<name>: yesterday <...> / today <...> / blockers <none or issue key + description>
Tickets In Progress > 3 days: <keys, owner, follow-up action>
```

### 4.3 Sprint progress check (comment on CHURN-33, mid-sprint)

```
Progress — <sprint name>, day <n> of <m>, <YYYY-MM-DD>
Points Done / committed: <x> / <y>
At-risk Stories: <keys and reason>
Scope changes: <added/removed keys and why>
```

### 4.4 Sprint end: report evidence (comment on CHURN-33; attach to CHURN-36)

```
Sprint end — <sprint name>, completed in Jira on <YYYY-MM-DD>
Burndown chart screenshot: <attachment name>   (Board 3 → Reports → Burndown chart)
Sprint report screenshot: <attachment name>    (Board 3 → Reports → Sprint report)
Completed: <keys, points>    Not completed → moved to: <keys → next sprint>
```

### 4.5 Sprint review and retrospective (comment on CHURN-35)

```
Sprint review — <sprint name>, <YYYY-MM-DD>     Present: <names>
Demoed: <story key — who demoed — outcome>
Retrospective
  Went well: <...>
  To improve: <...>
  Action item (owner, due): <...>
```

### 4.6 Backlog review (comment on CHURN-32, once per sprint)

```
Backlog review — <sprint name>, <YYYY-MM-DD>
Checked: Epic links, points, sprint allocation, assignees, acceptance criteria
Changes made: <key — field — old → new — reason>
New issues triaged: <keys, owner, estimate>
```

## 5. Definition of Done for the E6 Stories

| Story | Done when |
|---|---|
| CHURN-32 | A backlog review (template 4.6) has been recorded for each sprint that runs |
| CHURN-33 | For each of Sprints 1–3: a planning record (4.1), the sprint started in Jira on its real date, and the burndown and sprint-report screenshots saved (4.4) |
| CHURN-36 | `docs/PROJECT_PROGRESS_REPORT.md` includes the real sprint screenshots and review/retrospective notes, and the team has reviewed it |

Recurring obligations must not be marked Done before the sprints have actually happened.
