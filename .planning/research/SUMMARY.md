# Project Research Summary

**Project:** F1 AI Companion App — New Capabilities Milestone
**Domain:** Real-time sports AI companion — three-platform (iOS, Web, Backend) with live timing, agentic LLM, and push infrastructure
**Researched:** 2026-02-16
**Confidence:** MEDIUM (stack HIGH from direct codebase inspection; features/pitfalls MEDIUM from training knowledge)

## Executive Summary

This is a brownfield milestone on an existing, functional F1 AI race engineer app with a FastAPI backend (Render.com), Next.js web frontend (Vercel), and SwiftUI iOS app. The existing system is feature-rich — 11 agentic LLM tools, live WebSocket timing, FastF1 data, ChromaDB RAG — but it has three production-grade problems that must be fixed before new capabilities are added: ChromaDB is re-initialized on every request (2-5s latency hit), WebSocket connections accumulate without cleanup (memory leak), and the FastF1 global lock will serialize all concurrent requests under race-day load. These are not optional cleanups — they are load-bearing fixes that gate everything else.

The recommended approach is to layer new capabilities in dependency order: fix the infrastructure first, add backend data features (predictions, weather), surface them in client UIs, then tackle the highest-complexity items (Dynamic Island, real-time AI commentary, APNs push) that depend on everything below being stable. The tech research confirms no new major runtime dependencies are needed for predictions or architecture changes — scipy and pandas already ship with FastF1, SSE-starlette is the only meaningful new backend library, and iOS additions use Apple system frameworks (ActivityKit, UserNotifications) exclusively. Testing infrastructure (pytest + pytest-asyncio for backend, Vitest + MSW for frontend) is the other addition that pays compounding dividends across all subsequent phases.

The highest risks are: (1) APNs push notification complexity is routinely underestimated — it requires Apple Developer credentials, separate token types for regular vs Live Activity pushes, and physical device testing; it should be its own dedicated phase. (2) Render.com free tier cold starts will kill real-time UX on race day without an uptime ping service and aggressive iOS reconnection logic. (3) Prediction framing matters as much as accuracy — F1 fans are technically literate and will distrust the entire app if predictions are presented as oracular rather than probabilistic reasoning with explicit uncertainty.

---

## Key Findings

### Recommended Stack

The existing stack (FastAPI + LangChain/Gemini + FastF1 + ChromaDB + Next.js + SwiftUI) is already appropriate and must not be replaced. All new capabilities are achievable with minimal additions. For testing: `pytest`, `pytest-asyncio`, `pytest-mock`, and `respx` on the backend; `vitest`, `@testing-library/react`, and `msw` on the frontend. For live commentary: `sse-starlette` (thin SSE wrapper). For APNs: `PyJWT` and `cryptography`. No ML training libraries (scikit-learn, XGBoost) should be added — statistical/heuristic predictions using existing `pandas` and `scipy` are sufficient and produce more interpretable output for F1 fans.

**Core new technologies:**
- `pytest` + `pytest-asyncio`: backend test runner — required because the existing `generate()` route uses async streaming that `TestClient` cannot properly test
- `vitest` + `msw`: frontend testing — Jest fails on the ESM/Next.js 16 combination; Vitest is native ESM with MSW streaming support
- `sse-starlette`: SSE for AI commentary — commentary is unidirectional push; SSE is simpler than WebSocket for this pattern
- `PyJWT`: APNs JWT token signing — direct APNs without Firebase vendor lock-in, correct for a portfolio-scale project
- `ActivityKit` (Apple system framework): Dynamic Island live activities — already satisfied by iOS 17.0 target; no version gating needed

See `.planning/research/STACK.md` for full installation commands and version rationale.

### Expected Features

