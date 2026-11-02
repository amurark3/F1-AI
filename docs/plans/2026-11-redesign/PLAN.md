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

| Topic        | Decision                                                                                                                                                                                                                               |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Order        | **Bugs first.** Phase P0 ships as its own small PR, then the redesign phases.                                                                                                                                                          |
| Navigation   | One top bar on every screen; the Race Control sidebar is removed. Champions, Debriefs and Rulebook go under "More".                                                                                                                    |
| Homepage     | Photo hero using `frontend/public/hero-car.jpg` (the user's image, currently untracked), with live data below it.                                                                                                                      |
| Display font | Barlow Condensed for page titles and section heads. Geist Sans for UI and body, Geist Mono for labels and data.                                                                                                                        |
| Logo         | **B1 "Apex"**: `docs/design/redesign/logo/rl-1-apex.svg` (racing line + red apex dot on a #0B0F18 tile). The user rejected the other variants; B8 is "too strong and blinding".                                                        |
| Visual spec  | The mockups in `docs/design/redesign/` (start at `index.html`, tokens in `system.css`). Build each screen to match its mockup.                                                                                                         |
| Charts       | Legends are **welcome when they add data points**. Telemetry Head-to-Head charts are **independent cards**, each with its own insight title, not one synced stack. Every chart title is **computed from data**, never written by hand. |
| Tests        | Frontend coverage reaches **literal 100%** by the end. Use a per-folder ratchet. No `v8/istanbul/c8 ignore` comments; delete dead code instead.                                                                                        |
| Names        | f1db is canonical: `driver.name` / `last_name` / `abbreviation` and the constructor id. No new Postgres identity table; read-path overlay only.                                                                                        |
| New ideas    | All 6 approved. See the "New ideas" map below.                                                                                                                                                                                         |

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
- **Verify:** pytest. After deploy (user's call), recompute R20 (see the prediction-backfill memory; `scripts/backfill_predictions.py`). Note that writes from another process get clobbered by running production until Render restarts.

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
- **P1.8 Coverage include list** = `app/ui/**`, `app/race-control/weekend/**`, `app/race-control/components/**`, at 100%.
- **P1.9** Update the `CLAUDE.md` design section to the new tokens and rules: Barlow display font, text tones, red usage, the gain token, and legends allowed.
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
  - `race-control/profiles/**` joins the coverage include list.
- **PR:** `feat: one canonical name for every driver and team`.

## Phase P3 — Global chrome and homepage

- **P3.1 `app/ui/shell/`:**
  - `navConfig.ts`;
  - `SiteHeader` (logo B1 + wordmark, mono links, sliding red underline);
  - `MoreMenu`, `MobileNav` (uses `useScrollLock`);
  - `RaceStatusChip` ("● R20 · PRE-RACE", live pulse, countdown on hover; shell segment + `useClock`).
  - Remove `NavShell` and `RaceControlShell`. `race-control/layout.tsx` becomes a container only.
- **P3.2** Move `/race-control/teams` to `/race-control/standings`, with redirects in `next.config.ts`.
- **P3.3 Homepage** per `home.html`:
  - photo hero;
  - next-up strip, with a champion tile when the title is decided;
  - the **2026-so-far season rail**;
  - sections 01–03 with data motifs.
  - It must render with the backend cold (live parts stream in).
- **P3.4** Styled `not-found.tsx` and `global-error.tsx`; footer from `navConfig`.
- **Accept:** e2e covers the nav, More menu, mobile drawer and homepage CTAs; coverage for `ui/shell`, `home`, `layout`, `page`. **PR.**

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
- **P4.3 Grand Prix tabs**, matching their mockups:
  - Weekend: hero with map, countdown and stakes (shows the clinch);
  - Sessions: qualifying table with gap bars, knock-out cuts, DSQ rows;
  - Grid: staggered grid, penalty chips with FIA document references once D2 lands, the pit-lane box;
  - Stints: the P0 logic plus the new visuals and legend;
  - Predictions: 22 cars, seat TBC, why-P1 attribution, risk, model scorecard.
  - Split `GrandPrixView.tsx` (443 lines) and `GrandPrixPanels.tsx` (404).
- **P4.4 Telemetry:**
  - Header: the picker, then a single toolbar.
  - Speed map draws itself.
  - Head-to-head becomes **independent cards** (lap/sectors, mini-sector map, delta (smoothed, ending at the official gap), speed, throttle, brake, gear).
  - Tyre wear has four charts (degradation scatter, race pace, wear rate by stint with the raw value beside it, stint lengths).
  - Titles computed. Shares of the lap are time-based, matching the speed map.
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
  - **Forecast vs measured** (idea #4): OpenF1 measured track temperature and rainfall beside the Open-Meteo forecast.
- **P7.4 Weekend live feed UI** (idea #1): a feed panel on the Command Center and the Grand Prix hub showing new FIA decisions as they publish (penalty, grid drop, deleted lap), each linking to its document.
- **P7.5 Sweep.** `grep` for `#00FF78` used as an accent, `italic uppercase`, `text-neutral-`, `#151817`, `#0F1210` and `--font-barlow` fallbacks, and fix them. `SourceBadge` on every data screen (idea #5).
- **Accept:** coverage for `rulebook`, `engineer` and `race-control/page`. **PR.**

## Phase P8 — Race Rewind (idea #6)

- **Design is already decided** (memory `project-race-rewind-design`): a lap chart, plus a scrubber driving an order tower.
- **Position changes are classified** as on-track pass, pit cycle or inherited. They come from OpenF1 `position` / `overtakes` + pit + retirements, and are labelled "position changes" unless they are classified passes.
- **Accept:** an R19 replay matches the FIA final classification at the flag. **PR.**

## Phase P9 — Coverage completion

- Cover what's left: hooks (`useChat`, `useLiveTiming` with a mock WebSocket, `useVoice`), lib, utils, chat components, LocalTime, ServerWarming*, and the root configs (`next.config.ts`, `instrumentation*`, `sentry.*`).
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

`P0 → P1 → P2 → P3 → D1 → P4 → P5 → D2 → P6 → P7 → P8 → P9`

- P4 can start before D1 finishes; the Grid tab's FIA reasons wait for D2.
- P6.1's penalty timeline uses race control first and gains FIA decisions after D2.
- P9 can be chipped at any time but finishes last.
