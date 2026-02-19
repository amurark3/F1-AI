# Phase 1: Infrastructure Hardening - Research

**Researched:** 2026-02-16
**Domain:** Python/FastAPI backend infrastructure (logging, singletons, WebSocket, config extraction, dead code removal)
**Confidence:** HIGH

## Summary

Phase 1 addresses six infrastructure requirements that harden the existing Python FastAPI backend. The codebase currently has: (1) ChromaDB + HuggingFace embeddings re-initialized on every `consult_rulebook` tool call, (2) WebSocket connections with no heartbeat or stale-connection cleanup, (3) dead MCP prediction stubs importing from a non-existent `app/ml/` directory, (4) extensive `print()` statements with emoji prefixes instead of structured logging, (5) LLM safety settings set to BLOCK_NONE across all categories, and (6) hardcoded timeout values scattered across `routes.py` and `main.py`.

All six requirements are well-understood, self-contained refactoring tasks with no external dependencies. The standard Python ecosystem provides mature solutions for each. The primary risk is the ChromaDB singleton requiring careful handling of HuggingFace embedding model loading time at startup (the `sentence-transformers/all-MiniLM-L6-v2` model is ~90MB and takes several seconds to load).

**Primary recommendation:** Address these as six independent, parallelizable tasks. Start with dead code removal (INFRA-03) since it simplifies the codebase for subsequent changes, then tackle the remaining five in any order.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | ChromaDB vector store initializes once at startup as a singleton, not per tool call | Singleton pattern with module-level initialization in `app/api/tools.py`; embeddings + Chroma client created once during import |
| INFRA-02 | WebSocket connections have heartbeat pings and stale connections are cleaned up automatically | asyncio background task pattern for ping/pong; connection manager class with TTL tracking |
| INFRA-03 | Dead MCP prediction stubs and broken imports are removed from codebase, and README.md references to removed prediction modules are cleaned up | `mcp_server.py` lines 497-525 import from non-existent `app/ml/`; README references ML training, scikit-learn, predictions endpoint |
| INFRA-04 | Backend uses structured JSON logging instead of print() with emoji prefixes | `structlog` 25.x with JSON renderer; 53 print() calls across 5 files need replacement |
| INFRA-05 | LLM safety settings are reviewed and set to appropriate levels for production | Current BLOCK_NONE on all 4 categories; recommend BLOCK_ONLY_HIGH for F1 domain content |
| INFRA-06 | Hardcoded timeouts (30s tool, 60s race data) are extracted to configuration constants | 6+ timeout values across `routes.py` and `main.py`; centralize in `app/config.py` |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | latest | Web framework | Already in use |
| uvicorn[standard] | latest | ASGI server | Already in use; `standard` extra includes websockets |
| langchain-chroma | latest | ChromaDB vector store wrapper | Already in use for RAG |
| langchain-huggingface | latest | HuggingFace embeddings | Already in use for embeddings |
| langchain-google-genai | latest | Gemini LLM integration | Already in use; provides HarmCategory/HarmBlockThreshold |

### New Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.x | Structured JSON logging | Replace all print() statements; JSON output in production, pretty console in dev |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| structlog | python-json-logger | structlog has better FastAPI integration, contextvars support, and dev/prod dual mode |
| structlog | stdlib logging only | Missing structured output, context binding, and processor pipeline |

**Installation:**
```bash
pip install structlog
```

## Architecture Patterns

### Recommended Changes to Project Structure
```
backend/
├── app/
│   ├── config.py          # NEW: All configurable constants (timeouts, model names, paths)
│   ├── logging_config.py  # NEW: structlog configuration (JSON prod, pretty dev)
│   ├── api/
│   │   ├── routes.py      # MODIFIED: Use logger, use config constants, fix WebSocket
│   │   ├── tools.py       # MODIFIED: Use logger, ChromaDB singleton, use config constants
│   │   └── prompts.py     # MODIFIED: Remove prediction capability claims
│   └── rag/
│       └── ingest.py      # MODIFIED: Use logger (lower priority, CLI script)
├── mcp_server.py          # MODIFIED: Remove predict/scenario tools, fix imports
├── main.py                # MODIFIED: Use logger, initialize logging on startup
└── requirements.txt       # MODIFIED: Add structlog
```

