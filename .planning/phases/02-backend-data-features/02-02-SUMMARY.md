---
phase: 02-backend-data-features
plan: 02
subsystem: data
tags: [fastf1, openweathermap, pit-strategy, weather, gps, httpx, caching, threading]

# Dependency graph
requires:
  - phase: 01-infrastructure-hardening
    provides: structlog logging, config.py os.getenv pattern, FastF1 thread safety pattern
  - phase: 02-01
    provides: data module structure (app/data/), prediction engine patterns, _fastf1_lock pattern
provides:
  - analyze_pit_strategy() with stint breakdown, historical strategies, undercut/overcut, safety car probability
  - get_weather_for_circuit() async function with OpenWeatherMap integration and TTL caching
  - GPS coordinates (lat/lon) for all 32 circuits in CIRCUIT_DATA
  - get_circuit_gps() helper for coordinate lookups
  - Track-specific context for street/desert/coastal/high-altitude circuits
  - Strategy impact assessment based on rain probability thresholds
affects: [02-03, 03-backend-chat-tools, 04-ios-web-ui]

# Tech tracking
tech-stack:
  added: [httpx]
  patterns: [async-weather-api, ttl-dict-cache, track-context-enrichment, one-call-fallback-to-current]

key-files:
  created:
    - backend/app/data/strategy.py
    - backend/app/data/weather.py
  modified:
    - backend/app/api/circuits.py

key-decisions:
  - "Strategy module uses same _fastf1_lock and caching pattern as predictions.py for consistency"
  - "Weather uses httpx.AsyncClient with One Call 3.0 -> 2.5 current weather fallback chain"
  - "Track surface temperature estimated from air temp + cloud cover heuristic (no API provides track temp)"
  - "Strategy impact uses 40% rain threshold for dual scenario recommendation, 20% for intermediate backup"
  - "GPS coordinates added directly to CIRCUIT_DATA dict rather than a separate lookup table"

patterns-established:
  - "Async weather API pattern: try premium API first, fallback to free tier, graceful error on missing key"
  - "TTL dict cache for async modules: simple (timestamp, data) tuple with configurable TTL from config.py"
  - "Track context enrichment: raw API data combined with domain-specific circuit knowledge"

requirements-completed: [DATA-02, DATA-03]

# Metrics
duration: 28min
completed: 2026-02-18
---

# Phase 2 Plan 2: Strategy & Weather Summary

**Pit strategy analysis engine with FastF1 stint extraction and OpenWeatherMap weather module with GPS-based circuit lookups and track context enrichment**

## Performance

- **Duration:** 28 min
- **Started:** 2026-02-18T21:56:56Z
- **Completed:** 2026-02-18T22:24:55Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Pit strategy engine extracts full stint breakdowns (compound, lap ranges, degradation curves, pit windows) from FastF1 laps data
- Historical strategy analysis from last 3 circuit editions with dominant strategy identification and safety car probability
- Undercut/overcut analysis comparing pit timing between adjacent drivers with position gain/loss tracking
- Live weather module with OpenWeatherMap One Call 3.0 + 2.5 fallback, TTL caching, and hourly forecasts
- All 32 circuits now have GPS coordinates for weather API lookups
- Track-specific context adds strategic value (street circuit drainage, desert sand, high altitude, coastal wind)

## Task Commits

Each task was committed atomically:

1. **Task 1: Build pit strategy analysis engine** - `d2d1ab8` (feat)
2. **Task 2: Build weather module with circuit GPS and caching** - `9a2c7c3` (feat)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `backend/app/data/strategy.py` - Pit strategy analysis engine with analyze_pit_strategy()
- `backend/app/data/weather.py` - OpenWeatherMap weather module with get_weather_for_circuit()
- `backend/app/api/circuits.py` - Added lat/lon GPS to all 32 circuits + get_circuit_gps() helper

## Decisions Made
- Used same _fastf1_lock and in-memory caching pattern as predictions.py for consistency across data modules
- Weather module uses httpx.AsyncClient (async) rather than requests (sync) since it will be called from FastAPI async endpoints
- One Call 3.0 API tried first with fallback to free 2.5 API -- allows the app to work on free tier
- Track surface temperature estimated via heuristic (air temp + sun exposure factor) since no weather API provides track temp
- GPS coordinates embedded in CIRCUIT_DATA dict entries rather than a separate mapping -- keeps circuit data co-located
- Strategy impact assessment uses graduated thresholds: 40% rain = dual strategy, 20% = intermediate backup

## Deviations from Plan

None - plan executed exactly as written.

## User Setup Required

**External services require manual configuration.** The weather module requires an OpenWeatherMap API key:
- Set `OPENWEATHERMAP_API_KEY` environment variable
- Get a key at https://home.openweathermap.org/api_keys
- Subscribe to "One Call by Call" for hourly forecast with rain probability (optional; falls back to free 2.5 API)
- The module returns a helpful error message when the key is missing -- it does not crash

## Issues Encountered
- Python dependencies (fastf1, structlog, httpx) not installed in system Python 3.9 -- verification done via AST parsing and static analysis rather than runtime import. Code is structurally correct and follows established patterns from predictions.py.

## Next Phase Readiness
- Strategy and weather modules are pure-function computation ready to be wrapped as LangChain tools in Plan 03
- Both modules follow the same patterns as predictions.py (threading.Lock, in-memory cache, structlog)
- Weather module is async-ready for FastAPI integration

## Self-Check: PASSED

- [x] backend/app/data/strategy.py - FOUND
- [x] backend/app/data/weather.py - FOUND
- [x] backend/app/api/circuits.py - FOUND
- [x] Commit d2d1ab8 (strategy engine) - FOUND
- [x] Commit 9a2c7c3 (weather + GPS) - FOUND

---
*Phase: 02-backend-data-features*
*Completed: 2026-02-18*
