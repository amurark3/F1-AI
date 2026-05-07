---
phase: 03-client-feature-surface
plan: 01
subsystem: api
tags: [swift, ios, codable, observable, viewmodel, caching]

# Dependency graph
requires:
  - phase: 02-backend-data-features
    provides: /api/predictions/{year}/{round} REST endpoint returning PredictionsResponse JSON
provides:
  - PredictionsResponse, DriverPrediction, AccuracyStats Codable structs in ios/F1AI/Models/Predictions.swift
  - APIClient.fetchPredictions(year:round:) with 30-min cache in ios/F1AI/Services/APIClient.swift
  - PredictionsViewModel @Observable class with loadPredictions, retry, toast state management
affects:
  - 03-02-PLAN.md (PredictionsView depends on PredictionsViewModel and DriverPrediction)
  - 03-05-PLAN.md (any prediction-related UI or widgets)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@Observable ViewModel pattern matching StandingsViewModel structure"
    - "fetchCached(url:cacheKey:maxAge:) generic cache wrapper reused for new endpoint"
    - "Dual error path: first-load self.error vs background refresh toastMessage"
    - "Backend HTTP 200 + error body handling via PredictionsResponse.error field"

key-files:
  created:
    - ios/F1AI/Models/Predictions.swift
    - ios/F1AI/ViewModels/PredictionsViewModel.swift
  modified:
    - ios/F1AI/Services/APIClient.swift

key-decisions:
  - "PredictionsResponse.error: String? field decodes backend HTTP 200 error body (no upcoming race or data failure)"
  - "First-load failure sets self.error for ContentUnavailableView; background refresh failure sets toastMessage for toast overlay"
  - "fetchPredictions caches for 1800 seconds (30 min) — backend recomputes when qualifying data becomes available"

patterns-established:
  - "Predictions data layer pattern: model in Models/, APIClient extension, @Observable ViewModel"

requirements-completed:
  - CLIENT-01

# Metrics
duration: 1min
completed: 2026-03-01
---

# Phase 3 Plan 01: iOS Predictions Data Layer Summary

**PredictionsResponse/DriverPrediction/AccuracyStats Codable models, APIClient.fetchPredictions with 30-min cache, and @Observable PredictionsViewModel with dual-path error handling (first-load vs background refresh)**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-01T04:42:25Z
- **Completed:** 2026-03-01T04:43:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `Predictions.swift` with three Codable structs matching backend JSON exactly, including `error: String?` field for HTTP 200 error body decoding
- Extended `APIClient` with `fetchPredictions(year:round:)` using 30-min cache via existing generic `fetchCached` helper
- Created `PredictionsViewModel` as `@Observable` class distinguishing first-load errors (sets `self.error` for `ContentUnavailableView`) from background refresh failures (sets `toastMessage` for toast overlay)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Predictions.swift Swift models** - `51f5684` (feat)
2. **Task 2: Add fetchPredictions to APIClient + create PredictionsViewModel** - `2525b37` (feat)

**Plan metadata:** (docs: complete plan — see final commit)

## Files Created/Modified
- `ios/F1AI/Models/Predictions.swift` - PredictionsResponse, DriverPrediction, AccuracyStats Codable structs with snake_case CodingKeys
- `ios/F1AI/Services/APIClient.swift` - Added fetchPredictions(year:round:) in new MARK section; no existing methods modified
- `ios/F1AI/ViewModels/PredictionsViewModel.swift` - @Observable ViewModel with dual error path, loadPredictions, retry, dismissToast

## Decisions Made
- `error: String?` field on `PredictionsResponse` is intentional to handle backend returning HTTP 200 with an error body (e.g., no upcoming race found, data unavailable)
- First-load path and background-refresh path are explicitly separated: first-load clears `error` and sets `isLoading`, refresh keeps existing data and uses `toastMessage` — this matches the locked UX decision from CONTEXT.md
- `fetchPredictions` placed before `// MARK: - Health` to maintain API section ordering consistent with existing MARK structure

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- iOS predictions data layer is complete; Plans 02 and 05 can now build prediction UI on top of `PredictionsViewModel` and `DriverPrediction`
- No blockers for Phase 3 continuation

## Self-Check: PASSED

- ios/F1AI/Models/Predictions.swift: FOUND
- ios/F1AI/ViewModels/PredictionsViewModel.swift: FOUND
- .planning/phases/03-client-feature-surface/03-01-SUMMARY.md: FOUND
- Commit 51f5684: FOUND
- Commit 2525b37: FOUND

---
*Phase: 03-client-feature-surface*
*Completed: 2026-03-01*
