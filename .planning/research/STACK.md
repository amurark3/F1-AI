# Technology Stack

**Project:** F1 AI Companion App — New Capabilities Milestone
**Researched:** 2026-02-16
**Mode:** Brownfield addition — existing FastAPI + Next.js + SwiftUI preserved

---

## Context: What Already Exists

This is NOT a greenfield stack recommendation. The following is already in place and is NOT being re-recommended:

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend runtime | Python 3.10, FastAPI, Uvicorn | Deployed on Render.com |
| LLM orchestration | LangChain + Gemini 2.0 Flash | 11 tools, agentic loop |
| Data | FastF1, Ergast (via FastF1), OpenF1 API | Historical + live timing |
| RAG | ChromaDB + sentence-transformers/all-MiniLM-L6-v2 | FIA regulations |
| Web frontend | Next.js 16, React 19, Tailwind 4, Vercel AI SDK 5 | Streaming chat |
| iOS | SwiftUI, iOS 17.0+, WidgetKit (existing widget) | UserNotifications already present |
| Web search | Tavily | Per-query tool call |

The new capabilities this milestone adds are: race outcome predictions, tire strategy analysis, live AI commentary, iOS push notifications + Dynamic Island live activities, test coverage, and performance improvements.

---

## New Stack: Libraries and Tools to Add

### 1. Python Backend — Testing

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `pytest` | `>=8.3` | Test runner | Universally standard; already expected by CI tools |
| `pytest-asyncio` | `>=0.24` | Async test support | Required for testing FastAPI async endpoints with `async def` test functions |
| `httpx` | already in requirements | HTTP client for tests | FastAPI's `TestClient` is built on httpx; use `AsyncClient` with `ASGITransport` for true async tests |
| `pytest-mock` | `>=3.14` | Mocking | Wrap `unittest.mock` in pytest fixtures; avoids manual mock setup in each test |
| `respx` | `>=0.21` | Mock httpx requests | Intercepts outbound `httpx.AsyncClient` calls (OpenF1, Tavily) without real network calls |
| `fakeredis` | already in venv | Not needed yet | Skip; no Redis in this project |

**Why pytest-asyncio over alternatives:**
- `anyio` pytest plugin is an option but adds a runtime dependency not already present
- `pytest-asyncio` is the de-facto standard for FastAPI testing per the official FastAPI docs
- Set `asyncio_mode = "auto"` in `pytest.ini` to avoid per-test `@pytest.mark.asyncio` decorators

**Testing pattern for this codebase:**
```python
# pytest.ini
[pytest]
asyncio_mode = auto

# tests/test_routes.py
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
```

**Why AsyncClient + ASGITransport over TestClient:**
The existing `generate()` function in routes.py uses `StreamingResponse` with an async generator. `TestClient` (synchronous) cannot properly await streaming async generators — it silently collects all chunks. `AsyncClient` with `ASGITransport` tests the real async code path including streaming behavior.

**Confidence:** MEDIUM — Based on FastAPI docs pattern (fetched from official docs) and knowledge of httpx 0.26+ API. The `ASGITransport` approach is current as of httpx 0.23+.

---

### 2. Python Backend — Race Prediction / Tire Strategy

