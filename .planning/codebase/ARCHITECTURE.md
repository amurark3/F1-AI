# Architecture

**Analysis Date:** 2026-02-16

## Pattern Overview

**Overall:** Agentic AI system with streaming backend and real-time chat frontend

**Key Characteristics:**
- LLM agent executes tool-driven queries with multi-turn reasoning loops
- Streaming responses enable real-time UI updates during tool execution
- Backend FastAPI server orchestrates F1 data from multiple sources
- Frontend Next.js client maintains conversation state locally with IndexedDB-like persistence
- Race Engineer persona constrains LLM to F1-domain-specific analysis and strategy

## Layers

**AI/LLM Layer:**
- Purpose: Runs agentic reasoning loop with tool bindings
- Location: `backend/app/api/routes.py` (chat_endpoint, lines 81-198)
- Contains: Gemini 2.0 Flash model with bound tool definitions
- Depends on: Tools layer, External APIs (Google Generative AI)
- Used by: Frontend chat interface

**Tools Layer:**
- Purpose: Provides LLM-callable tools for F1 data access and external APIs
- Location: `backend/app/api/tools.py`
- Contains: 11 tools via @tool decorators (get_race_results, compare_drivers, etc.)
- Depends on: Data sources (FastF1, Ergast, Tavily, ChromaDB)
- Used by: AI/LLM layer via TOOL_LIST and TOOL_MAP

**Data Access Layer:**
- Purpose: Wraps external F1 data sources with caching and normalization
- Location: `backend/app/api/routes.py` (endpoints), `backend/app/api/tools.py` (tools), `backend/app/api/circuits.py` (static data)
- Contains: FastF1 sessions, Ergast API calls, FastF1 caching, ChromaDB vector store
- Depends on: FastF1, Ergast, fastf1.Cache, ChromaDB, Tavily
- Used by: Tools and endpoints

**API Layer:**
- Purpose: REST endpoints that drive UI and provide scheduled/real-time data
- Location: `backend/app/api/routes.py`
- Contains: 8 endpoints (chat, schedule, race, standings, compare, live, health)
- Depends on: Data access layer, Tool layer
- Used by: Frontend via fetch()

**Frontend UI Layer:**
- Purpose: React components that render chat, standings, and race data
- Location: `frontend/app/components/`
- Contains: ChatScreen, ChatMessages, RaceCard, Standings, RaceCalendar, etc.
- Depends on: useChat hook, API_BASE constants
- Used by: Page layouts

**State Management Layer:**
- Purpose: Manages conversation history and UI state locally
- Location: `frontend/app/hooks/useChat.ts`, `frontend/app/hooks/useLocalChats.ts`
- Contains: Chat creation, message persistence, streaming response handling
- Depends on: localStorage, fetch API
- Used by: UI components

**Application Core:**
- Purpose: FastAPI app setup, CORS, lifespan, route mounting
- Location: `backend/main.py`
- Contains: FastAPI instantiation, middleware, background prefetch loop, lifespan management
- Depends on: dotenv, FastAPI, routes, asyncio
- Used by: Uvicorn server

## Data Flow

**Chat Query Flow:**

1. User types message in ChatInput component (`frontend/app/components/ChatInput.tsx`)
2. handleSubmit in useChat hook (`frontend/app/hooks/useChat.ts:132-136`) fires
3. sendMessage sends POST to `/api/chat` with message history as JSON
4. Backend chat_endpoint receives request (`backend/app/api/routes.py:81-198`)
5. System prompt with RACE_ENGINEER_PERSONA injected (`backend/app/api/prompts.py`)
6. LLM invoked with llm_with_tools.ainvoke() (line 132)
7. **Agentic Loop (max 5 turns):**
   - If LLM requests tools: execute each tool via TOOL_MAP[tool_name].invoke()
   - Append ToolMessage with results back to history
   - Re-invoke LLM with results
   - If LLM produces text: yield it to stream and break
8. Frontend reads stream chunks, parsing [TOOL_START]/[TOOL_END] markers (useChat.ts:100-108)
9. Tool status updates UI with executing tool name (setToolStatus)
10. Final assistant message accumulated and saved to localStorage

**Race Data Request Flow:**

1. Frontend component (e.g., RaceCard) fetches `/api/race/{year}/{round_num}`
2. Backend route handler _build_race_detail_sync (line 404-617) executes
3. Acquires _fastf1_lock (threading.Lock at line 389) to prevent concurrent session loads
4. Fetches race results, qualifying, sprint data from FastF1.get_session()
5. Formats data into nested dict with results, qualifying, podium, sprint_qualifying
6. Caches result in race_detail_cache keyed by (year, round_num)
7. Returns cached data on subsequent requests instantly

**Background Prefetch Flow:**

1. Server startup triggers lifespan context manager (main.py:96-105)
2. _prefetch_race_details task spawned (line 99)
3. Every 30 minutes (line 1800 sleep), iterates current season schedule
4. For completed races not in cache, calls _build_race_detail_sync via asyncio.to_thread()
5. Caches result; pauses 5 seconds between races to avoid API hammering
6. Provides instant responses when user requests race data

