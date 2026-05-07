# Phase 5: Push Infrastructure - Pattern Map

**Mapped:** 2026-05-01
**Files analyzed:** 16 (10 backend + 6 iOS)
**Analogs found:** 14 / 16 (2 are greenfield with no close analog)

## File Classification

### Backend (Python / FastAPI)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/data/db.py` (NEW) | infrastructure / config | resource-singleton | `backend/app/api/routes.py` (FastF1 cache singleton, lines 134-138) + `backend/main.py` (lifespan, lines 106-117) | role-match (no existing async ORM pattern) |
| `backend/app/data/device_tokens.py` (NEW) | model + repository | CRUD | `backend/app/data/predictions.py` (module pattern + cache layer, lines 1-77) | partial (no SQLAlchemy ORM exists yet — closest is the in-memory cache module) |
| `backend/app/services/apns_client.py` (NEW) | service / external client | request-response (HTTP/2) | `backend/app/data/weather.py` (httpx client + module-level cache, lines 1-34) | role-match (external HTTP client + module singleton) |
| `backend/app/api/push.py` (NEW) | controller / route module | request-response + event-driven dispatch | `backend/app/api/routes.py::chat_endpoint` (POST + Pydantic body, lines 144-156) | exact for register endpoint; role-match for dispatch |
| `backend/app/api/routes.py` (MODIFY) | controller | event-driven (WebSocket) | itself — `live_timing()` lines 1239-1357 | self (extension point) |
| `backend/main.py` (MODIFY) | entry-point / config | lifecycle | itself — `lifespan()` lines 106-117 | self (extension point) |
| `backend/app/config.py` (MODIFY) | config | env-var read | itself — every existing constant follows the same pattern | self |
| `backend/requirements.txt` (MODIFY) | dependency manifest | static | itself | self |
| `backend/alembic/env.py` (NEW) | infrastructure | migration | none — first migration in project | no analog |
| `backend/render.yaml` (MODIFY) | deployment config | static | itself — existing `services:` block | self |

### iOS (Swift / SwiftUI)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `ios/F1AI/F1AIApp.swift` (MODIFY) | app entry / scene root | lifecycle | itself, lines 1-13 | self (extension point) |
| `ios/F1AI/Services/AppDelegate.swift` (NEW) | service / OS-bridge | callback | `ios/F1AI/Services/NotificationService.swift` (UNUserNotificationCenter usage, lines 27-37) | partial (notification framework match, but no UIApplicationDelegate exists) |
| `ios/F1AI/Services/PushRegistrationService.swift` (NEW) | service | request-response | `ios/F1AI/Services/LiveActivityService.swift` (singleton service with state, lines 1-12) | role-match |
| `ios/F1AI/Services/APIClient.swift` (MODIFY) | service / HTTP | request-response | itself — `fetchPredictions()` lines 83-87 | self |
| `ios/F1AI/Services/NotificationService.swift` (MODIFY) | service | local config + UD | itself — `UserDefaults` extension lines 113-135 | self |
| `ios/F1AI/Views/Settings/NotificationSettingsView.swift` (MODIFY) | view (SwiftUI Form) | view-binding | itself — Section + Toggle lines 53-72 | self |
| `ios/F1AI/F1AI.entitlements` (NEW) | config | static | none — first entitlements file | no analog |
| `ios/project.yml` (MODIFY) | build config | static | itself, lines 17-32 | self |

---

## Pattern Assignments

### `backend/app/api/push.py` (controller, request-response + event-driven)

**Analog:** `backend/app/api/routes.py` for the POST endpoint shape and the WebSocket integration point.

**Imports pattern** (from `backend/app/api/routes.py` lines 21-52):
```python
import os
import asyncio
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone

from app.config import (
    TOOL_TIMEOUT_SECONDS,
    # ...
)

logger = structlog.get_logger()
router = APIRouter()
```

Apply: `from sqlalchemy.ext.asyncio import AsyncSession`, `from fastapi import APIRouter, Depends, status`, `from app.data.db import get_db`, `from app.data import device_tokens as repo`. Same `logger = structlog.get_logger()` line; same `router = APIRouter()` line.

**Pydantic body model pattern** (from `backend/app/api/routes.py` lines 144-147):
```python
class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat."""
    messages: List[dict]
```

Apply directly — define `RegisterTokenPayload(BaseModel)` next to the router, with field-level `Field(...)` regex constraints from RESEARCH.md §Code Examples.

**POST endpoint pattern** (from `backend/app/api/routes.py` lines 153-156):
```python
@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint that drives an agentic tool-use loop.
    """
    today = datetime.now().strftime("%B %d, %Y")
```

