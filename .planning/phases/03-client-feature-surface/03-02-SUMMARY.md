---
phase: 03-client-feature-surface
plan: 02
subsystem: ui
tags: [swiftui, predictions, expandable-card, segmented-picker, team-color]

# Dependency graph
requires:
  - phase: 03-01
    provides: PredictionsViewModel, PredictionsResponse, DriverPrediction models, fetchPredictions in APIClient
provides:
  - PredictionDriverCard: expandable SwiftUI card (position, team, confidence range, factors)
  - PredictionsView: loading/error/empty/content state view consuming PredictionsViewModel
  - StandingsTab updated with three-segment picker (Drivers | Constructors | Predictions)
affects:
  - 03-05 (ToastView overlay plugs into PredictionsView placeholder)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pass upcoming race as parameter from parent rather than re-fetching schedule inside PredictionsView"
    - "Parallel async let in .task for concurrent standings + schedule loading"
    - "Integer segment state instead of Bool for 3+ segment pickers"

key-files:
  created:
    - ios/F1AI/Views/Predictions/PredictionDriverCard.swift
    - ios/F1AI/Views/Predictions/PredictionsView.swift
  modified:
    - ios/F1AI/Views/Tabs/StandingsTab.swift

key-decisions:
  - "Segment picker uses integer tag (0/1/2) rather than Bool to support three options cleanly"
  - "PredictionsView receives upcomingRace and year as parameters from StandingsTab to avoid duplicating CalendarViewModel"
  - "ProgressView used for loading state instead of custom skeleton shimmering (no third-party dependency)"
  - "accuracy.racesEvaluated checked directly as Int (not cast to Int?) since model field is non-optional"

patterns-established:
  - "PredictionDriverCard pattern: @State isExpanded toggled via withAnimation(.spring), chevron rotates 180 degrees"
  - "Empty state via ContentUnavailableView with flag.checkered icon when upcomingRace is nil or hasNoUpcomingRace"
  - "First-load error via ContentUnavailableView with Retry button; background refresh errors go to toast (Plan 05)"

requirements-completed:
  - CLIENT-01

# Metrics
duration: 8min
completed: 2026-03-03
---

# Phase 3 Plan 02: PredictionsView with Expandable Cards Summary

**SwiftUI PredictionsView with tap-to-expand driver cards embedded as a third segment in StandingsTab's segmented picker**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-03T04:58:01Z
- **Completed:** 2026-03-03T05:06:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- PredictionDriverCard renders position badge, driver name, team (with TeamColor accent bar), and confidence range collapsed by default; tapping expands to show up to 3 key factors with spring animation
- PredictionsView handles four states: ProgressView while loading, ContentUnavailableView+Retry on first-load error, empty state when no upcoming race, and LazyVStack of driver cards on success
- StandingsTab updated from a two-segment Bool picker to a three-segment integer picker (Drivers | Constructors | Predictions), loading schedule and standings in parallel via async let

## Task Commits

Each task was committed atomically:

1. **Task 1: Create PredictionDriverCard.swift** - `7a11103` (feat)
2. **Task 2: Create PredictionsView.swift and update StandingsTab** - `7b42e26` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `ios/F1AI/Views/Predictions/PredictionDriverCard.swift` - Expandable card with spring animation, team colour accent, and factor reveal
- `ios/F1AI/Views/Predictions/PredictionsView.swift` - Full state machine view consuming PredictionsViewModel
- `ios/F1AI/Views/Tabs/StandingsTab.swift` - Three-segment picker with CalendarViewModel for upcoming race lookup

## Decisions Made

- Segment picker uses integer state (0/1/2) rather than Bool — cleaner for three options and extensible if a fourth segment is ever added
- PredictionsView receives `upcomingRace: RaceEvent?` and `year: Int` as parameters from StandingsTab; schedule data isn't duplicated inside PredictionsView
- Loading skeleton replaced with simple `ProgressView` to avoid `.shimmering()` which is not a standard SwiftUI modifier (no third-party dependency introduced)
- `accuracy.racesEvaluated` used directly as `Int` (not `as Int?`) since the Predictions model declares it as non-optional — avoids a spurious compiler warning

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unnecessary `as Int?` cast on non-optional Int**
- **Found during:** Task 2 (PredictionsView content area)
- **Issue:** Plan template used `accuracy.racesEvaluated as Int?` but `AccuracyStats.racesEvaluated` is declared as `Int` (non-optional), making the conditional binding redundant and producing a compiler warning
- **Fix:** Changed `if let racesEvaluated = accuracy.racesEvaluated as Int?, racesEvaluated > 0` to `if accuracy.racesEvaluated > 0` and used `accuracy.racesEvaluated` directly in the label
- **Files modified:** ios/F1AI/Views/Predictions/PredictionsView.swift
- **Verification:** No conditional binding needed; non-optional field used directly
- **Committed in:** 7b42e26 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor correctness fix to avoid compiler warning. No scope creep.

## Issues Encountered

None - all plan logic mapped cleanly to existing ViewModels and models from Phase 03-01.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PredictionsView is complete with a comment placeholder where Plan 05 (ToastView) will attach the toast overlay
- PredictionDriverCard is standalone and reusable
- StandingsTab is fully wired — selecting the Predictions segment renders predictions immediately on first entry

---
*Phase: 03-client-feature-surface*
*Completed: 2026-03-03*

## Self-Check: PASSED

- FOUND: ios/F1AI/Views/Predictions/PredictionDriverCard.swift
- FOUND: ios/F1AI/Views/Predictions/PredictionsView.swift
- FOUND: ios/F1AI/Views/Tabs/StandingsTab.swift
- FOUND: .planning/phases/03-client-feature-surface/03-02-SUMMARY.md
- FOUND: commit 7a11103 (Task 1)
- FOUND: commit 7b42e26 (Task 2)