**Verdict: No new ML libraries needed. Use pandas + scipy (already available via FastF1's dependencies) with domain heuristics.**

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `scipy` | already in venv | Statistical utilities | `scipy.stats.percentileofscore`, linear regression for position predictions |
| `pandas` | already in requirements | Data manipulation | FastF1 already returns DataFrames; all prediction logic operates on them directly |
| `numpy` | already in venv (FastF1 dep) | Numerical operations | Weighted averages, compound scoring |

**What NOT to use:**
- Do NOT add scikit-learn, XGBoost, or any ML training library — the milestone spec explicitly says "statistical/heuristic, not ML training." scikit-learn adds ~60MB to the Docker image, and Render.com's build time would increase significantly.
- Do NOT add Prophet or statsmodels — overkill for a heuristic approach; adds complexity without proportional benefit for F1 predictions.

**Prediction approach (heuristics that work with FastF1 data):**
```python
# Compound scoring: weighted recent form + qualifying delta + historical circuit performance
# All inputs come from existing FastF1 + Ergast tool calls
# Output: ranked list of drivers with confidence percentage
```

**Tire strategy approach:**
- FastF1 already provides `session.laps["Compound"]` and `session.laps["TyreLife"]`
- Historical stint length distributions per compound per circuit already accessible
- No new libraries needed; pure pandas analysis

**Confidence:** HIGH — FastF1's DataFrame output is the input; all statistics are in scipy/numpy already present.

---

### 3. Python Backend — Live AI Commentary

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `sse-starlette` | `>=2.1` | Server-Sent Events | Cleaner than raw `StreamingResponse` for push-style commentary updates; maintains connection without WebSocket handshake overhead |
| `asyncio` | stdlib | Event coordination | Already used; async generator pattern streams Gemini output as commentary chunks |

**Why SSE over WebSocket for commentary:**
- Commentary is unidirectional: backend pushes text, client only reads
- WebSocket is bidirectional and adds connection management overhead
- The existing `/api/live/{year}/{round_num}` WebSocket endpoint already handles bidirectional timing data; commentary should be a separate concern
- SSE reconnects automatically in browsers (native `EventSource`); SwiftUI needs a small wrapper (URLSession streaming)
- FastAPI already supports `StreamingResponse` — sse-starlette is a thin wrapper that adds proper SSE headers and retry semantics

**Commentary generation pattern:**
```python
# Triggered by live timing events (position changes, pit stops detected from OpenF1 poll)
# Gemini 2.0 Flash generates 1-2 sentence commentary per event
# Streamed as SSE event to connected clients
```

**Confidence:** MEDIUM — SSE-starlette is well-established in FastAPI ecosystem. Gemini streaming is already working in the chat endpoint; same pattern applies here.

---

### 4. Python Backend — ChromaDB Singleton (Performance)

**No new library needed — this is a refactoring task using FastAPI's existing lifespan mechanism.**

**Current problem:** `consult_rulebook` in tools.py creates a new `Chroma(...)` instance on every tool call, reloading the embedding model each time (~2-5 second cold start per call).

**Fix pattern:**
```python
# main.py — use FastAPI lifespan context manager (FastAPI >= 0.93, already available)
from contextlib import asynccontextmanager
from fastapi import FastAPI

_chroma_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _chroma_client
    _chroma_client = Chroma(persist_directory="data/chroma", embedding_function=embeddings)
    yield
    _chroma_client = None  # cleanup

app = FastAPI(lifespan=lifespan)
```

Tools then receive the singleton via dependency injection rather than creating new instances.

**Confidence:** HIGH — FastAPI lifespan is stable API since 0.93; this is the recommended pattern for expensive startup resources in official FastAPI docs.

---

### 5. Python Backend — Async Patterns (Performance)

**No new libraries needed — pattern changes only.**

| Pattern | Current State | Fix |
|---------|--------------|-----|
| FastF1 session load | `asyncio.to_thread()` with `threading.Lock()` | Already correct; lock prevents concurrent FastF1 loads |
| ChromaDB retrieval | Sync call inside async handler | Move to singleton + `asyncio.to_thread()` for embedding computation |
| OpenF1 polling | `httpx.AsyncClient` (good) | Already async-native |

**What NOT to add:**
- Do NOT add Celery or Redis for background tasks — Render.com free tier has no Redis, and the polling architecture already works via WebSocket async loop
- Do NOT add APScheduler — overkill; asyncio `sleep` loop in WebSocket handler already provides the polling pattern

**Confidence:** HIGH — Architecture review of existing code; all issues are refactoring, not new dependencies.

---

### 6. Frontend (Next.js) — Testing with Vitest

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `vitest` | `^3.0` | Test runner | Built for Vite/Next.js; 10-20x faster than Jest for TypeScript projects; native ESM support matches Next.js App Router |
| `@testing-library/react` | `^16.0` | React component testing | Standard for user-interaction-focused tests; works with Vitest |
| `@testing-library/user-event` | `^14.0` | User interaction simulation | Companion to testing-library; simulates real user events |
| `@vitejs/plugin-react` | `^4.0` | React transform in Vitest | Required for JSX transform support in Vitest |
| `jsdom` | `^25.0` | DOM environment | Vitest's default test environment for browser-like DOM |
| `msw` | `^2.0` | API mocking | Mock Service Worker intercepts fetch calls at the network layer; integrates cleanly with Next.js server/client components |

**Why Vitest over Jest:**
- Next.js 16 + React 19 with Tailwind 4 uses native ESM throughout; Jest requires complex transform configuration to handle this
- Vitest is Vite-native and handles ESM without babel transforms
- The existing `package.json` has no Jest config; starting with Vitest avoids fighting legacy config
- The AI SDK 5 (`@ai-sdk/react`, `ai`) exports ES modules — Jest's `transformIgnorePatterns` becomes a maintenance burden

**Why MSW over manual fetch mocking:**
- The `ChatViewModel` calls the backend streaming endpoint; MSW can intercept and return a readable stream for realistic test conditions
- MSW v2 has first-class support for streaming responses (critical for testing SSE/streaming chat)

**Configuration:**
```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

**Confidence:** MEDIUM — Vitest 3.x is current as of late 2025. Next.js 16 + React 19 pairing is evident from package.json. MSW v2 streaming support is documented.

---

### 7. iOS — Push Notifications (APNs)

**Current state:** `NotificationService.swift` exists and uses `UNUserNotificationCenter` for LOCAL notifications (scheduled calendar triggers). No remote push infrastructure exists.

**What to add:**

| Component | Tool/Framework | Purpose | Why |
|-----------|---------------|---------|-----|
| APNs registration | `UIApplication.registerForRemoteNotifications()` | Register device token with Apple | System framework; no third-party needed |
| Token delivery | Backend endpoint `POST /api/devices` | Store device token server-side | Simple REST; enables targeted push |
| Push sending (backend) | `httpx` (already in requirements) + APNs HTTP/2 API | Send pushes from Python backend | Direct APNs integration without vendor lock-in; avoids Firebase/OneSignal cost |
| JWT signing (backend) | `PyJWT` `>=2.9` | Sign APNs JWT authentication token | Lightweight; standard for APNs provider authentication |

**Why direct APNs over Firebase Cloud Messaging:**
- Firebase adds Google SDK dependency to iOS app (~15MB); for a portfolio project this is unnecessary complexity
- APNs HTTP/2 API is well-documented and sufficient for low-volume (F1 race schedule) notifications
- No Firebase project setup required; simpler deployment

**What NOT to add:**
- Do NOT add OneSignal or Braze — paid vendor services inappropriate for a learning/portfolio project
- Do NOT add Firebase Cloud Messaging — heavy dependency for simple race start/session reminders

**Backend implementation:**
```python
# pip install PyJWT>=2.9 cryptography
import jwt
import httpx
import time

def create_apns_token(key_id: str, team_id: str, private_key: str) -> str:
    return jwt.encode(
        {"iss": team_id, "iat": time.time()},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id}
    )
