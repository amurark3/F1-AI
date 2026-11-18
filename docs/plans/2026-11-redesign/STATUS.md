# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
  - Keep it small: one line of evidence per row, detail in the log. When a phase's PR merges, move its `done` rows and its log entries to [`STATUS-archive.md`](STATUS-archive.md) and rewrite "Current focus".
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Now (2026-11-18): phase D2** (FIA documents ingest, live feed backend), started at the user's request. D2.1 shipped early in PR #106 (merged 2026-11-18); D2's phase PR will hold D2.2–D2.4. P4.7 (Grand Prix hub fixes) is in its own PR. Next: D2.2's parsers the feed needs first (penalties, grids, deleted laps), then the rest of D2.2, D2.3, D2.4. Then P7.4, P7.3, P6.
- **Merged:** PR #102 (2026-11-14), PR #103 (D1 + P4, 2026-11-15) PR #105 (P5 + N1, 2026-11-17; rows and log in the archive) and PR #106 (D2.1 + the analytics consent banner, 2026-11-18). PR #102's production steps are done.
- **Two branches (user, 2026-11-09):**
  - **`feat/oracle-backend`** (pushed): all of P0c. P0c.1–P0c.8 are at `3821aa5`, ready for its PR `feat: always-on backend on Oracle Cloud`, which the user opens. Cutover follows `docs/deploy/ORACLE.md` §2 once the Oracle VM exists; the user's agent is still retrying for A1 capacity. Then P0c.9. Work on it only in a separate git worktree, never on `dev`.
  - **`dev`** (this file): the UI and data phases. **Never start a P0c task on `dev`.**
- **Waiting:**
  - P3.2 is free to start (it waited for D1).
  - P3.5 and P3.6 wait for P0c to merge: P0c.7's frontend touches `lib/server/backend.ts`, `CommandCenterView.tsx`, `champions.ts` and `mockBackend.ts`, the files P3.6 rewrites.
  - P0b.1b and P0c.9 wait for the Oracle cutover.