**Must have (table stakes) — already expected by users or gates other features:**
- Live weather + track conditions — existing tool is a stub; AI race/strategy analysis is incomplete without it
- Push notifications for all session types — FP1/FP2/FP3/Quali uncovered; existing scaffold just needs extension
- AI predictions on iOS — backend ML exists; no iOS UI surfaces it; high visibility for low effort
- AI championship scenario on iOS — backend calculator exists; same situation as predictions
- Error handling + offline UX — blank screens and unhandled errors disqualify a portfolio piece
- Unit + integration tests — zero current coverage; required to demonstrate engineering discipline
- Dynamic Island live activity — iOS-native, technically non-trivial, strong portfolio signal
- Backend performance: ChromaDB singleton + WebSocket cleanup — production-blocking issues

**Should have (differentiators):**
- Real-time AI commentary — highest differentiation but highest complexity; fire-and-forget Gemini on significant timing events
- Multi-widget suite — three additional WidgetKit widgets; no new backend work
- Shareable AI analysis cards — extend existing ShareableResultCard to cover AI chat messages
- Race engineer persona depth — technical depth preference setting; prompt engineering only
- Tyre degradation visualisation — SwiftUI Charts + new stint API endpoint

**Defer to subsequent milestone:**
- Strategy simulator — depends on live weather and stable performance layer
- AI race preview scheduled job — APScheduler + storage adds backend complexity before hardening is solid
- Historical head-to-head stats — incremental; Ergast multi-year reliable but not differentiated

**Anti-features — never build:**
- Real-time lap telemetry streaming (legal/technical impossibility with FastF1)
- Fantasy F1, social features, betting odds (scope explosion or legal risk)
- Android app (doubles maintenance cost, fragments portfolio focus)

See `.planning/research/FEATURES.md` for full dependency graph.

### Architecture Approach

The app follows a strict layered architecture: FastAPI backend owns all business logic and data fetching; the agentic loop (Gemini + 11 LangChain tools) handles all natural language; clients (Next.js, iOS, WidgetKit) are pure consumers with no business logic. All new features must respect this boundary. Predictions get a new `predictions.py` module and REST endpoint. Live AI commentary extends the existing WebSocket as a new message type (`{"type": "commentary", ...}`) — additive and non-breaking. Dynamic Island uses an app-driven model (LiveTimingViewModel pushes ActivityKit updates from existing WebSocket data) so no backend changes are needed. APNs requires a new `POST /api/push/register` endpoint and a backend token registry, but device tokens must be treated as ephemeral (re-register on every app launch; cold start clears in-memory registry).

**Major components:**
1. `predictions.py` (new) — pure computation module, no LLM calls, no HTTP; feeds new REST endpoint and two new LangChain tools
2. `LiveActivityManager.swift` (new) — ActivityKit lifecycle manager fed by existing LiveTimingViewModel; no backend changes
3. APNs push layer (new) — backend token registry + httpx HTTP/2 to APNs; iOS `registerForRemoteNotifications` + token delivery to backend

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams and anti-patterns.

### Critical Pitfalls

1. **FastF1 global lock serializing all requests** — Under race-day load, a single slow FastF1 call blocks every other request. Use ProcessPoolExecutor for FastF1 fetches (not ThreadPoolExecutor — GIL does not protect file I/O), pre-warm cache on startup, and serve stale data with background refresh rather than blocking. Do not try to parallelize FastF1 calls — this causes crashes due to FastF1's non-thread-safe internals.

2. **ChromaDB re-initialization per call** — Already identified in codebase: `consult_rulebook` creates a new `HuggingFaceEmbeddings` + `Chroma` instance on every invocation. Fix is a module-level lazy singleton (`_get_vector_db()`). This is a Phase 1 task with zero risk — internal to tools.py, no API contract changes.

3. **APNs complexity is routinely underestimated** — Regular device tokens, Live Activity push tokens, and push-to-start tokens are three different things. Sandbox vs production environments fail silently. Build on physical device from day one. Split basic APNs and Dynamic Island into separate sub-phases; do not attempt both simultaneously.

4. **Render.com cold starts on race day** — Free tier spins down after 15 minutes of inactivity. Cold start with FastF1 + ChromaDB + ML model = 30-90 second delay. Prevention: UptimeRobot free-tier ping every 14 minutes + eager startup in FastAPI lifespan. Document that race-day reliability requires paid Render tier.

