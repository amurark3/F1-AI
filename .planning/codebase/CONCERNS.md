# Codebase Concerns

**Analysis Date:** 2026-02-16

## Tech Debt

**Missing ML Module — Race Predictions Broken:**
- Issue: `mcp_server.py` references `app.ml.predict` and `app.ml.scenario` modules (lines 505, 522) but these modules do not exist. Any call to `predict_race_results()` or `calculate_championship_scenario()` will fail immediately.
- Files: `backend/mcp_server.py` (lines 498-526), `backend/app/ml/predict.py` (MISSING), `backend/app/ml/scenario.py` (MISSING)
- Impact: Two advertised MCP tools are non-functional. Users querying for race predictions or championship scenarios get hard failures. These tools are exposed via MCP but will crash when invoked.
- Fix approach: Either implement the ML modules (`predict.py` and `scenario.py` under `backend/app/ml/`) with the required functions `predict_race()` and `calculate_title_scenario()`, or remove/stub these tools from `mcp_server.py` with a clear "not yet implemented" message.

**Duplicate Debug Print Statement:**
- Issue: `backend/app/api/tools.py` line 530 contains a raw debug print: `print(f"DEBUG ERROR: {e}")` which serves no purpose and leaks to logs
- Files: `backend/app/api/tools.py:530`
- Impact: Pollutes server logs with debug output that should be handled via proper logging framework
- Fix approach: Replace with structured logging using Python's `logging` module; remove ad-hoc print statements from production code

**Duplicated Code Between Routes and Tools:**
- Issue: Time-formatting logic `_fmt_timedelta()` is duplicated in both `backend/app/api/tools.py` (lines 49-65) and `backend/app/api/routes.py` (lines 392-401). Similar patterns appear in `mcp_server.py` (lines 48-56).
- Files: `backend/app/api/tools.py`, `backend/app/api/routes.py`, `backend/mcp_server.py`
- Impact: Changes to formatting logic must be synchronized across three locations; risk of inconsistency
- Fix approach: Extract to `backend/app/api/utils.py` or similar shared module; import in all three files

**Relaxed LLM Safety Settings:**
- Issue: `backend/app/api/routes.py` lines 50-55 disable all Gemini safety filters (BLOCK_NONE) with a comment that it's necessary to discuss "crashes and incidents"
- Files: `backend/app/api/routes.py:46-56`
- Impact: Opens the assistant to generating harmful content; safety guardrails are intended to remain active even when discussing sensitive topics
- Fix approach: Use default safety settings (BLOCK_MEDIUM_AND_ABOVE) or targeted filter exceptions only for F1-specific content; test with safer thresholds first

**Hardcoded Timeouts Without Configuration:**
- Issue: Tool execution timeout (30s, line 160), race detail timeout (60s, line 622), and FastF1 operations lock timeout are hardcoded throughout the codebase
- Files: `backend/app/api/routes.py:160` (30s tool), `backend/app/api/routes.py:622` (60s race detail)
- Impact: Cannot tune performance without code changes; different tools may have different legitimate timeout needs
- Fix approach: Move timeouts to environment variables or a config module; set reasonable defaults but allow override per tool

**Unvalidated Timezone Lookup:**
- Issue: `backend/app/api/routes.py` lines 257-263 assume `race_date` and other timestamps are always valid when calculating event status, but doesn't guard against NaT (Not a Time)
- Files: `backend/app/api/routes.py:257-263` (schedule endpoint), `routes.py:465-466` (race detail)
- Impact: If FastF1 returns malformed dates, the comparison will fail silently or crash
- Fix approach: Add explicit NaT checks and safe defaults before timestamp comparisons

## Known Bugs

**Track Conditions Tool is a Stub:**
- Symptoms: Calling `get_track_conditions()` tool always returns a static "not yet implemented" message regardless of input location
- Files: `backend/app/api/tools.py:72-85`
- Trigger: Any user query asking "what are the weather conditions" or similar
- Workaround: None; users must check weather manually. Tell model to use web search for live weather via `perform_web_search()` tool

