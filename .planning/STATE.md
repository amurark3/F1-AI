# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** An intelligent F1 race engineer that can answer any Formula 1 question using real data -- race results, driver comparisons, regulations, and live timing -- across web and mobile.
**Current focus:** Phase 3 (next)
**Completed:** Phase 1: Infrastructure Hardening, Phase 2: Backend Data Features

## Current Position

Phase: 2 of 5 -- COMPLETE
Plan: 3 of 3 in current phase -- ALL COMPLETE
Status: Phase 2 Complete -- Ready for Phase 3
Last activity: 2026-02-18 -- Completed 02-03-PLAN.md (tool wiring + predictions endpoint)

Progress: [██████░░░░] 60%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 14min
- Total execution time: 1.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-hardening | 2/2 | 14min | 7min |
| 02-backend-data-features | 3/3 | 53min | 18min |

**Recent Trend:**
- Last 5 plans: 01-01 (6min), 01-02 (8min), 02-01 (20min), 02-02 (28min), 02-03 (5min)
- Trend: Plan 03 was fast (wiring only, no new data modules)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: 5-phase structure after removing Test Infrastructure (personal project, not going to production)
- Roadmap: TEST-01, TEST-02, TEST-03 deferred to v2
- Roadmap: Predictions use statistical/heuristic approach, not ML training (per PROJECT.md)
- Roadmap: APNs push is Phase 5 (last) due to external infrastructure dependency and complexity
- 01-01: LLM safety uses BLOCK_ONLY_HIGH for dangerous/harassment (F1 crash content), BLOCK_MEDIUM_AND_ABOVE for hate/sexual (not F1-relevant)
- 01-01: All config constants in backend/app/config.py with os.getenv() pattern for env overrides
- 01-01: Removed dead MCP prediction tools (predict_race_results, calculate_championship_scenario) importing from non-existent app.ml
- 01-02: structlog with ConsoleRenderer (dev) / JSONRenderer (prod) based on ENVIRONMENT env var
- 01-02: ChromaDB singleton uses threading.Lock with double-check pattern for thread safety
- 01-02: WebSocket heartbeat uses application-level JSON pings for client compatibility
- 02-01: Prediction scoring uses 5 weighted factors with proportional rebalancing when data sources missing
- 02-01: Confidence ranges from stdev of input signals; pre-qualifying fallback widens by 15pp
- 02-01: Accuracy history stored as JSON with atomic write-to-temp-then-rename
- 02-01: Data module pattern established: pure computation in app/data/, thin wrappers in tools.py
- 02-02: Strategy module uses same _fastf1_lock and caching pattern as predictions.py for consistency
- 02-02: Weather uses httpx.AsyncClient with One Call 3.0 -> 2.5 current weather fallback chain
- 02-02: Track surface temp estimated from air temp + cloud cover heuristic (no API provides track temp)
- 02-02: Strategy impact uses 40% rain threshold for dual scenario, 20% for intermediate backup
- 02-02: GPS coordinates embedded in CIRCUIT_DATA dict rather than separate mapping
- 02-03: Weather tool uses asyncio.run() with RuntimeError fallback for event loop detection
- 02-03: Predictions REST caches until qualifying data available, then recomputes
- 02-03: Chat predictions include rich narrative; REST returns structured JSON (per CONTEXT.md)
- 02-03: Old get_track_conditions stub fully removed and replaced by get_weather_conditions

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 requires Apple Developer account with p8 auth key -- confirm availability before planning Phase 5
- Render.com free tier: ChromaDB on ephemeral storage resets on deploy -- may need persistent disk or managed vector DB
- FastF1 thread safety on current version should be verified before Phase 1 implementation

## Session Continuity

Last session: 2026-02-18
Stopped at: Completed 02-03-PLAN.md (tool wiring + predictions endpoint) -- Phase 2 COMPLETE
Resume file: None
