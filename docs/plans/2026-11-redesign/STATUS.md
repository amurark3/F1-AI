# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
  - Keep it small: one line of evidence per row, detail in the log. When a phase's PR merges, move its `done` rows and its log entries to [`STATUS-archive.md`](STATUS-archive.md) and rewrite "Current focus".
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Now (2026-11-23): P3.5 and P3.6 resumed in parallel** (user: "Resume", after a pause; see the log). Before that: P3.5 and P3.6 ran in parallel (user: "start these parallely"). Neither waits for Oracle any more (see the log, 2026-11-23). Then P9.1.
- **Merged:** every redesign PR through #112 (N2, P8.1, P6.2; 2026-11-23). Their rows and log are in the archive.
- **Also open:** PR #113, backend hardening from the 2026-11-23 audit (`docs/plans/2026-11-hardening/`, its own STATUS).
- **Hosting (user, 2026-11-18): P0c is on hold.** Oracle has no A1 capacity, so Render stays production, kept warm by a cron-job.org GET on `/api/health/deep` every 5 minutes. Hugging Face Spaces is not an option (it needs PRO, 2026-11-22).
  - **`feat/oracle-backend`** (pushed, `3821aa5`): P0c.1–P0c.8, unmerged. Work on it only in a separate worktree, never on `dev`. If Oracle resumes, rebase it onto `dev` and drop P0c.7's frontend: P3.5 reimplements that half on `dev`.
  - **`dev`** (this file): UI and data phases. **Never start a P0c task on `dev`, and never cherry-pick from `feat/oracle-backend`** (user, 2026-11-23: reimplement instead).
- **Waiting:** P0b.1b and P0c.9 wait for an Oracle cutover.
- **Open user steps for production (not recorded as done):**
  1. Run `scripts.regrade_actuals` on production: dry run, then `--apply`.
  2. After P0c merges, register `session_store.ensure_schema` and `fia_documents.store.ensure_schema` in `scripts/ensure_schema.py`.
  3. S.3: add the `GOOGLE_API_KEY` repo secret, then run the rulebook ingest workflow.
- **FastF1 left after D1** (not on the request path): `mcp_server.py`, `scripts/backfill_predictions.py`, and the live-session fallback in `race_stints.py`.
- **Agents:** each runs in a worktree under `.claude/worktrees/`, created from `dev` with `git worktree add`. The coordinator merges the agent's branch into `dev` (no cherry-picks, user 2026-11-23) and records status here. A new session first runs `ListAgents` (another busy F1-AI session may already coordinate), then checks each branch for its `Task:` commit, verifies, merges, records and runs `git worktree remove`.
- **Branch:** `dev`. Commit each task locally; **never push `dev`** unless the user asks for that push (each past permission covered one push and PR only).
- **PRs (user-owned):** each phase's commits go together as one new PR, which the user opens, reviews and merges. At the end of a phase, note here that it is ready for its PR (title from PLAN.md) and stop; don't push, open or manage PRs.

## Tasks

Open tasks only. `done` rows are in [`STATUS-archive.md`](STATUS-archive.md).

| ID | Task | Status | Commit / PR | Evidence / notes |
| --- | --- | --- | --- | --- |
| P0c.9 | Decommission Render, Supabase and the Render-era workflows (7 stable days after cutover; next PR) | blocked | | On `feat/oracle-backend`, after the cutover plus 7 stable days. Never on `dev`. |
| P0b.1b | Weather: diagnose the Open-Meteo failures from the VM's logs | blocked | | Waits for the P0c cutover (`feat/oracle-backend`). |
| P3.5 | Restart lights: from the real `/api/ready` stages (no timer pacing), never blocking, on every route only while the backend restarts or is unreachable; top-bar chip slot | in_progress (2026-11-23, P3.5b) | | User 2026-11-06. **2026-11-23:** no longer waits for P0c. Split: **P3.5a** mockup `restart-lights.html` (**done 2026-11-23**, Opus agent with design-director; checked: stages match `WARMUP_STEPS`, only hex is `--dim` copied from `--rc-dim`, no horizontal scroll at 390 px); **P3.5b** build: reimplement P0c.7's non-blocking notice on `dev` from the plan text (no cherry-pick), then the P3.5 lights, against the mockup. Render-safe: P0c.7's 5 s budget, dropped 429 retry and all-season prerender stay out. |
| P3.6 | Non-blocking pages: no page-level backend awaits; every section on `useSection` / Suspense; split shared endpoints | in_progress (2026-11-23, P3.6b–d) | | User 2026-11-06. Depends on P0b.3 (done). **2026-11-23:** no longer waits for P0c (its overlap was the Oracle-only `backend.ts` / `champions.ts` tuning, which stays off `dev`). Page-sized: Opus brief `p3.6-brief.md`, then a Sonnet worktree executor. |
| P9.1 | Coverage completion to 100% across `app/**` | todo | | |

## Log (append only; newest at the bottom)

