---
phase: 03-client-feature-surface
plan: 03
subsystem: ui
tags: [swiftui, championship, contention-math, what-if, segmented-picker, wdc, wcc]

# Dependency graph
requires:
  - phase: 03-02
    provides: StandingsTab three-segment picker, StandingsViewModel.selectedYear, APIClient fetchDriverStandings/fetchConstructorStandings/fetchSchedule
provides:
  - ChampionshipViewModel: @Observable with contention math, sprint-aware maxPointsRemaining, wdcClinched/wccClinched
  - ChampionshipDriverRow: per-driver contender row with position, name, team, points, delta to leader
  - ChampionshipConstructorRow: per-constructor contender row with same layout
  - ChampionshipView: WDC/WCC sub-tabs with preset what-if buttons (Next 3/5/All) and Stepper
  - StandingsTab updated to 4 segments (Drivers | Constructors | Predictions | Championship)
affects:
  - 03-04 (CompareView/DriverCompareView — no dependency on Championship segment)
  - 03-05 (ToastView overlay — applies to PredictionsView, not Championship)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ChampionshipViewModel fetches drivers, constructors, schedule concurrently via async let"
    - "maxPointsRemaining accounts for sprint weekends using isSprint flag on RaceEvent"
    - "wccContenders uses 2x the WDC max remaining (both cars score per race weekend)"
    - "Preset buttons drive vm.whatIfRaces; Stepper supplements for fine-grained ±1 control"
    - "StandingsTab integer segment tag extended from 3 to 4 — clean extension point established in 03-02"
    - "Clinch banner replaces scenario controls post-championship — single conditional branch on wdcClinched/wccClinched"

key-files:
  created:
    - ios/F1AI/ViewModels/ChampionshipViewModel.swift
    - ios/F1AI/Views/Championship/ChampionshipDriverRow.swift
    - ios/F1AI/Views/Championship/ChampionshipView.swift
  modified:
    - ios/F1AI/Views/Tabs/StandingsTab.swift

key-decisions:
  - "StandingsTab passes vm.selectedYear to ChampionshipView so year picker controls both standings and championship data simultaneously"
  - "wdcContenders / wccContenders compute mathematical elimination dynamically from maxPointsRemaining — no hardcoded cutoffs"
  - "Sprint weekends add 8 pts (max sprint race score) to maxPointsRemaining per RESEARCH.md recommendation"
  - "whatIfRaces defaults to 3 (Next 3 preset selected) — most actionable early-season scenario"
  - "Championship directory created at ios/F1AI/Views/Championship/ mirroring existing Predictions/ pattern"

# Metrics
duration: 12min
completed: 2026-03-03
---

# Phase 3 Plan 03: Championship Scenario View Summary

**ChampionshipViewModel with mathematical elimination logic, WDC/WCC scenario view with preset what-if buttons (Next 3/5/All), and StandingsTab extended to 4 segments**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-03T10:44:19Z
- **Completed:** 2026-03-03T11:37:17Z (approximately)
- **Tasks:** 2
- **Files created:** 3 new, 1 modified

## Accomplishments

- `ChampionshipViewModel` is `@Observable` and loads drivers, constructors, schedule concurrently via `async let`. `maxPointsRemaining` correctly accounts for sprint weekends by adding 8 points per sprint round (via `isSprint` flag on `RaceEvent`).
- `wdcContenders` and `wccContenders` filter by mathematical elimination: only drivers/constructors whose gap to the leader is within remaining available points are shown. `wccContenders` uses 2x the driver max since both cars score per race.
- `wdcClinched`/`wccClinched` return `true` when all challengers are mathematically eliminated — `ChampionshipView` then shows a clinch banner (trophy icon + champion name/points) instead of scenario controls.
- `ChampionshipView` has WDC/WCC sub-tabs via a segmented `Picker`. Preset buttons (Next 3, Next 5, All N) set `vm.whatIfRaces`; a `Stepper` provides ±1 fine-grained control. Both buttons and stepper update the displayed contender logic instantly (reactive via `@Observable`).
- `StandingsTab` extended from 3 to 4 segments — `Text("Championship").tag(3)` added and `case 3: ChampionshipView(year: vm.selectedYear)` wired up. Year picker from `StandingsViewModel.selectedYear` keeps championship data in sync with driver/constructor standings.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ChampionshipViewModel** - `d9cd94f` (feat)
2. **Task 2: Create Championship views and update StandingsTab** - `3ad5882` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `ios/F1AI/ViewModels/ChampionshipViewModel.swift` - @Observable ViewModel with sprint-aware contention math and concurrent API fetching
- `ios/F1AI/Views/Championship/ChampionshipDriverRow.swift` - Both `ChampionshipDriverRow` and `ChampionshipConstructorRow` structs with position/points/delta display
- `ios/F1AI/Views/Championship/ChampionshipView.swift` - Full championship view with WDC/WCC tabs, preset buttons, Stepper, clinch banner, loading/error/empty states
- `ios/F1AI/Views/Tabs/StandingsTab.swift` - Extended from 3-segment to 4-segment picker with Championship at tag 3

## Decisions Made

- `StandingsTab` passes `vm.selectedYear` (from `StandingsViewModel`) to `ChampionshipView` — year picker controls both views without duplicating state
- Mathematical elimination uses `maxPointsRemaining` computed dynamically from the actual upcoming schedule, not a hardcoded number
- Sprint weekends add 8 points to `maxPointsRemaining` (the maximum sprint race score), consistent with F1's points system
- `whatIfRaces` defaults to 3 — the "Next 3" scenario is the most relevant for mid-season viewers
- Championship directory mirrors the existing Predictions/ directory structure

## Deviations from Plan

None - plan executed exactly as written. All types matched existing models (`DriverStanding.driver` as String, `RaceEvent.isSprint` as `Bool?`, `ConstructorStanding` with position/team/points/wins fields).

## Issues Encountered

None - all plan logic mapped cleanly to existing APIClient methods and model types.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- StandingsTab has 4 segments fully wired — Championship tab renders contenders on first entry
- ChampionshipView is self-contained and responsive to year changes via the shared year picker
- The Championship directory at `ios/F1AI/Views/Championship/` is ready for any future sub-views if needed

---
*Phase: 03-client-feature-surface*
*Completed: 2026-03-03*

## Self-Check: PASSED

- FOUND: ios/F1AI/ViewModels/ChampionshipViewModel.swift
- FOUND: ios/F1AI/Views/Championship/ChampionshipDriverRow.swift
- FOUND: ios/F1AI/Views/Championship/ChampionshipView.swift
- FOUND: ios/F1AI/Views/Tabs/StandingsTab.swift
- FOUND: .planning/phases/03-client-feature-surface/03-03-SUMMARY.md
- FOUND: commit d9cd94f (Task 1: ChampionshipViewModel)
- FOUND: commit 3ad5882 (Task 2: Championship views + StandingsTab)
