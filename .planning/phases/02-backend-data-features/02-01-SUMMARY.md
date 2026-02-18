---
phase: 02-backend-data-features
plan: 01
subsystem: data
tags: [fastf1, predictions, heuristic-scoring, json-persistence, threading]

# Dependency graph
requires:
  - phase: 01-infrastructure-hardening
    provides: structlog logging, config.py os.getenv pattern, FastF1 thread safety pattern
provides:
  - compute_race_predictions() function for all 20 drivers with confidence ranges
  - save_prediction() and get_accuracy_stats() for prediction accuracy tracking
  - Scoring weight constants in config.py
  - Pre-qualifying fallback using practice session data
  - backend/app/data/ module structure for strategy and weather modules
affects: [02-02, 02-03, 02-04, 02-05, 03-backend-chat-tools, 04-ios-web-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [weighted-heuristic-scoring, json-file-persistence, proportional-weight-adjustment, atomic-file-write]

key-files:
  created:
    - backend/app/data/__init__.py
    - backend/app/data/predictions.py
  modified:
    - backend/app/config.py

key-decisions:
  - "Prediction scoring uses 5 weighted factors summing to 1.0 with proportional rebalancing when data sources are missing"
  - "Confidence ranges computed from standard deviation of input signals -- low variance = tighter confidence"
  - "Accuracy history stored as JSON file with atomic write-to-temp-then-rename pattern"
  - "Pre-qualifying fallback treats practice data as weak signal (0.10 weight) with 15pp confidence widening"

patterns-established:
  - "Data module pattern: pure computation in app/data/, thin wrappers in tools.py and routes.py"
  - "Proportional weight adjustment: when data sources are missing, remaining weights are normalized to sum to 1.0"
  - "Atomic JSON persistence: write to .tmp then rename for corruption safety"

requirements-completed: [DATA-01]

# Metrics
duration: 20min
completed: 2026-02-18
---

# Phase 2 Plan 1: Race Prediction Engine Summary

**Weighted heuristic scoring model combining qualifying, recent form, circuit history, team strength, and grid delta with confidence ranges and JSON-backed accuracy tracking**

## Performance

- **Duration:** 20 min (wall clock inflated by rate limit pause)
- **Started:** 2026-02-18T08:32:59Z
- **Completed:** 2026-02-18T14:53:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Race prediction engine computes weighted scores for all drivers using 5 data signals with proportional rebalancing when sources are unavailable
- Pre-qualifying fallback path detects missing qualifying and uses practice session pace with wider confidence ranges
- Accuracy tracker persists predictions to JSON, loads actual results from FastF1, and computes rolling top-3/top-10/avg-error metrics
- All FastF1 session loads use thread-safe _fastf1_lock; aggressive in-memory caching across 6 different cache dicts

## Task Commits

Each task was committed atomically:

1. **Task 1: Create prediction scoring engine with heuristic model** - `5af2758` (feat)
2. **Task 2: Add prediction accuracy tracker with JSON persistence** - `af7c4e9` (feat)

## Files Created/Modified
- `backend/app/data/__init__.py` - Data module package init with module docstring
- `backend/app/data/predictions.py` - Race prediction engine (compute_race_predictions, save_prediction, get_accuracy_stats, record_actual_result) with caching, thread safety, and factor generation
- `backend/app/config.py` - Added 8 new constants: QUALIFYING_WEIGHT, RECENT_FORM_WEIGHT, CIRCUIT_HISTORY_WEIGHT, TEAM_STRENGTH_WEIGHT, GRID_TO_FINISH_WEIGHT, OPENWEATHERMAP_API_KEY, WEATHER_CACHE_TTL, PREDICTION_HISTORY_PATH

## Decisions Made
- Scoring weights are normalized proportionally when data sources are missing (e.g., if no circuit history, remaining 4 weights are rescaled to sum to 1.0) rather than leaving gaps
- Confidence ranges use standard deviation of input signals rather than fixed tiers -- when signals agree (low stdev), range is ~80-95%; when they conflict (high stdev), range drops to ~35-55%
- Practice data gets only 0.10 weight in pre-qualifying mode (per RESEARCH.md recommendation) with an additional 15 percentage point confidence widening
- JSON persistence uses write-to-temp-then-rename for POSIX atomicity rather than file locks alone
- Lazy backfill: get_accuracy_stats() automatically attempts to record_actual_result() for races missing actual data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Prediction engine ready for LangChain tool wrapper (Plan 02-04) and REST endpoint (Plan 02-05)
- backend/app/data/ module structure ready for strategy.py (Plan 02-02) and weather.py (Plan 02-03)
- Config.py already includes OPENWEATHERMAP_API_KEY and WEATHER_CACHE_TTL for Plan 02-03

## Self-Check: PASSED

All files verified present. Both task commits (5af2758, af7c4e9) confirmed in git log.

---
*Phase: 02-backend-data-features*
*Completed: 2026-02-18*