**State Management:**

- User messages stored in message history array (useChat.ts:11)
- Chat metadata (id, title, messages) persisted to localStorage as JSON
- Chat list (chats[]) is Redux-like state synced to localStorage on each change
- Messages are read-only once sent; only last assistant message is updated during streaming
- Each chat has its own message array; switching chats swaps message view (useChat.ts:24-28)

## Key Abstractions

**Chat Session:**
- Purpose: Encapsulates one conversation with message history
- Examples: `frontend/app/hooks/useLocalChats.ts:Chat` interface, `backend/app/api/routes.py` message array handling
- Pattern: Stateful object with id, title, updatedAt, messages[]. Created on first message, persisted to localStorage

**Tool:**
- Purpose: LLM-callable function with name, description, and implementation
- Examples: `backend/app/api/tools.py` @tool decorators (get_race_results, compare_drivers, etc.)
- Pattern: LangChain @tool decorator wraps function with metadata; collected in TOOL_LIST for binding to LLM

**Race Detail:**
- Purpose: Enriched race data combining multiple FastF1 queries
- Examples: `backend/app/api/routes.py:race_detail_cache`, keys are (year, round_num)
- Pattern: Dict with circuit_info, race_results, qualifying, podium, sprint_results; cached in memory after expensive load

**Message (Chat):**
- Purpose: Single utterance in conversation thread
- Examples: `frontend/app/hooks/useLocalChats.ts:Message` interface, backend LangChain Message types
- Pattern: Object with role (user/assistant) and content (text). In backend, also SystemMessage, HumanMessage, AIMessage, ToolMessage for LLM context

## Entry Points

**Backend Server:**
- Location: `backend/main.py:137-138`
- Triggers: `uvicorn run main:app`
- Responsibilities: FastAPI app instantiation, middleware setup, lifespan management, route mounting

**Frontend Page:**
- Location: `frontend/app/page.tsx`
- Triggers: Next.js routing to /
- Responsibilities: Renders Home component wrapping ChatScreen in NavShell

**Chat Endpoint:**
- Location: `backend/app/api/routes.py:81-198`
- Triggers: POST /api/chat with ChatRequest payload
- Responsibilities: Run agentic loop, stream responses with tool markers

**Schedule Endpoint:**
- Location: `backend/app/api/routes.py:201-270`
- Triggers: GET /api/schedule/{year}
- Responsibilities: Return F1 season calendar with session times and sprint detection

**Race Detail Endpoint:**
- Location: `backend/app/api/routes.py:625-654`
- Triggers: GET /api/race/{year}/{round_num}
- Responsibilities: Return enriched race data (results, qualifying, podium) with caching and timeout

## Error Handling

**Strategy:** Graceful degradation with user-facing error messages

**Patterns:**

- **Tool Timeout (routes.py:158-164):** If tool takes >30s, return friendly timeout message instead of crashing
- **Tool Execution Error (routes.py:166-170):** Catch exception, return error text as ToolMessage, let LLM decide how to handle
- **LLM Loop Max Turns (routes.py:192):** If LLM doesn't produce text after 5 turns, notify user that reasoning hit limit
- **Frontend Fetch Error (useChat.ts:121-125):** Catch network errors and append error message to chat for user visibility
- **Race Data Timeout (routes.py:649-651):** If FastF1 load takes >60s, return timeout error with cache miss note
- **Missing Data (tools.py:479-480):** If ChromaDB search returns no results, return "No regulations found" message
- **Chat Overflow (useChat.ts:95-118):** If stream read fails mid-transfer, incomplete message remains visible (graceful degradation)

## Cross-Cutting Concerns

**Logging:** Python print() statements with emoji prefixes (🤖, 🔄, 🛠️, etc.) for CLI visibility; frontend uses console.error() for debug. No structured logging library.

**Validation:**
- Backend: FastF1 and Ergast return pandas DataFrames; iterate with pd.notna() checks before access
- Frontend: useChat checks activeChatId before syncing messages; checks response.ok before processing stream
- Chat Request model (`backend/app/api/routes.py:72-74`) is basic (messages: List[dict]) without strict validation

**Authentication:** None. Backend is open to CORS-allowed origins (main.py:117-125). No user identity or permission checks.

**Concurrency:**
- Backend uses threading.Lock (_fastf1_lock) to serialize FastF1 session loads (not thread-safe)
- asyncio.to_thread() wraps sync FastF1 calls to avoid blocking event loop
- Frontend uses React hooks with useCallback to prevent stale closures in async handlers
- Race detail cache is dict (not thread-safe but acceptable for read-heavy workload)

**Rate Limiting:** None. Tavily web search tool may have API rate limits (handled by Tavily client). No client-side debounce on chat submissions.

**Data Persistence:**
- Backend: race_detail_cache is in-memory only; clears on server restart
- Frontend: Chat messages persisted to localStorage; IndexedDB-like persistence via local storage JSON serialization
- FastF1 cache: Disk cache in `f1_cache/` directory speeds up repeated data loads

---

*Architecture analysis: 2026-02-16*
