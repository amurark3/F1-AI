---
phase: 04-live-race-experience
plan: "05"
subsystem: ui
tags: [swift, swiftui, websocket, observable, commentary, live-timing]

# Dependency graph
requires:
  - phase: 04-04
    provides: Backend commentary engine emitting {"type":"commentary","data":{...}} WebSocket messages

provides:
  - CommentaryEntry model (Codable/Identifiable/Hashable) in LiveTiming.swift
  - Two-step WebSocket decode branching on type field before LiveTimingData enum
  - commentaryEntries array on LiveTimingService and LiveTimingViewModel
  - CommentaryFeedView with event-type icons, ISO time formatting, and empty state
  - Timing/Commentary segmented picker in LiveTab with badge dot on new commentary

affects:
  - 04-06 (any further live race UI work)
  - 04-07 (live session integration)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Two-step WebSocket message decode (JSONSerialization for type, then JSONDecoder for payload)
    - Prepend-with-cap pattern for capped scrollback lists (prefix(100).map)
    - Badge dot on segmented picker using @State hasNewCommentary + .onChange(of:) + .onAppear clear

key-files:
  created:
    - ios/F1AI/Views/Live/CommentaryFeedView.swift
  modified:
    - ios/F1AI/Models/LiveTiming.swift
    - ios/F1AI/Services/LiveTimingService.swift
    - ios/F1AI/ViewModels/LiveTimingViewModel.swift
    - ios/F1AI/Views/Tabs/LiveTab.swift
    - ios/F1AI.xcodeproj/project.pbxproj

key-decisions:
  - "Commentary decoded via two-step approach (JSONSerialization then JSONDecoder) to avoid touching the brittle LiveTimingData singleValueContainer enum decoder"
  - "Commentary entries prepended (most recent first) and capped at 100 entries using prefix(100).map"
  - "Badge dot uses @State hasNewCommentary cleared on Commentary segment .onAppear — no auto-segment switch"

patterns-established:
  - "Two-step WebSocket decode: branch on raw type string before attempting typed decode"
  - "LiveTimingService stores all observable state; ViewModel exposes computed properties only"

requirements-completed:
  - LIVE-03
  - LIVE-05

# Metrics
duration: 3min
completed: 2026-03-08
---

# Phase 4 Plan 05: iOS Commentary UI Summary

**CommentaryFeedView with event-type SF Symbol icons added to LiveTab behind a Timing/Commentary segmented picker, with badge dot notification driven by two-step WebSocket decode branching on message type**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-08T23:17:42Z
- **Completed:** 2026-03-08T23:20:05Z
- **Tasks:** 5 (Steps 1-5 in plan)
- **Files modified:** 6

## Accomplishments
- Added `CommentaryEntry` (Codable, Identifiable, Hashable) to LiveTiming.swift without touching the existing LiveTimingData enum decoder
- Refactored `handleMessage()` to decode `type` via JSONSerialization first, branching commentary messages before the LiveTimingMessage decode path
- Created `CommentaryFeedView.swift` with SF Symbol icons per event type, ISO 8601 time formatting, empty state, and LazyVStack feed
- Added `Timing`/`Commentary` segmented picker to `LiveTab` with badge dot that appears when commentary arrives while user is on Timing segment and clears on Commentary tab `.onAppear`
- Registered `CommentaryFeedView.swift` in `project.pbxproj` across all four required sections (PBXBuildFile, PBXFileReference, PBXGroup, PBXSourcesBuildPhase)

## Task Commits

All steps committed together atomically (all changes were interdependent; no intermediate compilable state existed between steps):

1. **Steps 1-5: CommentaryEntry model, service decode, VM exposure, CommentaryFeedView, LiveTab picker** - `aab3624` (feat)

## Files Created/Modified
- `/ios/F1AI/Views/Live/CommentaryFeedView.swift` - New scrollable feed with event icons, time formatting, and empty state
- `/ios/F1AI/Models/LiveTiming.swift` - Added CommentaryEntry struct
- `/ios/F1AI/Services/LiveTimingService.swift` - Added commentaryEntries property; two-step handleMessage() decode
- `/ios/F1AI/ViewModels/LiveTimingViewModel.swift` - Exposed commentaryEntries computed property
- `/ios/F1AI/Views/Tabs/LiveTab.swift` - Segmented picker, badge dot, LiveSegment enum
- `/ios/F1AI.xcodeproj/project.pbxproj` - Registered CommentaryFeedView.swift

## Decisions Made
- Two-step WebSocket decode (JSONSerialization for type field, then JSONDecoder for payload) preserves the existing brittle singleValueContainer enum decoder without modification
- Entries prepended and capped at 100 using `([entry] + self.commentaryEntries).prefix(100).map { $0 }` — maintains most-recent-first order efficiently
- Badge dot uses `@State hasNewCommentary` cleared on `.onAppear` of Commentary tab — no auto-switch, visual only per CONTEXT.md spec

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- iOS commentary UI is complete; LiveTab now surfaces AI-generated commentary alongside the timing tower
- Backend commentary WebSocket messages (from 04-04) will populate the feed in live sessions
- Ready for 04-06 and 04-07 live session integration work

---
*Phase: 04-live-race-experience*
*Completed: 2026-03-08*

## Self-Check: PASSED

Files verified present:
- FOUND: ios/F1AI/Views/Live/CommentaryFeedView.swift
- FOUND: ios/F1AI/Models/LiveTiming.swift
- FOUND: ios/F1AI/Services/LiveTimingService.swift
- FOUND: ios/F1AI/ViewModels/LiveTimingViewModel.swift
- FOUND: ios/F1AI/Views/Tabs/LiveTab.swift

Commits verified:
- FOUND: aab3624 feat(04-05): iOS commentary UI with segmented picker and badge dot
