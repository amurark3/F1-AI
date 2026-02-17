# Architecture Patterns

**Domain:** F1 AI Race Engineer — three-platform companion app
**Researched:** 2026-02-16
**Confidence:** HIGH (based on direct codebase inspection)

---

## Existing Architecture (As-Built)

Before describing how new features integrate, the current state must be fully understood.

### System Diagram

```
                              ┌─────────────────────────────────────────────┐
                              │              Render.com (Backend)            │
                              │                                              │
                              │  FastAPI (uvicorn, single process)           │
                              │  ┌──────────────────────────────────────┐   │
                              │  │           Agentic Loop               │   │
                              │  │  Gemini 2.0 Flash (LangChain)        │   │
                              │  │  ├── 11 LangChain @tool functions    │   │
                              │  │  ├── ChromaDB RAG (FIA rulebook)     │   │
                              │  │  └── asyncio.to_thread (FastF1)      │   │
                              │  └──────────────────────────────────────┘   │
                              │  ┌──────────────────────────────────────┐   │
                              │  │         Data Layer                   │   │
                              │  │  FastF1 (+ threading.Lock)           │   │
                              │  │  Ergast (via FastF1)                 │   │
                              │  │  OpenF1 API (WebSocket polling)      │   │
                              │  │  Tavily (web search)                 │   │
                              │  │  in-memory race_detail_cache (dict)  │   │
                              │  └──────────────────────────────────────┘   │
                              └──────────────┬──────────────────────────────┘
                                             │  HTTPS / WSS
                    ┌────────────────────────┼────────────────────┐
                    │                        │                    │
          ┌─────────▼──────────┐  ┌──────────▼────────┐  ┌──────▼──────────────┐
          │  Next.js (Vercel)  │  │  iOS App (SwiftUI) │  │  WidgetKit Extension│
          │                    │  │                    │  │                    │
          │  /api/chat         │  │  APIClient.swift   │  │  NextRaceWidget    │
          │  (streaming fetch) │  │  ChatStreamService │  │  (polls /schedule) │
          │  /api/schedule     │  │  LiveTimingService │  │                    │
          │  /api/race         │  │  NotificationSvc   │  │                    │
          │  /api/standings    │  │  CacheService      │  │                    │
          │  ws://live         │  │  (SwiftData)       │  │                    │
          │                    │  │                    │  │                    │
          │  SWR + fetch       │  │  MVVM + @Observable│  │                    │
          │  localStorage chat │  │  SwiftData cache   │  │                    │
          └────────────────────┘  └────────────────────┘  └────────────────────┘
```

### Existing Component Boundaries

| Component | Responsibility | What It Does NOT Do |
|-----------|---------------|---------------------|
| FastAPI backend | All business logic, data fetching, LLM calls | No auth, no DB, no push server |
| Gemini + tools | Agentic reasoning, tool dispatch | Not called for non-chat endpoints |
| FastF1 layer | Historical session data (behind threading.Lock) | No live data, not async-safe |
| OpenF1 polling | Live positions during sessions | No historical data |
| ChromaDB | FIA regulation vector search | Not used for race data |
| Next.js frontend | Web UI, streaming reader, localStorage chat | No business logic |
| iOS APIClient | REST + WebSocket client with SwiftData cache | No data transformation |
| WidgetKit | Static schedule display, poll on timer | No chat, no WebSocket |
| NotificationService | Local UNUserNotificationCenter scheduling | No push server, no APNs |

### Key Architectural Constraints (from codebase inspection)

1. **FastF1 global lock.** `threading.Lock()` in routes.py serializes ALL FastF1 session loads. This means concurrent requests for different races queue up behind each other. The existing `_fastf1_lock` is module-level and shared across the process.

2. **Single-process Render deployment.** `uvicorn main:app` runs one process. All state (race_detail_cache, _live_connections dict, _fastf1_lock) is in-memory and lost on cold start. There is no Redis, no DB, no persistent store.

3. **Cold starts.** Render.com free tier sleeps after 15 minutes of inactivity. First request after sleep hits cold start. The 30-second startup delay in `_prefetch_race_details` means the prefetch loop is not running for the first 30 seconds post-cold-start.