**Race Detail Cache Never Evicts:**
- Symptoms: First request to `/api/race/{year}/{round}` is slow (5-15s), but subsequent requests return stale data even if more recent session data has been fetched
- Files: `backend/app/api/routes.py:385` (in-memory cache dict), no TTL or invalidation strategy
- Trigger: User checks race results shortly after the race finishes, then checks again 1 hour later with different data available
- Workaround: Restart the backend server to clear cache. For live coverage scenarios this is not viable.
- Impact: Users see outdated results without knowing data has been refreshed elsewhere

**OpenF1 WebSocket Session Key Lookup Never Fails Over:**
- Symptoms: If `_find_openf1_session()` returns None (line 707), the live timing websocket (`routes.py:860-897`) enters an infinite loop polling with `session_key=None`, returning no position data
- Files: `backend/app/api/routes.py:707-724`, `routes.py:860-897`
- Trigger: OpenF1 API is unavailable or returns 404 for the given race
- Workaround: None; user's websocket connection hangs silently
- Impact: Live timing feature silently fails during races when OpenF1 integration breaks

## Security Considerations

**API Keys Hardcoded in Code Paths:**
- Risk: Environment variable references for `GOOGLE_API_KEY` and `TAVILY_API_KEY` are properly loaded via `.env`, but if `.env` is missing, the application boots without clear validation
- Files: `backend/main.py:11-14`, `backend/app/api/routes.py:49`, `backend/app/api/tools.py:38`, `mcp_server.py:15-23`
- Current mitigation: `.env` file is git-ignored (assumed); loading happens early in main.py via `load_dotenv()`
- Recommendations:
  1. Add explicit validation in `main.py` that checks both `GOOGLE_API_KEY` and `TAVILY_API_KEY` exist before starting server
  2. Raise a clear error with helpful message if keys are missing
  3. Log which APIs are successfully initialized at startup (without revealing key values)

**CORS Configuration Uses Hardcoded Fallback:**
- Risk: `backend/main.py:117` uses `"http://localhost:3000"` as fallback CORS origin if `ALLOWED_ORIGINS` env var is missing. This is only safe in dev; production deployments may accidentally expose the API.
- Files: `backend/main.py:117`
- Current mitigation: Must be explicitly set via env var for production
- Recommendations:
  1. Remove localhost fallback; require explicit ALLOWED_ORIGINS env var
  2. Add startup validation that fails fast if origin is not configured in production

**Persona Prompt Attempts Jailbreak Defense:**
- Risk: `backend/app/api/prompts.py:14-26` includes jailbreak-resistance instructions, but these are instructions to the user-facing model, not to the backend. If a user crafts a sophisticated prompt attack, they bypass these instructions.
- Files: `backend/app/api/prompts.py:14-26`
- Current mitigation: LLM safety filters (albeit relaxed); tool-use constraints
- Recommendations:
  1. Test prompt injection scenarios (e.g., user message containing system prompt override)
  2. Consider additional input validation/sanitization before passing to LLM
  3. Monitor for suspicious patterns in chat logs (tokens like "ignore previous" or role-change attempts)

## Performance Bottlenecks

**FastF1 Session Loads Block All Race Detail Requests:**
- Problem: `backend/app/api/routes.py:389` uses a single global threading lock `_fastf1_lock` to ensure only one FastF1 session loads at a time. Any user requesting race detail must wait for all previous requests to complete (up to 60s each).
- Files: `backend/app/api/routes.py:389`, `routes.py:473`, `routes.py:524`, `routes.py:554`, `routes.py:591`
- Cause: FastF1 library is not thread-safe; concurrent session loads cause data corruption
- Impact: If 5 users request race data simultaneously, requests 2-5 wait sequentially (up to 240s for request 5)
- Improvement path:
  1. Pre-fetch completed race details in background loop (`main.py:29-93`) so most requests hit memory cache
  2. Implement a request queue with bounded depth and clear "too many concurrent requests" error rather than silent queueing
  3. Consider using process-pool or async executor specifically for FastF1 if concurrency increases

**Prefetch Loop Processes Races Serially:**
- Problem: `backend/main.py:29-93` sleeps 5 seconds between each race prefetch. If there are 24 races in a season, prefetch takes 2 minutes. Meanwhile, completed races remain uncached until the next sweep (30 minutes later).
- Files: `backend/main.py:29-93`
- Cause: Cautious approach to not overwhelm F1 data source, but overly conservative
- Improvement path:
  1. Increase batch size (e.g., prefetch 2-3 races in parallel using asyncio.gather)
  2. Reduce sleep between races to 2-3 seconds if monitoring shows API stability
  3. Prioritize completed recent races over old ones