### Pattern 1: ChromaDB Singleton via Module-Level Initialization
**What:** Initialize the HuggingFace embeddings model and ChromaDB client once at module import time, reuse across all tool calls.
**When to use:** Any expensive resource that should be created once (DB connections, ML models, embedding models).
**Example:**
```python
# app/api/tools.py — top of file, after imports

import structlog
from app.config import CHROMA_DB_PATH, EMBEDDING_MODEL_NAME

logger = structlog.get_logger()

# --- ChromaDB Singleton ---
# Initialize ONCE at import time. The embedding model (~90MB) loads here.
# Subsequent calls to consult_rulebook() reuse this instance.
_embeddings = None
_vector_db = None

def _get_vector_db():
    """Lazy singleton for ChromaDB + embeddings. Initializes on first call."""
    global _embeddings, _vector_db
    if _vector_db is None:
        logger.info("chromadb.initializing", db_path=CHROMA_DB_PATH, model=EMBEDDING_MODEL_NAME)
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        _vector_db = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=_embeddings)
        logger.info("chromadb.ready")
    return _vector_db
```

**Why lazy singleton over eager:** The embedding model takes 3-5 seconds to load. Eager loading in module scope would block FastAPI startup. Lazy loading defers to first `consult_rulebook` call, so startup is fast but first rulebook query pays the cost once.

### Pattern 2: WebSocket Connection Manager with Heartbeat
**What:** A class that tracks active WebSocket connections and runs a background ping task per connection.
**When to use:** Any WebSocket endpoint that needs to detect and clean up stale connections.
**Example:**
```python
# In routes.py

import structlog
from app.config import WS_HEARTBEAT_INTERVAL, WS_STALE_TIMEOUT

logger = structlog.get_logger()

class ConnectionManager:
    """Manages WebSocket connections with heartbeat-based cleanup."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._last_pong: dict[int, float] = {}  # ws id -> timestamp

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()
        if room not in self._connections:
            self._connections[room] = []
        self._connections[room].append(websocket)
        self._last_pong[id(websocket)] = asyncio.get_event_loop().time()
        logger.info("websocket.connected", room=room)

    def disconnect(self, room: str, websocket: WebSocket):
        if room in self._connections:
            self._connections[room] = [
                ws for ws in self._connections[room] if ws != websocket
            ]
        self._last_pong.pop(id(websocket), None)
        logger.info("websocket.disconnected", room=room)

    async def heartbeat(self, websocket: WebSocket):
        """Send periodic pings; close if no pong within timeout."""
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                try:
                    await websocket.send_json({"type": "ping"})
                    self._last_pong[id(websocket)] = asyncio.get_event_loop().time()
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
```

### Pattern 3: Centralized Configuration Constants
**What:** A single `config.py` module holding all magic numbers as named constants, loaded from environment variables with sensible defaults.
**Example:**
```python
# app/config.py
import os

# --- Timeouts ---
TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))
FASTF1_TIMEOUT_SECONDS = int(os.getenv("FASTF1_TIMEOUT_SECONDS", "60"))
PREFETCH_RACE_TIMEOUT_SECONDS = int(os.getenv("PREFETCH_RACE_TIMEOUT_SECONDS", "60"))
OPENF1_HTTP_TIMEOUT_SECONDS = int(os.getenv("OPENF1_HTTP_TIMEOUT_SECONDS", "10"))

# --- WebSocket ---
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "15"))
WS_STALE_TIMEOUT = int(os.getenv("WS_STALE_TIMEOUT", "60"))
WS_POLL_INTERVAL = int(os.getenv("WS_POLL_INTERVAL", "8"))

# --- Agentic Loop ---
MAX_AGENT_TURNS = int(os.getenv("MAX_AGENT_TURNS", "5"))

# --- ChromaDB / RAG ---
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
RULEBOOK_TOP_K = int(os.getenv("RULEBOOK_TOP_K", "6"))

# --- Prefetch ---
PREFETCH_STARTUP_DELAY = int(os.getenv("PREFETCH_STARTUP_DELAY", "30"))
PREFETCH_INTERVAL = int(os.getenv("PREFETCH_INTERVAL", "1800"))
PREFETCH_INTER_RACE_DELAY = int(os.getenv("PREFETCH_INTER_RACE_DELAY", "5"))

# --- LLM ---
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
```