Apply: `@router.post("/push/register", status_code=status.HTTP_204_NO_CONTENT)` with `payload: RegisterTokenPayload, session: AsyncSession = Depends(get_db)`. Returns `None`.

**Error/logging pattern** (from `backend/app/api/routes.py` lines 235-242):
```python
try:
    tool_result = await asyncio.wait_for(
        asyncio.to_thread(TOOL_MAP[tool_name].invoke, tool_args),
        timeout=TOOL_TIMEOUT_SECONDS,
    )
except asyncio.TimeoutError:
    logger.warning("tool.timeout", tool=tool_name, timeout_seconds=TOOL_TIMEOUT_SECONDS)
except Exception as tool_err:
    logger.error("tool.error", tool=tool_name, error=str(tool_err))
```

Apply: catch `aioapns` errors inside `_send_one()` and log with the same dotted event-name style: `logger.warning("apns.send_failed", token=t.apns_token[-8:], error=str(e))`. NEVER log the full token (security — global `security.md`).

**Event-driven dispatch fan-out pattern** (from `backend/app/api/routes.py` lines 1290-1294):
```python
curr_status, curr_stints = await asyncio.gather(
    _fetch_session_status(session_key),
    _fetch_stint_counts(session_key),
)
```

Apply: `await asyncio.gather(*[_send_one(t) for t in tokens])` to fan out APNs sends concurrently (HTTP/2 multiplexed; cheap).

**Per-event cooldown state pattern** (from `backend/app/api/routes.py` lines 1296-1310 — `_commentary_state` dict):
```python
state = _commentary_state.setdefault(room, {
    "last_time": 0.0,
    "prev_positions": [],
    # ...
})
# ...
if now_ts - state["last_time"] >= COMMENTARY_COOLDOWN_SECONDS:
```

Apply: extend the same in-memory-dict pattern keyed by `(room, event_type)` tuple per RESEARCH.md §Pattern 7. Module-level: `_push_cooldown_state: dict[tuple[str, str], float] = {}`. Use `time.time()` (already imported in routes.py).

---

### `backend/app/data/device_tokens.py` (model + repository, CRUD)

**Analog:** `backend/app/data/predictions.py` for the module structure (header docstring + module-level cache + thread-safety lock pattern). NO existing SQLAlchemy ORM in the codebase — RESEARCH.md §Pattern 4 + §Pattern 5 patterns (directly from SQLAlchemy 2.0 docs) become the source of truth for the ORM-specific code.

**Module header docstring pattern** (from `backend/app/data/predictions.py` lines 1-18):
```python
"""
Race Prediction Engine
======================
Computes probabilistic race outcome predictions for all drivers using a
weighted heuristic scoring model.  Data sources:

  - Qualifying results (or practice session data as fallback)
  ...

Thread safety: All FastF1 session loads are wrapped with ``_fastf1_lock``
to prevent data corruption from concurrent loads.
"""
```

Apply: same banner-style docstring (===) explaining the table, columns, lifecycle (upsert on register, deactivate on APNs 410), and concurrency guarantee (sessions are per-request via `Depends(get_db)`).

**Imports pattern** (from `backend/app/data/predictions.py` lines 20-40):
```python
import structlog
# ...
from app.config import (
    QUALIFYING_WEIGHT,
    # ...
)
logger = structlog.get_logger()
```

Apply (combined with RESEARCH.md §Pattern 4 SQLAlchemy imports):
```python
from datetime import datetime, timezone
import structlog
from sqlalchemy import String, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.data.db import Base
logger = structlog.get_logger()
```

**ORM model pattern (from RESEARCH.md §Pattern 4):**
```python
class DeviceToken(Base):
    __tablename__ = "device_tokens"
    device_uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    apns_token: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled_event_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    bundle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

**Repository functions pattern (from RESEARCH.md §Pattern 5 + Code Examples):**
```python
async def upsert_token(session: AsyncSession, payload: RegisterTokenPayload) -> DeviceToken:
    stmt = pg_insert(DeviceToken).values(...).on_conflict_do_update(
        index_elements=[DeviceToken.device_uuid],
        set_={...},
    ).returning(DeviceToken)
    result = await session.execute(stmt)
    return result.scalar_one()

async def deactivate_token(session: AsyncSession, device_uuid: str) -> None:
    ...

async def tokens_for_event_type(session: AsyncSession, event_type: str, environment: str) -> list[DeviceToken]:
    ...