5. **Prediction framing destroys trust if done wrong** — F1 fans are among the most technically literate sports audiences. Display predictions as probability ranges with visible reasoning ("Based on tire age and pit delta..."), not as single-value outputs. Frame as "Race Engineer Analysis," not "Prediction." A rule-based system with transparent logic earns more fan trust than an opaque ML oracle.

---

## Implications for Roadmap

Based on the dependency graph across all four research files, a six-phase structure is recommended.

### Phase 1: Infrastructure Hardening
**Rationale:** Three production-blocking issues (ChromaDB re-init, WebSocket leak, dead MCP imports) must be fixed before any new feature is added. These are foundational — every subsequent phase runs on top of them. The risk of adding features on top of unfixed infrastructure is compounding bug debt.
**Delivers:** Stable, monitorable backend; ChromaDB singleton; WebSocket heartbeat cleanup; structured JSON logging; dead code removal; LLM safety settings review.
**Addresses:** Table stakes — backend performance, error handling groundwork.
**Avoids:** Pitfalls 2 (ChromaDB), 3 (WebSocket), 7 (dead MCP code), 8 (relaxed LLM safety), 9 (no structured logging), 10 (hardcoded timeouts).
**Research flag:** Standard patterns — well-documented FastAPI lifespan, singleton, and logging patterns. Skip research-phase.

### Phase 2: Test Infrastructure
**Rationale:** Zero current test coverage means any subsequent feature addition is unverifiable. Tests must be established before the codebase grows further. Starting immediately after infrastructure hardening means tests can cover the fixed code and serve as regression guards.
**Delivers:** pytest suite covering critical backend routes and tools; Vitest suite covering frontend hooks; XCTest stubs for iOS ViewModels; CI configuration.
**Uses:** `pytest`, `pytest-asyncio`, `respx` (backend); `vitest`, `msw` (frontend).
**Implements:** Architecture's test isolation patterns — mock FastF1 at `fastf1.get_session` level; mock Gemini with `unittest.mock`.
**Avoids:** Pitfall — 0% test coverage compounds all bugs in every subsequent phase.
**Research flag:** Standard patterns. Skip research-phase.

### Phase 3: Core Data and Backend Features
**Rationale:** Live weather completes the stub tool and unblocks AI preview and strategy features. Predictions module is a pure computation layer with no client dependencies — build it here so clients can consume it in the next phase. This phase has no APNs or iOS complexity.
**Delivers:** `predictions.py` module + `GET /api/predictions/{year}/{round_num}` endpoint; two new LangChain tools (`predict_race_outcome`, `analyze_pit_strategy`); live weather/track conditions integration (OpenWeatherMap); all expressed as statistical/heuristic outputs with probability framing.
**Uses:** `pandas`, `scipy` (already present via FastF1); OpenWeatherMap or WeatherAPI free tier.
**Avoids:** Pitfall 6 (prediction accuracy framing — build UI language into the API response format from the start).
**Research flag:** Needs research-phase — OpenWeatherMap API integration for F1 venue coverage, and weather data schema for strategy prompts, should be verified before implementation.

### Phase 4: Client Feature Surface
**Rationale:** Backend capabilities from Phase 3 are now ready to surface. iOS and web prediction UIs require no new backend work. Extending local push notifications to cover all session types is a low-effort, high-perceived-value change. AI championship scenario UI reuses existing backend calculator. This phase maximises visible output for minimal new risk.
**Delivers:** iOS PredictionsView + PredictionsViewModel; Web prediction panel; iOS championship scenario view; push notifications for FP1/FP2/FP3/Qualifying/Sprint (local UNCalendarNotificationTrigger, not APNs); error handling and empty-state views across all iOS and web screens.
**Implements:** Architecture's client-as-pure-consumer boundary — no business logic in clients.
**Avoids:** Pitfall 15 (session state confusion — test features against sprint weekend schemas explicitly).
**Research flag:** Standard patterns. Skip research-phase.

