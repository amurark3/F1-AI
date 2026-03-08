---
phase: 04-live-race-experience
verified: 2026-03-08T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 4: Live Race Experience Verification Report

**Phase Goal:** During active sessions, users get live position tracking on Dynamic Island and AI-generated commentary that explains what is happening in real time
**Verified:** 2026-03-08
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dynamic Island compact view shows selected driver position, gap to leader, and current lap during an active session | VERIFIED | `RaceLiveActivity.swift` compact trailing renders `"P\(trackedPosition) L\(currentLap)"` from `ContentState`; `LiveActivityService.swift` populates `trackedGap`, `trackedPosition`, `currentLap` from live positions + sessionStatus |
| 2 | Dynamic Island expanded view shows full timing data and updates in real-time from WebSocket feed | VERIFIED | Expanded leading renders position + driver name, trailing renders `LAP N/M` + gap, bottom renders session status with color; `LiveTab.swift` calls `liveActivityService.update()` on every `onChange(of: vm.positions)` triggered by WebSocket |
| 3 | When a significant event occurs AI commentary appears within 30 seconds explaining the context | VERIFIED | `routes.py` `_detect_event()` detects position change, safety car, pit stop; `_generate_commentary()` calls Gemini via `asyncio.to_thread`; result sent as `{"type":"commentary"}` WebSocket message; iOS and web both handle this message type |
| 4 | AI commentary does not fire more than once every 30 seconds regardless of event frequency | VERIFIED | `routes.py` guards with `if now_ts - state["last_time"] >= COMMENTARY_COOLDOWN_SECONDS` before calling `_detect_event`; state is per-room dict `_commentary_state`; `state["last_time"]` updated immediately after broadcast |
| 5 | Commentary panel is visible in both iOS and web UIs as a dedicated section during live sessions | VERIFIED | iOS: `CommentaryFeedView.swift` rendered by `LiveTab.swift` in the "Commentary" segment of a segmented picker with badge dot; Web: `CommentaryPanel.tsx` rendered in `/live/page.tsx` in a `lg:w-80` sidebar column |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `ios/F1AIWidgets/RaceLiveActivity.swift` | Dynamic Island compact + expanded + lock screen views | VERIFIED | 95 lines; `RaceLiveActivityAttributes` with all `ContentState` fields; `DynamicIsland` closure with all 4 regions; registered in `F1AIWidgets` bundle |
| `ios/F1AI/Services/LiveActivityService.swift` | Activity start/update/end lifecycle | VERIFIED | 74 lines; `@Observable`; `startActivity`, `update`, `endActivity` methods; reads `UserDefaults("favoriteDriver")`; `ActivityAuthorizationInfo` guard |
| `ios/F1AI/Views/Tabs/LiveTab.swift` | Wires LiveActivityService + commentary picker | VERIFIED | 201 lines; `@State private var liveActivityService = LiveActivityService()`; `onChange(of: vm.positions)` starts/updates activity; `onChange(of: vm.sessionStatus?.status)` ends activity on "finished"/"ended"; segmented picker with `CommentaryFeedView` |
| `ios/F1AI/Views/Live/CommentaryFeedView.swift` | iOS commentary feed UI | VERIFIED | 68 lines; event-type icons (SF Symbols), time formatting, empty state, `LazyVStack` with `ForEach`; non-stub |
| `ios/F1AI/Models/LiveTiming.swift` (CommentaryEntry) | Data model for commentary entries | VERIFIED | `CommentaryEntry` struct with `CodingKeys` mapping `event_type` snake case |
| `ios/F1AI/Services/LiveTimingService.swift` (commentary) | WebSocket message branching for commentary | VERIFIED | Two-step decode: `JSONSerialization` reads `type`, branches to `CommentaryEntry` decode if `"commentary"`, prepends to `commentaryEntries` array |
| `ios/F1AI/ViewModels/LiveTimingViewModel.swift` | Exposes `commentaryEntries` | VERIFIED | `var commentaryEntries: [CommentaryEntry] { service.commentaryEntries }` |
| `ios/F1AI/Views/Settings/NotificationSettingsView.swift` | Favorite driver setting | VERIFIED | `@AppStorage("favoriteDriver")` + `TextField` in "Live Race Tracking" section |
| `backend/app/api/routes.py` (commentary engine) | Event detection, Gemini call, 30s rate limit, broadcast | VERIFIED | `_commentary_state`, `COMMENTARY_COOLDOWN_SECONDS=30`, `_fetch_session_status`, `_fetch_stint_counts`, `_detect_event`, `_generate_commentary` all present and wired in `live_timing` handler |
| `backend/app/api/routes.py` (lap count) | `session_status` WebSocket message with lap/total_laps | VERIFIED | `_fetch_current_lap` fetches `/v1/laps`; `_find_openf1_session` refactored to return `tuple[str,int]`; `session_status` message sent after positions every poll cycle |
| `frontend/app/hooks/useLiveTiming.ts` | WebSocket hook for web | VERIFIED | 86 lines; handles `"positions"`, `"session_status"`, `"commentary"`, `"ping"`; commentary prepended with `.slice(0,100)` |
| `frontend/app/components/LiveTimingTower.tsx` | Web timing tower | VERIFIED | 99 lines; position table, session status pill with lap count, connected/loading states |
| `frontend/app/components/CommentaryPanel.tsx` | Web commentary sidebar | VERIFIED | 72 lines; `AnimatePresence` + `motion.div` animations; event-type icon/color map; empty state |
| `frontend/app/live/page.tsx` | Web live page | VERIFIED | Detects in-progress race via `/api/schedule/YYYY`; two-column layout `flex-col lg:flex-row`; `CommentaryPanel` at `lg:w-80` |
| `frontend/app/components/NavShell.tsx` | "Live" nav item | VERIFIED | `{ href: '/live', label: 'Live' }` present in `NAV_ITEMS` array |
| `ios/F1AI.xcodeproj/project.pbxproj` | Dual-target membership for RaceLiveActivity.swift | VERIFIED | Two distinct `PBXBuildFile` entries (`7652D92F...` and `BE36DA7E...`) both referencing `RaceLiveActivity.swift` |
| `ios/project.yml` | `NSSupportsLiveActivities` capability | VERIFIED | `INFOPLIST_KEY_NSSupportsLiveActivities: YES` and `INFOPLIST_KEY_NSSupportsLiveActivitiesFrequentUpdates: YES` under `targets.F1AI.settings.base`; also reflected in `project.pbxproj` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `LiveTab.swift` | `LiveActivityService` | `@State private var liveActivityService` + `onChange(of: vm.positions)` | WIRED | `startActivity`/`update`/`endActivity` all called correctly |
| `LiveTab.swift` | `CommentaryFeedView` | `case .commentary:` branch | WIRED | `CommentaryFeedView(entries: vm.commentaryEntries)` |
| `LiveTimingService.swift` | `commentaryEntries` | `handleMessage` two-step decode | WIRED | Branches on `type == "commentary"`, decodes `CommentaryEntry`, prepends to `self.commentaryEntries` |
| `LiveTimingViewModel.swift` | `LiveTimingService.commentaryEntries` | Computed property | WIRED | `var commentaryEntries: [CommentaryEntry] { service.commentaryEntries }` |
| `LiveActivityService.swift` | `SessionStatus.lap/totalLaps` | `buildContentState(tracked:sessionStatus:)` | WIRED | Reads `sessionStatus?.lap ?? 0` and `sessionStatus?.totalLaps ?? 0` into `ContentState` |
| `routes.py live_timing` | Commentary engine | After positions send, inside `while True` | WIRED | `_detect_event` + `_generate_commentary` + `send_json` all inside the positions-available branch |
| `routes.py` | Session status broadcast | After positions send | WIRED | `send_json({"type":"session_status","data":{...}})` sent every poll cycle when positions are available |
| `useLiveTiming.ts` | `CommentaryPanel.tsx` | Props via `page.tsx` | WIRED | `commentary` state passed as `entries` prop to `CommentaryPanel` |
| `useLiveTiming.ts` | `LiveTimingTower.tsx` | Props via `page.tsx` | WIRED | `positions`, `sessionStatus`, `isConnected` passed as props |
| `RaceLiveActivityView` | `F1AIWidgets` bundle | `NextRaceWidget.swift` body | WIRED | `RaceLiveActivityView()` added after `NextRaceWidget()` in bundle body |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| LIVE-01 | 04-01, 04-02, 04-03, 04-07 | Dynamic Island shows current driver position, gap to leader, current lap, and safety car status during active sessions | SATISFIED | `RaceLiveActivity.swift` compact trailing: `"P\(trackedPosition) L\(currentLap)"`; expanded trailing: gap; expanded bottom: session status; `LiveActivityService` populates all fields from WebSocket data; lap data now sent via `session_status` messages (04-07) |
| LIVE-02 | 04-01, 04-02, 04-07 | Dynamic Island compact and expanded views update in real-time from existing WebSocket timing data | SATISFIED | `LiveTab.swift` `onChange(of: vm.positions)` calls `liveActivityService.update()` on every WebSocket position message; `session_status` messages update lap info |
| LIVE-03 | 04-04, 04-05 | AI commentary generates contextual insights when significant timing events occur | SATISFIED | `_detect_event` detects position changes, safety car, pit stops; `_generate_commentary` calls Gemini; iOS `CommentaryFeedView` and web `CommentaryPanel` both display entries |
| LIVE-04 | 04-04 | AI commentary is rate-limited (30-second cooldown) | SATISFIED | `COMMENTARY_COOLDOWN_SECONDS = 30`; `if now_ts - state["last_time"] >= COMMENTARY_COOLDOWN_SECONDS` guard; `state["last_time"] = time.time()` set after broadcast |
| LIVE-05 | 04-05, 04-06 | AI commentary appears in both iOS and web UIs as a dedicated commentary panel | SATISFIED | iOS: segmented "Timing"/"Commentary" picker in `LiveTab.swift` with badge dot; Web: `CommentaryPanel` in right sidebar of `/live` page |