- **Open user steps for production after PR #103 (not recorded as done):**
  1. Run `scripts.regrade_actuals` on production: dry run, then `--apply`. The D1.8 review fixes it waited for are in (D1.8b, `90263f5`, merged with PR #103).
  2. After P0c merges, register `session_store.ensure_schema` and `fia_documents.store.ensure_schema` in `scripts/ensure_schema.py`.
- **FastF1 left after D1** (not on the request path): `mcp_server.py`, `scripts/backfill_predictions.py`, and the live-session fallback in `race_stints.py` (archive, 2026-11-14 "FastF1 left after D1.9/D1.10").
- **Agents:** each runs in a worktree under `.claude/worktrees/`, created from `dev` with `git worktree add`; the coordinator cherry-picks onto `dev` and records status here. A new session first runs `ListAgents` (another busy F1-AI session may already coordinate), then checks each branch for its `Task:` commit, verifies, cherry-picks, records and runs `git worktree remove`.
- **Branch:** `dev`. Commit each task locally; **never push `dev`** (user, 2026-11-03). **One exception (user, 2026-11-16):** after phase P5 and N1, push `dev` and open the PR; that permission covers this one push and PR only. **Second exception (user, 2026-11-18):** push `dev` and open the PR for D2.1 + the analytics consent banner; that one push and PR only. **Third (user, 2026-11-18):** push `dev` and open the PR for P4.7; that one push and PR only. Pushing `feat/oracle-backend` was the user's request of 2026-11-09.
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
| P4.7 | Grand Prix hub fixes (user, 2026-11-18): Weekend hero above the tabs per `grand-prix.html`; every race opens on Weekend; the selected rail tick is never red | done | `git log --grep "Task: P4.7"` | **Done 2026-11-18** (coordinator, inline). vitest 1385 passed at 100 %, e2e 53 passed; throwaway screenshots at 1440 and 390 px match `grand-prix.html`. See the log. |
| D2.1 | Generalized FIA document ingest | done | D2.1a `058d55b`, D2.1b `git log --grep "Task: D2.1b"` | **Done 2026-11-17** (coordinator, inline). D2.1a: backend 4615 passed at 100 %. D2.1b: the classifier pins all 85 R19 titles (35 penalty, 7 classification, 7 deleted laps, 5 grid, 3 entry list, …); a live run collected Las Vegas's first 3 documents with their text. |
| D2.2 | FIA parsers (penalties, grids, classifications, deleted laps, entry list, Pirelli) | in_progress | | Started 2026-11-18 (coordinator, worktree `.claude/worktrees/d2-2`). Split: D2.2a penalties, grids, deleted laps (the feed's); D2.2b classifications, entry list, Pirelli. |
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
- **2026-11-17 · Phase D2 started; D2.1 done (coordinator `f1-ai-69`, inline; split into D2.1a + D2.1b).**
  - **D2.1a** (`058d55b`, refactor): the fetcher, listing, PDF text, withdrawal rules and `SourceDocument` moved from `app/data/power_units/` to `app/data/fia_documents/` (`site`, `listing`, `text`, `rescission`, `document`). The PU tracker imports them and is unchanged; only `is_power_unit_title` stays in `power_units/ingest.py`.
  - **D2.1b:** `fia_documents/kinds.py` (title → penalty / grid / classification / deleted_laps / entry_list / power_unit / pirelli / timetable / other, computed at read time, never stored), `fia_documents/store.py` (one row per document in the `fia_documents` table, keyed by URL, looked up by year + event; file fallback `FIA_DOCUMENTS_DIR`, one JSON per season; failures raise `FiaStoreError`), `fia_documents/ingest.py` and `scripts/ingest_fia_documents.py` (`--all-events`, `--max-new-events`, `--cache-dir`, `--require-database`). Fixture: `tests/fixtures/fia_documents/event_page_mexico_2026.html` (R19's 85 rows, fetched 2026-11-17).
  - **Why a table, not the document store:** a season is about 1,800 documents and several MB of text; one document-store entry would be read and rewritten whole every 5 minutes on a weekend.
  - **Findings:** (1) the season page lists events alphabetically, not by date; on 2026-11-17 Las Vegas is the active event with 3 documents. (2) A recalled document stays on the page as "Recalled - Doc 13 - …" with no PDF link: the listing drops it, so a held copy is judged withdrawn (unlisted). Docs 13 and 15 are missing from R19's numbering for that reason. (3) A full season from nothing is about 5 hours at the 10 s crawl delay, so a scheduled job backfills with `--max-new-events`. (4) Kind rules: a lap deletion is titled "Infringement", a driver change and a permission to start "Decision"; a penalty needs "Car N" in the title, so the technical delegate's "MGU-K Infringement, Car 30" report and "Decision - Qualifying SC2-SC1 Times" are `other`.
  - **Not done here:** no schedule yet (D2.4 adds the 5-minute Action); the production table fills on the first scheduled run or a manual backfill. The PU tracker still runs its own hourly job and corpus, so its few PU documents are fetched twice; moving it onto this store is not in the plan.
- **2026-11-18 · P4.7: Grand Prix hub fixes (user report from production, coordinator, inline).**
  - **Weekend tab:** the hero (round / total · country, status tag, the race in display type, red rule, circuit · city, then the countdown or the winner) and the facts strip now sit above the tabs as `WeekendTop`, in place of `RaceHeader`; the other tabs keep `RaceHeader`. The left column was empty because the race name lived in `RaceHeader` and the hero below the tabs held only the circuit name. The map sits in its own bordered panel. The tab bar is lower on Weekend than on the other tabs: the user chose the mockup over a fixed tab bar.
  - **Default tab:** every round opens on Weekend and picking another round clears `tab` and `view` (user's choice). Before, a tab stuck across rounds once one was clicked and otherwise followed the calendar (Results after the race, Grid after qualifying). `defaultHubTab` deleted; `grand-prix-tabs.md` updated, its decision 1 marked superseded.
  - **Season strip:** the selected tick is taller, never red (it read as Ferrari): a won round keeps its team colour, any other is white; the "R21" label above it is white. Mockups changed to match (`system.css`, `grand-prix.html`; R19's selected tick in the gp-* pages and `debrief.html` now Red Bull blue).
  - **Also fixed:** the Weekend schedule printed "Nov 19, 202604:30 PM": `LocalTime` renders bare text, so the date and time merged into one flex item and the gap never applied.
  - **Not done:** the mockup's dotted map background (no token for it); the red "R21" in the race picker is unchanged (brand red on the round number, in the mockup too).