### Pattern 4: Structured Logging Configuration
**What:** Configure structlog once at startup with JSON output for production and pretty console output for development.
**Example:**
```python
# app/logging_config.py
import logging
import os
import structlog

def setup_logging():
    """Configure structlog for the application. Call once at startup."""
    is_dev = os.getenv("ENVIRONMENT", "development") == "development"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to also go through structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
```

### Anti-Patterns to Avoid
- **Re-creating ChromaDB client per request:** Current pattern in `consult_rulebook()` creates `HuggingFaceEmbeddings` + `Chroma` on every call. The embedding model load alone takes 2-3 seconds.
- **print() for logging:** Not parseable, no log levels, no structured context, not capturable by log aggregators.
- **Magic numbers in function bodies:** Makes tuning impossible without code changes; prevents environment-specific configuration.
- **WebSocket without heartbeat behind reverse proxy:** Render.com, Cloudflare, and most load balancers drop idle WebSocket connections after 60-120 seconds of inactivity.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured logging | Custom JSON formatter | structlog 25.x | Handles contextvars, processor chains, dev/prod modes, stdlib bridging |
| WebSocket ping/pong | Custom TCP-level implementation | Starlette/FastAPI built-in ping + application-level heartbeat | The ASGI WebSocket spec supports it natively |
| Configuration management | Custom config parser | `os.getenv()` with defaults in a single module | Simple, standard, no dependency needed for this scale |

**Key insight:** All six requirements are refactoring tasks, not feature builds. The solutions are standard Python patterns. No new frameworks or services are needed beyond adding `structlog`.

## Common Pitfalls

### Pitfall 1: ChromaDB Singleton Thread Safety
**What goes wrong:** Multiple concurrent `consult_rulebook` calls during singleton initialization could cause race conditions.
**Why it happens:** FastAPI serves requests concurrently; two requests hitting an uninitialized singleton simultaneously.
**How to avoid:** Use `threading.Lock` around the lazy initialization check, or initialize during FastAPI lifespan startup.
**Warning signs:** Intermittent errors on first few rulebook queries after startup.

### Pitfall 2: Embedding Model Download on First Run
**What goes wrong:** First startup on a fresh Render deploy downloads the 90MB sentence-transformers model, causing a long startup delay.
**Why it happens:** Render.com ephemeral storage means the model is not cached between deploys.
**How to avoid:** This is a known constraint noted in blockers. The model download happens regardless; the singleton just ensures it happens once per process, not per request.
**Warning signs:** First rulebook query after deploy takes 10-30 seconds.

### Pitfall 3: Logging Migration Breaking Existing Behavior
**What goes wrong:** Replacing print() with logger calls changes output format, which could break any downstream tooling or developer expectations.
**Why it happens:** print() goes to stdout immediately; structlog may buffer or format differently.
**How to avoid:** Run in dev mode (pretty console) during development; only use JSON mode when ENVIRONMENT=production.
**Warning signs:** Missing log output during development.

### Pitfall 4: WebSocket Heartbeat Interval vs Proxy Timeout
**What goes wrong:** Heartbeat interval is longer than the reverse proxy idle timeout, so connections still drop.
**Why it happens:** Render.com and Cloudflare have idle connection timeouts (typically 60-100 seconds).
**How to avoid:** Set heartbeat interval to 15-20 seconds (well under any proxy timeout). The requirement says 60-second cleanup, so use 15s ping interval with 60s staleness threshold.
**Warning signs:** WebSocket disconnections despite heartbeat implementation.