```

**Confidence:** MEDIUM — APNs JWT authentication is a stable Apple API. PyJWT is the standard Python JWT library. However, this requires an Apple Developer account and p8 key file not currently in the project — this is an infrastructure prerequisite, not just a code change.

---

### 8. iOS — Dynamic Island Live Activities

**Current state:** No ActivityKit integration exists. The widget target (`F1AIWidgets`) exists and is properly configured in project.yml — Live Activities use a similar widget extension mechanism.

**What to add:**

| Component | Framework | Purpose | Why |
|-----------|-----------|---------|-----|
| Live Activity definition | `ActivityKit` (iOS 16.1+) | Define live activity data model | System framework; no third-party needed |
| Dynamic Island UI | `WidgetKit` + `ActivityKit` | Render compact/expanded/minimal presentations | Already have WidgetKit configured; same target can host Live Activities |
| Push-to-update | APNs `live-activity` push type | Update activity without user opening app | Real-time lap/position updates during race |
| Backend push update | `httpx` + APNs (same as #7) | Send activity update pushes | Reuses the APNs infrastructure from #7 |

**iOS version requirement:** ActivityKit requires iOS 16.1+. The project currently targets iOS 17.0 — this is satisfied with margin.

**Dynamic Island data model for F1:**
```swift
import ActivityKit
import WidgetKit

