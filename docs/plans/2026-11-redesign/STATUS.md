# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
  - Keep it small: one line of evidence per row, detail in the log. When a phase's PR merges, move its `done` rows and its log entries to [`STATUS-archive.md`](STATUS-archive.md) and rewrite "Current focus".
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Now (2026-11-23): P3.5 and P3.6 are done and merged on `dev`, which completes phase P3.** P3 is ready for its PR, `feat: restart lights and non-blocking pages (P3.5, P3.6)`, which the user opens. **P9 is done too** (P9.1, merged `0f2b3de`), so P3 and P9 are both ready for their PR(s). No open `todo` task remains in the redesign plan; only P0c.9 and P0b.1b are left, both blocked on Oracle. Before that: P3.5 and P3.6 ran in parallel (user: "start these parallely"). Neither waits for Oracle any more (see the log, 2026-11-23). Then P9.1.
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
- **Branch:** `dev`. Commit each task locally; **never push `dev`** unless the user asks for that push (each past permission covered one push and PR only). **2026-11-23 (user): "Push and raise a PR"**: P3.5, P3.6 and P9.1; that push and PR only.
- **PRs (user-owned):** each phase's commits go together as one new PR, which the user opens, reviews and merges. At the end of a phase, note here that it is ready for its PR (title from PLAN.md) and stop; don't push, open or manage PRs.

## Tasks

Open tasks only. `done` rows are in [`STATUS-archive.md`](STATUS-archive.md).

| ID | Task | Status | Commit / PR | Evidence / notes |
| --- | --- | --- | --- | --- |
| P0c.9 | Decommission Render, Supabase and the Render-era workflows (7 stable days after cutover; next PR) | blocked | | On `feat/oracle-backend`, after the cutover plus 7 stable days. Never on `dev`. |
| P0b.1b | Weather: diagnose the Open-Meteo failures from the VM's logs | blocked | | Waits for the P0c cutover (`feat/oracle-backend`). |
| P3.5 | Restart lights: from the real `/api/ready` stages, never blocking, top-bar chip slot | done | P3.5a `8370c40`, P3.5b `5434be4` (merge `f9b6788`) | **Done 2026-11-23.** Mockup `restart-lights.html` (Opus + design-director); build by a Sonnet worktree executor, merged into `dev`. On `dev` with P3.6: lint + typecheck clean, coverage 100 % (6602/6602 statements), build clean, e2e 81 passed. |
| P3.6 | Non-blocking pages: no page-level backend awaits | done | P3.6a `e9254a2`, b `680d5d2`, c `c5a2ca9`, d `e7d9c1a` (merge `5785bbe`) | **Done 2026-11-23.** Opus brief `p3.6-brief.md`, Sonnet worktree executor. `next dev` against a 20 s stub: TTFB 10.1 s → 0.05 s on `/race-control`, `/grand-prix`, `/telemetry`. Route table unchanged (ISR symbols and revalidate values). `e2e/non-blocking.spec.ts` 15 passed. Same final gates as P3.5. |
| P9.1 | Coverage completion to 100% across `app/**` | done | `3339d32` (merge `0f2b3de`) | **Done 2026-11-23** (Sonnet worktree executor, no brief). The gate is now `app/**/*.{ts,tsx}`, excluding only tests and `.d.ts`, at 100 % per file. On `dev`: lint + typecheck clean, vitest 243 files / 2104 tests passed, 100 % (6852 statements, 5626 branches), build clean, e2e 81 passed. CI enforces it through `npm run test:coverage` in `pr-auto-review.yml`. |

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
- **2026-11-23 · P3.5b merged into `dev` (`f9b6788`, branch commit `5434be4`; Sonnet worktree executor).**
  - **Executor's gates, run in the worktree:** lint, tsc and Prettier clean; vitest 2041 passed at 100 %; build clean, `/` still static; Playwright 66 passed.
  - **Coordinator's checks:** one commit, clean tree, no suppressions; `backend.ts`, `champions.ts` and the page files untouched; only `vitest.config.mts` is shared with P3.6.
  - **Outside the file list, accepted:**
    - `ui/placeTooltip.ts` clamps a 320 px tooltip inside the viewport, after the 390 px visual check showed it at about −40 px.
    - `e2e/standings.spec.ts` asserts the empty status region instead of no `dialog`.
  - **Decisions:**
    - **One sr-only `role="status"` region, in `ServerStatusNotice`.** The mockup put it on the bar slot; one region avoids two with the same name, so `WarmupLights` is visual only.
    - **Dismiss hides the notice for the current run only.** A later failed fetch starts a new run.
    - **The unreachable state has no e2e test.** Its 120 s timing is unit-tested with fake timers.
  - **Not checked by eye:** "starting" on `/` at 390 px, and "back online" / lights out, which only e2e and unit tests cover.
  - **P3.5 stays `in_progress`** until the full suite passes on `dev` with P3.6 merged.