### Pitfall 5: Dead Code Removal Missing References
**What goes wrong:** Removing `predict_race_results` and `calculate_championship_scenario` from `mcp_server.py` but missing references in README, prompts, or frontend.
**Why it happens:** Dead code references are scattered across multiple files and file types.
**How to avoid:** Use grep across entire project for: `predict`, `prediction`, `ML`, `scikit`, `joblib`, `app.ml`, `models/`, `race_predictor`.
**Warning signs:** Broken imports at runtime, misleading documentation.

### Pitfall 6: Safety Settings Too Restrictive for F1 Content
**What goes wrong:** Setting safety filters to BLOCK_MEDIUM_AND_ABOVE causes the model to refuse discussing race crashes, accidents, injuries, and aggressive overtakes.
**Why it happens:** F1 content legitimately discusses dangerous situations (crash at Copse, driver hospitalization, fire).
**How to avoid:** Use BLOCK_ONLY_HIGH for DANGEROUS_CONTENT and HARASSMENT. Keep BLOCK_MEDIUM_AND_ABOVE for SEXUALLY_EXPLICIT and HATE_SPEECH. Test with F1-specific queries about incidents.
**Warning signs:** Model returning safety-blocked responses for legitimate F1 queries.

## Code Examples

### Dead Code to Remove (INFRA-03)

**In `mcp_server.py`** -- Remove lines 497-525 (predict_race_results and calculate_championship_scenario tools):
```python
# REMOVE: These import from app.ml which no longer exists
@mcp.tool()
def predict_race_results(year: int, grand_prix: str) -> str:
    ...
    from app.ml.predict import predict_race  # BROKEN IMPORT
    ...

@mcp.tool()
def calculate_championship_scenario(year: int, driver: str) -> str:
    ...
    from app.ml.scenario import calculate_title_scenario  # BROKEN IMPORT
    ...
```