4. **No push infrastructure.** NotificationService on iOS uses only UNUserNotificationCenter (local scheduled notifications). There is no APNs device token registration, no server-side push endpoint, and no mechanism for the backend to push to devices.

5. **WebSocket cleanup gap.** `_live_connections` dict accumulates stale WebSocket entries. The cleanup in the finally block only removes the specific socket that disconnected — but if a disconnect exception fires before the finally, entries can leak.

6. **ChromaDB re-initialization.** The `consult_rulebook` tool creates a new `HuggingFaceEmbeddings` and `Chroma` instance on every call. This loads the embedding model from disk each time — expensive.

7. **CORS is env-var driven.** `ALLOWED_ORIGINS` splits on commas — the iOS app talks directly to the backend (no CORS restriction for native clients). Frontend and iOS are both consumers of the same backend API.

---

## New Feature Integration Architecture

### Feature 1: Race Predictions and Strategy Analysis

**What it is:** Pre-race outcome predictions based on qualifying results, historical performance, circuit characteristics, and weather. Pit strategy analysis with undercut/overcut windows.

**Integration pattern: New backend tools + new API endpoints**

Predictions are pure computation over existing data (FastF1 historical data, circuit info). Do NOT add an ML dependency or external service. Use statistical/heuristic computation.

```
Architecture:

backend/
├── app/
│   ├── api/
│   │   ├── tools.py          ← Add: predict_race_outcome, analyze_pit_strategy tools
│   │   ├── routes.py         ← Add: GET /api/predictions/{year}/{round_num}
│   │   └── predictions.py    ← New: prediction computation module (pure Python)
```

**Data flow for predictions:**

```
Client request
    │
    ▼
GET /api/predictions/{year}/{round_num}
    │
    ├── FastF1 (via _fastf1_lock): load qualifying session
    ├── FastF1 (via _fastf1_lock): load last N race sessions at same circuit
    ├── circuit info (circuits.py, in-memory)
    │
    ▼
predictions.py: compute_predictions(quali_data, history, circuit)
    │    ├── grid position correlation with finish → weight factor
    │    ├── driver form index (last 3 races avg position)
    │    ├── team pit stop speed (historical avg)
    │    └── tire strategy suggestion (circuit laps × tire degradation heuristic)
    │
    ▼
Return JSON: {predictions: [...], strategy: {...}, confidence: "statistical"}
```

**LLM tool integration:** Add two new tools to `TOOL_LIST`:
- `predict_race_outcome(year, grand_prix)` — calls predictions.py, returns formatted markdown
- `analyze_pit_strategy(year, grand_prix, driver)` — returns undercut/overcut windows

**Build dependency:** predictions.py has NO dependency on other new features. Build this first.

**FastF1 lock constraint:** Prediction endpoint must go through `asyncio.to_thread` with the `_fastf1_lock` like all other FastF1 calls. Do not add a separate lock. This means prediction requests serialize behind race detail requests.

**iOS/Web integration:** Both clients call `GET /api/predictions/{year}/{round_num}` directly. iOS adds a new prediction card in the race detail view. Web adds a prediction panel below the race card.

---

### Feature 2: Live AI Commentary

**What it is:** During a live session, the AI generates periodic commentary — "HAM has just undercut VER with a 2.3s faster pit stop, and is now running in clean air on fresher rubber..." — based on live timing data from OpenF1.

**Integration pattern: New WebSocket message type on existing WS endpoint**

The existing `/api/live/{year}/{round_num}` WebSocket polls OpenF1 positions every 8 seconds. Commentary is generated by calling Gemini with position delta context.

```
Architecture addition:

routes.py (existing live_timing WebSocket handler)
    │
    ├── Existing: poll OpenF1 positions every 8s
    │
    └── New: Commentary generation every N polls (configurable, default: every 3rd poll = ~24s)
         │
         ├── Detect significant events:
         │   ├── Position change ≥ 2 places (overtake)
         │   ├── Position change at same lap count (likely pit stop)
         │   ├── Gap to leader increases suddenly (safety car / VSC)
         │   └── New session status message
         │
         ├── Build context string from position deltas
         │
         ├── Call Gemini (non-streaming, brief prompt) via asyncio
         │
         └── Broadcast new message type over existing WebSocket:
             {"type": "commentary", "data": {"text": "...", "trigger": "overtake"}}
```