Entries up to 2026-11-23 (through PR #112) are in [`STATUS-archive.md`](STATUS-archive.md).

- **2026-11-23 · P3.5 and P3.6 unblocked without Oracle (user: "Can these be done despite not doing the oracle migration?" → "start these parallely"; "Do not do cherry pick. Reimplement them").**
  - The block was file overlap with P0c.7 (`07fbbaf` on `feat/oracle-backend`), not a dependency: `/api/ready` and its stages already exist on `dev` (`routers/readiness.py`), and P0c.7 is frontend only.
  - An in-memory trial merge of `07fbbaf` onto `dev` conflicts in `layout.tsx`, `page.tsx`, `CommandCenterView.tsx`, `ServerWarmingOverlay.tsx`, README, PLAN and STATUS, because `dev` moved on (static homepage, P7.3). It is not applied: P3.5b reimplements the notice half.
  - **Half of P0c.7 is wrong for Render and stays off `dev`:** `backend.ts` 5 s server-render budget (was 10 s), dropping the 429 retry, and prerendering all 77 champion seasons (Render answered a third of that burst with 429). Copy that says "restart" must also cover Render's cold start.
  - Without those, P3.5 and P3.6 touch disjoint files except `e2e/support/mockBackend.ts` (P3.5 adds a `readiness` option, P3.6 a delay option) and `vitest.config.mts` include lines; the coordinator merges those.
- **2026-11-23 · P3.5a done: `restart-lights.html` (Opus agent, design-director).**
  - **Placement:** the top-bar status-chip slot carries Starting and Back online at every width, phones included. The real `StatusSlot` is `hidden sm:flex`, so the restart lights are its one phone exception. Stage detail sits in the kit `Tooltip`. Only Unreachable adds a bottom card (Try again and Dismiss need 44 px targets). The card is not a dialog: no focus move, nothing inert, no scroll lock.
  - **Copy:** "Server starting" with "3/5" (phone: "Starting"); "Back online"; "Not responding" (phone: "No response"); card "Server isn't responding". The tooltip names both cases: a restart after an update, or the free tier waking from sleep (about a minute).
  - **Lights out:** at 600 ms, then the strip goes at `LAUNCH_DURATION_MS` (1200 ms). The agent proposed the 600 ms; the plan only says "then plays lights out".
- **2026-11-23 · P3.6 brief `p3.6-brief.md` (Opus planner); the coordinator accepted its defaults.**
  - Only three pages still await data at page level: Command Center (`race-control/page.tsx:33`), Grand Prix (`grand-prix/page.tsx:33`, `:47`) and Telemetry (`telemetry/page.tsx:22`, behind a full-page `PageLoader`). P5–P8 already converted the others. The driver, team and car pages read the backend only in `generateMetadata` and `generateStaticParams`.
  - **No endpoint splits and no backend change.** `/overview/{y}/shell` stays whole: the stakes need the selected race, and `RaceStatusChip` belongs to P3.5.
  - **Split:** P3.6a Command Center, P3.6b Grand Prix (one Suspense boundary around the hub), P3.6c Telemetry (`TelemetryLab` frame; `PageLoader` deleted), P3.6d `e2e/non-blocking.spec.ts`.
  - **Defaults accepted:**
    - **Metadata:** link-preview bots may still wait on data-backed titles when the cache is cold. Browsers don't, because Next 16 streams metadata.
    - **Grand Prix:** a cold uncached render swaps the empty hub for the full one only when all its server fetches finish.
  - **Ports:** e2e uses the fixed port 3100 with `reuseExistingServer: false`, so parallel worktree runs clash, failing on "port in use". Executors wait for a free port. The coordinator runs the full suite after merging.
- **2026-11-23 · P3.5b and P3.6 paused (user: "Save the agents progress and stop them for now").** Both Sonnet executors were stopped. Their work stays in the worktrees; neither branch is merged into `dev`. No dev server or e2e process was left running.
  - **P3.6:** worktree `.claude/worktrees/p3.6`, branch `p3.6`.
    - **P3.6a** (Command Center) is committed as `e9254a2`.
    - **P3.6b** (Grand Prix) is staged, not committed. The agent reported 100 % coverage on the directory just before the stop; the coordinator has not verified it. Files: `GrandPrixHub.tsx`, `HubPage.test.tsx`, `hubSeed.ts`, `page.tsx`.
    - **Next:** commit P3.6b through the hook's gates, then P3.6c (Telemetry) and P3.6d (`e2e/non-blocking.spec.ts`) per `p3.6-brief.md`.
  - **P3.5b:** worktree `.claude/worktrees/p3.5b`, branch `p3.5b`.
    - **Nothing is committed.** The work is all on disk: the gate, overlay and `StartLightGantry` deleted; new `ServerStatusNotice` and `ui/shell/WarmupLights`, with tests; `serverStatus.ts` + test; `useServerStatus` + test; `layout`, `SiteHeader`, `placeTooltip` and `globals.css` edited; `mockBackend.ts`, `standings.spec.ts`, `vitest.config.mts`; new `e2e/server-status.spec.ts`.
    - **It stopped at the visual check,** a production build on 3105. Which gates had passed by then is unknown, so re-run all of them.
    - **Scratch files, never commit:** `frontend/e2e/zz-shot.spec.ts` and `frontend/pw.shot.config.ts`.
    - **Next:** finish the visual check against `restart-lights.html`, run the full gates, then commit with `Task: P3.5b`.
  - **Not in P3.6's brief:** P3.5b touched `ui/placeTooltip.ts` + its test and `e2e/standings.spec.ts`. Check both against P3.6's files at merge (`placeTooltip` is shared kit).
  - **Merge:** merge `p3.5b` and `p3.6` into `dev` (no cherry-picks), then run the full e2e suite. Fix the `useServerStatus` mocks in P3.6's tests if the hook's return type changed.
- **2026-11-23 · P3.5b and P3.6 resumed (user: "Resume").** Both executors continue in their worktrees from the paused state recorded above.