**In `README.md`** -- Remove/update these sections:
- Line 6: "ML model trained on historical race data" -- remove ML reference
- Line 31: `scikit-learn (ML race predictions)` -- remove from architecture diagram
- Line 42: Race Predictions ML feature row -- rewrite for statistical approach
- Lines 109-117: ML model training section -- remove entirely
- Line 135: `/api/predictions` endpoint -- remove (doesn't exist in routes.py)
- Lines 199-200: MCP tools 11/12 (predict, scenario) -- remove
- Lines 302, 319-320: ML directory references -- remove
- Lines 334-335: predictions page reference -- keep (frontend exists, will be reimplemented)
- Line 379: scikit-learn in tech stack -- remove

**In `prompts.py`** -- Line 39 mentions "calculate championship scenarios" which still exists as a tool, but remove any ML prediction references if present.

### Hardcoded Values to Extract (INFRA-06)

Current locations of magic numbers:
```
routes.py:160  -> timeout=30              (tool execution timeout)
routes.py:622  -> FASTF1_TIMEOUT = 60     (race detail timeout, already a constant but not configurable)
routes.py:670  -> timeout=10              (OpenF1 HTTP client timeout)
routes.py:710  -> timeout=10              (OpenF1 session finder timeout)
routes.py:887  -> timeout=0.1            (WebSocket receive check)
main.py:39     -> await asyncio.sleep(30) (prefetch startup delay)
main.py:76     -> timeout=60              (prefetch race timeout)
main.py:88     -> await asyncio.sleep(5)  (inter-race prefetch delay)
main.py:93     -> await asyncio.sleep(1800) (prefetch loop interval)
routes.py:129  -> max_turns = 5           (agentic loop max turns)
```

### Existing print() Calls to Replace (INFRA-04)

Total: 53 print() calls across 5 files:
- `tools.py`: 15 calls (tool execution logging with emoji)
- `routes.py`: 17 calls (request handling, errors, tool dispatch)
- `main.py`: 5 calls (prefetch loop status)
- `ingest.py`: 11 calls (CLI ingestion script -- lower priority, but should be consistent)
- `scripts/test_models.py`: 5 calls (test script -- lowest priority)

Replace pattern:
```python
# BEFORE:
print(f"🛠️  EXECUTING: {tool_name} with args {tool_args}")

# AFTER:
logger.info("tool.executing", tool=tool_name, args=tool_args)
```

### LLM Safety Settings Review (INFRA-05)

```python
# CURRENT (routes.py lines 50-55): Everything set to BLOCK_NONE
safety_settings={
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}

# RECOMMENDED: Appropriate for F1 domain content
safety_settings={
    # F1 discusses crashes, fires, injuries -- keep permissive
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    # F1 has team rivalries, driver criticism -- keep somewhat permissive
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    # Not relevant to F1 -- can be stricter
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    # Not relevant to F1 -- can be stricter
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}
```

Note: The system prompt already has strong identity guardrails (lines 15-26 in prompts.py) that refuse non-F1 topics. The safety settings are a defense-in-depth layer.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `print()` debugging | structlog JSON logging | Industry standard since 2020+ | Machine-parseable logs, log levels, context binding |
| Per-request ChromaDB init | Singleton / lazy init | Always been best practice | Eliminates 2-3 second overhead per rulebook query |
| No WebSocket heartbeat | Ping/pong with TTL tracking | WebSocket RFC 6455 | Prevents connection leaks, works with reverse proxies |
| Hardcoded magic numbers | Environment-configurable constants | Twelve-Factor App methodology | Deploy-time tuning without code changes |

**Deprecated/outdated:**
- `langchain_community.vectorstores.chroma.Chroma` -- use `langchain_chroma.Chroma` instead (already correct in codebase)
- The `app/ml/` directory and all scikit-learn ML prediction code has been removed but references remain

## Open Questions

1. **Render.com WebSocket proxy timeout**
   - What we know: Render.com likely has an idle WebSocket timeout, commonly 60-100 seconds
   - What's unclear: The exact timeout value for the free tier
   - Recommendation: Use 15-second heartbeat interval which is safe for any proxy. Validate after deployment.

2. **ChromaDB initialization during lifespan vs lazy**
   - What we know: Eager init in lifespan blocks startup; lazy init delays first query
   - What's unclear: Whether Render.com has a startup health check timeout that eager init might violate
   - Recommendation: Use lazy singleton (initialize on first `consult_rulebook` call). The 3-5 second delay on first query is acceptable for a personal project.

3. **ingest.py logging migration**
   - What we know: It's a CLI script run manually, not part of the server
   - What's unclear: Whether it should use the same structlog config or keep simple print()
   - Recommendation: Migrate to structlog for consistency, but this is lowest priority within INFRA-04.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `backend/app/api/routes.py`, `backend/app/api/tools.py`, `backend/mcp_server.py`, `backend/main.py` -- direct code inspection
- structlog 25.x documentation: https://www.structlog.org/ -- current stable version
- FastAPI WebSocket documentation: built-in to Starlette/FastAPI

### Secondary (MEDIUM confidence)
- structlog + FastAPI integration patterns: https://gist.github.com/nymous/f138c7f06062b7c43c060bf03759c29e
- Gemini safety settings: https://ai.google.dev/gemini-api/docs/safety-settings
- LangChain Chroma reference: https://reference.langchain.com/python/integrations/langchain_chroma/
- FastAPI WebSocket heartbeat discussion: https://github.com/fastapi/fastapi/discussions/11701

### Tertiary (LOW confidence)
- Render.com WebSocket proxy timeout specifics -- not verified, using conservative 15s interval

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use except structlog which is the clear industry standard
- Architecture: HIGH -- patterns are standard Python/FastAPI; no novel architecture needed
- Pitfalls: HIGH -- identified from direct codebase analysis; all are well-known Python patterns
- Dead code inventory: HIGH -- verified via grep; `app/ml/` directory confirmed non-existent

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (stable domain, no fast-moving dependencies)
