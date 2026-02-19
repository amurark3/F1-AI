---
phase: 01-infrastructure-hardening
plan: 02
subsystem: infra
tags: [structlog, chromadb, websocket, logging, singleton]

# Dependency graph
requires:
  - phase: 01-01
    provides: "config.py with CHROMA_DB_PATH, EMBEDDING_MODEL_NAME, RULEBOOK_TOP_K, WS_HEARTBEAT_INTERVAL, WS_STALE_TIMEOUT"
provides:
  - "Structured JSON logging via structlog with dev/prod dual mode"
  - "ChromaDB lazy singleton for one-time vector DB initialization"
  - "WebSocket ConnectionManager with heartbeat pings and stale cleanup"
affects: [02-ai-quality, 03-ios-mvp, 04-live-timing]

# Tech tracking
tech-stack:
  added: [structlog]
  patterns: [structured-logging, lazy-singleton, connection-manager-heartbeat]

key-files:
  created:
    - backend/app/logging_config.py
  modified:
    - backend/app/api/routes.py
    - backend/app/api/tools.py
    - backend/main.py
    - backend/app/rag/ingest.py
    - backend/requirements.txt

key-decisions:
  - "structlog with ConsoleRenderer (dev) / JSONRenderer (prod) based on ENVIRONMENT env var"
  - "ChromaDB singleton uses threading.Lock with double-check pattern for thread safety"
  - "WebSocket heartbeat uses application-level JSON pings (not protocol pings) for client compatibility"

patterns-established:
  - "Structured logging: use structlog.get_logger() at module level, dot-separated event names (e.g. tool.executing, agent.turn)"
  - "Lazy singleton: module-level _var = None with threading.Lock and double-check locking"
  - "ConnectionManager pattern: connect/disconnect/heartbeat/touch/is_stale lifecycle"

requirements-completed: [INFRA-01, INFRA-02, INFRA-04]

# Metrics
duration: 8min
completed: 2026-02-18
---

# Phase 01 Plan 02: Structured Logging, ChromaDB Singleton, WebSocket Heartbeat Summary

**structlog with dev/prod dual mode replacing all 48 print() calls, ChromaDB lazy singleton with thread-safe locking, and WebSocket ConnectionManager with 15s heartbeat pings**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-18T07:26:24Z
- **Completed:** 2026-02-18T07:34:15Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- All 48 print() calls across routes.py, tools.py, main.py, and ingest.py replaced with structured structlog calls using dot-separated event names
- ChromaDB vector store initializes once via lazy singleton with threading.Lock -- second consult_rulebook() call skips initialization entirely
- WebSocket connections use ConnectionManager with heartbeat pings every 15 seconds and automatic detection of stale connections after 60 seconds

## Task Commits

Each task was committed atomically:

1. **Task 1: Add structlog and replace all print() statements** - `df8a32b` (feat)
2. **Task 2: ChromaDB lazy singleton and WebSocket heartbeat** - `21a5bac` (feat)

## Files Created/Modified
- `backend/app/logging_config.py` - structlog configuration with dev/prod dual mode via ENVIRONMENT env var
- `backend/requirements.txt` - Added structlog dependency
- `backend/app/api/tools.py` - Structured logging + ChromaDB lazy singleton with _get_vector_db()
- `backend/app/api/routes.py` - Structured logging + ConnectionManager class with heartbeat/stale detection
- `backend/main.py` - setup_logging() call during lifespan startup + structured logging
- `backend/app/rag/ingest.py` - Structured logging for ingestion script

## Decisions Made
- Used structlog with ConsoleRenderer for dev and JSONRenderer for production, toggled by ENVIRONMENT env var
- ChromaDB singleton uses threading.Lock with double-check locking pattern to prevent race conditions on first initialization
- WebSocket heartbeat uses application-level JSON `{"type": "ping"}` instead of WebSocket protocol pings since the client may not handle protocol pings
- Silenced noisy third-party libraries (httpx, chromadb, sentence_transformers, httpcore) at WARNING level

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 01 (Infrastructure Hardening) is now complete with both plans executed
- Structured logging foundation ready for all subsequent phases
- ChromaDB singleton pattern ready for Phase 02 AI quality improvements
- WebSocket ConnectionManager ready for Phase 04 live timing enhancements

## Self-Check: PASSED

- All 6 files found on disk
- Commit df8a32b found (Task 1)
- Commit 21a5bac found (Task 2)
- Zero print() statements in target files confirmed

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-18*
