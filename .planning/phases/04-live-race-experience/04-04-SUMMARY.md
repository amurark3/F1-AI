---
phase: 04-live-race-experience
plan: "04"
subsystem: api
tags: [websocket, gemini, openf1, commentary, live-timing, asyncio]

# Dependency graph
requires:
  - phase: 04-live-race-experience
    provides: WebSocket live_timing handler in routes.py, OpenF1 polling infrastructure, llm instance
provides:
  - Per-room commentary state with 30-second cooldown guard
  - _fetch_session_status() polling OpenF1 /v1/race_control for safety car / flag events
  - _fetch_stint_counts() polling OpenF1 /v1/stints for pit stop detection
  - _detect_event() priority-ordered event comparator (safety car > position change > pit stop)
  - _generate_commentary() Gemini-backed commentary with template fallback
  - {"type": "commentary"} WebSocket messages broadcast alongside {"type": "positions"} messages
affects: [04-live-race-experience, ios-live-timing, web-live-timing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - asyncio.gather for parallel auxiliary OpenF1 polls within the WebSocket event loop
    - asyncio.to_thread wrapping synchronous llm.invoke to avoid blocking event loop
    - Module-level dict keyed by room string for per-room state (commentary cooldown + prev snapshots)
    - First-snapshot skip pattern to avoid false positives on initial connection

key-files:
  created: []
  modified:
    - backend/app/api/routes.py

key-decisions:
  - "Commentary state keyed by room string (year-round) at module level — shared across connections so 30s cooldown applies per room, not per client"
  - "First snapshot stored and skipped for detection to prevent every driver on initial connect from firing as a position change"
  - "asyncio.to_thread for llm.invoke — Gemini call is synchronous and would block WebSocket updates for all clients"
  - "Template fallback strings used on any Gemini error rather than blocking or retrying"
  - "Event priority: safety car / red flag first, then position change, then pit stop — only one event per 30s window"

patterns-established:
  - "asyncio.gather pattern: parallel auxiliary OpenF1 polls within async handler for minimal latency overhead"
  - "Cooldown guard pattern: compare time.time() against state['last_time'] before detection"

requirements-completed:
  - LIVE-03
  - LIVE-04

# Metrics
duration: 1min
completed: 2026-03-08
---

# Phase 4 Plan 04: Backend Commentary Engine Summary

**Gemini-backed AI commentary engine integrated into the WebSocket live_timing handler, detecting position changes, safety car events, and pit stops with a 30-second per-room cooldown, broadcasting `{"type": "commentary"}` messages alongside existing `{"type": "positions"}` messages**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-08T23:13:53Z
- **Completed:** 2026-03-08T23:15:52Z
- **Tasks:** 1 (5 implementation steps as single atomic change)
- **Files modified:** 1

## Accomplishments
- Added `_commentary_state` module-level dict and `COMMENTARY_COOLDOWN_SECONDS = 30` constant
- Added four helper functions: `_fetch_session_status`, `_fetch_stint_counts`, `_detect_event`, `_generate_commentary`
- Wired commentary detection into `live_timing` WebSocket loop after positions broadcast
- Parallel auxiliary polls via `asyncio.gather` minimize latency overhead per poll cycle
- Gemini commentary call wrapped in `asyncio.to_thread`; template fallback on any LLM error

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend commentary engine (all 5 steps)** - `5fd39ce` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `/Users/adityamurarka/Desktop/F1-AI/backend/app/api/routes.py` - Added commentary state, 4 helper functions, commentary detection wired into live_timing loop (+209 lines)

## Decisions Made
- Commentary state keyed by room string at module level — shared across connections so 30-second cooldown applies per room (whichever connection polls first sets `last_time`)
- First snapshot skip: store initial positions/status/stints but skip detection to prevent false positive "every driver changed position" on first connect
- `asyncio.to_thread` for `llm.invoke` — Gemini call is synchronous; wrapping avoids blocking the WebSocket event loop for all connected clients
- Template fallback strings on any LLM error (no blocking, no retries)
- Event priority order: safety car / red flag > position change > pit stop — only one event fires per 30-second window

## Deviations from Plan

None - plan executed exactly as written. All helper functions and wiring follow the plan's implementation steps verbatim.

## Issues Encountered
None - Python 3.10 pyenv version mismatch prevented using `python` directly, used `python3` for syntax check. No impact on implementation.

## Self-Check: PASSED
- FOUND: `/Users/adityamurarka/Desktop/F1-AI/backend/app/api/routes.py`
- FOUND: commit 5fd39ce

## Next Phase Readiness
- Commentary engine complete; both iOS and web clients will receive `{"type": "commentary", "data": {...}}` messages automatically
- Ready for 04-05 (iOS live race tab consuming commentary messages) and 04-06 (web live race dashboard)
- No blockers

---
*Phase: 04-live-race-experience*
*Completed: 2026-03-08*