```

**No-mutation rule (global `coding-style.md`):** SQLAlchemy ORM rows are inherently mutable, but the upsert returns a fresh `DeviceToken` instance each time — never mutate `.apns_token` on a fetched row in place. For event payloads inside `dispatch_push_for_event()`, use `@dataclass(frozen=True)` (per `python/coding-style.md`).

---

### `backend/app/services/apns_client.py` (service, request-response)

**Analog:** `backend/app/data/weather.py` for the module-level lazy client + structlog pattern. No exact APNs analog exists — combine with RESEARCH.md §Pattern 2.

**Module-level lazy client pattern** (from `backend/app/data/weather.py` lines 19-34):
```python
import time
from datetime import datetime, timezone

import httpx
import structlog

from app.config import OPENWEATHERMAP_API_KEY, WEATHER_CACHE_TTL

logger = structlog.get_logger()

# In-memory TTL cache
_weather_cache: dict[str, tuple[float, dict]] = {}
```

Apply: same shape — module-level `_client: APNs | None = None`, plus `init_apns()` / `get_apns()` / `close_apns()` accessor functions per RESEARCH.md §Pattern 2.

**Singleton lifecycle pattern** (from `backend/app/api/routes.py` lines 134-138 — FastF1 cache init):
```python
if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache("f1_cache")
```

This shows the codebase already uses module-level "init once" pattern. Apply the same for APNs but call `init_apns()` from `main.py:lifespan()` — NOT at module import — because Render's filesystem is ephemeral and the cert may need to be materialized first.

**Cert materialization pattern** (NEW per RESEARCH.md Open Question §Q2):
```python
def _materialize_cert() -> str:
    """Decode APNS_CERT_B64 env var to a temp PEM file. Returns the path."""
    b64 = os.getenv("APNS_CERT_B64")
    if not b64:
        return os.getenv("APNS_CERT_PATH", "secrets/apns-cert.pem")
    import base64, tempfile
    pem = base64.b64decode(b64)
    f = tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False)
    f.write(pem)
    f.close()
    return f.name