**New WebSocket message type (additive, non-breaking):**
```python
# New message types added to existing WS handler
{"type": "positions", "data": [...]}     # existing
{"type": "commentary", "data": {...}}    # new
{"type": "session_status", "data": {...}} # new
{"type": "flag", "data": {...}}          # new
```

**iOS integration:** `LiveTimingService.swift` already decodes `LiveTimingData` as an enum with `positions`, `sessionStatus`, `flag` cases. Add `commentary` case. The `LiveTimingMessage` model handles this with a new enum case.

**Web integration:** Same pattern — the existing WebSocket client in the frontend listens to the WS stream and adds a commentary panel.

**Rate limiting constraint:** Gemini calls during live sessions must be rate-controlled. Do not call Gemini on every position update. Use an event detection threshold (position delta ≥ 2 places, or first occurrence of a gap change > 5 seconds) AND a minimum interval (30 seconds between commentary messages). This prevents cost explosion during safety car restarts where many positions change at once.

**Critical: do not block the polling loop.** Gemini call must be `asyncio.create_task()` — fire-and-forget with a timeout. If Gemini takes longer than the next poll interval, skip that commentary cycle. Do not await it inline.

```python
# Pattern:
async def _generate_commentary(context: str, connections: list[WebSocket]):
    try:
        response = await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content=context)]),
            timeout=10
        )
        for ws in connections:
            await ws.send_json({"type": "commentary", "data": {"text": response.content}})
    except asyncio.TimeoutError:
        pass  # Skip this commentary cycle

# In the polling loop:
if should_generate_commentary(positions, last_positions):
    asyncio.create_task(_generate_commentary(context, connections))
```

**Build dependency:** Requires the existing WebSocket infrastructure. No new endpoints. Depends on position data being available — only works during live sessions.

---

### Feature 3: iOS Push Notifications (Race Events)

**What it is:** Real-time push notifications for overtakes, safety cars, pit stops, and penalties during a live race. Requires APNs (Apple Push Notification service) and a server-side push mechanism.

**Critical architecture decision: local scheduled vs. server push**

The existing NotificationService uses `UNUserNotificationCenter` for LOCAL scheduled notifications (30 min and 5 min reminders). These work without any server involvement. TRUE real-time race event notifications (safety car deployed NOW, VER just overtook HAM) require APNs and server-to-device push.

**Recommended pattern: Hybrid — extend local notifications for sessions, add APNs for live events**

```
Session reminders (existing + expand):
    iOS NotificationService → UNCalendarNotificationTrigger
    Source: /api/schedule data, scheduled at app launch / calendar view
    Covers: Practice, Qualifying, Sprint, Race reminders (currently: race only)
    Build: LOW complexity, just extend existing NotificationService

Live event push (new — requires infrastructure):
    OpenF1 polling backend
        │
        ├── Detect: overtake, safety car, VSC, red flag, pit stop, penalty
        │
        ▼
    APNs (via python-apns2 or httpx to APNs HTTP/2 API)
        │
        ▼
    iOS device (UNUserNotificationCenter receives push)
```

**APNs integration requires:**
1. `GET /api/push/register` — receives device token from iOS, stores in-memory (or file-backed dict)
2. APNs p8 key file (uploaded to Render, loaded via env var path)
3. `python-apns2` or `httpx` with HTTP/2 for APNs API calls
4. Device token storage — in-memory dict keyed by session_key (lost on cold start — iOS must re-register each app launch)
5. iOS: call `UIApplication.shared.registerForRemoteNotifications()`, send token to backend

**Data flow for live push:**

```
iOS app launch
    │ POST /api/push/register {"device_token": "abc123", "session_key": "9999"}
    │
    ▼
Backend: stores {session_key: [device_tokens]}

OpenF1 polling loop (per active WS session)
    │
    ├── Detect significant event (overtake, flag change, safety car)
    │
    ├── Broadcast via WebSocket (existing — for connected clients)
    │
    └── If registered device tokens for this session_key:
            Send APNs push to each registered token
            {"aps": {"alert": {"title": "Safety Car", "body": "Debris on track..."}}}
```