- **2026-11-23 · P3.6 merged into `dev` (`5785bbe`); P3.5 and P3.6 done.**
  - **Executor (Sonnet worktree):** four commits, all on the brief's file list. `PageLoader` deleted (no other user). It ran only its own and the affected specs: 15 + 14 passed.
  - **Timings (`next dev` against a stub that answers after 20 s):** TTFB 10.1 s → 0.05 s on `/race-control`, `/race-control/grand-prix` and `/race-control/telemetry`. A link-preview bot on a driver page still waits about 10 s for the metadata, as accepted.
    - The driver page itself was not changed. Its browser "before" of 8.2 s TTFB is unexplained; treat the driver-page row as unverified.
  - **The brief's survey was off in one place:** the grep still shows `grand-prix/page.tsx:37` and `:51`. Both run inside the un-awaited `loadSeed`, not in the page body.
  - **Final gates on `dev`, both tasks merged (coordinator):** `npm run lint` and `typecheck` clean; `test:coverage` 100/100/100/100 (6602 statements, 5517 branches); `npm run build` clean; `npx playwright test` 81 passed. The vitest test count was cut from the log.
  - Worktrees `p3.5b` and `p3.6` and their branches are removed.
- **2026-11-23 · P9.1 sized and started (user: "after that continue with P9").**
  - **How it was measured:** on `dev` at `fca2db2`, with `--coverage.include='app/**/*.{ts,tsx}'` (tests and `.d.ts` excluded) and thresholds off. 327 files measured; 17 are below 100 %. `useChat` and `useVoice` no longer exist, so the plan's hook list is out of date.
  - **The 17 files (statements covered / total):**
    - `lib/server/`: `backend.ts` 11/52, `champions.ts` 5/14, `profiles.ts` 0/8, `raceControl.ts` 4/16.
    - `hooks/useLiveTiming.ts` 0/35 (needs a mock WebSocket).
    - `utils/errors.ts` 0/10; `lib/errorTracking.ts` 0/3.
    - `race-control/components/Charts.tsx` 8/12; `components/LocalTime.tsx` 21/24.
    - Branch gaps only: `lib/entityLinks.ts`, `lib/formatTime.ts`, `constants/api.ts`.
    - One-statement pages: `calendar`, `consumer`, `predictions`, `race-control/intel`, `race-control/predictions`.
- **2026-11-23 · P9.1 merged into `dev` (`0f2b3de`, branch commit `3339d32`); P9.1 done.**
  - **Gate:** `COVERAGE_INCLUDE = ["app/**/*.{ts,tsx}"]`, excluding only `*.test.*` and `*.d.ts` (there are none under `app/` today). Per-file 100 % is unchanged. Config files sit outside `app/` and stay outside the gate.
  - **New tests:** `lib/server/{backend,champions,profiles,raceControl}`, `useLiveTiming` (mock WebSocket), `errorTracking`, `LocalTime`, `entityLinks`, `formatTime`, `constants/api`, and `app/redirects.test.ts` (the five redirect pages; none has a `next.config.ts` redirect, so all are kept). `Charts.test.tsx` now covers the attribution tooltip.
  - **Deleted:** `utils/errors.ts`, which had no importer (coordinator re-checked).
  - **`backend.ts` edit, structural only:** the retry loop's trailing `return null` was unreachable, so the loop condition moved into the body. It still returns at `attempt === MAX_ATTEMPTS`, and the budget check runs every pass (coordinator read it). Render's settings (10 s, 429 retry, 12 prerendered seasons) are now pinned by tests.
  - **Found, not fixed:**
    - `useLiveTiming` never reconnects after a socket error; a dropped socket stays down until the year or round changes.
    - In `raceControl.ts`, a stray doc comment stacks above `getPredictionSnapshot`'s JSDoc.
- **2026-11-23 · Bug fixes for PR #114 (user: "Fix the bugs as well"; coordinator, inline).**
  - **`useLiveTiming` reconnects.** A dropped socket now reopens after 1 s, doubling up to 30 s; the delay resets after a successful open. Unmount, or a year or round change, stops retries, and a late close from an old socket is ignored. Before, the tower sat on "Connecting to live timing…" until the round changed. The tests were written first and failed first. Frontend 2107 tests at 100 %, e2e 81 passed.
  - **Stacked doc comment** above `getPredictionSnapshot` merged into its JSDoc.
  - **Metadata wait for link-preview bots: not changed, by decision.** Those pages are prerendered and cached, so bots get cached HTML. The wait happens only on an uncached page while the backend is slow. A short metadata timeout would then show a generic title in exactly those previews.