```

**Error logging** — match the `weather.py` and `routes.py` style: structured event names with dotted prefixes (`"apns.init"`, `"apns.send_failed"`).

---

### `backend/app/data/db.py` (infrastructure, resource-singleton)

**Analog:** `backend/main.py:lifespan()` lines 106-117 for the lifecycle hook + `backend/app/api/routes.py:llm` lines 118-128 for the module-level lazy client.

**Lifecycle pattern** (from `backend/main.py` lines 106-117):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: starts background prefetch on boot, cancels on shutdown."""
    setup_logging()
    logger.info("server.starting")
    task = asyncio.create_task(_prefetch_race_details())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

Apply: extend this lifespan to call `await init_db_engine()` before yield and `await close_db_engine()` after yield. Also call `init_apns()` (sync) before yield and `await close_apns()` after.

**Module structure** (NEW; combined with RESEARCH.md §Pattern 1 + SQLAlchemy 2.0 async docs):
```python
"""
Database Engine & Session Factory
=================================
Provides the async SQLAlchemy 2.0 engine, sessionmaker, and FastAPI
dependency for per-request DB sessions.

Lifecycle: init_db_engine() called from main.py:lifespan() at startup;
close_db_engine() at shutdown. The engine is a module-level singleton.
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import DATABASE_URL

class Base(DeclarativeBase):
    pass

_engine = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None

async def init_db_engine() -> None:
    global _engine, _SessionLocal
    # Render gives postgres:// — SQLAlchemy 2.x needs postgresql+asyncpg://
    url = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    _engine = create_async_engine(url, pool_pre_ping=True)
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

async def close_db_engine() -> None:
    if _engine is not None:
        await _engine.dispose()

async def get_db() -> AsyncSession:
    assert _SessionLocal is not None, "init_db_engine() must run first"
    async with _SessionLocal() as session:
        yield session
```

**URL-rewrite quirk** (from RESEARCH.md §Assumptions Log A3): Render exposes `postgres://...` which SQLAlchemy 2.x rejects — must rewrite to `postgresql+asyncpg://`.

---

### `backend/app/api/routes.py` (MODIFY — controller extension)

**Modification points:**

1. **`_detect_event()` extension** (around line 1187, just before the trailing `return None`):
   - Add penalty detection branch (read OpenF1 `/v1/race_control` messages with `category=OTHER` containing the word "PENALTY") — extend the existing `_fetch_session_status()` helper at lines 1089-1115 by adding a sibling `_fetch_recent_penalties()` that follows the exact same shape (httpx async client + try/except + structured warn log).
   - Add fastest-lap detection branch — track session-min lap time keyed by `(session_key)` in a new module-level dict that mirrors `_commentary_state` (lines 1085 area). Read OpenF1 `/v1/laps` similarly to `_fetch_stint_counts()` lines 1118-1138.

   **Existing helper to copy** (lines 1089-1115):
   ```python
   async def _fetch_session_status(session_key: int) -> str:
       try:
           url = f"https://api.openf1.org/v1/race_control?session_key={session_key}&category=SafetyCar,Flag"
           async with httpx.AsyncClient(timeout=5.0) as client:
               resp = await client.get(url)
               resp.raise_for_status()
               messages = resp.json()
           # ...
       except Exception as e:
           logger.warning("commentary.race_control_fetch_error", error=str(e))
           return ""
   ```

   Apply: identical shape for `_fetch_recent_penalties()` and `_fetch_fastest_lap()`, with category filter or path adjusted.

2. **`live_timing()` push dispatch hook** (insert immediately after line 1331 — the `await websocket.send_json(commentary_entry)` for commentary):

   **Existing context** (lines 1319-1337):
   ```python
   if event:
       commentary_text = await _generate_commentary(event, race_name)
       if commentary_text:
           commentary_entry = { ... }
           await websocket.send_json(commentary_entry)
           state["last_time"] = time.time()
           logger.info("commentary.broadcast", room=room, event_type=event["type"])
   ```

   Apply: after the existing `await websocket.send_json(commentary_entry)`, add a fire-and-forget call:
   ```python
   from app.api.push import dispatch_push_for_event   # top-of-file import
   asyncio.create_task(
       dispatch_push_for_event(
           room=room,
           event=event,
           commentary_text=commentary_text,
           race_name=race_name,
       )
   )
   ```

   **Why fire-and-forget:** matches the existing `asyncio.create_task(_prefetch_race_details())` pattern in `main.py` line 111. Per RESEARCH.md §Pitfall 5, never `await` APNs sends inside the WS poll loop — they take 50-200ms each and would stall position updates.

---

### `backend/main.py` (MODIFY — entry point extension)

**Existing lifespan** (lines 106-117) is the extension point. Wrap the new resources around the existing `_prefetch_race_details` task:

**Pattern to extend:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("server.starting")
    # NEW: init DB and APNs before the prefetch task starts
    await init_db_engine()
    init_apns()
    task = asyncio.create_task(_prefetch_race_details())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # NEW: close in reverse order
    await close_apns()
    await close_db_engine()
```

**Router registration** (line 139):
```python
app.include_router(routes.router, prefix="/api")
```

Apply: add `app.include_router(push.router, prefix="/api")` immediately after — same prefix, same pattern. Import: `from app.api import push`.

---

### `backend/app/config.py` (MODIFY — env-var constants)

**Existing pattern (every block in this file):**
```python
# WebSocket settings
WS_RECEIVE_TIMEOUT = float(os.getenv("WS_RECEIVE_TIMEOUT", "0.1"))
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "15"))
```

Apply (per RESEARCH.md §Code Examples — Backend env config additions):
```python
# ---------------------------------------------------------------------------
# APNs push notifications (Phase 5)
# ---------------------------------------------------------------------------
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.f1ai.app")
APNS_CERT_PATH = os.getenv("APNS_CERT_PATH", "secrets/apns-cert.pem")
APNS_USE_SANDBOX = os.getenv("ENVIRONMENT", "development").lower() != "production"

# Per-event push cooldowns (seconds)
PUSH_COOLDOWN_SAFETY_CAR = int(os.getenv("PUSH_COOLDOWN_SAFETY_CAR", "60"))
PUSH_COOLDOWN_POSITION = int(os.getenv("PUSH_COOLDOWN_POSITION", "15"))
PUSH_COOLDOWN_FASTEST_LAP = int(os.getenv("PUSH_COOLDOWN_FASTEST_LAP", "30"))
PUSH_COOLDOWN_PENALTY = int(os.getenv("PUSH_COOLDOWN_PENALTY", "15"))

# Database (PostgreSQL on Render)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/f1ai_dev")
```

Same banner-comment style (`# ---`), same `os.getenv("KEY", "default")` typing-cast pattern.

---

### `ios/F1AI/F1AIApp.swift` (MODIFY — app root)

**Current** (lines 1-13):
```swift
@main
struct F1AIApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
        .modelContainer(for: CachedResponse.self)
    }
}
```

**Modification points** (per RESEARCH.md §Pattern 6):
1. Add `@UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate` inside the struct.
2. Add `@Environment(\.scenePhase) private var scenePhase`.
3. Append `.onChange(of: scenePhase) { _, newPhase in ... }` modifier to the WindowGroup chain — same chaining style already used for `.modelContainer(...)`.

Apply (concrete shape, copying RESEARCH.md §Pattern 6):
```swift
@main
struct F1AIApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
        .modelContainer(for: CachedResponse.self)
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task {
                    let granted = await NotificationService.shared.requestPermission()
                    if granted {
                        await MainActor.run { UIApplication.shared.registerForRemoteNotifications() }
                    }
                }
            }
        }
    }
}
```

**Permission helper already exists** — `NotificationService.shared.requestPermission()` lines 29-37 of `NotificationService.swift` — reuse, do not redefine.

---

### `ios/F1AI/Services/AppDelegate.swift` (NEW)

**Analog:** `ios/F1AI/Services/NotificationService.swift` — the only file in the project that imports `UserNotifications`. Copy the import block and the singleton style.

**Imports & singleton pattern** (from `ios/F1AI/Services/NotificationService.swift` lines 1-7):
```swift
import Foundation
import UserNotifications

final class NotificationService {
    static let shared = NotificationService()
    private init() {}
```

Apply (combined with RESEARCH.md §Pattern 6):
```swift
import UIKit
import UserNotifications

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { await PushRegistrationService.shared.register(apnsToken: token) }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Silent failure — UI-SPEC: log only
    }

    // MainActor wrap for UI updates per RESEARCH.md §Pitfall 7
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                 didReceive response: UNNotificationResponse) async {
        let userInfo = response.notification.request.content.userInfo
        if let _ = userInfo["deep_link"] as? String {
            await MainActor.run { /* deep-link to Live tab */ }
        }
    }
}
```

**`final class` + `private init()` pattern** matches every existing service in `ios/F1AI/Services/`.

---

### `ios/F1AI/Services/PushRegistrationService.swift` (NEW)

**Analog:** `ios/F1AI/Services/LiveActivityService.swift` for the singleton-with-private-state shape.

**Singleton + state pattern** (from `ios/F1AI/Services/LiveActivityService.swift` lines 1-12):
```swift
import ActivityKit
import Foundation

@Observable
final class LiveActivityService {
    private var currentActivity: Activity<RaceLiveActivityAttributes>?

    var isActive: Bool { currentActivity != nil }

    func startActivity(race: RaceEvent, positions: [LivePosition], sessionStatus: SessionStatus?) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        guard currentActivity == nil else { return }
```

Apply (combined with RESEARCH.md §Code Examples — iOS scene-phase re-register):
```swift
import Foundation
import UIKit

@MainActor
final class PushRegistrationService {
    static let shared = PushRegistrationService()
    private var lastSentToken: String?
    private init() {}

    func register(apnsToken: String) async {
        guard apnsToken != lastSentToken else { return }   // idempotent debounce
        // ... build payload, call APIClient.shared.registerPushToken(...)
        lastSentToken = apnsToken
    }

    private static func currentEnvironment() -> String {
        #if DEBUG
        return "sandbox"
        #else
        return "production"
        #endif
    }
}
```

**`@MainActor` annotation** required per RESEARCH.md §Pitfall 7 — every UI-touching service in this codebase uses `@Observable` or operates on the main actor; `LiveActivityService` is `@Observable`, but PushRegistrationService modifies a non-UI cache and is invoked from `AppDelegate` callbacks (background thread), so `@MainActor` is the correct annotation.

**No Keychain in current codebase** — RESEARCH.md mandates Keychain for the device UUID per `swift/security.md`. This is the FIRST keychain consumer in the project; planner should add a tiny `KeychainService.swift` helper or use a one-off `Keychain` wrapper inline. There is no analog file.

---

### `ios/F1AI/Services/APIClient.swift` (MODIFY — add POST method)

**Existing pattern** — every existing method is GET (lines 47-87). The class lacks any POST helper. The cleanest extension is to add a POST `registerPushToken(payload:)` that does NOT use the `fetchCached` GET helper.

**GET pattern to NOT copy** (lines 47-50):
```swift
func fetchSchedule(year: Int) async throws -> [RaceEvent] {
    let url = URL(string: "\(baseURL)/api/schedule/\(year)")!
    return try await fetchCached(url: url, cacheKey: "schedule-\(year)", maxAge: 1800)
}
```

**Encoder/decoder pattern** (lines 13-19):
```swift
private init() {
    let config = URLSessionConfiguration.default
    config.timeoutIntervalForRequest = 35
    config.timeoutIntervalForResource = 60
    self.session = URLSession(configuration: config)
    self.decoder = JSONDecoder()
}
```

The class already holds `session` and `decoder`. Add a `JSONEncoder` for POST bodies (no existing one), then add:

```swift
func registerPushToken(payload: RegisterTokenRequest) async throws {
    let url = URL(string: "\(baseURL)/api/push/register")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONEncoder().encode(payload)
    let (_, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse, http.statusCode == 204 else {
        throw URLError(.badServerResponse)
    }
}
```

Field naming convention: backend uses snake_case (`device_uuid`, `apns_token`); the iOS `RegisterTokenRequest: Codable` struct fields can match snake_case directly OR use `CodingKeys`. Recommend snake_case-named properties for one-shot clarity (consistent with `RaceEvent`, `LivePosition` etc., which decode from snake_case backend output).

---

### `ios/F1AI/Services/NotificationService.swift` (MODIFY — UD extension)

**Existing UserDefaults extension pattern** (lines 113-135):
```swift
extension UserDefaults {
    var enabledNotificationSessions: Set<String> {
        get {
            let arr = array(forKey: "notificationEnabledSessions") as? [String]
            return Set(arr ?? NotificationService.allSessionKeys)
        }
        set {
            set(Array(newValue), forKey: "notificationEnabledSessions")
        }
    }

    var notificationAdvanceMinutes: Int {
        get {
            let stored = integer(forKey: "notificationAdvanceMinutes")
            return [5, 15, 30].contains(stored) ? stored : 15
        }
        set {
            set(newValue, forKey: "notificationAdvanceMinutes")
        }
    }
}
```

Apply (mirror exactly — same `forKey:` string convention, same default-on behavior):
```swift
extension UserDefaults {
    /// Which live race events trigger push notifications. Defaults to all five.
    var pushEnabledEventTypes: Set<String> {
        get {
            let arr = array(forKey: "pushEnabledEventTypes") as? [String]
            return Set(arr ?? ["overtake", "safety_car", "red_flag", "penalty", "fastest_lap"])
        }
        set {
            set(Array(newValue), forKey: "pushEnabledEventTypes")
        }
    }
}
```

**Key string source-of-truth** (per RESEARCH.md §Assumption A10): The strings `"overtake"`, `"safety_car"`, `"red_flag"`, `"penalty"`, `"fastest_lap"` MUST match the backend `_detect_event()` output. Define a `static let allEventTypes` on `NotificationService` (mirror lines 22-25) so the settings UI can iterate.

---

### `ios/F1AI/Views/Settings/NotificationSettingsView.swift` (MODIFY — append section)

**Existing Section + Toggle pattern** (lines 53-72):
```swift
Section {
    ForEach(sessionDisplayLabels, id: \.key) { item in
        Toggle(item.label, isOn: Binding(
            get: { enabledSessions.contains(item.key) },
            set: { isOn in
                if isOn {
                    enabledSessions.insert(item.key)
                } else {
                    enabledSessions.remove(item.key)
                }
                UserDefaults.standard.enabledNotificationSessions = enabledSessions
            }
        ))
    }
} header: {
    Text("Session Types")
} footer: {
    Text("Select which sessions trigger a notification.")
}
```

Apply: copy this exact Section structure, swap the binding to `pushEnabledEventTypes` (the new UD ext), swap the labels list to event-type display names (`"Overtakes"`, `"Safety Car"`, `"Red Flag"`, `"Penalty"`, `"Fastest Lap"`), and append it as a new Section after line 73 with header `Text("Live Race Alerts")`.

**State-driven binding pattern** (line 11):
```swift
@State private var enabledSessions: Set<String> = UserDefaults.standard.enabledNotificationSessions
```

Apply: add a parallel `@State private var enabledPushEventTypes: Set<String> = UserDefaults.standard.pushEnabledEventTypes` line.

---

### `ios/project.yml` (MODIFY — entitlements + capability)

**Existing settings.base block** (lines 17-32):
```yaml
settings:
  base:
    INFOPLIST_KEY_UIApplicationSceneManifest_Generation: YES
    # ...
    PRODUCT_BUNDLE_IDENTIFIER: com.f1ai.app
    INFOPLIST_KEY_NSSupportsLiveActivities: YES
    INFOPLIST_KEY_NSSupportsLiveActivitiesFrequentUpdates: YES
```

Apply: add `CODE_SIGN_ENTITLEMENTS: F1AI/F1AI.entitlements` to this same `base:` block — same key=value style. Per RESEARCH.md §Pitfall 2.

---

### `ios/F1AI/F1AI.entitlements` (NEW)

**No analog** — first entitlements file in the project. Use Apple's standard plist shape (RESEARCH.md §Pitfall 2):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>development</string>
</dict>
</plist>
```

Distribution builds auto-switch to `production` via the signing profile.

---

### `backend/render.yaml` (MODIFY — DB + env vars)

**Existing services block (full file):**
```yaml
services:
  - type: web
    name: f1-ai-backend
    runtime: python
    rootDir: backend
    buildCommand: pip install --upgrade pip && pip install -r requirements.txt && python app/rag/ingest.py
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: GOOGLE_API_KEY
        sync: false
      - key: TAVILY_API_KEY
        sync: false
      - key: ALLOWED_ORIGINS
        sync: false
      - key: PYTHON_VERSION
        value: 3.10.12
```

**Apply:**
1. Append a `databases:` top-level block with a Postgres free instance.
2. Add new `envVars` entries: `APNS_BUNDLE_ID` (sync: true with value `com.f1ai.app`), `APNS_CERT_B64` (`sync: false`), `APNS_CERT_PASSWORD` (`sync: false`, optional), `ENVIRONMENT` (`sync: true`, value `production`), `DATABASE_URL` (link to the new database via `fromDatabase`).
3. Update `buildCommand` to also run `alembic upgrade head` after `pip install`.

---

### `backend/alembic/env.py` (NEW — no analog)

**No analog in project** — first migration in this codebase. Use the alembic stock async template per RESEARCH.md §Code Examples — Alembic env.py (async). Plan must run `alembic init -t async backend/alembic` to get the canonical template, then patch in `from app.data.db import Base` and `from app.data import device_tokens  # noqa`.

---

## Shared Patterns

### Logging

**Source:** Every Python module in `backend/app/` uses the same pattern.

`backend/app/api/routes.py` lines 25, 54:
```python
import structlog
# ...
logger = structlog.get_logger()
```

Use everywhere with dotted event names: `logger.info("apns.dispatched", event_type=..., recipients=...)`, `logger.warning("apns.send_failed", token=token[-8:], error=str(e))`. Never `print()`. Never log full APNs token.

**Apply to:** `app/api/push.py`, `app/services/apns_client.py`, `app/data/db.py`, `app/data/device_tokens.py`.

---

### Async helper pattern (FastF1 / blocking operations)

**Source:** `backend/app/api/routes.py` lines 230-233:
```python
tool_result = await asyncio.wait_for(
    asyncio.to_thread(TOOL_MAP[tool_name].invoke, tool_args),
    timeout=TOOL_TIMEOUT_SECONDS,
)
```

**Apply to:** any blocking call (e.g., `cryptography.pkcs12.load_key_and_certificates` if .p12 conversion runs at startup) — wrap with `asyncio.to_thread(...)`. aioapns itself is native async, so `send_notification` does NOT need wrapping.

---

### Configuration / Env vars

**Source:** `backend/app/config.py` (entire file).

Pattern: `CONST_NAME = type_cast(os.getenv("CONST_NAME", "default_string"))`. Banner comments (`# ---`) group related settings. Never read `os.getenv()` outside `config.py` for new settings.

**Apply to:** all new APNs / DB / cooldown constants. Module imports them as `from app.config import APNS_BUNDLE_ID, ...`.

---

### Module-level cache + thread-safety

**Source:** `backend/app/data/predictions.py` lines 47-71:
```python
_fastf1_lock = threading.Lock()
_qualifying_cache: dict[tuple[int, int], Any] = {}
# ...
```

**Apply to:** `_push_cooldown_state: dict[tuple[str, str], float] = {}` in `app/api/push.py`. No lock needed because the WebSocket loop is single-task per room (asyncio is cooperative; cooldown state is read+written in a single coroutine sequence).

---

### Pydantic body validation

**Source:** `backend/app/api/routes.py` lines 144-147:
```python
class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat."""
    messages: List[dict]
