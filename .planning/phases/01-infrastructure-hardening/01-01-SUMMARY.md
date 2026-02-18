---
phase: 01-infrastructure-hardening
plan: 01
subsystem: infra
tags: [config, safety-settings, dead-code-removal, gemini, mcp]

# Dependency graph
requires: []
provides:
  - "Centralized config.py with 17 environment-configurable constants"
  - "Clean MCP server without broken prediction tool stubs"
  - "F1-appropriate LLM safety settings (no BLOCK_NONE)"
  - "Accurate system prompt capabilities list"
affects: [01-infrastructure-hardening, 02-core-improvements]

# Tech tracking
tech-stack:
  added: []
  patterns: ["os.getenv() with defaults for all config constants", "config.py as single source of truth for magic numbers"]

key-files:
  created: ["backend/app/config.py"]
  modified: ["backend/app/api/routes.py", "backend/main.py", "backend/mcp_server.py", "backend/app/api/prompts.py"]

key-decisions:
  - "DANGEROUS_CONTENT and HARASSMENT use BLOCK_ONLY_HIGH (F1 discusses crashes, injuries, rivalries)"
  - "HATE_SPEECH and SEXUALLY_EXPLICIT use BLOCK_MEDIUM_AND_ABOVE (not relevant to F1, stricter is safe)"
  - "Removed championship scenario capability from prompts (tool was dead code, no backing implementation)"
  - "Skipped backend/README.md cleanup because file does not exist"

patterns-established:
  - "Config pattern: all magic numbers in backend/app/config.py, imported where needed"
  - "Environment override pattern: int(os.getenv('NAME', 'default')) for all numeric constants"

requirements-completed: [INFRA-03, INFRA-05, INFRA-06]

# Metrics
duration: 6min
completed: 2026-02-18
---

# Phase 1 Plan 1: Config Foundation, Dead Code Removal, and LLM Safety Summary

**Centralized 17 config constants with env overrides, removed 2 dead MCP prediction tools importing from non-existent app.ml, and replaced all BLOCK_NONE safety settings with F1-appropriate levels**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-18T07:19:21Z
- **Completed:** 2026-02-18T07:25:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Created backend/app/config.py with 17 extracted constants (timeouts, model settings, prefetch, WebSocket, RAG) all configurable via environment variables
- Removed predict_race_results and calculate_championship_scenario dead tool stubs from mcp_server.py that imported from non-existent app.ml module
- Replaced all 4 BLOCK_NONE safety settings with F1-appropriate levels (BLOCK_ONLY_HIGH for dangerous content/harassment, BLOCK_MEDIUM_AND_ABOVE for hate speech/sexually explicit)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create centralized config.py and wire up all hardcoded values** - `53b5f70` (feat)
2. **Task 2: Remove dead MCP prediction stubs and clean README** - `924b669` (fix)
3. **Task 3: Set appropriate LLM safety settings for F1 domain** - `820e1c5` (feat)

## Files Created/Modified
- `backend/app/config.py` - NEW: Centralized configuration with 17 env-configurable constants
- `backend/app/api/routes.py` - Replaced hardcoded timeouts/model settings with config imports, updated safety settings
- `backend/main.py` - Replaced hardcoded prefetch timing values with config imports
- `backend/mcp_server.py` - Removed dead predict_race_results and calculate_championship_scenario tools, removed ML model health check
- `backend/app/api/prompts.py` - Removed non-existent championship scenario capability, added accurate capabilities (driver comparison, web search)

## Decisions Made
- DANGEROUS_CONTENT uses BLOCK_ONLY_HIGH because F1 legitimately discusses crashes, fires, and driver injuries
- HARASSMENT uses BLOCK_ONLY_HIGH because F1 coverage includes team rivalries and driver criticism
- HATE_SPEECH and SEXUALLY_EXPLICIT use BLOCK_MEDIUM_AND_ABOVE since they are not relevant to F1 domain content
- Removed "calculate championship scenarios" from prompts.py since the backing tool was dead code with no implementation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Removed false capability claim from system prompt**
- **Found during:** Task 2 (Dead code removal)
- **Issue:** prompts.py claimed "You can calculate championship scenarios" but the backing tool was dead code importing from non-existent app.ml.scenario
- **Fix:** Replaced with accurate capabilities (driver comparison, web search) that match actual tool implementations
- **Files modified:** backend/app/api/prompts.py
- **Verification:** Capabilities listed now match tools in TOOL_LIST
- **Committed in:** 924b669 (Task 2 commit)

### Skipped Items

**2. backend/README.md does not exist**
- **Found during:** Task 2
- **Issue:** Plan specified cleaning ML/scikit-learn references from backend/README.md, but this file does not exist in the repository
- **Impact:** No action needed -- nothing to clean up
- **Verification:** Confirmed via directory listing and glob search

---

**Total deviations:** 1 auto-fixed (1 missing critical), 1 skipped (file not found)
**Impact on plan:** Auto-fix was necessary for accuracy. Skipped item had zero impact since the file doesn't exist.

## Issues Encountered
- Routes import test requires TAVILY_API_KEY and GOOGLE_API_KEY environment variables at module load time (pre-existing issue, not caused by our changes). Verified with dummy keys set.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- backend/app/config.py is ready for Plan 02 to import WebSocket constants (WS_HEARTBEAT_INTERVAL, WS_STALE_TIMEOUT, WS_POLL_INTERVAL)
- All hardcoded values extracted; Plan 02 can focus on logging, ChromaDB singleton, and WebSocket hardening

---
## Self-Check: PASSED

- backend/app/config.py: FOUND
- 01-01-SUMMARY.md: FOUND
- Commit 53b5f70 (Task 1): FOUND
- Commit 924b669 (Task 2): FOUND
- Commit 820e1c5 (Task 3): FOUND

---
*Phase: 01-infrastructure-hardening*
*Completed: 2026-02-18*