**Build dependency:** This is the most complex new feature. It requires:
- APNs credentials (Apple Developer account — p8 key, Team ID, Bundle ID)
- New backend endpoint for device token registration
- httpx or python-apns2 for APNs HTTP/2 calls
- iOS: AppDelegate / notification delegate for remote notifications

**Render.com constraint:** APNs requires persistent HTTPS connections (HTTP/2). Render.com free tier supports this but the APNs connection pool will reset on cold start. Use httpx async client with http2=True rather than maintaining a persistent APNs connection.

**Recommended build order for notifications:**
1. First: extend local session reminders to cover FP1, FP2, FP3, Qualifying (easy win)
2. Second: APNs push for live events (major undertaking — own milestone phase)

---

### Feature 4: iOS Dynamic Island Live Activities

**What it is:** A live activity in the Dynamic Island showing current race position, gap to leader, and tire info for a followed driver during a live session.

**Integration pattern: ActivityKit + new backend SSE or WebSocket data contract**

Dynamic Island Live Activities use `ActivityKit` (not WidgetKit). They require:
- A `ActivityAttributes` struct defining static and dynamic data
- An `Activity<MyAttributes>` instance started from the main app
- Updates pushed to the activity via `activity.update()` in the main app (from WebSocket data)
- OR pushed server-side via APNs with `apns-push-type: liveactivity`

**Recommended: App-driven (not server-pushed) — simpler given existing WebSocket**

```
iOS LiveTimingService (existing WebSocket)
    │
    │ Receives position updates every 8s
    │
    ▼
LiveTimingViewModel (existing @Observable)
    │
    │ Detects followed-driver position change
    │
    ▼
LiveActivityManager (new)
    │
    ├── Start: Activity<F1LiveActivityAttributes>.request(attributes:, contentState:, ...)
    ├── Update: await activity.update(using: newContentState)
    └── End: await activity.end(dismissalPolicy: .immediate)
```

**Data contract (no backend changes needed):**
The existing WebSocket already provides `position`, `driver`, `gap`, `tyre`, and `pit_stops` fields in `LivePosition`. The Live Activity content state uses exactly this data.

```swift
// New files needed:
// ios/F1AI/Widgets/F1LiveActivity.swift    — ActivityAttributes + ContentState
// ios/F1AI/Services/LiveActivityManager.swift — start/update/end lifecycle
```

**Build dependency:** Requires the existing WebSocket to be functional and stable. No backend changes needed. Does NOT require APNs push for live activity updates (app-driven model). iOS 16.1+ required (ActivityKit minimum). All existing iOS target iOS 17.0+ so this is satisfied.

**WidgetKit vs ActivityKit distinction:** The existing `NextRaceWidget` uses `WidgetKit` (StaticConfiguration). Live Activities use `ActivityKit` and must be in a separate Widget Extension target OR the same extension with `ActivityConfiguration`. They share the F1AIWidgets target.

---

### Feature 5: Test Infrastructure

**What it is:** pytest test suite for backend tools and agentic loop; Jest/Vitest tests for frontend hooks; potential XCTest for iOS.

**Integration pattern: Tests alongside source, no architectural change**

```
backend/
├── tests/
│   ├── test_tools.py           ← Unit tests: mock FastF1, test tool output format
│   ├── test_routes.py          ← Integration tests: TestClient, mock LLM responses
│   ├── test_agentic_loop.py    ← Mock Gemini, verify tool dispatch and stream output
│   └── conftest.py             ← Shared fixtures (mock FastF1, mock Gemini)
│
frontend/
├── __tests__/
│   ├── useChat.test.ts         ← Mock fetch, verify stream parsing, tool status
│   └── ChatScreen.test.tsx     ← Render tests
```

**Key test isolation challenges:**
- FastF1 requires a cache directory and downloads data — mock with `pytest-mock` at the `fastf1.get_session` level
- Gemini calls must be mocked — use `langchain` testing utilities or `unittest.mock`
- ChromaDB re-initialization per call — test by mocking `Chroma` class
- Tool stream parsing in iOS `ChatStreamService` — Swift tests with XCTest

