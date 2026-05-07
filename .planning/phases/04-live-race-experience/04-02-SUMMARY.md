---
phase: "04"
plan: "02"
subsystem: "ios-live-activity"
tags: [ios, activitykit, dynamic-island, live-activity, swift]
dependency_graph:
  requires: ["04-01"]
  provides: ["dynamic-island-lifecycle"]
  affects: ["ios/F1AI/Views/Tabs/LiveTab.swift"]
tech_stack:
  added: ["ActivityKit"]
  patterns: ["@Observable service", "onChange lifecycle wiring", "UserDefaults-driven tracked driver"]
key_files:
  created:
    - ios/F1AI/Services/LiveActivityService.swift
  modified:
    - ios/F1AI/Views/Tabs/LiveTab.swift
    - ios/F1AI.xcodeproj/project.pbxproj
decisions:
  - "ActivityKit import kept in LiveActivityService only — LiveTab uses it only for the @State property type, avoiding widget-target import confusion"
  - "Tracked driver re-read from UserDefaults on every update() call so mid-session favorite changes propagate without restart"
  - "staleDate set to +30s on start/update so iOS grays the Dynamic Island if the app backgrounds and data stops"
metrics:
  duration: "2min"
  completed: "2026-03-08"
  tasks_completed: 2
  files_changed: 3
---

# Phase 4 Plan 02: Live Activity Lifecycle Manager (iOS) Summary

**One-liner:** `@Observable LiveActivityService` managing `Activity<RaceLiveActivityAttributes>` start/update/end, wired into LiveTab via onChange observers for positions and session status.

## What Was Built

Created `LiveActivityService.swift` — an `@Observable` service that owns the `Activity<RaceLiveActivityAttributes>` handle and exposes three async-safe methods: `startActivity`, `update`, and `endActivity`. Wired this service into `LiveTab.swift` so the Dynamic Island lifecycle is fully driven by WebSocket data events.

### LiveActivityService

- Guards on `ActivityAuthorizationInfo().areActivitiesEnabled` before requesting
- Guards on `currentActivity == nil` to prevent double-starting
- `resolveTrackedDriver` reads `UserDefaults.standard.string(forKey: "favoriteDriver")` on every call — covers both start and update so mid-session favorite changes take effect immediately on the next WebSocket push
- `buildContentState` is a pure helper — shared by all three lifecycle methods
- `staleDate: Date().addingTimeInterval(30)` on start and update — iOS grays the island display if data stops flowing (app backgrounded)
- `endActivity` uses `ActivityUIDismissalPolicy.after(30 * 60)` so the island stays visible 30 minutes post-session then auto-dismisses

### LiveTab Wiring

- `import ActivityKit` added at the top
- `@State private var liveActivityService = LiveActivityService()` added as view-owned state
- `onChange(of: vm.positions)`: on first non-empty positions array → `startActivity`; on subsequent changes → `Task { await update(...) }`
- `onChange(of: vm.sessionStatus?.status)`: ends activity when status transitions to "finished" or "ended"
- `onDisappear`: calls `endActivity` alongside `vm.disconnect()` so the island ends cleanly when user navigates away

## Deviations from Plan

### Context discovered during execution

**Plan 04-04 had already modified LiveTab.swift** before this plan ran (the file had `commentaryEntries`, `selectedSegment`, `CommentaryFeedView`, and `hasNewCommentary` — none of which were in the plan's reference copy). The integration was adapted to slot correctly alongside those additions without conflict. All onChange modifiers were added inside the same `liveContent()` function body at the correct level.

This is not a deviation from 04-02 — it reflects out-of-order plan execution. No auto-fix rules triggered.

## Self-Check: PASSED

- ios/F1AI/Services/LiveActivityService.swift: FOUND
- Commit ab903f5 (Task 1): FOUND
- Commit 89e5e0f (Task 2): FOUND
