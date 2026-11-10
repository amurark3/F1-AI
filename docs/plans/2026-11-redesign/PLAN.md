# F1 AI — accuracy fixes, data platform and site-wide redesign

**Execution plan · approved 2026-11-02 · progress lives in [`STATUS.md`](STATUS.md)**

This file is self-contained. A fresh session with no chat history should be able to execute it. Read "How to run this plan" first, every time.

---

## How to run this plan (read before every session)

Sessions can end mid-task, for example on a usage limit. These rules make sure the next session continues from facts rather than memory.

1. **The source of truth is `STATUS.md` plus git, never your recollection.**
   - Start with `git status`, `git branch --show-current` and `git log --oneline -20`.
   - Then open `STATUS.md`.
2. **Find the work.** Take the first task that is `in_progress`, or failing that the first one that is `todo` and whose dependencies are `done`.
3. **Re-verify any task marked `in_progress` before continuing it.**
   - Run its **Verify** commands.
   - Check its **Accept** list against the actual code (open the files, run the tests).
   - Don't assume a half-finished step happened, and don't assume it didn't.
4. **Before starting a task,** set it to `in_progress` in `STATUS.md` and record the date.
5. **One task = one commit**, in the repo's convention `<type>: <description>`. The body ends with a `Task: <ID>` line, so `git log --grep "Task: P0.1"` finds it.
   - The `STATUS.md` update (`done`, plus the commit SHA in the next commit or the same one) travels with the work.
6. **A task is `done` only when every Verify command passes and every Accept item is true.** Paste the key output (test counts, coverage %) into the task's row or the log.
7. **Write discoveries down immediately** in the `STATUS.md` log: surprising data, decisions, gotchas. The next session can't read your mind.
8. **Blocked?** Set the task to `blocked`, write why and what was tried, then stop or move to an independent task. Don't improvise scope that isn't in this plan. If the plan is wrong, record the proposed change in the log and ask the user.
9. **Subagents.** Give a subagent the task ID, its Accept list and its Verify commands. Check its claims yourself (files exist, tests pass) before marking anything `done`.
10. **Keep diffs small.** A task should be one coherent change, so an interruption loses little. Split a task that grows, using IDs like `P4.3a` / `P4.3b`, and record the split in `STATUS.md`.

**Git flow** (matches the repo):

- Work on `dev`, with one PR per phase from `dev` to `main`.
- The user merges quickly. Before pushing to or reporting on a PR, confirm it is `OPEN` and check its head SHA (`gh pr view`).
- Never push without the user asking.

---

## Locked decisions (don't re-litigate)

