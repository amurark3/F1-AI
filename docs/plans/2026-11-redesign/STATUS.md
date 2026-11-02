# Status: accuracy fixes, data platform and redesign

Plan: [`PLAN.md`](PLAN.md). **Read its "How to run this plan" section before touching anything.**

- **Updating this file:**
  - Set a task to `in_progress` (with the date) before starting it.
  - Set it to `done` only after its Verify commands pass and every Accept item is true. Record the commit SHA and the key evidence.
  - Add anything surprising to the log below.
- **Statuses:** `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Next task:** P0.1
- **Branch:** `dev`
- **Open PR:** none

## Tasks

| ID   | Task                                                                               | Status | Commit / PR                   | Evidence / notes                                               |
| ---- | ---------------------------------------------------------------------------------- | ------ | ----------------------------- | -------------------------------------------------------------- |
| P0.1 | Stints: status from the classification (OpenF1 `session_result`)                   | in_progress (2026-11-02) |                               |                                                                |
| P0.2 | Stops and times from the official pit sheet; red-flag entries excluded             | todo   |                               |                                                                |
| P0.3 | Prediction roster: 22 cars, ≤2 per team, seat TBC                                  | todo   |                               |                                                                |
| P0.4 | Prediction factor text agrees with attribution                                     | todo   |                               |                                                                |
| P0.5 | Computed, provisional, cross-checked standings                                     | todo   |                               |                                                                |
| P0.6 | Clinch state everywhere                                                            | todo   |                               |                                                                |
| P1.1 | Test infrastructure (Vitest, MSW, Playwright, CI, no-ignore lint rule)             | todo   |                               |                                                                |
| P1.2 | Tokens + Barlow Condensed font                                                     | todo   |                               |                                                                |
| P1.3 | Logo B1 Apex: icon.svg, apple-icon, OG image, lockup                               | todo   |                               |                                                                |
| P1.4 | UI kit in `app/ui/` (+ SourceBadge)                                                | todo   |                               |                                                                |
| P1.5 | Primitive fixes (neutral defaults, red loaders, panel fold)                        | todo   |                               |                                                                |
| P1.6 | Delete dead components and charts                                                  | todo   |                               |                                                                |
| P1.7 | Commit mockups, docs, plan, hero image                                             | done   | `git log --grep "Task: P1.7"` | Rejected logo variants deleted; only `logo/rl-1-apex.svg` kept |
| P1.8 | Coverage ratchet: ui, weekend, components                                          | todo   |                               |                                                                |
| P1.9 | Update the CLAUDE.md design section                                                | todo   |                               |                                                                |
| P2.1 | `identity.py`: `resolve_driver` / `canonical_driver`                               | todo   |                               |                                                                |
| P2.2 | Every backend emit point uses canonical names                                      | todo   |                               |                                                                |
| P2.3 | Frontend `DriverName` / `TeamName`; delete name hacks                              | todo   |                               |                                                                |
| P3.1 | Top bar, More menu, mobile nav, race status chip                                   | todo   |                               |                                                                |
| P3.2 | `/race-control/standings` route + redirects                                        | todo   |                               |                                                                |
| P3.3 | Homepage per mockup (incl. season rail)                                            | todo   |                               |                                                                |
| P3.4 | not-found / global-error / footer                                                  | todo   |                               |                                                                |
| D1.1 | Postgres tables with provenance                                                    | todo   |                               |                                                                |
| D1.2 | OpenF1 per-session ingest job + Action                                             | todo   |                               |                                                                |
| D1.3 | Per-fact source resolvers (`sources` in payloads)                                  | todo   |                               |                                                                |
| D1.4 | OpenF1 quirk handling with tests                                                   | todo   |                               |                                                                |
| P4.1 | Race picker (season rail)                                                          | todo   |                               |                                                                |
| P4.2 | Circuit-by-round route                                                             | todo   |                               |                                                                |
| P4.3 | Grand Prix tabs per mockups; split large files                                     | todo   |                               |                                                                |
| P4.4 | Telemetry header, independent head-to-head cards, tyre wear                        | todo   |                               |                                                                |
| P5.1 | Standings progression endpoint                                                     | todo   |                               |                                                                |
| P5.2 | Standings page per mockup                                                          | todo   |                               |                                                                |
| P5.3 | Clinch calculator (idea #2)                                                        | todo   |                               |                                                                |
| P5.4 | Teams index, Team page, Driver page                                                | todo   |                               |                                                                |
| D2.1 | Generalized FIA document ingest                                                    | todo   |                               |                                                                |
| D2.2 | FIA parsers (penalties, grids, classifications, deleted laps, entry list, Pirelli) | todo   |                               |                                                                |
| D2.3 | FIA final classification as authority in resolvers                                 | todo   |                               |                                                                |
| D2.4 | Weekend live feed backend (idea #1)                                                | todo   |                               |                                                                |
| P6.1 | Debrief per mockup                                                                 | todo   |                               |                                                                |
| P6.2 | Radio moments (idea #3)                                                            | todo   |                               |                                                                |
| P6.3 | Power Units per mockup                                                             | todo   |                               |                                                                |
| P6.4 | Champions per mockup + verified records                                            | todo   |                               |                                                                |
| P7.1 | Engineer: inline charts + sources                                                  | todo   |                               |                                                                |
| P7.2 | Rulebook: cites articles + stewards' decisions                                     | todo   |                               |                                                                |
| P7.3 | Command Center polish + forecast vs measured (idea #4)                             | todo   |                               |                                                                |
| P7.4 | Weekend live feed UI (idea #1)                                                     | todo   |                               |                                                                |
| P7.5 | Sweep + SourceBadge everywhere (idea #5)                                           | todo   |                               |                                                                |
| P8.1 | Race Rewind (idea #6)                                                              | todo   |                               |                                                                |
| P9.1 | Coverage completion to 100% across `app/**`                                        | todo   |                               |                                                                |

## Log (append only; newest at the bottom)

- **2026-11-02 · planning.**
  - **Locked decisions:** bugs first, logo B1, all 6 ideas. Mockups in `docs/design/redesign/`; data audit in `docs/DATA_SOURCES.md`.
  - **Before P1.7, these are untracked:** `docs/DATA_SOURCES.md`, `docs/design/`, `docs/plans/`, `frontend/public/hero-car.jpg`.
- **2026-11-02 · facts verified for P0 fixtures** (R19 Mexico City, session_key 11404):
  - **Classification:** FIA doc 86 matches OpenF1 `session_result`. DNF: LIN L58, BEA L47, BOT L42, STR L5, ALO L5.
  - **Standings after R19:** ANT 380 · VER 261 · HAM 259 · RUS 250 · LEC 245; Mercedes 630 · Ferrari 504 · Red Bull 382 · McLaren 365.
  - **Red flag** after lap 45, standing restart on lap 46. Jolpica pit sheet stops (red-flag lap and >120 s excluded): VER 1, HAM 2, LAW 2, HIR 3, STR 1.
  - **R20 snapshot:** 23 drivers in production (TSU, OCO extra; HIR missing).
- **2026-11-02 · P1.7 done.**
  - Committed `docs/DATA_SOURCES.md`, `docs/design/redesign/` (19 mockups + index, `system.css`, B1 logo), `docs/plans/2026-11-redesign/`, `frontend/public/hero-car.jpg` and the `CLAUDE.md` pointer.
  - Deleted the first-round logos and rejected racing-line variants B2–B8 at the user's request.
- **2026-11-02 · decision (user):** no full revamp of the Command Center. It is the reference design and gets only the alignment pass already in P0.6, P1.2, P1.4, P1.5, P2, P3.1 and P7.3–P7.5. Its new parts (FIA live feed, forecast vs measured, restyled timing tower) have **no mockup by choice**. Build them in P7 from the shared kit and the existing Command Center look; don't stop to ask for one.