struct F1RaceActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var leadDriver: String
        var lap: Int
        var totalLaps: Int
        var topPositions: [String]  // ["VER", "NOR", "LEC"]
        var safetyCarDeployed: Bool
    }
    var raceName: String
    var raceRound: Int
}
```

**Why this approach:**
- The existing widget target in `F1AIWidgets` already imports WidgetKit; ActivityKit is complementary, not a replacement
- The `project.yml` XcodeGen config only needs a new file added to the `F1AIWidgets` target — no new target needed
- APNs push-to-update eliminates the need for the iOS app to keep a WebSocket open during a race (battery efficiency)

**Confidence:** MEDIUM — ActivityKit/Dynamic Island is a stable API since iOS 16.2 (widely adopted). iOS 17 target means no version-gating needed. The push-update mechanism requires the APNs infrastructure from item #7 — these two items are dependent.

---

## Installation Commands

### Backend new additions

```bash
# Testing
pip install pytest>=8.3 pytest-asyncio>=0.24 pytest-mock>=3.14 respx>=0.21

# Live commentary SSE
pip install sse-starlette>=2.1

# iOS push notifications (APNs)
pip install PyJWT>=2.9 cryptography>=42.0
```

### Frontend new additions

```bash
npm install -D vitest@^3.0 @vitest/coverage-v8@^3.0
npm install -D @testing-library/react@^16.0 @testing-library/user-event@^14.0
npm install -D @vitejs/plugin-react@^4.0 jsdom@^25.0
npm install -D msw@^2.0
```

### iOS additions

No CocoaPods or Swift Package Manager packages needed — all additions use Apple system frameworks (ActivityKit, UserNotifications).

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Python test runner | pytest | unittest | pytest fixtures and parametrize are superior for this codebase |
| Async Python testing | pytest-asyncio | anyio pytest plugin | anyio adds a runtime dep not currently used; pytest-asyncio is simpler for FastAPI |
| HTTP mocking (Python) | respx | responses (for requests lib) | Project uses httpx, not requests; respx is httpx-native |
| Frontend test runner | Vitest | Jest | ESM/Next.js 16 compatibility issues with Jest make Vitest the better choice |
| API mocking (frontend) | MSW v2 | nock / jest-fetch-mock | MSW works at network layer; handles streaming correctly |
| Push delivery (iOS) | Direct APNs via httpx | Firebase/OneSignal | Zero vendor cost; sufficient for portfolio scale |
| Live prediction logic | pandas + scipy heuristics | scikit-learn / XGBoost | No training data pipeline; heuristics are more interpretable for F1 domain |
| Commentary push mechanism | SSE (sse-starlette) | WebSocket | Commentary is unidirectional; SSE is simpler and auto-reconnects |

---

## Dependency Constraints

**Python version:** 3.10 (locked in render.yaml). All recommended packages support Python 3.10.

**iOS deployment target:** 17.0 (locked in project.yml). ActivityKit requires iOS 16.1+, so no version gating needed.

**Render.com free tier constraints:**
- No Redis available → no Celery/background task queue
- Ephemeral filesystem → ChromaDB data must be ingest at build time (already done in render.yaml `buildCommand`)
- 512MB RAM → sentence-transformers model (`all-MiniLM-L6-v2`, ~80MB) is already the right choice; do NOT add larger embedding models

---

## Sources

- FastAPI testing docs (official, fetched 2026-02-16): https://fastapi.tiangolo.com/advanced/testing-dependencies/
- FastAPI lifespan docs: https://fastapi.tiangolo.com/advanced/events/
- ActivityKit: Apple system framework, iOS 16.1+ (stable API, training knowledge)
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/ (training knowledge, version MEDIUM confidence)
- Vitest: https://vitest.dev/ (training knowledge, version MEDIUM confidence)
- MSW v2: https://mswjs.io/ (training knowledge, MEDIUM confidence)
- APNs HTTP/2 API: Apple developer documentation (training knowledge, HIGH confidence — stable API)
- PyJWT: https://pyjupter.readthedocs.io/ (training knowledge, MEDIUM confidence)
- Project codebase: read directly from /Users/adityamurarka/Desktop/F1-AI/ (HIGH confidence — direct inspection)