**Build dependency:** Tests can be added at any point. Start with tools (pure functions) before the agentic loop (more complex to mock).

---

### Feature 6: Performance Improvements

**What it is:** ChromaDB singleton, FastF1 lock improvements, WebSocket cleanup.

**ChromaDB singleton (fix re-initialization):**

```python
# In tools.py — replace per-call Chroma initialization:

# CURRENT (bad):
def consult_rulebook(query: str, year: int = None):
    embeddings = HuggingFaceEmbeddings(...)  # loads model every call
    vector_db = Chroma(...)                  # opens DB every call

# RECOMMENDED (good):
# Module-level singleton, initialized once at startup:
_embeddings: HuggingFaceEmbeddings | None = None
_vector_db: Chroma | None = None

def _get_vector_db() -> Chroma:
    global _embeddings, _vector_db
    if _vector_db is None:
        _embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        _vector_db = Chroma(persist_directory="data/chroma", embedding_function=_embeddings)
    return _vector_db
```

This change is purely internal to tools.py — no API contract changes, no client changes needed.

**FastF1 lock — no change to lock semantics, but add timeout logging:**

The threading.Lock() is correct — FastF1 is not thread-safe and must be serialized. The improvement is observability: log lock wait time so slow requests are visible. Do not try to parallelize FastF1 calls — it causes crashes.

**WebSocket connection cleanup:**

```python
# Current cleanup in finally block — works for normal disconnect
# Add: periodic heartbeat + cleanup task

async def _cleanup_stale_connections():
    """Background task: ping all connections, remove dead ones."""
    while True:
        await asyncio.sleep(60)
        for room, connections in list(_live_connections.items()):
            alive = []
            for ws in connections:
                try:
                    await asyncio.wait_for(ws.send_json({"type": "ping"}), timeout=2)
                    alive.append(ws)
                except Exception:
                    pass
            _live_connections[room] = alive
```

Add this to the lifespan context manager in main.py alongside the prefetch task.

---

## Component Boundaries (Complete View)

| Component | Responsibility | Communicates With | Does Not Do |
|-----------|---------------|-------------------|-------------|
| `routes.py` | HTTP + WS endpoint routing, agentic loop, live timing | tools.py, prompts.py, predictions.py | Business logic |
| `tools.py` | LLM-callable tools, FastF1 access, ChromaDB access | FastF1, Ergast, Tavily, ChromaDB | HTTP routing |
| `predictions.py` (new) | Statistical prediction computation | FastF1 (via lock), circuits.py | LLM calls, HTTP |
| `main.py` | App factory, CORS, background tasks | routes.py | Business logic |
| `ChromaDB` | FIA regulation vector store | `consult_rulebook` tool only | Live data |
| `APIClient.swift` | REST + WS client, SwiftData cache | Backend API | Data transformation |
| `ChatStreamService.swift` | Streaming text parser, tool marker extraction | Backend /api/chat | State management |
| `LiveTimingService.swift` | WebSocket lifecycle, message dispatch | Backend ws://live | Position processing |
| `NotificationService.swift` | Local + push notification scheduling | UNUserNotificationCenter, APNs (new) | Data fetching |
| `LiveActivityManager.swift` (new) | Dynamic Island activity lifecycle | LiveTimingViewModel, ActivityKit | Data fetching |
| `ViewModels/` | State management, data orchestration | Services, APIClient | UI rendering |
| `NextRaceWidget.swift` | Static schedule countdown | Backend /api/schedule directly | Chat, WebSocket |

---

## Data Flow Diagrams

### Chat + Tool Call Flow (Existing)

```
User types message
    │
    ▼ POST /api/chat (streaming)
FastAPI agentic loop
    │
    ├── LLM.ainvoke(messages)
    │       │
    │       └── if tool_calls:
    │               yield "[TOOL_START]Tool Name[/TOOL_START]"
    │               asyncio.to_thread(tool.invoke, args)   ← FastF1 goes here
    │               yield "[TOOL_END]Tool Name[/TOOL_END]"
    │               LLM.ainvoke(messages + tool_results)
    │
    └── if text response:
            yield text chunks
    │
    ▼ StreamingResponse (text/plain)
Client (Next.js: ReadableStream reader | iOS: URLSession.bytes)
    │
    └── Parse [TOOL_START/END] markers, stream text to UI
```

