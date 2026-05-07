---
phase: 02-backend-data-features
plan: 03
subsystem: api
tags: [langchain, tools, fastapi, predictions, strategy, weather, rest-endpoint, caching]

# Dependency graph
requires:
  - phase: 02-01
    provides: "compute_race_predictions() function for prediction tool and REST endpoint"
  - phase: 02-02
    provides: "analyze_pit_strategy() and get_weather_for_circuit() for strategy and weather tools"
provides:
  - "get_race_predictions LangChain tool with race-engineer briefing format"
  - "get_pit_strategy LangChain tool with stint tables and undercut/overcut"
  - "get_weather_conditions LangChain tool with real weather data"
  - "GET /api/predictions/{year}/{round_num} REST endpoint with caching"
  - "Updated system prompt with prediction, strategy, weather capabilities"
affects: [03-ios-features, 04-ui-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tool wrapper pattern: thin @tool functions in tools.py wrapping data modules in app/data/"
    - "Async-to-sync bridge: asyncio.run() in new event loop for async data modules called from sync tool context"
    - "REST cache invalidation: recompute predictions when qualifying data becomes available"

key-files:
  created: []
  modified:
    - "backend/app/api/tools.py"
    - "backend/app/api/routes.py"
    - "backend/app/api/prompts.py"

key-decisions:
  - "Weather tool uses asyncio.run() with RuntimeError fallback for event loop detection"
  - "Predictions REST endpoint caches until qualifying data becomes available, then recomputes"
  - "Chat predictions include rich race-engineer narrative; REST returns structured JSON (per CONTEXT.md locked decision)"
  - "Old get_track_conditions stub fully removed and replaced by get_weather_conditions"

patterns-established:
  - "Tool wrapper pattern: @tool in tools.py imports from app.data.* and formats output for chat"
  - "REST vs Chat differentiation: structured JSON for REST, narrative briefing for chat tools"

requirements-completed: [DATA-04, DATA-05]

# Metrics
duration: 5min
completed: 2026-02-18
---

# Phase 2 Plan 3: Tool Wiring and Predictions Endpoint Summary

**Three new LangChain tools (predictions, strategy, weather) wired to data modules, plus cached predictions REST endpoint**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-18T22:36:59Z
- **Completed:** 2026-02-18T22:42:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Wired prediction, strategy, and weather data modules as LangChain @tool functions callable by the agentic chat loop
- Replaced the old get_track_conditions stub with real weather data via get_weather_conditions
- Added GET /api/predictions/{year}/{round_num} REST endpoint with in-memory caching and qualifying-aware invalidation
- Updated system prompt to advertise prediction, strategy, and weather capabilities
- Chat predictions include rich race-engineer narrative with top-5 detailed analysis and 6-20 summary table

## Task Commits

Each task was committed atomically:

1. **Task 1: Add three LangChain tool wrappers and update system prompt** - `8e568c7` (feat)
2. **Task 2: Add predictions REST endpoint with caching** - `4495cec` (feat)

## Files Created/Modified
- `backend/app/api/tools.py` - Added get_race_predictions, get_pit_strategy, get_weather_conditions tools; removed get_track_conditions stub; updated TOOL_LIST (now 13 tools)
- `backend/app/api/routes.py` - Added GET /predictions/{year}/{round_num} endpoint with predictions_cache and _should_recompute_predictions() invalidation
- `backend/app/api/prompts.py` - Updated RACE_ENGINEER_PERSONA capabilities list with prediction, strategy, and weather

## Decisions Made
- Weather tool uses asyncio.run() with RuntimeError fallback for event loop detection, since LangChain tools are invoked via asyncio.to_thread() in a sync context
- Predictions REST endpoint returns structured JSON directly from compute_race_predictions(); chat tool adds narrative formatting on top
- Cache invalidation checks if qualifying data became available since last computation by attempting fastf1.get_session(year, round_num, "Q")

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 2 data modules are fully wired: predictions, strategy, and weather accessible via both chat tools and REST API
- 13 LangChain tools now available to the agentic loop
- iOS/web clients can consume predictions via GET /api/predictions/{year}/{round_num}
- Phase 3 (iOS features) can integrate the predictions endpoint

## Self-Check: PASSED

- [x] backend/app/api/tools.py exists
- [x] backend/app/api/routes.py exists
- [x] backend/app/api/prompts.py exists
- [x] Commit 8e568c7 exists (Task 1)
- [x] Commit 4495cec exists (Task 2)

---
*Phase: 02-backend-data-features*
*Completed: 2026-02-18*
