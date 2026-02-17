# Domain Pitfalls: F1 AI Race Engineer

**Domain:** Real-time sports AI companion — F1 data, predictions, push notifications, iOS
**Researched:** 2026-02-16
**Confidence:** MEDIUM (training data + codebase context; WebSearch unavailable in this session)

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or production outages.

---

### Pitfall 1: FastF1 Global Session Lock Serializing All Requests

**What goes wrong:** FastF1 uses a module-level cache and in some code paths a process-level lock when loading session data. If two requests arrive for different sessions simultaneously, the second request blocks until the first completes. Under load (live race weekend, multiple users), p99 latency spikes to 30–120 seconds. The server appears hung.

**Why it happens:** FastF1 fetches and caches large Parquet/CSV files from the F1 timing server. The caching layer was designed for single-user offline analysis, not concurrent web service use. The `Cache.enable()` call and the internal `requests_cache` session are not thread-safe by default.

**Consequences:** Single slow request blocks all others. Render.com request timeout (default 30s) fires. Users see 504s during the exact moments they most want data (qualifying, race day). Cannot be fixed at the application layer without rearchitecting the data fetch layer.

**Warning signs:**
- Logs show requests queuing behind a single long-running FastF1 call
- Response times bimodal: fast (cache hit) or very slow (cache miss + lock contention)
- Timeouts cluster during session transitions (FP3 → Quali → Race)

