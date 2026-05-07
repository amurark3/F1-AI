---
phase: 03-client-feature-surface
plan: 04
subsystem: ui
tags: [swift, swiftui, notifications, usernotifications, userdefaults, appstorage]

# Dependency graph
requires:
  - phase: 03-client-feature-surface
    provides: "CalendarTab with race schedule and RaceEvent model with sessions dict"
provides:
  - "NotificationService.scheduleSessionReminders() scheduling all 7 F1 session types"
  - "UserDefaults extensions for notification settings persistence"
  - "NotificationSettingsView sheet with per-session toggles and advance time picker"
  - "CalendarTab gear icon opening notification settings"
  - "Notification permission request on CalendarTab first load"
affects: [03-client-feature-surface]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UserDefaults extension properties for structured settings storage"
    - "AppStorage for single-value UserDefaults bindings in SwiftUI"
    - "Prefix-based pending notification cleanup before rescheduling"
    - "Inline Binding set closures for immediate UserDefaults persistence"

key-files:
  created:
    - ios/F1AI/Views/Settings/NotificationSettingsView.swift
  modified:
    - ios/F1AI/Services/NotificationService.swift
    - ios/F1AI/Views/Tabs/CalendarTab.swift

key-decisions:
  - "Notification body format locked to '[Race Name] [Session] starts in N minutes' — no emoji, no round number prefix"
  - "Advance time identifier appended to notification ID (e.g. race-1-Practice 1-15) so changing advance time auto-clears via prefix-based cleanup"
  - "enabledNotificationSessions defaults to all 7 session keys when key absent from UserDefaults"
  - "notificationAdvanceMinutes validates against [5, 15, 30], returns 15 on corrupt/absent value"
  - "scheduleRaceReminders() kept as backward compatibility shim delegating to scheduleSessionReminders()"
  - "Permission request in CalendarTab .task modifier fires only when status is .notDetermined (no repeat prompts)"

patterns-established:
  - "Notification scheduling: prefix-based async cleanup then schedule inside getPendingNotificationRequests callback"
  - "Settings persistence: @AppStorage for scalar values, Binding set closure for Set<String> stored as [String] array"

requirements-completed: [CLIENT-03]

# Metrics
duration: 2min
completed: 2026-03-01
---

# Phase 3 Plan 04: Notification Expansion Summary

**UNUserNotifications expanded from Race-only to all 7 session types with per-session toggles, configurable advance time (5/15/30 min), and a settings sheet accessible via gear icon in CalendarTab**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-01T04:42:27Z
- **Completed:** 2026-03-01T04:44:07Z
- **Tasks:** 2
- **Files modified:** 3 (1 rewritten, 1 created, 1 updated)

## Accomplishments
- Rewrote NotificationService to schedule notifications for all 7 session types (FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, Race) with configurable advance time
- Created NotificationSettingsView with inline advance-time Picker and per-session Toggle controls, settings persisting across launches
- Updated CalendarTab with gear icon opening settings sheet and automatic permission request on first load

## Task Commits

Each task was committed atomically:

1. **Task 1: Expand NotificationService to all session types** - `46cc7ce` (feat)
2. **Task 2: Create NotificationSettingsView and update CalendarTab** - `b89f9f6` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `ios/F1AI/Services/NotificationService.swift` - Rewritten: scheduleSessionReminders(), rescheduleAll(), sessionDisplayNames dict, allSessionKeys, UserDefaults extensions for enabled sessions and advance minutes, backward compat shim
- `ios/F1AI/Views/Settings/NotificationSettingsView.swift` - New: advance time Picker (5/15/30 min), 7 per-session Toggle rows, permission denied warning
- `ios/F1AI/Views/Tabs/CalendarTab.swift` - Updated: @State showingSettings, gear toolbar button, sheet presentation, permission request in .task

## Decisions Made
- Notification body format: "[Race Name] [Session] starts in N minutes" — no emoji, no round number prefix (per must_haves in plan)
- Advance time appended to notification identifier so changing settings generates fresh IDs; prefix-based cleanup removes all stale notifications before rescheduling
- enabledNotificationSessions defaults to all 7 keys on first install (opt-out model, not opt-in)
- notificationAdvanceMinutes validates against [5, 15, 30] and returns 15 if value is corrupt or absent
- Permission request fires only when authorization status is `.notDetermined` — no repeat system prompts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — Settings directory (`ios/F1AI/Views/Settings/`) did not exist and was created as part of Task 2 (Rule 3 handled silently: missing directory is a blocking issue for file creation).

## User Setup Required
None - no external service configuration required. Notification permission is requested automatically on CalendarTab first load.

## Next Phase Readiness
- CLIENT-03 satisfied: all 7 session types schedule notifications by default
- NotificationService.rescheduleAll(for:) available for future use when schedule refreshes (e.g., after pull-to-refresh in CalendarTab)
- Settings UI ready for expansion (e.g., per-race toggles, quiet hours) in a future plan

---
*Phase: 03-client-feature-surface*
*Completed: 2026-03-01*