### Live Timing + Commentary Flow (New)

```
iOS/Web connects ws://api/live/{year}/{round}
    │
    ▼
WebSocket handler loop (8s interval)
    │
    ├── OpenF1 API poll → positions
    │       │
    │       ├── Broadcast {"type": "positions", "data": [...]}
    │       │
    │       └── Event detection:
    │               if significant_change(positions, last_positions)
    │               AND commentary_cooldown_elapsed():
    │                   asyncio.create_task(_generate_commentary(...))
    │                       │
    │                       └── Gemini.ainvoke(brief context prompt)
    │                               │
    │                               └── Broadcast {"type": "commentary", "data": {...}}
    │
    └── await asyncio.sleep(8)
```

### Push Notification Flow (New)

```
iOS app launch
    │ POST /api/push/register {device_token, session_key}
    ▼
Backend: _push_registry[session_key].append(device_token)

During live session polling (8s loop):
    │
    ├── Detect: safety_car | overtake | pit_stop | penalty
    │
    ├── Broadcast WebSocket (for connected clients)
    │
    └── For each token in _push_registry[session_key]:
            POST APNs HTTP/2 API
            {"aps": {"alert": {...}, "sound": "default"}}
```

### Prediction Data Flow (New)

```
Client: GET /api/predictions/{year}/{round_num}
    │
    ▼
asyncio.to_thread(_compute_predictions_sync, year, round_num)
    │
    ├── with _fastf1_lock:
    │       fastf1.get_session(year, round_num, "Q").load(...)
    │
    ├── Ergast: get last N races at this circuit
    │
    ├── circuits.py: get_circuit_info(location)
    │
    ▼
predictions.py: compute_predictions(quali, history, circuit)
    │
    ▼
Return JSON {predictions, strategy, confidence: "statistical"}
```

---

## Suggested Build Order

Based on dependencies between components:

### Layer 1 — Foundation (no dependencies on new features)

1. **ChromaDB singleton** — touches only tools.py, internal change, zero risk, immediate perf win
2. **WebSocket cleanup task** — touches only main.py and routes.py, adds reliability
3. **Extend local notifications** — extend NotificationService.swift for FP/Quali/Sprint reminders
4. **predictions.py module** — pure computation module, no UI, can be built and tested in isolation

### Layer 2 — Backend features (depend on Layer 1)

5. **Prediction endpoint** — `GET /api/predictions/{year}/{round_num}` + new LLM tools
6. **Live commentary** — extends existing WebSocket handler, depends on stable WS cleanup

### Layer 3 — Client features (depend on Layer 2)

7. **Prediction UI — Web** — consumes new prediction endpoint
8. **Prediction UI — iOS** — consumes new prediction endpoint, adds card to race detail
9. **Live commentary UI** — extends LiveTimingService to handle `commentary` message type
10. **Dynamic Island Live Activity** — depends on stable LiveTimingService WebSocket data

### Layer 4 — Push infrastructure (independent but complex)

11. **APNs device token registration** — new backend endpoint, iOS registration call
12. **APNs push for live events** — extends WebSocket polling loop

### Layer 5 — Tests (can begin at Layer 1, grows with features)

13. **Backend tool tests** — mock FastF1, test tool output format
14. **Agentic loop tests** — mock Gemini, verify tool dispatch
15. **Frontend hook tests** — mock fetch, verify stream parsing

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Parallelizing FastF1 Calls

**What:** Creating multiple threads each calling FastF1 session loads simultaneously.
**Why bad:** FastF1 is not thread-safe. Concurrent session loads corrupt internal FastF1 state and cause cryptic errors. The existing `_fastf1_lock` exists precisely to prevent this.
**Instead:** Queue FastF1 requests through the existing `_fastf1_lock` using `asyncio.to_thread`. For predictions that need multiple sessions (qualifying + race history), load them sequentially within the same `to_thread` call.