### Phase 5: Dynamic Island and Live AI Commentary
**Rationale:** Dynamic Island uses the existing WebSocket data stream via app-driven ActivityKit — no backend changes, but requires stable LiveTimingService from Phase 4. Live AI commentary extends the existing WebSocket as a new message type — requires stable WebSocket infrastructure from Phase 1 and the commentary rate-limiting pattern to avoid Gemini cost explosion.
**Delivers:** `LiveActivityManager.swift` + `F1LiveActivityAttributes` struct + Dynamic Island compact/expanded UI; commentary event detection in WebSocket loop with 30-second cooldown; `{"type": "commentary"}` WebSocket message broadcast; iOS and web commentary panel UI.
**Uses:** `ActivityKit` (Apple system framework, iOS 17.0 target); `asyncio.create_task()` fire-and-forget commentary generation with 10s timeout.
**Avoids:** Pitfalls 3 (WebSocket cleanup — Phase 1 fixes this first), Anti-Pattern 2 (blocking event loop with Gemini), Anti-Pattern 6 (calling Gemini on every poll), Pitfall 11 (OpenF1 unavailability — commentary must degrade gracefully), Pitfall 14 (LLM context exhaustion — use sliding window of last N events), Pitfall 12 (iOS background WebSocket killed — Live Activity handles background case).
**Research flag:** Needs research-phase — verify OpenF1 API rate limits and current reliability status; verify ActivityKit entitlement configuration for the XcodeGen project.yml format.

### Phase 6: APNs Push Infrastructure
**Rationale:** This is deliberately last — it requires Apple Developer infrastructure (p8 key, Team ID, Bundle ID) that is orthogonal to all other development, and its complexity is routinely underestimated. Building it after everything else is stable means the push events themselves (overtake, safety car) are already detected in the WebSocket loop from Phase 5.
**Delivers:** `POST /api/push/register` backend endpoint with in-memory device token registry; `PyJWT` APNs JWT token generation; APNs HTTP/2 push for live race events (overtake, safety car, red flag); iOS `UIApplication.registerForRemoteNotifications()` + token delivery; re-registration on every app foreground activation. Dynamic Island push-to-update as a stretch goal after basic APNs is confirmed working on physical device.
**Uses:** `PyJWT` + `cryptography`; `httpx` (already in requirements) with `http2=True`.
**Avoids:** Pitfall 4 (APNs complexity — split basic push and Dynamic Island push into separate deliverables; test on physical device from day one; treat tokens as ephemeral; separate sandbox vs production configurations), Pitfall 5 (cold start clears push registry — iOS must re-register on every foreground activation), Anti-Pattern 4 (in-memory token dict without persistence).
**Research flag:** Needs research-phase — verify current APNs HTTP/2 payload format for Live Activities (`apns-push-type: liveactivity`), p8 key configuration on Render.com, and `python-apns2` vs direct `httpx` HTTP/2 current best practice.

### Phase Ordering Rationale

- Phases 1 and 2 (infrastructure + tests) must come first because every subsequent phase runs on these foundations. Skipping them creates compounding bug debt.
- Phase 3 (backend data) before Phase 4 (client surface) is forced by the dependency graph — clients cannot consume what the backend does not yet serve.
- Phase 5 (Dynamic Island + commentary) before Phase 6 (APNs) because the commentary event detection logic in Phase 5 is exactly what Phase 6 reuses for push triggers. Building Phase 5 first means Phase 6 has a working event pipeline to integrate with.
- Phase 6 (APNs) is last by deliberate choice: it requires external infrastructure (Apple Developer credentials), has the highest complexity, and its value is additive — every phase before it delivers complete, shippable features.

### Research Flags