All 5 requirements explicitly covered by plan tasks. No orphaned requirements.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/api/routes.py` | 1152 | `race_name = f"Round {round_num} {year}"` — static fallback, never resolved to actual race name | Info | Commentary prompts use generic race name instead of e.g. "Bahrain Grand Prix"; Gemini output still valid |
| `backend/app/api/routes.py` | 1205 | Rate limit check happens BEFORE event detection, not after — a 31-second window where an event fires at second 1 produces commentary, but if cooldown resets to 0 at second 1, the NEXT event window starts at second 31 (correct behavior) | Info | No functional issue, just worth noting the semantic |

No blocker anti-patterns found. No TODO/FIXME/placeholder stubs. No empty implementations (return null/return {}).

---

### Human Verification Required

#### 1. Dynamic Island Renders During Simulator Live Session

**Test:** Run the iOS app in simulator with a simulated live session (mock WebSocket sending position data). Observe that the Dynamic Island compact view appears and shows driver abbreviation + position + lap.
**Expected:** Compact leading shows 3-letter driver abbreviation; compact trailing shows "P{N} L{lap}".
**Why human:** ActivityKit Live Activities cannot be inspected programmatically without a running app on device/simulator.

#### 2. Commentary Fires Within 30 Seconds of Event

**Test:** Connect a WebSocket client to `ws://localhost:8000/api/live/{year}/{round}` during a live session. Observe that after a position change between two poll cycles, a `{"type":"commentary"}` message arrives within the next poll cycle (8 seconds max).
**Expected:** Commentary message appears; a second event within 30 seconds produces no second message; after 30 seconds a new event produces a new message.
**Why human:** Requires a live or simulated OpenF1 session to generate actual position change snapshots.