```

**Apply to:** `RegisterTokenPayload` with strict field validation (regex on hex token, regex on environment enum, length bounds on UUID per RESEARCH.md §Code Examples). Project's existing models are loose (`List[dict]`); this new model SHOULD be strict because tokens are external untrusted input (global `security.md` — V5 Input Validation).

---

### Fire-and-forget background tasks

**Source:** `backend/main.py` line 111:
```python
task = asyncio.create_task(_prefetch_race_details())
```

**Apply to:** `dispatch_push_for_event()` invocation from `live_timing()` — wrap with `asyncio.create_task(...)` so the WebSocket loop never blocks waiting for APNs.

---

### iOS singleton service

**Source:** Every file in `ios/F1AI/Services/` (`APIClient.swift`, `LiveActivityService.swift`, `NotificationService.swift`, `CacheService.swift`, etc.):
```swift
final class NotificationService {
    static let shared = NotificationService()
    private init() {}
```

**Apply to:** `AppDelegate.swift` (note: `AppDelegate` is NOT a singleton — instantiated by `UIApplicationDelegateAdaptor`); `PushRegistrationService.swift` (IS a singleton via the same pattern, but adds `@MainActor`).

---

### iOS UserDefaults extension (preferences)

**Source:** `ios/F1AI/Services/NotificationService.swift` lines 113-135. Pattern: extend `UserDefaults` with computed properties; getter applies a sane default; setter stores `Array(set)` for `Set<String>`.

**Apply to:** `pushEnabledEventTypes` extension. Same exact shape.

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns directly):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/alembic/env.py` | infrastructure | migration | First migration in project — use `alembic init -t async` template per RESEARCH.md §Code Examples |
| `ios/F1AI/F1AI.entitlements` | config | static | First entitlements file — use Apple plist template per RESEARCH.md §Pitfall 2 |

For both, RESEARCH.md provides explicit copy-pasteable templates.

---

## Conventions Summary (for planner)

| Concern | Rule | Source |
|---------|------|--------|
| Logging | `structlog.get_logger()` + dotted event names | `backend/app/api/routes.py` line 54, used universally |
| Config constants | `os.getenv("KEY", "default")` in `config.py`, banner-comment groups | `backend/app/config.py` (entire file) |
| Pydantic models | `BaseModel` + `Field(...)` for input validation | `backend/app/api/routes.py` line 144 + RESEARCH.md §Code Examples |
| Async I/O | `httpx.AsyncClient` for HTTP, `asyncio.to_thread` for blocking calls, `asyncio.gather` for fan-out, `asyncio.create_task` for fire-and-forget | `backend/app/api/routes.py` lines 1126, 230, 1291; `backend/main.py` line 111 |
| File size | Max ~400 lines per new module; routes.py already 1417 lines — DO NOT add push code there beyond minimal hooks | global `coding-style.md` |
| Token handling | Never log full APNs token; only `token[-8:]` at DEBUG | RESEARCH.md §Anti-Patterns |
| iOS services | `final class` + `static let shared = ServiceName()` + `private init()` | every file in `ios/F1AI/Services/` |
| iOS concurrency | `@MainActor` for UI-touching state; `Task { ... }` to bridge sync→async; `await MainActor.run { ... }` for cross-isolation UI mutations | RESEARCH.md §Pitfall 7 + global `swift/coding-style.md` |
| iOS UserDefaults | Extend `UserDefaults` with computed property (getter/setter) | `ios/F1AI/Services/NotificationService.swift` lines 113-135 |
| iOS HTTP | `URLSession.shared.data(for:)` async; check `HTTPURLResponse.statusCode`; throw `URLError` on bad status | `ios/F1AI/Services/APIClient.swift` line 36 (existing) + new POST helper extends it |
| Snake_case JSON | Backend emits and consumes snake_case; iOS Codable structs use snake_case property names directly (no CodingKeys overhead) | every existing iOS Model |
| Immutability (Python) | `@dataclass(frozen=True)` for in-memory event payloads; SQLAlchemy ORM rows OK to be mutable rows but never modify in place | global `python/coding-style.md` |
| Immutability (Swift) | `let` over `var`; structs over classes for DTOs | global `swift/coding-style.md` |

---

## Metadata

**Analog search scope:** `backend/app/`, `ios/F1AI/`, `ios/F1AIWidgets/`, root config (`render.yaml`, `ios/project.yml`)
**Files scanned:** ~85 source files (54 Python, 30 Swift, 2 YAML, 1 entitlements scan)
**Existing patterns reused:** structlog logging, FastAPI APIRouter, Pydantic body validation, `asyncio.gather`/`create_task`/`to_thread`, `os.getenv` config layer, `httpx.AsyncClient` async HTTP, threading.Lock for module-level caches, iOS singleton-with-shared, iOS @MainActor for UI, iOS UserDefaults extension for prefs.
**Greenfield additions (no analog):** SQLAlchemy 2.0 async ORM, Alembic migrations, aioapns client, iOS UIApplicationDelegateAdaptor, iOS .entitlements file, iOS Keychain helper.
**Pattern extraction date:** 2026-05-01