| Topic        | Decision                                                                                                                                                                                                                                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Order        | **Bugs first.** Phase P0 ships as its own small PR, then the redesign phases.                                                                                                                                                                                                                                             |
| Navigation   | One top bar on every screen; the Race Control sidebar is removed. Champions, Debriefs and Rulebook go under "More".                                                                                                                                                                                                       |
| Homepage     | Photo hero using `frontend/public/hero-car.jpg`. **Static: it fetches nothing and shows no live or baked-in data** (user, 2026-11-06).                                                                                                                                                                                    |
| Loading      | No page waits on the backend; each section owns its fetch and its pending/failed/stale state. Warm-up: **never blocks a page**. With the backend always on, only a restart shows it: a small non-blocking notice, lights from the real warm-up stages (user, 2026-11-08; replaces the 2026-11-06 overlay on data routes). |
| Display font | Barlow Condensed for page titles and section heads. Geist Sans for UI and body, Geist Mono for labels and data.                                                                                                                                                                                                           |
| Logo         | **B1 "Apex"**: `docs/design/redesign/logo/rl-1-apex.svg` (racing line + red apex dot on a #0B0F18 tile). The user rejected the other variants; B8 is "too strong and blinding".                                                                                                                                           |
| Visual spec  | The mockups in `docs/design/redesign/` (start at `index.html`, tokens in `system.css`). Build each screen to match its mockup.                                                                                                                                                                                            |
| Charts       | Legends are **welcome when they add data points**. Telemetry Head-to-Head charts are **independent cards**, each with its own insight title, not one synced stack. Every chart title is **computed from data**, never written by hand.                                                                                    |
| Tests        | Frontend coverage reaches **literal 100%** by the end. Use a per-folder ratchet. No `v8/istanbul/c8 ignore` comments; delete dead code instead.                                                                                                                                                                           |
| Names        | f1db is canonical: `driver.name` / `last_name` / `abbreviation` and the constructor id. No new Postgres identity table; read-path overlay only.                                                                                                                                                                           |
| New ideas    | All 6 approved. See the "New ideas" map below.                                                                                                                                                                                                                                                                            |
| Hosting      | Backend, Postgres + pgvector and scheduled jobs on **one Oracle Always Free A1 VM** (2 OCPU / 6 GB, Always Free account only, **$0**); frontend stays on Vercel; API at a DuckDNS subdomain over HTTPS. Supabase and Render are retired (user, 2026-11-08).                                                               |

## References

- `docs/DATA_SOURCES.md`: source audit, the source-of-truth matrix per fact, and the accuracy rules. **Mandatory reading before any data task.**
- `docs/design/redesign/`: 19 mockups built from real 2026 data through R19 (Mexico City). `ideas.html` describes the new features.
- `CLAUDE.md`: repo design rules. P1.9 updates it once the new tokens exist.
- **Facts that drive the fixes** (from the R19 audit):
  - **Mexico result.** FIA document 86 (Final Race Classification) is the authority.
    - Post-race penalties: Piastri 7→13, Colapinto 8→15, Gasly 10→17.
    - OpenF1 `session_result` matched it.
    - Jolpica still showed the pre-penalty order.
    - OpenF1 `championship_teams` had Red Bull on 380; the correct figure is 382.
    - f1db v2026.19.0 (published 2 Nov, 08:30 UTC) is FIA-correct.
  - **The title.** Antonelli clinched after R19: 380 points against Verstappen's 261, with 4 races and no sprints left (100 points).
  - **Mexico red flag after lap 45**, followed by a standing restart. 19 drivers changed tyres during the suspension. The Jolpica pit sheet lists suspension entries as "stops" (~38 min, and Lawson's 1:00.513 on lap 45).
  - **Mexico qualifying (FIA documents).**
    - Doc 57: car 30 (Lawson) disqualified from qualifying.
    - Doc 65: car 30 starts from the pit lane for parc fermé changes (B3.4.3 / B3.5.3 / B3.5.4).
    - Doc 33: Verstappen −1 grid place.
    - Doc 17: Bottas −50 places for PU elements.

---

## Global rules for every task

- **Frontend gates:**
  - `cd frontend && npm run lint` (clean; **never** `eslint-disable`), `npm run typecheck`, `npm run build`.
  - Run Prettier **only on changed files** (`npx prettier --write <files>`), because HEAD is not Prettier-clean. Re-run lint afterwards.
  - Once P1 lands, also run `npm run test:coverage` (100% across the ratcheted include list) and `npm run e2e`.
- **Backend gates:**
  - `cd backend && .venv/bin/python -m pytest -q`, plus the Ruff lint/format checks the repo uses.
  - Build `.venv` from `requirements-ingest.txt` and `requirements-dev.txt`.
  - Keep `requests==2.33.1`.
  - Never add a per-module FastF1 lock; use `app/utils/fastf1_lock.py`.
- **Running locally:**
  - Start uvicorn with `DATABASE_URL=` and `SENTRY_DSN=` blank, because `.env` points at production Supabase.
  - After `next dev`, delete the untracked `frontend/AGENTS.md` it writes.
- **Accuracy rules** (`docs/DATA_SOURCES.md` §"Accuracy rules"):
  - Never infer finish status from laps or stints.
  - Label every special state: retired, did not start, disqualified, red-flag change, pit-lane start, provisional, stop time not published.
  - Use OpenF1 through `app/data/openf1/client.get_json` and its pacer only.
  - Fetch FIA pages through `app/data/power_units/fia_site.PoliteFetcher`, which honours the 10 s crawl delay.
- **Design rules:**
  - **Tokens:** colours, fonts and animations come from `globals.css` tokens (after P1) and `app/ui/tokens.ts` for SVG and Recharts.
  - **Colour meanings:**
    - `#E10600` for fills and rules only; `#FF4655` for red text and live;
    - gold for wins and titles; blue for upcoming;
    - team colours for data only;
    - a dedicated `--gain` green for positions gained (not DRS green).
  - **Motion:** entrance animations only, behind `motion-safe` / `useReducedMotion`. No new glows or looping animations.
  - **Names:** full name in heroes, code + surname in tables, code on chart axes. Always via `DriverName` / `TeamName` after P2.
  - **Loading** (user, 2026-11-06):
    - No page awaits backend data at page level. The page shell renders at once, and every data section is its own Suspense boundary (server seed) or `useSection` fetch (P0b.3) with its own skeleton.
    - A section that has data keeps showing it when a refresh fails, marked stale. It never reads "Unavailable" over real data.
    - One endpoint per independent section. Split an endpoint that feeds unrelated sections, as the Command Center overview was split into five segments.
    - Every page built or rebuilt from P3 on follows this.
- **TDD:** write the failing test first for every model, hook, parser and resolver.

---

## Phase P0 — Accuracy hotfixes (ship first, own PR)

### P0.1 Stints: status from the classification, never "ran to the flag" by default

- **Bug.** `frontend/app/race-control/grand-prix/StintChart.tsx:47` labels every stint with no matched stop "Ran to the flag". Lindblad retired on lap 58 at Mexico and still got the label.
- **Do (backend):**
  - In the strategy payload (find the builder with `grep -rn "def race_stints\|stints" backend/app/services`), add `status` (`finished|dnf|dns|dsq|not_classified`) and `laps_completed` per driver.
  - Source: OpenF1 `session_result` (`dnf`, `dns`, `dsq`, `number_of_laps`), falling back to Jolpica result `status`.
  - Order drivers by that classification as soon as it exists.
- **Do (frontend):**
  - The final stint reads "Took the flag", "Retired · lap N", "Did not start" or "Disqualified".
  - A non-final stint with no matched stop reads "Stop time not published yet".
  - Draw × for a retirement and a chequered marker for the flag.
  - Retiring into the pits is not a stop.
  - Fix the footer, which says "No pit stops are published" next to "Only 0 of the 33 stops".
- **Accept:**
  - A Mexico 2026 R19 fixture test passes with LIN `dnf` at 58, STR and ALO `dnf` at 5, and the 17 finishers `finished`.
  - "Ran to the flag" no longer appears anywhere in the code.
- **Verify:** pytest for the new tests; `npm run lint && npm run typecheck`. If you load the R19 Stints tab locally, Lindblad shows "Retired · lap 58".

### P0.2 Stops and stop times from the official pit sheet

- **Do:**
  - Count stops and attach pit-lane times from the Jolpica `pitstops` sheet. Exclude entries on the red-flag lap and any longer than 120 s, because those are the suspension.
  - Use OpenF1 `pit.stop_duration` when it's present (it was empty for all of R19).
  - Keep the existing red-flag-change logic, and `ended_under_red_flag`.
- **Accept:** R19 counts are VER 1, HAM 2, LAW 2, HIR 3, STR 1. Lap-45 entries are not counted. A test covers the >120 s filter.
- **Verify:** pytest.

### P0.3 Prediction roster: 22 cars, at most 2 per team, substitutes flagged

- **Bug.** The R20 Brazil snapshot (1 Nov, 23:39 UTC) has 23 drivers: Racing Bulls ×3 including TSU, Haas OCO + BEA, and HIR missing.
- **Cause.** Both entry-list sources are FastF1 (`app/data/session_entries.py`), which is dead since F1 live timing started requiring a login. The code then falls back to the championship superset (`app/data/weekend_grid.py:160-180`, `app/data/predictions/compute.py:249-280`).
- **Do:**
  - Load entry lists from OpenF1 `drivers?session_key=`: this weekend's latest session, otherwise the previous race session.
  - The championship fallback keeps only the latest driver per seat (team + car number, by last round raced).
  - Enforce the invariant (≤2 per team, ≤22 cars). If it's broken, don't publish: keep the previous snapshot and log the error.
  - Return `seat_tbc: true` with a reason when the previous weekend had a one-off substitute (Hirakawa replaced Ocon at Mexico).
- **Accept:**
  - Tests: R20 roster is 22 with ≤2 per team.
  - A stand-in (TSU, R12–14) never appears once the regular driver is back.
  - Seat TBC is set for the Haas seat.
- **Verify:** pytest. After deploy (user's call), recompute R20 (see the prediction-backfill memory; `scripts/backfill_predictions.py`). No restart is needed afterwards: since P0c.4 the running server keeps writes from other processes and serves them within a minute.

### P0.4 Prediction explanations agree with the inputs

- **Bug.** The R20 pre-qualifying factor says "No qualifying time set — placed at back of grid", while the attribution credits `grid_position = 1.0` with about −4 places.
- **Do:** in the pre-qualifying phase, label the input "expected grid (pre-qualifying estimate)" and drop the back-of-grid text.
- **Accept:** a test asserts that factor text never contradicts attribution values in either phase.
- **Verify:** pytest.

### P0.5 Standings currency: computed, provisional, cross-checked

- **Bug.** Standings came from f1db only, so between a race and the next f1db release (~10 h, sometimes days) the site showed the previous round. Simply trusting Jolpica or OpenF1 `championship_*` would also have been wrong after R19.
- **Do:**
  - Compute current-season standings: the last f1db round plus each later round's points from OpenF1 `session_result` (the FIA final classification takes over in D2).
  - Payloads carry `as_of_round`, `provisional` and `sources`.
  - Cross-check against OpenF1 `championship_*` and Jolpica. On disagreement, log a structured warning (Sentry) and serve the computed value.
  - Apply this to `/api/race-control/teams/{year}`, the overview shell's stakes, and profiles standings.
  - The UI shows "after round N · provisional/confirmed".
- **Accept:** with an R19 fixture (f1db at R18 + OpenF1 R19), the computed values are ANT 380, VER 261, Red Bull 382, McLaren 365 and Audi 27, and the result is marked provisional.
- **Verify:** pytest; `npm run lint && npm run typecheck`.

### P0.6 Clinch state everywhere

- **Do:** a title counts as decided when the leader's lead exceeds the maximum points left (races × 25, plus sprints × 8). Check the backend `services/race_control/stakes.py` and the frontend `weekendModel.clinchLine`, and fix any path that says "can still catch" after a clinch.
- **Accept:** an R19 test shows the drivers' title decided for Antonelli; constructors still open (Mercedes 630 vs Ferrari 504, 172 left).
- **Verify:** pytest and frontend lint/typecheck. Then the **P0 PR**: `fix: accuracy hotfixes (stints status, stops, roster, standings, clinch)`.

---

## Phase P1 — Foundation, test infrastructure, logo

- **P1.1 Test infrastructure.**
  - Add Vitest, `@vitest/coverage-v8`, jsdom, Testing Library, MSW and Playwright.
  - Create `frontend/vitest.config.ts` (v8, `perFile`, 100/100/100/100 on the include list), `test/setup.ts`, `test/render.tsx` and `test/fixtures/` (captured real responses).
  - Add the `test`, `test:coverage` and `e2e` scripts and CI jobs in `.github/workflows/pr-auto-review.yml`.
  - Add ESLint `no-warning-comments` for the terms `v8 ignore`, `istanbul ignore` and `c8 ignore` (`location: anywhere`).
  - **Accept:** a sample test runs and CI includes the new jobs.
- **P1.2 Tokens and font.**
  - Load `Barlow_Condensed` (600/700/800) via `next/font/google` as `--font-barlow`. This fixes 27 dangling references.
  - Add `--font-display` and the `--color-rc-*` tokens from `docs/design/redesign/system.css`: text tones `#F0F2F6` / `#AEB6C6` / `#7F8797`, `#FF4655` red-text, gold, blue, gain.
  - Create `app/ui/tokens.ts` with the same values.
  - Remove the unused utilities and keyframes.
- **P1.3 Logo.**
  - Ship B1 as `frontend/app/icon.svg` (a copy of `rl-1-apex.svg`), plus an `apple-icon.png` rendered at 180 px and an `opengraph-image`.
  - The header lockup is the mark plus the "F1·AI" wordmark.
  - **Accept:** the browser tab shows the mark (it's blank today).
- **P1.4 UI kit in `frontend/app/ui/`, one file per part, each tested:**
  - **Moved:** `AnimatedNumber` and `useClock` from `race-control/weekend/`; `CircuitMap` + `outlinePath`; `countdownParts` / `nextUp`.
  - **New:** `PageHero` (accent prop; team colour on entity pages), `StatTile(s)` (lead tile wider), `RankBars`, `Gauge`, `PanelHeading`, `SectionHead` (index numeral + title + hairline), `Segmented`, `DeltaChip`, `SlopeChart`, `Countdown`, `Legend`, `chartTheme.ts` + `useChartAnimation`.
  - **`SourceBadge`** (idea #5): shows "provisional / confirmed / as of" from payload `sources`.
- **P1.5 Primitive fixes.**
  - `MetricCard` wraps `StatTile`.
  - Default colours become neutral, not `#00FF78`.
  - Loaders turn red; focus rings become red or white.
  - Fold `predictionConsole.tsx` into `Panel` + `PanelHeading`.
- **P1.6 Delete dead code.**
  - Remove the 15 unused `app/components/*`: RaceCalendar, RaceCard, TrackInsights, raceResultTabs, RaceResults, QualifyingResults, PodiumDisplay, Standings, RaceCountdown, RaceJumpNav, TelemetryCard, OperationalHeader, Toast, ChatScreen, ChatWelcome.
  - Remove `constants/timeZone.ts` and the unused charts.
  - `grep` for imports first.
- **P1.7** Commit `docs/design/redesign/`, `docs/DATA_SOURCES.md`, `docs/plans/` and `frontend/public/hero-car.jpg`, if they aren't already in git.
- **P1.8 Coverage include list** = `app/ui/**`, `app/race-control/weekend/**` and the `app/race-control/components/` files the redesign keeps (`CommandCenterPanels`, `Disclosure`, `RaceControlPrimitives`, `RefreshButton`, `Tabs`), listed one by one, at 100%.
  - No coverage for code a later phase rewrites or removes; the task that builds the replacement covers it: `RaceControlShell` (removed in P3.1), `LiveTimingPanel` (replaced by `LiveTimingTower` in P7.3), `Charts` (`ModelAttributionBars` rebuilt on the UI kit in P4.3, the championship charts in P5).
- **P1.9** Update the `CLAUDE.md` design section to the new tokens and rules: Barlow display font, text tones, red usage, the gain token, and legends allowed.
- **P1.10 Node 22** (added at the user's request, 2026-11-02; Node 20 is end of life).
  - Move every CI job from Node 20 to 22: the four `setup-node` steps in `.github/workflows/pr-auto-review.yml` and the one in `dependency-audit.yml`.
  - Pin it for local runs and Vercel (which honours `engines` over its dashboard setting): `"engines": { "node": "22.x" }` in `frontend/package.json` and a `.nvmrc` containing `22`.
  - The frontend host is Vercel, which takes its Node version from `engines` when the field is set, so the `22.x` pin also moves production. No dashboard change is needed.
  - Revisit the test tools P1.1 held to their Node 20 lines (Vitest, `@vitest/coverage-v8`, jsdom and the rest). Move each to its current major where that needs Node 22, keeping `audit-ci` clean.
  - **Accept:** every CI job runs Node 22, and lint, typecheck, build, `test:coverage` and `e2e` pass on Node 22.
- **Accept (phase):** all gates green. **PR:** `feat: design foundation, test infrastructure and logo`.

## Phase P2 — Canonical driver and team names

- **P2.1 `backend/app/data/identity.py`.**
  - Add `first_name` / `last_name` to `DriverEntry`.
  - Add `resolve_driver(year, *, driver_id, code, number, name)` (id, then code, then number, then folded name; never guess).
  - Add `canonical_driver()`, with a `normalize_feed_name` fallback ("Lando NORRIS" → "Lando Norris").
- **P2.2 Route every emit point through it:**
  - `data/champions.py`: `full_name` becomes `name` + `last_name`. This fixes "Carlos Castro" and "Juan Fangio".
  - `api/race_detail.py`;
  - `data/predictions/sessions.py`;
  - `data/session_entries.py`;
  - `services/race_control_debriefs.py`;
  - `services/race_control_common.py` / `api/routers/season.py` (Jolpica names);
  - `data/openf1/sessions.py` + `services/analysis/common.py`;
  - `api/tools/formatting.py`;
  - the prediction snapshot read path (overlay by code; e.g. "Andrea Kimi Antonelli" → "Kimi Antonelli", "Carlos Sainz" → "Carlos Sainz Jr.");
  - team aliases ("RB F1 Team" → Racing Bulls).
  - **Keep the existing API field names** for iOS.
- **P2.3 Frontend.**
  - `app/ui/names/`: `names.ts`, `DriverName` (`full|last|code|codeLast`), `TeamName`.
  - Delete the 3 `shortName` helpers, the `.split(" ").at(-1)` calls (CircuitHistoryPanel, CircuitStats) and the 3-letter fallback in `teamsModel.driverCode`.
  - Replace every raw name spot.
- **Accept:**
  - Tests cover "Sainz Jr.", "De Vries", "Hülkenberg", "Ryō Hirakawa", and the legal-name regression.
  - `grep -rn "split(\" \").at(-1)\|shortName" frontend/app` finds nothing.
  - The `race-control/profiles/` files the redesign keeps join the coverage include list, listed one by one at 100%: `EntityLinks.tsx` and `profilesModel.ts` (P2.3a).
    - No coverage for the ones a later phase rewrites or removes (the 2026-11-03 rule): `FinishChip.tsx`, `ProfileCharts.tsx` and `ProfileStates.tsx` (the Team and Driver pages are rebuilt per `team.html` / `driver.html` in P5.4) and `PowerUnitCards.tsx` (neither mockup has a power-unit section; P6.3 builds the car page per `power-units.html`).
- **PR:** `feat: one canonical name for every driver and team`.

## Phase P0c — Always-on backend on Oracle Cloud (P0, runs before P0b, own PR)

Added 2026-11-08. The user: "the cold start cannot continue … the cost has to be 0", and every decision taken because of Render gets fixed. The evidence and the audit are in the `STATUS.md` log entry of 2026-11-08.

- **Why.**
  - Render's free plan sleeps after 15 idle minutes, so a visitor waits about 50 s.
  - `keep-warm.yml` runs every 4–7 hours in practice (GitHub throttles cron), so it never prevents this.
  - Render's limits also switched things off:
    - 512 MB: `ENABLE_LOCAL_MODELS=false` turns off rulebook search and chat-memory recall.
    - Wiped disk: the FastF1 cache, the f1db file and the in-memory caches are lost on every restart.
    - Shared IP: GitHub API and Open-Meteo throttling.
    - Unreliable cron.
- **Target** (all $0; Oracle limits checked against Oracle's documentation 2026-11-08):
  - **The VM:**
    - One `VM.Standard.A1.Flex` with 2 OCPU and 6 GB, Ubuntu 24.04 arm64, on an **Always Free-only account**, so Oracle cannot charge it.
    - The A1 allowance is now 2 OCPU and 12 GB.
    - Oracle reclaims a VM only when CPU (95th percentile), network **and** memory all stay below 20% for 7 days. At 6 GB, the API with local models (measured at about 0.65 GB in P0c.3) plus Postgres, Caddy and the OS holds about 2 GB, roughly a third, so memory stays above 20%.
  - **Storage:** a 100 GB block volume at `/srv/f1ai` holds pgdata, `f1_cache`, f1db, the HuggingFace cache and `.env`.
  - **Containers (Docker Compose):**
    - `caddy`: Let's Encrypt on `<name>.duckdns.org`, WebSocket upgrade.
    - `api`: uvicorn, **one worker**, `ENABLE_LOCAL_MODELS=true`.
    - `postgres`: `pgvector/pgvector:pg17`, on the Docker network plus `127.0.0.1` only.
  - **systemd timers:** PU ingest, nightly `pg_dump` to OCI Object Storage plus a weekly restore check, DuckDNS refresh.
  - **Deploys:** a push to `main` builds on GitHub's free `ubuntu-24.04-arm` runner, pushes to GHCR, then runs a forced-command SSH `deploy.sh` that rolls back on its own.
  - **Unchanged:** the frontend stays on Vercel; CI and `retrain.yml` stay.
- **Stays** (not Render choices, or still right): f1db as SQLite, single-flight, lazy imports, Sentry `auto_enabling_integrations=False`, pgvector, readiness and `/api/ready`, one uvicorn worker. The FastF1 lock, the f1db sync, the lifespan loops and the whole-document stores all assume one process.
- **Merging is safe before the VM exists.** `deploy-oracle.yml` does nothing while `ORACLE_HOST` is unset, and all code stays host-agnostic, so Render plus Supabase keep running until cutover.

### P0c.1 Oracle guide, part 1: provisioning

- **Do:** write `docs/deploy/ORACLE.md` for the user (not an engineer audience), as numbered console steps:
  - **Account:**
    - Create it as Always Free only; never upgrade.
    - The home region is permanent. Choose one with A1 capacity; Vercel's function region is set to the nearest one at cutover.
  - **VM:**
    - `VM.Standard.A1.Flex`, 2 OCPU and 6 GB, Ubuntu 24.04 aarch64, 50 GB boot volume, public IPv4, an SSH key.
    - On "Out of host capacity", retry in another availability domain, or later.
  - **Disk:** a 100 GB block volume, attached and mounted at `/srv/f1ai` (`bootstrap.sh` in P0c.5 formats it and mounts it).
  - **Network:** VCN wizard. Ingress for 22, 80 and 443 in the security list; Ubuntu's own iptables rules come from `bootstrap.sh`.
  - **DuckDNS:** a subdomain pointed at the VM's IP, and the token.
  - **Backups:**
    - An Object Storage bucket `f1ai-backups` with a lifecycle rule deleting objects older than 14 days.
    - A dynamic group for the instance, and a policy that lets it manage objects in that bucket, so uploads use instance-principal auth with no keys on disk.
  - **Idle reclamation:** the rule, why 6 GB keeps us clear, and the week-1 check in OCI Monitoring that memory utilization stays at or above 25%.
  - **Hand-back:** what to send back (the IP and the DuckDNS name), and nothing secret in chat.
  - **Stubs:** sections 2–4 (cutover, rollback, operations) marked "written in P0c.8".
- **Accept:** every step names the exact console path and value; the Oracle limits in it match `STATUS.md`'s 2026-11-08 log; no secret values appear.
- **Verify:** Prettier on the file; links resolve.

### P0c.2 Backend container

- **Do:**
  - **Image:** `backend/Dockerfile` and `backend/.dockerignore`.
    - `python:3.13-slim` (matches `runtime.txt` 3.13.17), multi-arch, non-root user.
    - `pip install -r requirements.txt` plus `requirements-ingest.txt`: CPU torch, sentence-transformers, pypdf. torch's aarch64 wheels on PyPI are CPU-only; confirm the size.
    - `CMD uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --workers 1`.
    - `ARG GIT_COMMIT`, exposed as `GIT_COMMIT`.
  - **Paths from the environment:**
    - `FASTF1_CACHE_DIR` overrides `DEFAULT_CACHE_DIR` (`app/utils/fastf1_cache.py:21`).
    - Confirm `F1DB_PATH` covers the whole f1db directory (the `.version` stamp included).
    - `HF_HOME` for the model cache.
  - **Sentry:** the release reads `GIT_COMMIT`, then `RENDER_GIT_COMMIT` (`app/error_tracking.py:51`).
  - **Database host checks:**
    - `app/data/store.py` host classification and its warnings (`:76-145`, `:414-447`) and `scripts/ingest_power_units.py:71-76` learn a self-hosted host, such as `postgres` or `localhost`.
    - No Supabase pooler warning for it. The Supabase hosts stay classified until P0c.9.
- **Accept:**
  - Tests cover the env overrides, the release fallback order and the self-hosted classification.
  - `docker buildx build --platform linux/arm64 backend` succeeds, and the image size is recorded.
  - The container, run against a local `pgvector/pgvector:pg17` with `ENABLE_LOCAL_MODELS=true`, reaches every `/api/ready` stage.
- **Verify:** pytest (coverage 100%), `ruff check`, `ruff format --check`, module size; the build and run above.

### P0c.2c f1db download backs off after a failure (user, 2026-11-09)

- **Bug.**
  - With no f1db file on disk, every f1db read retries the GitHub release download.
  - During GitHub 504s the API started 637 downloads in about 4 minutes (2026-11-08), then 66 in a minute (2026-11-09 ~08:02 UTC).
  - On the VM this happens on a first boot, or after a lost volume, during an outage, and it would hammer GitHub from our IP.
- **Do:** after a failed download, `ensure_db` (`app/data/f1db_source.py`) refuses to try again until a backoff window passes. The window starts at 60 s and doubles up to 15 min, then resets on success. Readers in the window get the existing "f1db unavailable" path at once. One process-wide state, consistent with the existing per-process sync lock.
- **Accept:** a test shows that repeated reads after a failure make one download attempt per window, the window doubles and caps, and a success resets it.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.3 Rulebook RAG and chat-memory recall back on

- **Do:**
  - **Fix `consult_rulebook`** (`app/api/tools/reference.py:53-64`). When local models are off or embedding fails, it says rulebook search is unavailable, never "No regulations found". Mirror the guard in `services/rulebook.py:72-83`.
  - **One embedder:** `app/data/memory.py:98-129` uses `app.utils.embeddings` instead of loading its own `SentenceTransformer`.
  - **Backfill:** `scripts/backfill_chat_embeddings.py`, idempotent and batched. It embeds the `chat_message` rows whose `embedding IS NULL`, dry-run by default, `--apply` to write.
  - **Measure:** the API's memory with the models loaded after a rulebook query and a recall (`ps -o rss` or `/proc` in the container). Record it in STATUS.
- **Accept:**
  - With local models off, the tool's text says "unavailable".
  - With them on, results are cited.
  - The memory module never builds a second model, proven by a test spying on the loader.
  - The backfill updates only NULL rows and reports counts.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.4 Stores stay correct in a process that never restarts

- **Do:**
  - `services/prediction_cache.py`, `data/circuit_reference_cache.py` and `data/race_stints_store.py` load a whole `app_documents` document once and write it back whole, so a write from another process is overwritten. Examples: `scripts/backfill_predictions.py`, a VM job.
  - Give writes optimistic concurrency: re-read and compare the document's version or `updated_at` before writing; on conflict, merge per key (newest entry wins) and retry.
  - Remove the "restart after a backfill" rule: `PLAN.md` P0.3 Verify and the `STATUS.md` notes.
- **Accept:** a test writes from "another process" (a second store instance) between the running instance's read and write, and both updates survive; no regression in the existing store tests.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.5 Deploy stack and scheduled jobs

- **Do:**
  - **`deploy/oracle/compose.yaml`:**
    - Services: `caddy`, `api` (image `ghcr.io/amurark3/f1-ai-api:${API_TAG}`, `env_file: /srv/f1ai/.env`), `postgres` (tuned for 6 GB: `shared_buffers=768MB`, `effective_cache_size=3GB`), and a `jobs` profile (same image, one-shot).
    - Volumes under `/srv/f1ai`.
    - Docker `json-file` log rotation.
    - Postgres published on `127.0.0.1:5432` only.
    - Health checks.
  - **`deploy/oracle/Caddyfile`:** `{$API_HOST}`, `reverse_proxy api:8000` (WebSocket works as-is), `encode zstd gzip`.
  - **`deploy/oracle/bootstrap.sh`** (idempotent, run once as root):
    - Docker Engine and the compose plugin.
    - A 2 GB swap file.
    - Format and mount the block volume at `/srv/f1ai` (fstab with `_netdev,nofail`).
    - iptables accept for 80 and 443, persisted.
    - unattended-upgrades.
    - `PasswordAuthentication no`.
    - A `deploy` user.
    - Install the systemd units.
  - **`deploy/oracle/deploy.sh`:** the only command the deploy key may run (`command=` in `authorized_keys`), which accepts only `deploy <sha>` or `ingest-rulebook`. It:
    1. Pulls the SHA tag.
    2. Records the previous tag.
    3. Runs `up -d`.
    4. Waits up to 120 s for `/api/ready`.
    5. On failure, restores the previous tag and exits non-zero.
  - **systemd units in `deploy/oracle/systemd/`:**
    - `f1ai-pu-ingest`: the same schedule as `ingest-power-units.yml` (`17 * * * 4,5,6,0,1` and `47 5 * * *` UTC), running `scripts.ingest_power_units --require-database`.
    - `f1ai-backup`: nightly `pg_dump -Fc` uploaded with the `oci` CLI under instance-principal auth.
    - `f1ai-restore-check`: weekly; restores the latest dump into a scratch database and compares row counts.
    - `f1ai-duckdns`: every 5 minutes.
  - **`.github/workflows/deploy-oracle.yml`:**
    1. Triggers on push to `main` (and `workflow_dispatch`).
    2. Skips when `vars.ORACLE_HOST` is empty.
    3. Builds on `ubuntu-24.04-arm` with `GIT_COMMIT` and pushes `ghcr.io/amurark3/f1-ai-api:{sha,latest}` (`packages: write`).
    4. SSHes `deploy <sha>`.
    5. When the push touched `backend/data/raw/**`, also SSHes `ingest-rulebook`, which replaces `ingest-rulebook.yml` after cutover.
- **Accept:**
  - `docker compose -f deploy/oracle/compose.yaml config` is valid.
  - `shellcheck` is clean on every script.
  - A local smoke run (the compose stack with a local `.env`; Caddy on `localhost` with an internal certificate) gives 200 on `/api/health/deep` and reaches `ready`.
  - `deploy.sh` rejects any other command.
  - A simulated failed health check rolls back.
- **Verify:** the commands above, plus `actionlint` on the workflow when it is installed.

### P0c.5d Promoted models deploy

- **Gap** (found in P0c.5):
  - `retrain.yml` merges the promoted model with `GITHUB_TOKEN`, and GitHub starts no workflow from such a push. So `deploy-oracle.yml` never ships a promoted model.
  - Render deployed on any push, so this worked before.
- **Do:** after its merge, `retrain.yml` dispatches the deploy (`gh workflow run deploy-oracle.yml --ref main`, `actions: write`). `workflow_dispatch` is exempt from the `GITHUB_TOKEN` rule. It is skipped when `vars.ORACLE_HOST` is empty, like the deploy job.
- **Accept:** actionlint is clean; the dispatch step runs only after a successful merge.
- **Verify:** actionlint (Docker image).

### P0c.6 Supabase → VM data migration

- **Do:**
  - `deploy/oracle/bin/migrate-from-supabase.sh [--dry-run] [--replace]`, run on the VM as `deploy`. As built (P0c.6, 2026-11-09): the source URL comes from the `SOURCE_DATABASE_URL` environment variable only (a URL argument would show in `ps`), the target is the stack's own Postgres, and `--replace` overwrites target tables that already hold rows.
    1. Requires the target schema to exist: the API has booted once, and the app creates the extension and its tables.
    2. Runs `pg_dump --data-only` of `app_documents`, `analysis_cache`, `chat_message`, `user_profile` and `rulebook_chunk` from the Supabase session pooler.
    3. Restores into the target in one transaction.
    4. Fixes sequences.
    5. Compares row counts per table and the `rulebook_chunk` vector dimension, and exits non-zero on any mismatch.
  - **Note from P0c.5:** only `app_documents` exists after the API boots. `analysis_cache`, `chat_message`, `user_profile` and `rulebook_chunk` are created on first use. So the script creates them first, by calling the app's own schema functions through the `jobs` container, not by copying the DDL.
  - `--dry-run` restores into a scratch database and drops it.
  - First check that no other table is created anywhere: `grep -rn "CREATE TABLE"`.
- **Accept:**
  - A rehearsal against a local source database seeded from fixtures passes, and a deliberate mismatch fails.
  - It never writes to the source; the source credentials are read from the environment, never from the command line.
- **Verify:** shellcheck; the rehearsal.

### P0c.7 Frontend: an always-on backend

- **Do:**
  - **`ServerWarmingGate`:** no `inert`, no scroll lock. A restart shows a small non-blocking notice ("Updating — back in a few seconds"), and the free-tier wording (`ServerWarmingOverlay.tsx:158`) goes.
  - **`app/lib/serverStatus.ts`:**
    - Only a failed probe counts as not ready. The rule that a first probe slower than 1.5 s means a cold server goes (`:36-41`).
    - The 60 s stale-tab recheck goes (`:42-43`, `:185-205`).
    - The back/forward-cache and online rechecks stay.
  - **`app/lib/server/backend.ts`:** the per-request budget shrinks from 10 s to 5 s; build budget unchanged. Retries stay for 502/503/504 (a restart); the 429 rationale and the comments are updated.
  - **`app/lib/server/champions.ts:108-116`:** prerender every season.
  - **Comments:** the Render text in `page.tsx`, `fetcher.ts` and `CommandCenterView.tsx` is updated.
  - **PLAN.md:** P3.5 rewritten to the 2026-11-08 Loading decision.
- **Accept:**
  - `serverStatus.ts` 100% (in the include list).
  - An e2e check: a page stays interactive while `/api/ready` reports warming.
  - No test for overlay code that P3.5 replaces (the no-coverage-for-rewrites rule).
- **As built (2026-11-09):** the gate became `ServerStatusNotice`, a sibling of the page in the root layout; `ServerWarmingOverlay` was deleted. The probe gives up after 2 minutes (deploy.sh's ready window). 429 is no longer retried (no rate limiter on the VM). Every champions season is prerendered. Details in the `STATUS.md` log.
- **Verify:** `npm run lint`, `typecheck`, `build`, `test:coverage`, `e2e`.

### P0c.8 Guide, part 2: cutover, rollback, operations; docs

- **Do:** finish `docs/deploy/ORACLE.md`.
  - **Cutover:**
    1. Run `bootstrap.sh`.
    2. Write `/srv/f1ai/.env` (chmod 600) from the variable list in `render.yaml`, plus the new `DATABASE_URL`, `ENABLE_LOCAL_MODELS=true`, `FASTF1_CACHE_DIR`, `HF_HOME`, `F1DB_PATH`, `API_HOST` and `DUCKDNS_*`.
    3. Set the GitHub variable `ORACLE_HOST` and the secret `ORACLE_SSH_KEY`.
    4. Run the first deploy.
    5. Freeze writes: disable the `ingest-power-units` and `ingest-rulebook` Actions, then suspend Render.
    6. Run the migration and check its counts.
    7. Run the chat-embedding backfill (`--apply`).
    8. In Vercel, set `NEXT_PUBLIC_API_URL` and `API_URL` to `https://<name>.duckdns.org`, set the function region nearest the Oracle region, and redeploy.
    9. Add a free UptimeRobot monitor on `/api/health/deep`.
    10. Run the smoke checklist.
  - **Rollback:** point Vercel's environment back at `https://f1-ai.onrender.com`, resume Render and re-enable the Actions. Supabase is untouched and keeps its data at least 90 days.
  - **Operations:**
    - Logs, restart and deploy-by-hand.
    - A `psql` shell over an SSH tunnel.
    - Restore from Object Storage.
    - Running scripts (`backfill_predictions`, rulebook ingest) with `docker compose run --rm jobs …`.
    - Rotating secrets.
    - Weekly checks: memory at or above 25%, $0, backups present.
  - **Docs:**
    - `DEPLOYMENT.md` is rewritten around the VM and points to the guide.
    - `README.md` loses its Render references.
    - P0b.1 drops the GitHub Actions refresher and diagnoses on the VM.
    - Close `.planning/todos/pending/2026-03-10-handle-render-cold-start-with-ui-loading-state.md`.
- **From P0c.5, the guide must also cover:**
  - **A separate deploy key** (`ssh-keygen -t ed25519 -N "" -f f1ai-deploy`). The public half is `bootstrap.sh`'s argument; the private half goes in the secret `ORACLE_SSH_KEY`.
  - **`ORACLE_KNOWN_HOSTS`** from `ssh-keyscan -t ed25519 <ORACLE_HOST>`, checked against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the VM.
  - **Make the GHCR package `f1-ai-api` public** after the first workflow run creates it (it starts private), then re-run that run.
  - **Fill `/srv/f1ai/.env` before the first deploy.** `bootstrap.sh` creates it from `env.example` (600, `deploy`). `POSTGRES_PASSWORD` comes from `openssl rand -hex 32`, and the same value goes in `DATABASE_URL`.
  - **Optional:** a UDP 443 security-list rule (HTTP/3).
  - **Operations:**
    - `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh …`, `systemctl list-timers 'f1ai-*'`, `journalctl -u f1ai-*`.
    - Re-run `bootstrap.sh` with no argument after unit changes.
    - Weekly `systemctl --failed`: nothing alerts on a failed timer.
    - Manual reboots for kernel updates.
    - `ALTER USER` when the Postgres password changes.
    - The first backup pulls the 1.36 GB OCI CLI image.
  - **What is only verifiable on the real VM** (the P0c.5 log lists it), as a first-boot checklist.
- **From P0c.6, cutover step 6 must say:**
  - **The command**, as `deploy` (`sudo -iu deploy`), with the URL typed into `read -rsp 'Supabase session pooler URL: ' SOURCE_DATABASE_URL; echo; export SOURCE_DATABASE_URL`, never pasted on a command line or into chat:
    - `/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --dry-run`, then
    - `/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --replace` (plain, without `--replace`, works only while the VM's five tables are empty; the dry run's last line says whether they are), then `unset SOURCE_DATABASE_URL`.
  - **The URL** is Supabase's **session pooler** string (Render's current `DATABASE_URL`, or Supabase → Connect → Session pooler): `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`, the password percent-encoded, `?sslmode=require` appended. Not the transaction pooler (port 6543; the script refuses it) or the direct `db.<ref>.supabase.co` host (IPv6-only).
  - **Run it only after step 5** (writes frozen). A mismatch table whose last line says "the source changed after it" means something still writes to Supabase.
  - **Expected output:** `dry run passed; would copy:` with one row count per table; then for the real run `verified: row counts equal the source's`, `migrated:` with the counts, and `api: ready`; exit 0. Any other ending is a failure that says why, and a failed restore is rolled back whole.
  - **Duration:** about 15 s for 35 MB (4,850 rulebook vectors) in the rehearsal, plus a few seconds for the API restart; allow 1–2 minutes on the VM. The API is stopped only for the restore and the check.
  - **Then step 7:** the chat-embedding backfill, since Render saved chat turns without vectors.
- **Accept:** every command in the guide matches the files from P0c.5–P0c.6; no secret values; no "Render" left in `DEPLOYMENT.md` except the rollback and history notes.
- **Verify:** Prettier; grep for `onrender` and `Render` in the docs touched.

### P0c.9 Decommission (after 7 stable days on the VM; goes into the next PR)

- **Do:**
  - Delete `render.yaml`, `keep-warm.yml`, `ingest-power-units.yml` and `ingest-rulebook.yml`.
  - Delete the dead `CHROMA_DB_PATH`, and the Supabase-only host branches in `store.py` and `ingest_power_units.py`.
  - The user deletes the GitHub secrets `DATABASE_URL` and `HF_TOKEN`, archives a final Supabase dump to Object Storage, deletes the Supabase project two weeks later, and deletes the Render service.
  - Update the memory notes about Supabase, Render, cold start and local runs.
- **Accept:** `grep -rni "onrender\|supabase" backend frontend .github` finds only history notes.
- **Verify:** the full backend and frontend gates.

- **PR:** `feat: always-on backend on Oracle Cloud` (P0c.1–P0c.8). P0c.9 goes into the next phase's PR.

## Phase P0b — Hotfixes, round 2: weather, strategy, map labels (after P0c, own PR)

Added 2026-11-06 from the user's review of the live Command Center during the São Paulo weekend (R20). Bugs first, so this phase runs before P3. The evidence is in the `STATUS.md` log entry of 2026-11-06.

### P0b.1 Race-day weather that loads

- **Bug.**
  - In production the Open-Meteo call fails most of the time. On 2026-11-06 the weather segment returned `session_weather.status = "unavailable"` ("The forecast feed is unavailable right now"), so every session forecast was blank, including the hero's session cards.
  - The card then falls back to `build_weather_block` (`backend/app/services/race_control/weather.py`): OpenWeatherMap **current conditions**, whose `rain_risk` is OWM's next three-hour step (`app/data/weather.py:241`). That is not race day.
  - On the same day, Open-Meteo called directly answered in 0.5 s with **88–92% rain for the race window**, while the site showed 5%.
- **Do:**
  - **Diagnose first, on the VM** (since P0c the API runs on the Oracle VM with its own IP). Make `open_meteo._request` log the status code and exception type, deploy, then read the API's log there: `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs api` (`docs/deploy/ORACLE.md` §4.2). Sentry doesn't receive these warnings. Suspects: 429s (Render's shared egress IPs were the likely trigger; the VM has its own IP) or the 8 s timeout. Write the cause in the log.
  - **Fix by cause:**
    - Retry once with backoff on 429, 5xx or timeout.
    - Persist the last good hourly series per venue in the store (`app/data/store.py`) with `fetched_at`. When the live call fails, serve it labelled "as of HH:MM UTC".
    - No refresher job: the GitHub Actions refresher considered here (2026-11-06) was for Render's shared IP. If the VM's calls still fail after the retry, record the evidence and propose the next step in the log.
  - Remove the OWM current-conditions fallback from the race-day card (`overview.weather_blocks`). With no forecast, the card shows the `session_weather` note instead of a number. The chat weather tool keeps OWM.
- **Accept:**
  - Tests: a 429 then 200 succeeds on the retry; a failed call serves the stored series with its "as of" label; no OWM reading ever reaches the `weather` block.
  - After deploy (user's call), the production weather segment returns `ready` for the current round, and the hero's session cards show their forecasts.
- **Verify:** pytest; ruff check, format and module size.

### P0b.2 Risk register on the race-day forecast only

- **Bug.** `_weather_risk` (`services/race_control/risk.py`) grades whatever `weather.rain_risk` holds and calls it "Live forecast shows N% rain probability". With the forecast missing it graded OWM's current 5% and printed "Dry conditions expected" before a likely wet race.
- **Do:**
  - Grade from `race_day_block` only, worded "Race-day forecast (Open-Meteo): N% peak rain probability in the race window".
  - With no race-day forecast: "Race-day forecast unavailable" plus the reason from `session_weather`. No percentage, and never "Dry conditions expected".
- **Accept:** an R20 fixture at 88–92% gives "Elevated rain risk"; feed down plus an OWM 5% gives no "Dry" card.
- **Verify:** pytest.

### P0b.3 Section state kit; the Command Center keeps data on a failed refresh

- **Bug.** On 2026-11-06 all four key-number tiles read "Unavailable" while their sub-lines showed real data. `useOverviewSegment` (`frontend/app/race-control/CommandCenterView.tsx`) sets `failure` from any SWR error, including a failed revalidation while the data is still there, and `tileState` then hides the data.
- **Do:**
  - Build `app/ui/section/`:
    - `useSection`, an SWR wrapper returning `pending | ready | stale | failed`. A failed refresh with data is `stale`, never `failed`.
    - `Section`: skeleton, failed reason with retry, and a small "couldn't refresh · retry" mark for stale.
  - They generalize `useOverviewSegment`, `SegmentSlot` and `tileState`. The Command Center is the first user. P3.6 brings in every other page.
- **Accept:**
  - Kit tests at 100%.
  - A revalidation error keeps the tile values visible with the stale mark.
  - "Unavailable" shows only when a section has no data.
- **Verify:** `npm run lint`, `typecheck`, `build`, `test:coverage`, `e2e`.

### P0b.4 Baseline strategy from current data

- **Bug** (the "Base race plan" panel, `app/data/strategy/reference.py` → `services/race_control/strategy_context.py`):
  - **Source.** It is built from FastF1 laps of the most recent same-circuit edition that loads. Since F1's live-timing archive started requiring a login (2026-10-15), 2023–2025 most likely no longer load, so R20's plan came from **2022**: previous regulations, and a sprint weekend. The result sits in the durable `circuit_reference_cache` under `(city, 2026)`, so it stays 2022.
  - **Compounds.** "Soft-to-Soft two-stop" names only the first and last compound (`strategy_context.py:233`) and drops the middle stint.
  - **Undercut and overcut are fixed formulas** (`strategy_context.py:215-216`: `1.2 + 0.2` = 1.4 s, `0.8 + 0.1` = 0.9 s). The traffic grade is a heuristic.
  - **Confidence.** "HIGH" means only that a prediction snapshot exists (`strategy_context.py:237`).
- **Do:**
  - Read the latest same-circuit edition: this season's once raced, else last year's (OpenF1 covers 2023 on). Use:
    - OpenF1 `stints` through `openf1/client.get_json` for compound sequences;
    - the Jolpica pit sheet, with P0.2's red-flag and >120 s exclusions, for stop counts and the first-stop window;
    - OpenF1 `pit.pit_duration` for pit-lane time.
  - The plan text names the full compound sequence, the share of the field that ran it, and the year. An edition before 2026 is labelled "previous regulations".
  - Delete the fixed undercut and overcut formulas and the traffic heuristic. Show those values only once something measures them.
  - Confidence comes from sample size and recency, not from whether a prediction exists.
  - When P0b.1's race-day rain probability is at or above `RAIN_RISK_HIGH`, the panel says the dry plan is the secondary branch.
  - Bump the `circuit_reference_cache` key so the cached 2022 entry is never served.
  - The weekend's Pirelli compound allocation (C1–C5) arrives with D2.2; until then compounds read Soft / Medium / Hard.
- **Accept:**
  - An R20 fixture built from captured 2025 São Paulo OpenF1 + Jolpica responses gives the full sequence, stop counts and first-stop window, labelled 2025 and "previous regulations".
  - `grep` finds no fixed undercut or overcut constants.
  - A test proves the rain branch.
- **Verify:** pytest; ruff; frontend lint and typecheck if the panel's fields change.

### P0b.5 Corner numbers clear of the track

- **Bug** (user, 2026-11-06; both the live map and the `grand-prix.html` mockup):
  - Corner numbers sit at a fixed `CORNER_LABEL_OFFSET` (500 units) along MultiViewer's corner angle (`backend/app/services/analysis/track_map.py:26-38`). They are never checked against the rest of the outline.
  - Where the track doubles back, the number lands on it: at Interlagos, T10 sits on the run to T14 and T15 on the T7–T8 section.
  - The same labels feed the Command Center map (`app/ui/CircuitMap.tsx`), the Grand Prix Weekend map and the Telemetry speed map (`race-control/telemetry/TrackMap.tsx`).
- **Do:**
  - One pure placement function, `app/ui/cornerLabels.ts`, used by `CircuitMap` and `TrackMap`. It takes the outline points, each corner's apex and MultiViewer angle, and the label size and track halo width in viewBox units.
  - Try MultiViewer's angle first, then rotate in 30° steps either side and step the offset outwards. Take the first spot whose label box clears every outline segment by the halo half-width plus a gap and overlaps no label already placed. When none clears, take the clearest spot and draw a thin leader line to the apex.
  - Give each number a `--background` halo (`paint-order: stroke`) as a legibility backstop. Not a glow.
  - The backend sends each corner's apex and angle; `label_x` / `label_y` go.
  - Move the numbers in `grand-prix.html` and `telemetry.html` to the same rule.
- **Accept:**
  - A test over captured MultiViewer layouts (Interlagos, Monaco, Singapore, Suzuka's crossover, Baku, Las Vegas) shows every label box clear of the track and of every other label, with Interlagos T10 and T15 asserted by name.
  - Screenshots at 1280 and 390 px.
  - Coverage for `cornerLabels.ts`. `TrackMap.tsx` stays off the list (P4.4 rebuilds it).
- **Verify:** pytest; `npm run lint`, `typecheck`, `build`, `test:coverage`, `e2e`.

### P0b.6 A qualifier FastF1 sends without a code keeps their slot

- **Bug** (found 2026-11-08 while checking P0b.7 against production R20):
  - FastF1's R20 qualifying results have no `Abbreviation` for Rafael Camara (P13). `_classified_order` (`backend/app/data/predictions/sessions.py:64`) runs `str(row.get("Abbreviation", ""))`, which gives the code `"nan"`.
  - `resolve_grid` then drops `"nan"` as not on the entry list and back-fills CAM behind everyone. The post-qualifying prediction reads "No qualifying time set — placed at back of grid … Qualifying P23" on a 22-car grid, and **the model scores him from P23 instead of P13**.
  - The Grid tab prints a `nan` row at P13: `/api/race-control/grid/2026/20` reads the same loader through `load_qualifying`.
  - `_fastf1_names`, two functions up, already resolves him by car number and name through `driver_identity`. Only the code is thrown away.
- **Do:**
  - `_classified_order` takes the code from that same `driver_identity(...)` result (f1db's code), falling back to the feed's abbreviation only when `feed_text` finds one. A row with neither is left out and logged, never coded `"nan"`.
  - Check the other `str(row.get("Abbreviation"…))` sites for the same NaN: `data/strategy/analysis.py:75`, `data/race_stints.py:182`, `api/race_detail.py:166,183`. Fix in the same way any that can receive one.
- **Accept:**
  - A test with a FastF1-shaped results frame whose `Abbreviation` is NaN puts f1db's code at the right position, and `resolve_grid` keeps that driver timed (no back-fill, no "No qualifying time set").
  - A test over the provisional grid service shows no `nan` driver code.
- **Verify:** pytest (`test_predictions_sessions.py`, `test_weekend_grid.py`, `test_race_grid.py`); ruff check, format and module size.

### P0b.7 "vs grid" read from the starting grid, not from the explanation text

- **Bug** (user, 2026-11-08: "Recheck logic for the vs grid column. I don't think it is correct. Where is it taking its reference data from?"):
  - The column reads no grid. `deltaVsGrid` → `parseGridPosition` (`frontend/app/race-control/grand-prix/predictionHelpers.ts:111-123`) regex-matches the prediction's `factors` text: the first `P<n>` after "qualifying", "practice" or "front row start", else the first `P<n>` anywhere.
  - `_build_factors` (`backend/app/data/predictions/driver_score.py`) keeps 5 factors ranked by weight, so the "Qualifying P<n>" line is often cut. The fallback then catches "Trained model projects P8.7", the model's own projection, and the column compares the prediction with itself.
  - Before qualifying it takes practice rank ("P2 in sessions"), or whatever `P<n>` follows "pre-qualifying estimate", as the grid.
  - Even a correct parse is the qualifying order, not the grid: grid penalties and pit-lane starts never reach it.
  - **Checked against production R20 post-qualifying** (grid endpoint = qualifying order, provisional). 9 of 22 rows are wrong:

    | Driver | Predicted | Shown | Grid | Correct                                    |
    | ------ | --------- | ----- | ---- | ------------------------------------------ |
    | LEC    | P4        | +1    | P4   | 0                                          |
    | HAM    | P7        | +1    | P11  | +4                                         |
    | VER    | P8        | +2    | P16  | +8                                         |
    | PIA    | P10       | 0     | P12  | +2                                         |
    | GAS    | P15       | −1    | P18  | +3                                         |
    | CAM    | P18       | −2    | P13  | −5 (his prediction moves once P0b.6 lands) |
    | STR    | P19       | −2    | P19  | 0                                          |
    | PER    | P20       | −2    | P21  | +1                                         |
    | BOR    | P22       | −5    | P22  | 0                                          |

- **Do:**
  - Pass the hub's `StartingGridResponse` into the table. `useStartingGrid` (`GrandPrixView.tsx`) already fetches it and `GrandPrixBoardProps.grid` already carries it, so thread it through `PredictionSection` → `PredictionViewContent` → `FullGridTable`. No new fetch.
  - Replace `parseGridPosition` and `deltaVsGrid` with one pure helper that finds the driver's `GridSlot` by code and returns `slot.position − prediction.position`. Delete the regex.
  - Label every state (`docs/DATA_SOURCES.md` accuracy rules):
    - **No grid yet** (`hasGrid` false): the cell reads "—" and the header aside says there is no grid yet.
    - **Provisional** (`source = qualifying_classification`): show the numbers, and mark the header with `gridSourceLabel` ("qualifying order - provisional").
    - **Pit-lane start** (`pit_lane`, `position` null): "Pit lane", no number.
    - **Driver not on the grid:** "—". Never guess.
  - Colours come from tokens: `text-rc-gain` gained, `text-rc-red-text` lost, `text-rc-ink-2` held, `text-rc-ink-3` unknown. The hard-coded hex in `deltaColor` goes.
  - The column means the same on both phase tabs: the predicted finish against where the car actually starts.
- **Accept:**
  - Helper tests cover official, provisional, pit lane, a driver missing from the grid and no grid, plus the R20 rows above (HAM +4, VER +8, BOR 0).
  - `grep -rn "parseGridPosition\|deltaVsGrid" frontend/app` finds nothing.
  - Coverage for the new helper only. `FullGridTable` stays off the list (P4.3b rebuilds the Predictions tab).
- **Verify:** `npm run lint`, `typecheck`, `build`, `test:coverage`.
- **PR:** `fix: race-day weather, risk register, strategy baseline, map labels and grid deltas from current data`.

## Phase P3 — Global chrome and homepage

- **P3.1 `app/ui/shell/`:**
  - `navConfig.ts`;
  - `SiteHeader` (logo B1 + wordmark, mono links, sliding red underline);
  - `MoreMenu`, `MobileNav` (uses `useScrollLock`);
  - `RaceStatusChip` ("● R20 · PRE-RACE", live pulse, countdown on hover; shell segment + `useClock`).
    - It neither renders nor fetches on static routes (`/`, listed in `navConfig`). There the slot is empty, except while the backend restarts or cannot be reached: then, on every route, it holds P3.5's restart lights, which never block.
  - Remove `NavShell` and `RaceControlShell`. `race-control/layout.tsx` becomes a container only.
- **P3.2** Move `/race-control/teams` to `/race-control/standings`, with redirects in `next.config.ts`.
- **P3.3 Homepage**, static (user, 2026-11-06: "there cannot be any live data on it"):
  - **First revise `home.html`** to a data-free version with the same composition: photo hero, sections 01–03 and the CTAs.
    - Remove the next-up strip and countdown, the champion tile, the 2026-so-far season rail, the standings motif (ANT 380 · VER 261 · HAM 259) and the sample AI Engineer answer.
    - Data motifs become data-free illustrations (racing line, the B1 apex). No numbers that can go stale or wrong between deploys.
  - **Then build it.** It fetches nothing, not even at build time, and `next build` lists `/` as static (○). The only API call on `/` is the readiness probe (P0c.7), which shows P3.5's restart lights only while the backend restarts.
- **P3.4** Styled `not-found.tsx` and `global-error.tsx`; footer from `navConfig`.
- **P3.5 Restart lights** (user, 2026-11-06; rewritten 2026-11-09 for the always-on backend, P0c.7, to the 2026-11-08 Loading decision):
  - **Today (after P0c.7):**
    - `ServerStatusNotice` (`app/components/`, mounted beside the page in the root layout, never around it) shows a small card at the bottom of every route while `/api/ready` is not ready. It reads "Updating — back in a few seconds", with the backend's stage detail and a compact `StartLightGantry` lit by `litCountForStage(stage)` (`STAGE_ORDER` mirrors `WARMUP_STEPS`).
    - Nothing is `inert` and scroll is never locked. The card is a polite live region that stays mounted, empty, while the backend is up.
    - After two minutes of failed probes it reads "Server isn't responding", with Try again and Dismiss. When the backend comes back it shows "Back online" with lights out for `LAUNCH_DURATION_MS`, then goes.
    - `e2e/server-status.spec.ts` guards it: a data route stays usable with `/api/ready` held at a stage, and nothing shows when it is ready.
  - **Do:** restyle it to the redesign; the behaviour stays.
    - **Lights from the real stages only, never paced by a timer.** A pure `lightsFor(stage, ready)` replaces `litCountForStage`:
      - the stage in progress sets the count (`pending` 1 … `store` 5);
      - ready keeps 5, then plays lights out;
      - an unknown stage, or a failed probe (no stage), keeps the highest count the run has reached, so the lights never go out mid-restart.
    - **Never blocking, on every route,** and only while the backend restarts or cannot be reached. No overlay, no `inert`, no scroll lock, and focus is never moved.
    - **Placement:** a compact `WarmupLights` strip plus a short label in the top bar's status-chip slot (P3.1), which it takes over while showing. Decide against the mockups whether the bottom card stays (for example on phones, where the slot is narrow, or for the unreachable state's Try again), and record the decision.
    - **Look:**
      - Tokens only: the lamps still hard-code their colours.
      - Each lamp fades on (entrance, behind `motion-safe`); under reduced motion, lamps switch on with no animation.
      - The newest lamp's existing `glow-pulse` loop goes unless the mockup keeps it. No new glows or loops.
  - **Accept:**
    - Unit tests for `lightsFor`: 1→5 by stage, 5 when ready, an unknown stage or a failed probe never lowers the count within a run.
    - e2e with `/api/ready` held at a stage (`mockBackend(page, { readiness })`):
      - `/` and a data route stay interactive (nothing `inert`) and show the lights at the stage's count;
      - ready plays lights out and the lights go;
      - a backend that is up shows nothing.
- **P3.6 Non-blocking pages** (user, 2026-11-06: "the APIs should be non-blocking to the page"):
  - **Today:**
    - `race-control/page.tsx` awaits all five overview segments (`Promise.all`) before any HTML.
    - `grand-prix`, the driver, team and power-unit car pages, `power-units`, `champions`, `debriefs`, `telemetry` and `teams` await their data at page level.
    - `lib/server/backend.ts` gives a server render 5 s, retries included (P0c.7; 10 s before), so a slow or restarting backend can hold first paint that long.
  - **Do:**
    - Remove every page-level backend await. The shell renders at once.
    - Each section takes its data through P0b.3's `useSection`, or a Suspense boundary with a server seed that SWR takes over.
    - Survey the endpoints and split any that feed unrelated sections, as the overview was split. List the splits in the log.
    - Metadata (`generateMetadata`) must not hold the stream either.
  - **Coverage:** the kit is already covered (P0b.3). The pages are covered by the tasks that rebuild them, per the no-coverage-for-rewrites rule.
  - **Accept:** e2e with the API delayed 20 s:
    - the header and section skeletons show within 1 s;
    - sections fill independently;
    - a 500 on one section leaves the others intact.
- **Accept (phase):**
  - e2e covers the nav, More menu, mobile drawer, homepage CTAs, the restart lights (never blocking, on `/` and data routes) and a delayed-API page.
  - Coverage for `ui/shell`, `home`, `layout`, `page` and the restart-lights components.
  - **PR.**

## Phase D1 — OpenF1 ingest and store (data platform, part 1)

- **D1.1 Postgres tables** keyed by `(year, round, session_key)`, each row with provenance (`source`, `fetched_at`, `provisional`):
  - `sessions`, `entries`, `classifications`, `pit_stops`, `stints`;
  - `race_control_messages`, `overtakes`, `positions`, `intervals`;
  - `weather_observations`, `team_radio` (URL only), `standings_snapshots`.
  - Follow the `app/data/store.py` / `analysis_cache` patterns.
- **D1.2 Ingest job.** Pull every endpoint for a session once it ends, and again an hour later. Use `scripts/` plus a GitHub Action, following the PU ingest pattern (`--require-database`).
- **D1.3 Source resolver services** per fact, following the matrix in `docs/DATA_SOURCES.md`. Payloads carry `sources` for `SourceBadge`.
- **D1.4 Quirk handling, with tests for each:**
  - lap rows missing `date_start` (carry the leader over);
  - `starting_grid` 404s for 2026;
  - `pit.stop_duration` can be empty;
  - 401 during live sessions means "live data unavailable".
- **Accept:** the R18 and R19 ingest is idempotent, and the resolver tests cover each fallback. **PR.**

## Phase P4 — Race picker, Grand Prix hub, Telemetry

- **P4.1 `app/ui/race-picker/`** per `grand-prix.html`:
  - a season rail placed by date, ticks in the winner's team colour, the selected round in red, a tooltip;
  - ‹ › arrows, an "All races" popover, keyboard support;
  - a `useSchedule` that dedupes the three separate schedule fetches.
  - It replaces `SeasonRoundStrip`, the Debriefs select and the Telemetry `YearPicker` row.
- **P4.2** Add a `GET /api/race-control/circuit/{year}/{round}` route over `build_circuit_segment`.
- **P4.3a Grand Prix Hub rethink** (design only, no app code; user, 2026-11-04): rethink every tab and every column for what it means and what data it shows, and add a **Results** tab.
  - Per tab (Weekend, Sessions, Grid, Stints, Results, Predictions), write down:
    - the one question the tab answers;
    - the data that answers it, and that data's authority per `docs/DATA_SOURCES.md`;
    - every column: what it means, its unit, and its special states (DNF with reason, DNS, DSQ, NC, pit-lane start, penalty, provisional).
    - A column that doesn't serve the tab's question goes. The tab order is part of the rethink.
  - **Results** owns the official race and sprint classification: the FIA final classification, which f1db mirrors until D2.3. A car that retired reads DNF with its reason, never its classified place, and gains no places (user, 2026-11-04).
  - **Sessions** keeps practice and qualifying.
  - **Predictions' Review** stops printing a second results table: it scores the prediction against Results and decides what "vs call" shows for a DNF.
  - **Draw the line with the Debrief** (P6.1, `debrief.html`): Results is the classification, the Debrief is the story of the race.
  - **Output:**
    - a spec, `docs/design/redesign/grand-prix-tabs.md`;
    - a new `gp-results.html`, revised `gp-*.html` mockups wherever a column changes, and a Results card in `index.html`.
    - **The user signs off before P4.3b starts.**
- **P4.3b Grand Prix tabs**, matching the P4.3a mockups (where P4.3a changes nothing, these hold):
  - Weekend: hero with map, countdown and stakes (shows the clinch);
  - Sessions: qualifying table with gap bars, knock-out cuts, DSQ rows;
  - Grid: staggered grid, penalty chips with FIA document references once D2 lands, the pit-lane box;
  - Stints: the P0 logic plus the new visuals and legend;
  - Results: per `gp-results.html`; `GrandPrixTab` (`app/lib/entityLinks.ts`) and `HUB_TABS` gain `results` (`?tab=results`);
  - Predictions: 22 cars, seat TBC, why-P1 attribution, risk, model scorecard.
  - Split `GrandPrixView.tsx` (443 lines) and `GrandPrixPanels.tsx` (404).
- **P4.4 Telemetry:**
  - Header: the picker, then a single toolbar.
  - Speed map draws itself.
  - Head-to-head becomes **independent cards** (lap/sectors, mini-sector map, delta (smoothed, ending at the official gap), speed, throttle, brake, gear).
  - Tyre wear has four charts (degradation scatter, race pace, wear rate by stint with the raw value beside it, stint lengths).
  - Titles computed. Shares of the lap are time-based, matching the speed map.
- **P4.5 Qualifying segments in the Telemetry Lab** (user, 2026-11-07: "the speed map for qualifying should take Q1, Q2, Q3 into consideration and group accordingly"):
  - **Today:** a qualifying session is one flat pool.
    - The lap picker (`AnalysisPickers.LapPicker`) lists every timed lap with no segment.
    - The driver picker shows one session-wide best.
    - The default lap is the session's fastest valid lap (`services/analysis/lap_selection.choose_lap`).
    - So a Q1 lap can be compared with a Q3 lap, and nothing shows who went out where.
  - **Do (backend):**
    - **Segment windows** come from OpenF1 `race_control` (`qualifying_phase` 1–3; SQ1–SQ3 in sprint qualifying): each phase runs from its first green light ("PIT EXIT OPEN") to its chequered flag, and red flags stay inside the window.
      - Mexico City 2026 (session 11400): Q1 21:00:00–21:25:07 (red flag 21:06:54, restart 21:14:00), Q2 21:33:00–21:48:00, Q3 21:55:00–22:08:00 UTC.
    - **Each lap gets a `segment`** from its `date_start`: a lap that starts before the chequered flag belongs to that segment even if it ends after.
    - **Cross-check** against OpenF1 `session_result.duration` ([Q1, Q2, Q3]): each driver's best in segment n must be a lap inside window n. On a mismatch, log a warning and mark the grouping unconfirmed.
    - **Never infer segments from lap gaps.** With no phases in race control, laps stay ungrouped, with a notice "Q1/Q2/Q3 not published for this session".
    - **The segment each driver reached** comes from the classified position and the elimination cut for the entry count (22 cars: 6 out in Q1, 6 out in Q2, 10 in Q3), not from which times exist. In Mexico City, Hülkenberg (P10) reached Q3 with no Q3 time and Albon (P16) reached Q2 with no Q2 time; they read "no time set in Q3" / "no time set in Q2".
    - **Disqualifications:** OpenF1 doesn't flag Lawson's qualifying disqualification (FIA doc 57; `dsq` is false). The label comes from f1db/Jolpica qualifying, and from the FIA classification after D2.2. A disqualified driver's laps stay viewable, labelled.
    - **Payloads:**
      - `timed_laps` carries `segment` per lap.
      - The driver list carries the best valid lap per segment and the segment reached.
      - `choose_lap` takes an optional `segment` and returns the fastest valid lap within it; the deleted-lap rule holds per segment.
  - **Do (frontend):**
    - When the session is qualifying, a `Segmented` control reads Q1 · Q2 · Q3 (SQ1–SQ3 for sprint qualifying). It defaults to the last segment the chosen driver reached. It sits in P4.4's toolbar and lives in the URL (`?segment=`).
    - The driver picker groups drivers into Q3 / Out in Q2 / Out in Q1 / Disqualified. Each shows their best valid lap in the selected segment, or why they have none ("didn't reach Q3", "no time set in Q3").
    - The lap picker groups laps under Q1 / Q2 / Q3 headings, with deleted laps marked as today.
    - The head-to-head shares `DriverPicker`: it gets the same groups and compares both drivers within the selected segment.
    - Titles are computed from data and name the segment (e.g. "Q3 · fastest valid lap").
    - Practice, sprint and race sessions are unchanged.
  - **Accept:**
    - Fixture from the captured Mexico City qualifying (OpenF1 `race_control`, `laps`, `session_result` for session 11400):
      - the three windows match the times above exactly;
      - every driver's per-segment best matches `session_result.duration`;
      - the groups are 10 / 6 / 6, with Hülkenberg in the Q3 group showing "no time set in Q3" and Albon in the Q2 group;
      - Lawson is labelled disqualified.
    - A sprint qualifying fixture groups SQ1–SQ3.
    - A session with no phases stays ungrouped, with the notice.
    - e2e switches Q1 → Q3 and the speed map redraws with that segment's lap.
- **Accept:** e2e drives the picker by keyboard and changes `?round=`; coverage for `race-picker`, `grand-prix` and `telemetry`. **PR.**

## Phase P5 — Standings, Teams, Drivers (+ clinch calculator)

- **P5.1** Add `GET /api/race-control/standings/{year}/progression` (points per round from the computed standings).
- **P5.2 Standings** per `standings.html`:
  - champion hero, or the leader before a title is decided;
  - the full order as `RankBars`;
  - the title-race line chart with a clinch marker;
  - constructors in two columns, read down each column;
  - `SourceBadge`.
- **P5.3 Clinch calculator** (idea #2):
  - for each driver and team still alive, "what they need" race by race (e.g. "Mercedes clinch in São Paulo if they outscore Ferrari by 4");
  - backend logic with tests for ties, sprints and decided titles.
- **P5.4 Teams index** per `teams.html` (cards + points-share bar); **Team page** per `team.html` (hero in the team colour, heat grid, points by weekend); **Driver page** per `driver.html` (car-number hero, form guide, teammate race and grid head-to-head, places gained, points per race).
- **Accept:** coverage for `standings`, `constructors`, `drivers` and `teams`. **PR.**

## Phase D2 — FIA documents ingest (data platform, part 2)

- **D2.1** Generalize `app/data/power_units/fia_site.py` + `ingest.py` into a document ingest covering every kind on the event page, using the polite fetcher and `pdf_text`.
- **D2.2 Parsers, each tested against real 2026 PDFs:**
  - Penalties (Infringement / Decision / Summons): car, offence, penalty kind and value, regulation article, status.
  - Starting grids (provisional and final).
  - Classifications (FP / Q / race, provisional and final).
  - Deleted laps.
  - Entry list and driver changes.
  - Pirelli preview (compounds C1–C5).
- **D2.3 Resolver integration.**
  - The FIA final classification becomes the authority for results and standings points. Provisional results become confirmed when it lands.
  - Grid-drop reasons attach to the grid.
  - FIA lap deletions feed every "fastest lap" pick.
- **D2.4 Weekend live feed backend** (idea #1): a GitHub Action polls every 5 minutes, Thursday to Sunday, honouring the crawl delay; `GET /api/weekend/{year}/{round}/feed` returns new documents as typed events.
- **Accept:** R19 parsed exactly as `docs/DATA_SOURCES.md` describes (docs 17, 33, 57, 65, 79, 86). **PR.**

## Phase P6 — Debrief, Power Units, Champions (+ radio moments)

- **P6.1 Debrief** per `debrief.html`:
  - a headline computed from the race (winner + context, e.g. the clinch);
  - podium, KPIs, **lap-leader strip**, **race trace** with SC/VSC/red-flag bands, grid→finish `SlopeChart`;
  - **penalty timeline** (race control + FIA), **overtakes leaderboard** ("on-track position changes · OpenF1");
  - picker limited to completed races, with `?round=`.
  - Split `DebriefsView.tsx` (510 lines).
- **P6.2 Radio moments** (idea #3): attach OpenF1 `team_radio` clips (audio URL, no transcript) to race moments within ±1 lap (stops, incidents, penalties). Play inline and label as audio.
- **P6.3 Power Units** per `power-units.html`: KPI row, pip matrix ordered by standings, shared-seat tags, the grid-places ranking, the car page.
- **P6.4 Champions** per `champions.html`:
  - hero for the latest champion;
  - record facts computed and verified (e.g. youngest: Antonelli 20 y 68 d vs Vettel 23 y 134 d);
  - title leaderboards;
  - wall by decade;
  - season pages.
- **Accept:** coverage for `debriefs`, `power-units` and `champions`. **PR.**

## Phase P7 — Engineer, Rulebook, Command Center, live feed UI, sweep

- **P7.1 Engineer** per `engineer.html`: answers include inline charts (generative UI) and source chips. Copy is computed from tool results.
- **P7.2 Rulebook** per `rulebook.html`: a large search, quick questions that submit straight away, and answers that cite the article plus a real stewards' decision (from the D2 store).
- **P7.3 Command Center:**
  - Barlow title;
  - remove the glow orb;
  - `LiveTimingTower` with team-colour edges and `DriverName codeLast`;
  - **Forecast vs measured** (idea #4): OpenF1 measured track temperature and rainfall beside the Open-Meteo forecast. It builds on P0b.1's stored forecast.
  - The weather card, the risk register, the strategy baseline and the corner labels were fixed in P0b. This task restyles them and doesn't rework their data.
- **P7.4 Weekend live feed UI** (idea #1): a feed panel on the Command Center and the Grand Prix hub showing new FIA decisions as they publish (penalty, grid drop, deleted lap), each linking to its document.
- **P7.5 Sweep.** `grep` for `#00FF78` used as an accent, `italic uppercase`, `text-neutral-`, `#151817`, `#0F1210` and `--font-barlow` fallbacks, and fix them. `SourceBadge` on every data screen (idea #5).
- **Accept:** coverage for `rulebook`, `engineer` and `race-control/page`. **PR.**

## Phase P8 — Race Rewind (idea #6)

- **Design is already decided** (memory `project-race-rewind-design`): a lap chart, plus a scrubber driving an order tower.
- **Position changes are classified** as on-track pass, pit cycle or inherited. They come from OpenF1 `position` / `overtakes` + pit + retirements, and are labelled "position changes" unless they are classified passes.
- **Accept:** an R19 replay matches the FIA final classification at the flag. **PR.**

## Phase P9 — Coverage completion

- Cover what's left: hooks (`useChat`, `useLiveTiming` with a mock WebSocket, `useVoice`), lib, utils, chat components, LocalTime, and the root configs (`next.config.ts`, `instrumentation*`, `sentry.*`).
- Switch the coverage include to `app/**` plus the root TypeScript files.
- **Accept:** `npm run test:coverage` reports 100/100/100/100 per file, and CI enforces it. **PR.**

---

## New ideas → where they land

| #   | Idea                           | Data                                  | Phase                                               |
| --- | ------------------------------ | ------------------------------------- | --------------------------------------------------- |
| 1   | Weekend live feed              | FIA documents every 5 min             | D2.4 backend, P7.4 UI                               |
| 2   | Clinch calculator              | Computed standings + points left      | P5.3                                                |
| 3   | Radio moments                  | OpenF1 `team_radio`                   | D1 store, P6.2 UI                                   |
| 4   | Forecast vs measured           | OpenF1 `weather` + Open-Meteo         | D1 store, P7.3 UI                                   |
| 5   | Provisional / confirmed badges | Resolver `sources`                    | P0.5 data, P1.4 `SourceBadge`, everywhere from P7.5 |
| 6   | Race Rewind                    | OpenF1 `position` / `overtakes` + pit | P8                                                  |

## Phase order and dependencies

`P0 → P1 → P2 → P0c → P0b → P3 → D1 → P4 → P5 → D2 → P6 → P7 → P8 → P9`

- P0c was added on 2026-11-08 as P0 (user) and runs first: P0b.1's Open-Meteo diagnosis belongs on the new host.
- P0b was added on 2026-11-06 and runs before P3 (bugs first). P3.6 depends on P0b.3's section kit.
- P4 can start before D1 finishes; the Grid tab's FIA reasons wait for D2.
- P6.1's penalty timeline uses race control first and gains FIA decisions after D2.
- P9 can be chipped at any time but finishes last.