### Anti-Pattern 2: Blocking the Event Loop with Gemini During Live Commentary

**What:** `await llm.ainvoke(context)` inline in the WebSocket polling loop.
**Why bad:** If Gemini takes 5+ seconds, the next OpenF1 poll is delayed. All connected WebSocket clients stop receiving position updates.
**Instead:** `asyncio.create_task(_generate_commentary(...))` with internal timeout. Commentary is best-effort — missing one commentary cycle is acceptable.

### Anti-Pattern 3: Creating a New ChromaDB Connection Per Tool Call

**What:** Instantiating `HuggingFaceEmbeddings` and `Chroma` inside the `consult_rulebook` function body.
**Why bad:** Loading the embedding model from disk on every rulebook query adds 2-5 seconds of latency per call and wastes memory.
**Instead:** Module-level singleton initialized once on first use (lazy init pattern shown above).

### Anti-Pattern 4: Storing Device Tokens in In-Memory Dict Without Persistence

**What:** `_push_registry: dict[str, list[str]]` in routes.py — tokens are lost on cold start.
**Why bad:** Every cold start (Render.com sleeps every 15 min of inactivity) invalidates all device registrations. iOS users will stop receiving push notifications after any backend restart.
**Instead:** iOS app re-registers device token on every app foreground activation (`sceneDidBecomeActive`). Backend accepts re-registration without error. Since there's no user auth, use session_key as the registration scope (registration is only valid for the current live session).

### Anti-Pattern 5: Treating Live Activity as a Widget

**What:** Trying to implement Dynamic Island live activities using `WidgetKit` `StaticConfiguration` or `AppIntentConfiguration`.
**Why bad:** Dynamic Island live activities require `ActivityKit` (`import ActivityKit`) and `ActivityConfiguration` — a completely different API from WidgetKit. They cannot share a `WidgetConfiguration` entry point.
**Instead:** Add `ActivityConfiguration` in the existing F1AIWidgets extension. The `F1LiveActivityAttributes` struct and widget view live alongside the existing `NextRaceWidget`.

### Anti-Pattern 6: Calling Gemini for Every OpenF1 Poll During Commentary

**What:** Generating commentary on every 8-second position update regardless of change.
**Why bad:** During a 50-lap race, this is 50 × 60 × 60 / 8 = 22,500 Gemini calls. Cost explosion. Rate limit exhaustion.
**Instead:** Commentary only when: (a) a position change of 2+ places occurs, OR (b) a safety car/flag event detected, AND (c) minimum 30-second cooldown since last commentary.

---

## Scalability Considerations

| Concern | Current State | With New Features | Mitigation |
|---------|--------------|-------------------|------------|
| FastF1 serialization | All requests queue behind lock | Prediction requests add to queue | Predictions module calls FastF1 once, returns cached result |
| WebSocket fan-out | Single server, in-memory connections | Commentary adds Gemini call per event | create_task, 30s cooldown, max 2 concurrent commentary tasks |
| APNs throughput | Not used | Push per event per registered token | Batch tokens, limit push to top-priority events |
| ChromaDB | Re-init per call | Same (until singleton fix) | Singleton is Phase 1 fix |
| Cold start | 15-min sleep interval | Push registry lost on cold start | iOS re-registers on each foreground activation |
| Memory | In-memory race cache | Same pattern for push registry | Acceptable for single-process deployment scope |

---

## Sources

- Direct codebase inspection: `backend/app/api/routes.py`, `tools.py`, `main.py`, `prompts.py`, `rag/ingest.py`
- Direct codebase inspection: `ios/F1AI/Services/`, `Models/`, `ViewModels/`, `F1AIWidgets/`
- Direct codebase inspection: `frontend/app/hooks/useChat.ts`, `components/`
- Apple ActivityKit documentation (knowledge cutoff Jan 2025): ActivityKit requires iOS 16.1+, uses `ActivityAttributes` protocol
- FastAPI background tasks pattern: `asyncio.create_task()` in async handlers
- Confidence: HIGH — all architectural claims are derived from the actual codebase, not assumed