#### 3. iOS Badge Dot Behavior

**Test:** Open the Live tab during an active session. Stay on "Timing" segment. Wait for a commentary event. Verify the "Commentary" segment label shows a dot indicator. Tap "Commentary" to verify the dot clears.
**Expected:** Badge dot appears on "Commentary" segment tab when new commentary arrives while user is on "Timing" segment. Dot disappears on tap.
**Why human:** State-driven UI behavior requires runtime observation.

#### 4. Web Two-Column Layout

**Test:** Open `/live` in a browser at `lg:` breakpoint (1024px+) during a live session. Verify timing tower is on the left and commentary panel is on the right.
**Expected:** Two-column flex layout; timing `flex-1`, commentary `w-80`. On mobile, they stack vertically.
**Why human:** CSS layout verification requires browser rendering.

---

### Gaps Summary

No gaps found. All 5 success criteria are verifiably implemented:

- The Dynamic Island declaration (`RaceLiveActivity.swift`) is substantive with all required fields and views, registered in both the widget bundle and both Xcode targets.
- The lifecycle service (`LiveActivityService.swift`) correctly starts on first position data, updates on every WebSocket message, and ends on session completion or tab dismissal.
- The backend commentary engine is fully wired into the `live_timing` WebSocket handler with event detection, Gemini generation, 30-second rate limiting, and fallback templates.
- The lap count integration (`_fetch_current_lap`, `_find_openf1_session` tuple refactor, `session_status` broadcast) is in place so the Dynamic Island compact view can show current lap.
- Both iOS (`CommentaryFeedView` in `LiveTab`) and web (`CommentaryPanel` in `/live/page.tsx`) have dedicated commentary UI sections that receive and display entries from the same WebSocket feed.

---

_Verified: 2026-03-08_
_Verifier: Claude (gsd-verifier)_
