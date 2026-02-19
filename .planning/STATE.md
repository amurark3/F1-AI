# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** An intelligent F1 race engineer that can answer any Formula 1 question using real data -- race results, driver comparisons, regulations, and live timing -- across web and mobile.
**Current focus:** Phase 2: AI Quality
**Completed:** Phase 1: Infrastructure Hardening

## Current Position

Phase: 2 of 5 (AI Quality)
Plan: 2 of 3 in current phase
Status: Executing Phase 2 -- Plan 01 Complete
Last activity: 2026-02-18 -- Completed 02-01-PLAN.md (race prediction engine with accuracy tracking)

Progress: [███░░░░░░░] 30%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 11min
- Total execution time: 0.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-hardening | 2/2 | 14min | 7min |
| 02-backend-data-features | 1/3 | 20min | 20min |

**Recent Trend:**
- Last 5 plans: 01-01 (6min), 01-02 (8min), 02-01 (20min)
- Trend: Phase 2 plans are heavier (data computation modules)

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 requires Apple Developer account with p8 auth key -- confirm availability before planning Phase 5
- Render.com free tier: ChromaDB on ephemeral storage resets on deploy -- may need persistent disk or managed vector DB
- FastF1 thread safety on current version should be verified before Phase 1 implementation

## Session Continuity

Last session: 2026-02-18
Stopped at: Completed 02-01-PLAN.md (race prediction engine)
Resume file: None
