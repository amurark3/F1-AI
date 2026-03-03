---
phase: 03-client-feature-surface
plan: 05
subsystem: ui
tags: [swiftui, toast, overlay, error-handling, background-refresh]

# Dependency graph
requires:
  - phase: 03-02
    provides: PredictionsView with Group body and PredictionsViewModel with toastMessage/toastIsRetryable/retry()
provides:
  - ToastView reusable SwiftUI component (ios/F1AI/Views/Shared/ToastView.swift)
  - PredictionsView with ZStack toast overlay wired to vm.toastMessage
affects: [03-06, phase-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ZStack(alignment: .bottom) overlay pattern for non-intrusive toast notifications"
    - "Caller-controlled visibility via onDismiss closure (no internal state in ToastView)"
    - "Task.sleep structured concurrency for auto-dismiss timers (not DispatchQueue)"

key-files:
  created:
    - ios/F1AI/Views/Shared/ToastView.swift
  modified:
    - ios/F1AI/Views/Predictions/PredictionsView.swift

key-decisions:
  - "ToastView holds no internal state — caller controls visibility via onDismiss closure"
  - "Auto-dismiss uses Task.sleep(for: .seconds(4)) structured concurrency per research"
  - "ZStack wraps Group so toast overlay does not affect scroll layout or cause reflow"
  - "onRetry is optional (nil for non-retryable errors) — ToastView is reusable by other views"

patterns-established:
  - "Toast pattern: ZStack(alignment: .bottom) with .transition(.move(edge: .bottom).combined(with: .opacity)) and .animation on ZStack"
  - "Separation of first-load failure (ContentUnavailableView) vs background refresh failure (toast)"

requirements-completed: [CLIENT-04]

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 3 Plan 05: Toast Error Overlay Summary

**Reusable ToastView with 4-second auto-dismiss wired into PredictionsView via ZStack overlay for background refresh failures, keeping stale data visible**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-03T11:59:40Z
- **Completed:** 2026-03-03T12:01:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `ToastView.swift` — a self-contained reusable toast component usable by any view in the app
- Auto-dismiss after exactly 4 seconds using structured concurrency (`Task.sleep`) not `DispatchQueue`
- Wired `ToastView` into `PredictionsView` via `ZStack(alignment: .bottom)` — toast floats over content without affecting scroll layout
- Background refresh failures show toast + keep stale driver cards visible; first-load failures still show `ContentUnavailableView`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ToastView shared component** - `91da46c` (feat)
2. **Task 2: Wire ToastView into PredictionsView** - `618655f` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `ios/F1AI/Views/Shared/ToastView.swift` - Reusable toast with message, optional Retry, auto-dismiss, onDismiss caller-controlled
- `ios/F1AI/Views/Predictions/PredictionsView.swift` - Wrapped Group in ZStack(alignment: .bottom), added toast overlay for vm.toastMessage

## Decisions Made

- `ToastView` holds no internal state — caller controls visibility via `onDismiss` closure, making it stateless and reusable
- `onRetry` is `(() -> Void)?` (optional) so the component can be used for both retryable and non-retryable errors
- `ZStack` wraps the entire Group so the toast is an overlay — does not affect `LazyVStack` scroll layout or cause reflow
- `.animation(.easeInOut(duration: 0.3), value: vm.toastMessage)` is on the `ZStack` so the toast slides in/out without re-rendering scroll content

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ToastView` is fully reusable for any future view needing background error notifications (Phase 4+ views)
- `PredictionsView` CLIENT-04 error handling complete: first-load uses `ContentUnavailableView`, background refresh uses `ToastView`
- Ready to continue Phase 3 Plan 06 (web predictions SWR integration)

## Self-Check: PASSED

- FOUND: `ios/F1AI/Views/Shared/ToastView.swift`
- FOUND: `ios/F1AI/Views/Predictions/PredictionsView.swift`
- FOUND: `.planning/phases/03-client-feature-surface/03-05-SUMMARY.md`
- FOUND commit: `91da46c` feat(03-05): create reusable ToastView shared component
- FOUND commit: `618655f` feat(03-05): wire ToastView into PredictionsView for background refresh failures

---
*Phase: 03-client-feature-surface*
*Completed: 2026-03-03*