**Prevention:**
- Run FastF1 fetches in a dedicated process pool (ProcessPoolExecutor, not ThreadPoolExecutor — the GIL does not protect FastF1's file I/O)
- Pre-warm cache for the active session at session start, not on first user request
- Serve stale cached data with a background refresh rather than blocking
- Set explicit per-fetch timeouts (10s) and return a 202+retry pattern rather than making the user wait

**Phase to address:** Data Infrastructure phase (before any feature that touches live session data)

---

### Pitfall 2: ChromaDB Re-initialization on Every API Call

**What goes wrong:** If the ChromaDB client is instantiated inside a request handler or per-call function, each call pays the initialization cost: opening the SQLite WAL, loading the HNSW index into memory, and establishing internal state. On a cold process this is 1–3 seconds. Under concurrency it creates lock contention on the SQLite file.

**Why it happens:** Easy to write `client = chromadb.Client()` inside a function during development. Works fine in a notebook or single test. Breaks under any real request load.

**Consequences:** Latency floor of 1–3s on every LLM-augmented response. SQLite file lock errors under concurrent requests. Chroma's HNSW index is rebuilt from disk on every call, defeating the purpose of a vector store.

**Warning signs:**
- Logs show "chromadb.Client()" appearing in per-request traces
- Latency on RAG-augmented endpoints is always slow regardless of query complexity
- SQLite "database is locked" errors in logs

**Prevention:**
- Initialize ChromaDB client exactly once at application startup (module-level or FastAPI lifespan event)
- Use `PersistentClient` with a fixed path, not an in-memory or ephemeral client
- For Render.com: persist the Chroma data directory on a mounted disk or replace with a managed vector DB (Pinecone free tier, Weaviate Cloud) to survive deploys
- Add a health check that verifies Chroma is reachable at startup

**Phase to address:** Core Infrastructure stabilization (first phase of this milestone)

---

### Pitfall 3: WebSocket Dead Connection Accumulation

**What goes wrong:** Mobile clients (iOS) go to background, switch networks, or lose connectivity without sending a clean close frame. The server retains the connection object in its connection registry. Over hours, the registry fills with dead connections. Broadcasts to dead connections raise exceptions that, if unhandled, can crash the WebSocket task. Memory grows unboundedly.

**Why it happens:** TCP connections do not fail immediately when a client disappears. The OS keep-alive mechanism takes minutes to detect a dead peer. Application-level code that only tracks `connect`/`disconnect` events never sees the disconnect for a silently-dropped client.

**Consequences:** Memory leak on long-running processes. Broadcast latency grows as the server attempts to write to each dead socket. On Render.com's free tier, memory limits cause OOM restarts, which drops all live connections.

**Warning signs:**
- `len(connected_clients)` grows monotonically during a race session and never shrinks
- Broadcast takes longer over time as the race progresses
- Occasional unhandled `ConnectionResetError` or `BrokenPipeError` in WebSocket send code

**Prevention:**
- Implement application-level heartbeat: server sends a ping frame every 15–20s; remove connections that do not respond within 10s
- Use structured connection registry (dict keyed by connection ID) with explicit cleanup on both `disconnect` event and failed send
- Wrap all WebSocket send calls in try/except; on any send failure, remove that connection immediately
- Log connection count as a metric; alert if it grows beyond expected concurrent users

**Phase to address:** WebSocket/Live Commentary phase (before shipping any real-time feature)

---

### Pitfall 4: Apple Push Notification Complexity Underestimated

**What goes wrong:** APNs (Apple Push Notification service) requires: a valid APNs auth key or certificate, correct bundle ID, correct environment (sandbox vs production), HTTP/2 connection pooling, token-based auth with JWT expiry, and correct payload structure. Dynamic Island requires Live Activities with ActivityKit, a separate entitlement, a specific payload format (`aps.content-state`), and a push-to-start token distinct from the regular device token. Teams routinely spend 2–3x their estimated time on this.

**Why it happens:** Apple's documentation is split across four separate frameworks (UserNotifications, ActivityKit, PushKit, BackgroundTasks). The sandbox and production environments behave differently. Device tokens expire and must be refreshed. The JWT for token-based auth expires every hour and must be regenerated.

**Consequences:** Push notifications work in development but fail silently in production (wrong environment). Dynamic Island does not update (wrong token type used). Background refresh drains battery and gets rate-limited by iOS. Users on older iOS versions (pre-16.1) have no Live Activities support.

**Warning signs:**
- APNs returning 400 "BadDeviceToken" errors
- Live Activity not updating despite pushes being sent
- "Push to start" token never arriving on device
- Notifications arriving with minutes of delay

**Prevention:**
- Use a push notification library that handles JWT rotation (e.g., `httpx` + manual JWT, or a dedicated APNs library)
- Treat push tokens as ephemeral: store with timestamp, re-request on every app launch, handle `didFailToRegisterForRemoteNotificationsWithError`
- Separate the regular notification token from the Live Activity push token — they are different
- Build and test on a physical device from day one; simulator APNs behavior is unreliable
- Gate Live Activities behind an iOS version check (require iOS 16.1+)
- Start with basic push notifications; add Dynamic Island as a separate sub-phase after basic push is confirmed working

**Phase to address:** iOS Push Notifications phase — split into (a) basic APNs, (b) Dynamic Island as separate deliverables

---

### Pitfall 5: Render.com Cold Start Killing Real-Time UX

**What goes wrong:** Render.com free/starter tier spins down after 15 minutes of inactivity. Cold start on a Python FastAPI service with FastF1, ChromaDB, and ML model loading takes 30–90 seconds. WebSocket clients connecting during cold start get connection refused or timeout. For a race-day app, cold starts happen exactly when traffic spikes (weekend race, previously idle weekdays).

**Why it happens:** Render's free tier is explicitly designed to spin down. Paid tiers (Starter $7/mo) keep processes alive but still have zero-downtime deploys that cause brief disconnects.

**Consequences:** First user after idle period waits 60–90s. WebSocket reconnect logic on iOS must handle this or the app appears broken. Any long-running FastF1 cache warm-up happens during the cold start, making it longer.

**Warning signs:**
- First request after idle takes >30s
- Logs show application starting from scratch (Python imports, model loading) on a request
- WebSocket client logs show repeated reconnection attempts

**Prevention:**
- Use a cron job or uptime service (UptimeRobot free tier) to ping the health endpoint every 14 minutes, preventing spin-down
- Implement eager startup in FastAPI `lifespan`: load models, initialize Chroma, pre-warm FastF1 cache for current/upcoming session
- Build aggressive WebSocket reconnection into the iOS client with exponential backoff + jitter
- Document that the app requires a paid Render tier for race-day reliability (important for portfolio presentation)

**Phase to address:** Infrastructure phase; iOS client must handle this in the WebSocket phase

---

### Pitfall 6: Prediction Accuracy Expectations from F1 Fans

**What goes wrong:** F1 fans are among the most technically literate sports fans in the world. Presenting an ML model's race outcome prediction as authoritative will be immediately scrutinized. Models that use historical data will be visibly wrong on street circuits, wet weather, safety car scenarios, and rookie seasons. Users will lose trust not in the prediction but in the entire app.

**Why it happens:** Developers frame predictions as "AI" without conveying uncertainty. A model predicting Verstappen wins every race in 2023 was statistically correct but useless. Contextual factors (tire strategy, pit stop timing, VSC/SC deployment) are hard to encode and are the actual interesting variables for fans.

**Consequences:** One viral post mocking a bad prediction can permanently damage perception of a portfolio project. Overclaiming accuracy also undermines the engineering credibility the project is meant to demonstrate.

**Warning signs:**
- Predictions display as single values ("Verstappen will win") without confidence intervals
- Model is not retrained after major regulation changes
- No acknowledgment of limitations in the UI

**Prevention:**
- Always display predictions with uncertainty ranges ("60–75% probability")
- Frame as "Race Engineer Analysis" not "Prediction" — position it as reasoning support, not oracle
- Show model inputs and reasoning, not just outputs ("Based on current tire age, pit stop delta of 22s, and VSC probability...")
- Explicitly call out what the model cannot know (safety car timing, mechanical failures)
- A rule-based system with transparent logic often outperforms an opaque ML model for fan trust

**Phase to address:** Predictions phase — UI/UX framing is as important as model accuracy

---

## Moderate Pitfalls

---

### Pitfall 7: Dead MCP Code and Removed Prediction Module References

**What goes wrong:** Existing codebase contains MCP code referencing prediction modules that have been removed. This creates import-time failures that can mask real errors, confuse future developers, and make the test suite non-deterministic (some paths fail silently, some fail loudly depending on import order).

**Prevention:**
- Audit and remove all dead code before adding new features — dead code is a debt multiplier
- Run `python -c "import app"` as a CI step to catch import-time errors
- Remove all MCP stubs referencing deleted modules before the predictions phase begins

**Phase to address:** Infrastructure cleanup (first task in the milestone)

---

### Pitfall 8: Relaxed LLM Safety Settings in Production

**What goes wrong:** Development often uses relaxed safety filters to speed up iteration. Shipping those settings to production exposes the app to prompt injection via F1 data (e.g., a driver name, team radio transcript, or race comment that manipulates the LLM) and potential ToS violations with the LLM provider.

**Prevention:**
- Restore default safety settings before any feature ships to production
- Sanitize all external data (FastF1 telemetry fields, team radio transcripts) before including in prompts
- Add input validation: reject prompts over a character limit, containing suspicious patterns
- Log all LLM inputs/outputs for audit (redacted if needed)

**Phase to address:** Security review before any public deployment

---

### Pitfall 9: No Structured Logging Making Production Debugging Impossible

**What goes wrong:** `print()` statements and unstructured logs mean that on Render.com, all output is a flat stream. When a live race WebSocket broadcast fails at 3pm on a Sunday, there is no way to correlate the failure with a specific session, user, or data fetch. Render's log retention is short (hours to days on free tier).

**Prevention:**
- Replace all `print()` with Python's `logging` module configured to emit JSON
- Include structured fields: `session_id`, `circuit`, `request_id`, `user_connection_id`
- Use log levels correctly: DEBUG for telemetry, INFO for lifecycle events, WARNING for degraded state, ERROR for failures
- Forward logs to a free external service (Papertrail, Logtail) before they expire on Render

**Phase to address:** Infrastructure phase — logging must be in place before real-time features are built

---

### Pitfall 10: Hardcoded Timeouts Causing Cascading Failures

**What goes wrong:** A single hardcoded timeout value (e.g., 30s for all external calls) means that a slow FastF1 fetch blocks a WebSocket handler that has a 30s client-side timeout, which causes the iOS app to show a spinner, which causes the user to tap retry, which creates another blocked request. Cascading.

**Prevention:**
- Use different timeouts per operation type: FastF1 fetch (60s, with 10s stale-serve fallback), LLM call (15s), APNs push (5s), WebSocket heartbeat (10s)
- Never share a timeout constant across different operation types
- Circuit-break external dependencies: after 3 consecutive timeouts, serve cached/degraded response for 60s before retrying

**Phase to address:** Infrastructure phase

---

### Pitfall 11: OpenF1 API Availability During Live Races

**What goes wrong:** OpenF1 (the open real-time F1 data API) has been unreliable during peak load — specifically during qualifying and race sessions when every developer's project is hitting it simultaneously. Rate limits are not well-documented. The API sometimes returns stale data (5–30 seconds behind) during high-pace moments.

**Why it happens:** OpenF1 is a community-run API, not an official FOM service. It depends on the same upstream timing feed. Infrastructure is not sized for worldwide race-day traffic.

**Consequences:** Live commentary feature goes silent exactly during the most exciting moments of a race (SC deployment, pit stop window, final lap).

**Warning signs:**
- API returning 429 or 503 during qualifying/race sessions
- Telemetry timestamps not advancing for 10+ seconds

**Prevention:**
- Implement a local data cache layer: store the last N telemetry records; serve cached data with a "Data delayed" indicator rather than showing nothing
- Poll OpenF1 at a conservative rate (1–2s interval, not as fast as possible)
- Have a fallback to a degraded-but-stable data source for commentary if live data is unavailable
- Build the commentary system to handle gaps gracefully ("Waiting for live data...")

**Phase to address:** Live Commentary phase

---

### Pitfall 12: iOS Background App Refresh Constraints

**What goes wrong:** iOS aggressively suspends background apps. A WebSocket connection held open by a background iOS app will be silently killed by iOS within 30 seconds of backgrounding. An app that assumes the WebSocket is alive when it returns to foreground will show stale data until the next data event, which can be minutes.

**Prevention:**
- Use push notifications (APNs) to deliver updates when the app is backgrounded, not WebSocket
- On app foreground (`sceneDidBecomeActive`), immediately reconnect WebSocket and fetch current state via REST before resuming live feed
- Use Live Activities + push-to-update for Dynamic Island — this is exactly what the API is designed for and works in background
- Do not use PushKit (VoIP pushes) to work around this — it violates Apple's guidelines and risks App Store rejection

**Phase to address:** iOS client phase

---

## Minor Pitfalls

---

### Pitfall 13: FastF1 Cache Growing Without Bound

**What goes wrong:** FastF1 downloads session data files (can be 50–200MB per session). On a server with limited disk (Render.com Starter has 512MB ephemeral disk), the cache fills over a season. New session data cannot be fetched. The app starts returning errors with no obvious cause.

**Prevention:**
- Set `Cache.enable(cache_path)` with a path on the persistent disk
- Implement a cache eviction policy: keep only the last 3 sessions, delete older files
- Monitor disk usage as a metric; alert at 80% full

---

### Pitfall 14: LLM Context Window Exhaustion on Long Race Sessions

**What goes wrong:** A race is ~90 minutes. If every telemetry update is appended to the conversation context and sent to the LLM, the context window fills up around lap 30–40. The LLM call starts failing, or the system silently truncates context, losing the early-race narrative.

**Prevention:**
- Use a sliding window: keep the last N events in context, not the full race history
- Summarize older context: "Laps 1–20: Verstappen led throughout, one VSC for debris" as a compressed prefix
- Use ChromaDB for retrieval-augmented context: retrieve the 3–5 most relevant historical moments rather than the full timeline

---

### Pitfall 15: Confusing Session State Between Practice, Qualifying, and Race

**What goes wrong:** FastF1 session types (FP1, FP2, FP3, Q, SQ, R, S) have different data schemas. A prediction model trained on Race data applied to Sprint Qualifying returns nonsense. Commentary prompts written for Race format produce incorrect analysis during Sprint weekends.

**Prevention:**
- Always pass session type through to all data processing and prompt generation code
- Test each feature against at least: a regular race weekend session, a sprint weekend session, and an off-season state (no active session)
- The 2024–2025 calendar has 6 sprint weekends; this is not an edge case

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Infrastructure cleanup | Dead MCP imports cause silent failures | Run import-time checks in CI immediately |
| Infrastructure cleanup | Relaxed LLM safety settings ship to prod | Add safety config review to deploy checklist |
| Core data layer | FastF1 global lock under concurrency | Use ProcessPoolExecutor; pre-warm on startup |
| Core data layer | ChromaDB re-init per call | Module-level singleton; FastAPI lifespan |
| Core data layer | Disk full from FastF1 cache | Eviction policy; monitor disk usage |
| WebSocket / live | Dead connections accumulate | Heartbeat + explicit cleanup on failed send |
| WebSocket / live | OpenF1 unavailable during races | Stale-serve cache; degrade gracefully |
| Live commentary | LLM context exhaustion over race | Sliding window + summarization |
| Live commentary | Sprint weekend schema mismatches | Session-type-aware prompts and data paths |
| Predictions | Overclaiming accuracy to fans | Frame as probability + reasoning, not oracle |
| iOS push (basic) | APNs environment mismatch (sandbox vs prod) | Separate configurations; test on device |
| iOS push (basic) | Device token expiry not handled | Re-register on every app launch |
| iOS push (Dynamic Island) | Push-to-start token different from device token | Separate token collection flow |
| iOS push (Dynamic Island) | iOS version gating missing | Require iOS 16.1+; degrade gracefully |
| iOS client | WebSocket killed in background | Push for background; reconnect on foreground |
| iOS client | Cold start not handled in reconnect logic | Exponential backoff with long max (120s) |
| All phases | No structured logging | JSON logging + external retention before shipping |
| All phases | 0% test coverage compounds all bugs | Add tests per phase; never merge untested infra |
| Deployment | Render cold starts on race day | Uptime ping + eager startup; document paid tier need |
| Deployment | Render ephemeral disk loses Chroma data | Mount persistent disk or use managed vector DB |

---

## Sources

**Confidence notes:**
- FastF1 locking behavior: MEDIUM confidence (well-known in Python F1 community; could not verify current FastF1 version behavior via web search in this session)
- ChromaDB initialization: HIGH confidence (standard Python singleton pattern, documented ChromaDB behavior)
- APNs / Dynamic Island complexity: HIGH confidence (Apple developer documentation, well-known complexity)
- OpenF1 reliability: MEDIUM confidence (community reports; could not verify current status)
- Render.com cold starts: HIGH confidence (documented Render behavior, widely reported)
- Prediction framing: HIGH confidence (general ML deployment best practice)
- iOS background constraints: HIGH confidence (Apple UIKit/SwiftUI documented behavior)

All claims marked MEDIUM confidence should be verified against current FastF1 GitHub issues and OpenF1 API status before the relevant phase begins.
