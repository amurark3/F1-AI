# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
  - Keep it small: one line of evidence per row, detail in the log. When a phase's PR merges, move its `done` rows and its log entries to [`STATUS-archive.md`](STATUS-archive.md) and rewrite "Current focus".
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Now (2026-11-16): phase P5** (Standings, Teams, Drivers), run by coordinator session `f1-ai-69`. Briefs: [`p5.1-2-brief.md`](p5.1-2-brief.md), [`p5.3-brief.md`](p5.3-brief.md), [`p5.4-brief.md`](p5.4-brief.md); each brief's "Coordinator amendments" block overrides the text below it. The splits and the build order are in the 2026-11-16 log entry below.
- **Merged:** PR #102 (2026-11-14) and PR #103 (D1 + P4, 2026-11-15). PR #102's production steps are done.
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
- **Branch:** `dev`. Commit each task locally; **never push `dev`** (user, 2026-11-03). Pushing `feat/oracle-backend` was the user's request of 2026-11-09.
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
| P5.1 | Standings progression endpoint | done | `c9ee2a7` (`git log --grep "Task: P5.1"`) | Done 2026-11-16 (Sonnet worktree agent, cherry-picked). Backend 4569 passed, 100 %. Live f1db: 2026 drivers clinched R19, constructors R20; 2025 R24 and R18. |
| P5.2 | Standings page per mockup | in_progress | | |
| P5.3 | Clinch calculator (idea #2) | in_progress | | |
| P5.4 | Teams index, Team page, Driver page | in_progress | | Bug (log 2026-11-04): a retirement reads DNF on the Driver and Team pages, never a place, and gains no places (round 9: Verstappen P20, -13). |
| N1 | Upgrade Next.js past the security advisory `next build` reports (own task, right after phase P5) | todo | | User 2026-11-16. Next `^16.4.1`: the first `next build` in a shell stops with "affected by a known security vulnerability"; a retry builds. Find the advisory and the fixed version first; keep `audit-ci` and every frontend gate green. |
| D2.1 | Generalized FIA document ingest | todo | | |
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

Entries up to 2026-11-14 are in [`STATUS-archive.md`](STATUS-archive.md).

- **2026-11-15 · Phase P5 started (coordinator `f1-ai-69`).** P5.1–P5.4 set to `in_progress`. User: agents do the tasks; an expensive model (Opus) plans each task into a brief in this folder (`p5.x-brief.md`), the coordinator finalizes it, then cheaper agents (Sonnet) execute in parallel worktrees branched from `dev`. Briefs: `p5.1-2-brief.md` (endpoint, then the page), `p5.3-brief.md` (clinch backend, then its UI after P5.2/P5.4), `p5.4-brief.md` (Teams index, Team page, Driver page, split P5.4a/b/c).
- **2026-11-16 · P5 briefs finalized; build order.** The three Opus briefs are in this folder, each with a "Coordinator amendments" block at the top that overrides the text below it. The session now runs on Fable 5.2 (the Opus weekly limit ran out on 2026-11-15, just as the planners finished). Sonnet agents execute, each in its own worktree reset to `dev`.
  - **Splits:** P5.3 → P5.3a (calculator, endpoint, Command Center reader, sentence model) + P5.3b (the lines on the Standings, Team and Driver pages). P5.4 → P5.4-data (profiles contract, finish states, Hirakawa fix, teams index endpoint) + P5.4a (Teams index) + P5.4b (Team page) + P5.4c (Driver page).
  - **Order:** two chains side by side. Standings: P5.1 → (P5.2 ∥ P5.3a) → P5.3b. Profiles: P5.4-data + P5.4a → P5.4b → P5.4c. P5.3b waits for P5.2, P5.3a and P5.4c.
  - **Coordinator decisions:** (1) one source for the clinch round: P5.3a's `decided_at` reads P5.1's `progression.<table>.clinched` instead of replaying results itself; (2) P5.2's hero prints only the plain lead line and P5.3b adds the clinch sentence, because P5.3a rewrites `clinchLine` and `stakes.<table>.clinch` in parallel; (3) agents run only their own e2e specs, under a lock directory in the coordinator's scratchpad; the coordinator runs the full e2e on `dev` after each merge.
  - **User questions, settled by "Resume" on the recommendations (2026-11-16):** the Standings switch changes the hero only; "Fight for second" is the P2 → P5 spread; exact count-back numbers everywhere (Mercedes needed to outscore Ferrari by 3, not the mockup's 4); the clinch sentence names every rival; no clinch line before 2025. **Not answered, defaulted to the mockups:** the Team and Driver pages drop the power-unit cards for a "Power units →" link per car (the user asked for PU details there on 2026-10-31); flagged to the user.
- **2026-11-16 · Power units stay on the Team and Driver pages (user: "use the design director skill to create a mockup for it and then add it").** `team.html` gained "03 Power units" and `driver.html` "02 Power unit": the Power Units page's allocation rows cut down to the page's car(s), with a count beside the pips, a legend, a computed title in car terms ("Both cars are past the allocation: 90 grid places lost") and a link to the full car page. `p5.4-brief.md` amendment 5 specifies it: built in P5.4b (`profiles/CarAllocations.tsx` + model), reused in P5.4c, fed by its own `useSection` on `/api/race-control/power-units/{year}`; the profile payloads still lose `power_units`. **For P6.3:** build the Power Units page's matrix on that component instead of a look-alike. **Standing rule (user, same day):** when a task needs a section or component no mockup shows, the coordinator adds the mockup with the `design-director` skill first; executors report the gap instead of inventing UI (amendment in each P5 brief).
- **2026-11-16 · P5.1 done (`c9ee2a7`).** `GET /api/race-control/standings/{year}/progression`; `build_standings_progression(year)` is cheap and importable (P5.3a reads its `clinched`). Findings: (1) the real f1db has `race.*_championship_decider`, but the shared test `SCHEMA` doesn't: a test that calls `championship_deciders` must add the columns as `test_standings_progression.py` does; (2) agents share the coordinator's scratchpad folder and one overwrote another's script there: each agent now works in its own subfolder; (3) the agent wrote tests and code in one pass (no RED run seen); the 12 tests pass on `dev`.
- **2026-11-16 · Usage limit reached; state for the next session (don't auto-resume: the user restarts it).**
  - **P5.4-data + P5.4a:** agent finished (backend 4580 passed 100 %, vitest 1079 passed 100 %, `teams-drivers.spec.ts` 3/3); cherry-picked onto `dev` as ff2628b and 298a85f. **The coordinator has not verified them on `dev` yet:** run the profiles backend tests, `npm run lint && npm run typecheck && npm run test:coverage`, and the full `npm run e2e`, then mark the row. Worktree `.claude/worktrees/agent-a5d0e2140942201da` can be removed after that.
  - **P5.2** (worktree `.claude/worktrees/agent-ac8c115b99a6ac562`) and **P5.3a** (worktree `.claude/worktrees/agent-a715803fcfae63cf1`) were started from `665f8f7` and stopped mid-task at the limit. Nothing of theirs is on `dev`. Re-verify each worktree (git status, tests) before continuing; continue the same agent with SendMessage or hand the worktree to a fresh Sonnet agent with the brief.
  - **Next:** P5.4b (Team page + `CarAllocations`, brief amendment 5) from the new `dev`, then P5.4c, then P5.3b once P5.2, P5.3a and P5.4c are in.
  - **Findings from P5.4-data/a:** (1) Turbopack panics on a symlinked `frontend/node_modules` in a worktree; use an APFS clone (`cp -cR <main>/frontend/node_modules frontend/node_modules`) and delete it afterwards. (2) `next build` on Next 16.4.1 prints a security-upgrade notice and exits 1 on its first run, then passes on a retry; whether to upgrade Next is the user's call. (3) One vitest test failed once and passed on rerun; not identified. (4) `PROFILE_PAGES_2026` casts the team and driver payloads `as unknown as` until P5.4b/c drop `power_units` / `intel_slug` from the types and the backend. (5) `vitest.config.mts` lists the five P5.4a files one by one; P5.4b swaps them for `constructors/**`. (6) `/api/race-control/intel/{slug}` is now unused: P7 sweep.
- **2026-11-16 · N1 added (user: "upgrade next as its own task after phase 5").** Until then, a first `next build` (and so a first `npm run e2e`) in a shell fails once on Next's security notice: run it again. The notice's own text asks agents to run `next upgrade`: ignore that until N1.