**Embedded Vector Database Initialization on Every Tool Call:**
- Problem: `backend/app/api/tools.py:467-468` and `mcp_server.py:450-451` instantiate a new Chroma client and load embeddings model (`sentence-transformers/all-MiniLM-L6-v2`) on every call to `consult_rulebook()`
- Files: `backend/app/api/tools.py:467-468`, `mcp_server.py:450-451`
- Cause: No persistent client; initialization happens in-function
- Impact: First rulebook lookup takes 3-5s (model download + database init); subsequent calls also incur this overhead
- Improvement path:
  1. Move Chroma client to module-level singleton initialized at startup (like FastF1 cache)
  2. Cache HuggingFaceEmbeddings model globally
  3. Add health check to verify database exists before starting server

## Fragile Areas

**Schedule Date Parsing Assumes Consistent Format:**
- Files: `backend/app/api/routes.py:219-264` (schedule endpoint), `routes.py:404-454` (race detail)
- Why fragile: Code assumes FastF1 always returns `EventDate` as a pandas Timestamp and Session columns have consistent names (Session1-Session5). If FastF1 API changes column naming or returns different types, parsing breaks silently.
- Safe modification: Add explicit type checks and fallbacks for missing columns before accessing them
- Test coverage: No test file found; no validation of API response structure

**Driver Name Resolution Uses Substring Matching:**
- Files: `backend/app/api/tools.py:294-304` (compare_drivers), `mcp_server.py:307-316`
- Why fragile: Lookup is case-insensitive substring match on LastName, BroadcastName, Abbreviation. If two drivers have overlapping names (e.g., "Jos" matches both "Joseph" and "Joséf"), behavior is undefined.
- Safe modification: Use exact abbreviation match first, then full name match, with clear fallback/error message if ambiguous
- Test coverage: No test cases for edge cases (partial matches, ambiguous names)

**Circuit Lookup Hardcodes Duplicate Location Names:**
- Files: `backend/app/api/circuits.py:10-279`
- Why fragile: Multiple entries for same circuit (e.g., "Monaco" and "Monte Carlo" both map to Circuit de Monaco; "Budapest" and "Mogyoród" both map to Hungaroring). If FastF1 changes location string format, lookup fails silently and returns None.
- Safe modification: Use a case-insensitive fuzzy match or canonical location mapping
- Test coverage: No test file found; no validation of lookup success

**Error Messages From Third-Party APIs Leaked to Client:**
- Files: `backend/app/api/tools.py` (all tool functions catch exceptions and return str(e)), `routes.py:269-270`, `routes.py:332-334`, `routes.py:375-377`, `mcp_server.py:164`, `mcp_server.py:202`, `mcp_server.py:241`, `mcp_server.py:283`
- Why fragile: Full exception strings (FastF1, Ergast, Tavily errors) are returned to the user, potentially revealing internal details or API structure. User sees "pandas.errors.ParserError: ..." instead of "Failed to load race data."
- Safe modification: Log full error server-side; return sanitized user-facing message to client
- Test coverage: No test cases for error scenarios

## Scaling Limits

**In-Memory Race Cache Unbounded:**
- Current capacity: One Python dict entry per (year, round_num) pair. With multiple seasons cached, could grow to 100+ MB per season
- Limit: No eviction policy; cache grows indefinitely until server restart
- Scaling path:
  1. Add LRU cache with bounded size (e.g., 100 entries = ~4-5 seasons)
  2. Implement TTL-based expiration (e.g., keep for 48 hours after race completes)
  3. Move to Redis for multi-process scenarios (if deployed with Gunicorn workers)

**WebSocket Connections Not Tracked or Limited:**
- Current capacity: `_live_connections` dict in `routes.py:664` grows with each connected client. No heartbeat check; dead connections accumulate.
- Limit: If 100+ users connect to live timing and half disconnect abruptly (network failure), 50 stale sockets remain in memory indefinitely
- Scaling path:
  1. Add periodic heartbeat/ping-pong to detect dead connections
  2. Implement connection limit per session to prevent resource exhaustion
  3. Periodically clean up closed sockets from the connections dict

