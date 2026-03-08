---
phase: 04-live-race-experience
plan: "07"
subsystem: api
tags: [websocket, openf1, live-timing, dynamic-island, swift]

# Dependency graph
requires:
  - phase: 04-02
    provides: LiveActivityService with ContentState lap/totalLaps fields and SessionStatus Swift model

provides:
  - Backend broadcasts {"type": "session_status"} WebSocket messages with current lap and total laps
  - _fetch_current_lap() helper fetching max(lap_number) from OpenF1 /v1/laps
  - _find_openf1_session() now returns (session_key, total_laps) tuple
  - Lap number cache (last_known_lap) survives transient /v1/laps failures

affects:
  - phase-05-apns-notifications

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lap cache pattern: last_known_lap variable persists last good value across failed fetches"
    - "Tuple return from OpenF1 session lookup bundles session_key + total_laps in one call"

key-files:
  created: []
  modified:
    - backend/app/api/routes.py

key-decisions:
  - "_find_openf1_session returns tuple[str, int] | None so session_key and total_laps are fetched atomically in one API call"
  - "lap cache (last_known_lap) preserves last good lap count across failed /v1/laps fetches rather than broadcasting null each cycle"
  - "session_status sent after positions so iOS receives positions first (triggering activity start) then lap update follows"
  - "total_laps field uses or-chain across three possible OpenF1 field names (total_laps, laps, number_of_laps) for resilience"

patterns-established:
  - "Graceful degradation: null sent for lap/total_laps when data unavailable — no crash, no silent drop"

requirements-completed:
  - LIVE-01
  - LIVE-02

# Metrics
duration: 5min
completed: 2026-03-08
---

# Phase 4 Plan 7: Lap Count Integration Summary

**Backend WebSocket now broadcasts `session_status` messages with live lap number (max across /v1/laps entries) and total laps (from /v1/sessions), surfacing "L34/57" in Dynamic Island via existing iOS SessionStatus model**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-08T00:00:00Z
- **Completed:** 2026-03-08T00:05:00Z
- **Tasks:** 1 (all 4 implementation steps in one atomic commit)
- **Files modified:** 1

## Accomplishments
- Refactored `_find_openf1_session()` to return `tuple[str, int] | None` bundling session_key and total_laps
- Added `_fetch_current_lap()` async helper fetching `max(lap_number)` from OpenF1 `/v1/laps`
- Added `last_known_lap` cache in the poll loop to survive transient failures
- Backend now broadcasts `{"type": "session_status", "data": {"status": "started", "lap": N, "total_laps": M}}` after each positions push

## Task Commits

Each task was committed atomically:

1. **All implementation steps** - `3dbf736` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `/Users/adityamurarka/Desktop/F1-AI/backend/app/api/routes.py` - Added `_fetch_current_lap()`, refactored `_find_openf1_session()` return type, updated `live_timing()` to unpack tuple and broadcast session_status

## Decisions Made
- `_find_openf1_session` returns tuple so session_key and total_laps are fetched in a single API round-trip
- `last_known_lap` cache variable preserves last good value across /v1/laps failures — better than broadcasting null every cycle
- session_status message sent AFTER positions so iOS ActivityKit starts from position data first, then updates lap on next observation
- `total_laps` field uses an or-chain across three possible OpenF1 field names (`total_laps`, `laps`, `number_of_laps`) for field-name uncertainty resilience

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 4 is now complete. All 7 plans executed.
- Phase 5 (APNs push notifications) can begin — requires Apple Developer account with p8 auth key.
- Dynamic Island lap display will work once a live race session is active (OpenF1 returns data only during live sessions).

---
*Phase: 04-live-race-experience*
*Completed: 2026-03-08*