Needs research-phase during planning:
- **Phase 3:** OpenWeatherMap/WeatherAPI integration — confirm venue coverage, API rate limits, and schema mapping to strategy prompt inputs before implementation.
- **Phase 5:** ActivityKit XcodeGen configuration — verify `project.yml` entitlement format for Live Activities in the existing XcodeGen setup; ActivityKit entitlement is required and must be added correctly.
- **Phase 5:** OpenF1 API current reliability — verify current rate limit documentation and reliability status before designing commentary degradation strategy.
- **Phase 6:** APNs Live Activity push payload — verify `aps.content-state` format and `apns-push-type: liveactivity` behavior against current Apple documentation; this changes between iOS versions.

Phases with standard patterns (skip research-phase):
- **Phase 1:** FastAPI lifespan singleton, WebSocket heartbeat, structured logging — all well-documented, established patterns.
- **Phase 2:** pytest-asyncio + Vitest configuration — both have complete official documentation and follow established patterns for FastAPI and Next.js.
- **Phase 4:** Local UNCalendarNotificationTrigger extension, SwiftUI view composition — standard iOS patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All new additions verified against existing codebase (direct inspection); no speculative dependencies added |
| Features | MEDIUM | Baseline inventory from direct code inspection (HIGH); feature categorisation relative to competitors from training knowledge (MEDIUM); no web access to verify current competitor feature sets |
| Architecture | HIGH | All claims derived from direct codebase inspection; component boundaries, data flows, and anti-patterns are based on actual code read |
| Pitfalls | MEDIUM | ChromaDB, Render cold starts, iOS background constraints: HIGH confidence (documented behavior). FastF1 locking under load, OpenF1 reliability: MEDIUM confidence (could not verify current FastF1 version or OpenF1 SLA via web search) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **FastF1 thread safety on current version:** PITFALLS.md recommends ProcessPoolExecutor, but could not verify if current FastF1 version has improved concurrency handling. Verify against FastF1 GitHub issues before Phase 1 implementation.
- **OpenF1 API current rate limits and SLA:** Community reports suggest unreliability during races, but no official SLA exists. Monitor during Phase 5 testing on a live race weekend; design commentary to degrade gracefully regardless.
- **Apple Developer account prerequisite for Phase 6:** APNs requires a paid Apple Developer account and a p8 auth key. This is infrastructure, not code. Confirm this is available before Phase 6 is scheduled or it will block the entire phase.
- **Render.com persistent disk for ChromaDB:** The Phase 1 singleton fix prevents per-call re-init, but the ChromaDB data directory is on ephemeral storage on Render free tier. A deploy resets it. Either mount a persistent disk (Render paid) or migrate to a managed vector DB (Pinecone free tier) before deploying Phase 1 to production.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `backend/app/api/routes.py`, `tools.py`, `main.py`, `prompts.py` — all architectural claims
- Direct codebase inspection: `ios/F1AI/Services/`, `Models/`, `ViewModels/`, `F1AIWidgets/` — all iOS component claims
- Direct codebase inspection: `frontend/app/hooks/useChat.ts`, `components/` — all web component claims
- FastAPI lifespan docs (official, fetched 2026-02-16): https://fastapi.tiangolo.com/advanced/events/
- FastAPI testing docs (official, fetched 2026-02-16): https://fastapi.tiangolo.com/advanced/testing-dependencies/
- Apple ActivityKit documentation — system framework, iOS 16.1+, stable API

### Secondary (MEDIUM confidence)
- pytest-asyncio documentation — https://pytest-asyncio.readthedocs.io/ (training knowledge, version MEDIUM)
- Vitest 3.x documentation — https://vitest.dev/ (training knowledge, MEDIUM)
- MSW v2 streaming documentation — https://mswjs.io/ (training knowledge, MEDIUM)
- FastF1 concurrency behavior — Python F1 community knowledge; could not verify current version behavior
- OpenF1 API reliability — community reports; no official SLA

### Tertiary (LOW confidence)
- Competitor feature comparison (official F1 app, F1TV, RaceFans, WTF1, Pitwall) — training data only; official sources not verified during research session

---
*Research completed: 2026-02-16*
*Ready for roadmap: yes*
