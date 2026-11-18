# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
  - Keep it small: one line of evidence per row, detail in the log. When a phase's PR merges, move its `done` rows and its log entries to [`STATUS-archive.md`](STATUS-archive.md) and rewrite "Current focus".
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Now (2026-11-17): phase D2** (FIA documents ingest, live feed backend), started at the user's request. Order inside D2: D2.1 (ingest) → the parsers the feed needs (penalties, grids, deleted laps) → the rest of D2.2 → D2.3 → D2.4. Then P7.4, P7.3, P6.
- **Merged:** PR #102 (2026-11-14), PR #103 (D1 + P4, 2026-11-15) and PR #105 (P5 + N1, 2026-11-17; rows and log in the archive). PR #102's production steps are done.
- **Two branches (user, 2026-11-09):**
  - **`feat/oracle-backend`** (pushed): all of P0c. P0c.1–P0c.8 are at `3821aa5`, ready for its PR `feat: always-on backend on Oracle Cloud`, which the user opens. Cutover follows `docs/deploy/ORACLE.md` §2 once the Oracle VM exists; the user's agent is still retrying for A1 capacity. Then P0c.9. Work on it only in a separate git worktree, never on `dev`.
  - **`dev`** (this file): the UI and data phases. **Never start a P0c task on `dev`.**
- **Waiting:**
  - P3.2 is free to start (it waited for D1).
  - P3.5 and P3.6 wait for P0c to merge: P0c.7's frontend touches `lib/server/backend.ts`, `CommandCenterView.tsx`, `champions.ts` and `mockBackend.ts`, the files P3.6 rewrites.
  - P0b.1b and P0c.9 wait for the Oracle cutover.
- **Open user steps for production after PR #103 (not recorded as done):**
  1. Run `scripts.regrade_actuals` on production: dry run, then `--apply`. The D1.8 review fixes it waited for are in (D1.8b, `90263f5`, merged with PR #103).
  2. After P0c merges, register `session_store.ensure_schema` in `scripts/ensure_schema.py`.
- **FastF1 left after D1** (not on the request path): `mcp_server.py`, `scripts/backfill_predictions.py`, and the live-session fallback in `race_stints.py` (archive, 2026-11-14 "FastF1 left after D1.9/D1.10").
- **Agents:** each runs in a worktree under `.claude/worktrees/`, created from `dev` with `git worktree add`; the coordinator cherry-picks onto `dev` and records status here. A new session first runs `ListAgents` (another busy F1-AI session may already coordinate), then checks each branch for its `Task:` commit, verifies, cherry-picks, records and runs `git worktree remove`.
- **Branch:** `dev`. Commit each task locally; **never push `dev`** (user, 2026-11-03). **One exception (user, 2026-11-16):** after phase P5 and N1, push `dev` and open the PR; that permission covers this one push and PR only. Pushing `feat/oracle-backend` was the user's request of 2026-11-09.
- **PRs (user-owned):** each phase's commits go together as one new PR, which the user opens, reviews and merges. At the end of a phase, note here that it is ready for its PR (title from PLAN.md) and stop; don't push, open or manage PRs.

## Tasks

Open tasks only. `done` rows are in [`STATUS-archive.md`](STATUS-archive.md).

| ID | Task | Status | Commit / PR | Evidence / notes |
| --- | --- | --- | --- | --- |
| P0c.9 | Decommission Render, Supabase and the Render-era workflows (7 stable days after cutover; next PR) | blocked | | On `feat/oracle-backend`, after the cutover plus 7 stable days. Never on `dev`. |
| P0b.1b | Weather: diagnose the Open-Meteo failures from the VM's logs | blocked | | Waits for the P0c cutover (`feat/oracle-backend`). |
| P3.2 | `/race-control/standings` route + redirects | todo | | |
| P3.5 | Restart lights: from the real `/api/ready` stages (no timer pacing), never blocking, on every route only while the backend restarts or is unreachable; top-bar chip slot | todo | | User 2026-11-06; rewritten 2026-11-09 (P0c.7) for the 2026-11-08 Loading decision. Today: P0c.7's `ServerStatusNotice` card. |
| P3.6 | Non-blocking pages: no page-level backend awaits; every section on `useSection` / Suspense; split shared endpoints | todo | | User 2026-11-06. Depends on P0b.3. |
| D2.1 | Generalized FIA document ingest | in_progress | | Started 2026-11-17 (coordinator, inline). |
| D2.2 | FIA parsers (penalties, grids, classifications, deleted laps, entry list, Pirelli) | todo | | |
| D2.3 | FIA final classification as authority in resolvers | todo | | |
| D2.4 | Weekend live feed backend (idea #1) | todo | | |
| P6.1 | Debrief per mockup | todo | | |
| P6.2 | Radio moments (idea #3) | todo | | |
| P6.3 | Power Units per mockup | todo | | |
| P6.4 | Champions per mockup + verified records | todo | | |
| P7.1 | Engineer: inline charts + sources | todo | | |
| P7.2 | Rulebook: cites articles + stewards' decisions | todo | | |
| P7.3 | Command Center polish + forecast vs measured (idea #4) | todo | | |
| P7.4 | Weekend live feed UI (idea #1) | todo | | |
| P7.5 | Sweep + SourceBadge everywhere (idea #5) | todo | | |
| P8.1 | Race Rewind (idea #6) | todo | | |
| P9.1 | Coverage completion to 100% across `app/**` | todo | | |

## Log (append only; newest at the bottom)

Entries up to 2026-11-17 (phases P5 and N1) are in [`STATUS-archive.md`](STATUS-archive.md).