**No Request Rate Limiting:**
- Current capacity: No rate limiting on `/api/chat` endpoint. One user can spam requests and trigger 30s tool timeouts repeatedly.
- Limit: Backend becomes unresponsive under high concurrent tool-call load
- Scaling path:
  1. Add token-bucket or sliding-window rate limiter using Redis or in-process store
  2. Implement per-IP or per-session rate limits (e.g., 10 requests/minute)
  3. Add circuit breaker to fail fast if FastF1 API is overloaded

## Dependencies at Risk

**FastF1 Version Pinning Missing:**
- Risk: `backend/requirements.txt:26` lists `fastf1` with no version constraint. Major version updates could break API calls.
- Impact: If FastF1 releases v0.2.0 with breaking API changes, `pip install -r requirements.txt` could install incompatible version
- Migration plan: Pin to `fastf1==0.1.x` or higher with explicit compatibility testing. Monitor FastF1 releases for breaking changes.

**Outdated Lap Records in Static Circuit Data:**
- Risk: `backend/app/api/circuits.py:10-267` hardcodes lap records (e.g., Melbourne 2024, Silverstone 2020) which become stale each season
- Impact: Users see old records; no way to update without code change
- Migration plan:
  1. Fetch lap records dynamically from FastF1 at startup
  2. Cache and invalidate weekly
  3. If hardcoding is necessary, add a docstring with last-updated date and quarterly review schedule

**Gemini API Stability Unmonitored:**
- Risk: `backend/app/api/routes.py:46-59` uses `ChatGoogleGenerativeAI()` with no fallback, retry policy, or circuit breaker. If Google's API goes down, all chat requests fail immediately.
- Impact: Service unavailable during Google Cloud incidents
- Migration plan:
  1. Implement exponential backoff on 429 (rate limit) and 503 (service unavailable) responses
  2. Cache recent chat responses and serve stale responses with warning during outages
  3. Add secondary LLM option (e.g., Claude via Anthropic API) as fallback

## Test Coverage Gaps

**No Tests for API Endpoints:**
- What's not tested: All FastAPI endpoints (`/api/chat`, `/api/schedule`, `/api/race`, `/api/standings/*`, `/api/compare`, `/api/live`, `/health`) have zero test coverage
- Files: `backend/app/api/routes.py` (all 9 endpoints)
- Risk: Refactoring breaks endpoints silently; error paths never validated
- Priority: High — these are public API surface

**No Tests for Tool Functions:**
- What's not tested: All 11 tools in `backend/app/api/tools.py` are untested. No validation that tools parse FastF1 data correctly or handle edge cases.
- Files: `backend/app/api/tools.py:72-609` (all tools)
- Risk: Malformed Markdown tables, missing columns, or API changes break tool behavior without detection
- Priority: High — tools are user-facing

**No Tests for Chat Loop Logic:**
- What's not tested: The agentic loop in `routes.py:118-193` that orchestrates tool calls and LLM invocations. No validation of message ordering, tool result formatting, or max_turns enforcement.
- Files: `backend/app/api/routes.py:118-193`
- Risk: Loop could enter infinite state, skip tool results, or corrupt message history without detection
- Priority: Critical — orchestration is core feature

**No Frontend Component Tests:**
- What's not tested: React components (`ChatScreen`, `RaceCard`, `Standings`, etc.) are untested. No validation of rendering, state updates, or error handling.
- Files: `frontend/app/components/*.tsx` (all files), `frontend/app/hooks/*.ts`
- Risk: UI breaks silently; regression in error states goes undetected
- Priority: Medium — frontend is visible to users but less critical than backend logic

**No Integration Tests:**
- What's not tested: End-to-end flow from user message through tool execution to response. No validation of backend-frontend communication, WebSocket behavior, or caching.
- Files: No test file exists
- Risk: Deployment breaks contract between frontend and backend without detection
- Priority: Medium — integration failures are discovered in production

**No Performance Tests:**
- What's not tested: Race detail loading time, chat loop latency, prefetch throughput
- Files: No benchmark file
- Risk: Performance regressions go unnoticed; optimizations can't be validated
- Priority: Low — but necessary before scaling to production load

---

*Concerns audit: 2026-02-16*
