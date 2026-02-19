# External Integrations

**Analysis Date:** 2026-02-16

## APIs & External Services

**LLM & AI:**
- Google Generative AI (Gemini 2.0-flash) - AI-powered race analysis and chat
  - SDK/Client: `langchain-google-genai`, `google-generativeai`
  - Auth: `GOOGLE_API_KEY` environment variable
  - Model: `gemini-2.0-flash` (temperature 0 for deterministic responses)
  - Endpoint: `https://generativeai.googleapis.com/v1/...`
  - Safety settings: Relaxed for racing incidents/crashes (BLOCK_NONE for dangerous content, hate speech, harassment, sexually explicit)
  - Location: `backend/app/api/routes.py` (lines 46-56)

**Web Search:**
- Tavily Search API - Real-time F1 news and recent events lookup
  - SDK/Client: `tavily-python`
  - Auth: `TAVILY_API_KEY` environment variable
  - Usage: Tool invoked by LLM for queries beyond model knowledge cutoff
  - Configuration: `search_depth="basic"`, `max_results=3`
  - Location: `backend/app/api/tools.py` (perform_web_search function)

**F1 Data Sources:**
- FastF1 API (internal Python library) - Session telemetry, lap data, race results
  - SDK/Client: `fastf1` Python package
  - Cache: Local disk cache at `f1_cache/` directory
  - Data includes: race results, qualifying sessions, telemetry, lap times
  - Location: Used throughout `backend/app/api/routes.py` and `backend/app/api/tools.py`

- Ergast API (via fastf1.ergast) - F1 historical data and standings
  - SDK/Client: `fastf1.ergast.Ergast`
  - Endpoints queried: driver standings, constructor standings, race results, qualifying results
  - Lightweight alternative to full FastF1 loads
  - Location: `backend/app/api/routes.py` (lines 284-334, 338-377) and tools.py

- OpenF1 API - Live race timing positions
  - Endpoint: `https://api.openf1.org/v1/position` (position data)
  - Endpoint: `https://api.openf1.org/v1/sessions` (find session keys)
  - HTTP Client: `httpx` (async)
  - Poll interval: 8 seconds
  - WebSocket streaming to connected clients
  - Location: `backend/app/api/routes.py` (lines 667-724, live timing endpoint)

## Data Storage

**Databases:**
- None (stateless API)

**Vector Database (RAG):**
- ChromaDB - Vector embeddings for FIA regulations lookup
  - Purpose: Semantic search over official Sporting, Technical, Financial regulations
  - Embeddings model: `sentence-transformers/all-MiniLM-L6-v2`
  - Persistence: Local directory at `data/chroma/`
  - Data source: PDF regulations loaded via `backend/app/rag/ingest.py`
  - Access: `langchain_chroma.Chroma` via LangChain
  - Location: `backend/app/api/tools.py` (consult_rulebook function, lines 427-492)

**Caching:**
- FastF1 Local Disk Cache - Session data caching
  - Location: `backend/f1_cache/`
  - Prevents repeated API calls for same session data
  - Setup: `fastf1.Cache.enable_cache("f1_cache")` in `backend/app/api/routes.py`

- In-Memory Race Detail Cache (Backend)
  - Type: Python dict keyed by `(year, round_num)`
  - Variable: `race_detail_cache` in `backend/app/api/routes.py` (line 385)
  - Purpose: Cache enriched race data (circuit, results, qualifying, podium)
  - Populated: On-demand requests + background prefetch loop
  - Lifetime: Application uptime

- iOS Local Cache
  - Type: SwiftData persistent store
  - Model: `CachedResponse`
  - Purpose: Cache API responses for offline capability
  - Location: `ios/F1AI/Models/` and app initialization

## Authentication & Identity

**Auth Provider:**
- None (stateless, no user accounts)

**API Key Management:**
- Environment variables only
- Required keys:
  - `GOOGLE_API_KEY` - Gemini API authentication
  - `TAVILY_API_KEY` - Tavily search authentication

## Monitoring & Observability

**Error Tracking:**
- None (console logging only)

**Logs:**
- Console output via Python print statements
- Debug indicators: 🤖 (model), 🛠️ (tools), ✅ (success), ❌ (errors), ⏱️ (timeouts)
- Location: Throughout `backend/app/api/routes.py` and `backend/app/api/tools.py`

## CI/CD & Deployment

**Hosting:**
- Render.com - Backend service
- iOS - TestFlight / App Store (not deployed yet)
- Frontend - Suggested: Vercel (Next.js native platform)

**CI Pipeline:**
- None configured (manual deployment)

**Build & Start:**
- Build: `pip install --upgrade pip && pip install -r requirements.txt && python app/rag/ingest.py`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Specified in: `render.yaml`

## Environment Configuration

**Required Environment Variables:**
```
GOOGLE_API_KEY       # Gemini API key for LLM
TAVILY_API_KEY       # Tavily search API key
ALLOWED_ORIGINS      # CORS origins (comma-separated, e.g., "http://localhost:3000,https://example.com")
PYTHON_VERSION       # Python version (3.10.12 on Render)
```

**Secrets Location:**
- Backend: `.env` file (not committed, see `.gitignore`)
- Example: `backend/.env.example` shows required structure
- Production: Render.com environment variables (marked `sync: false` for secrets)

## Webhooks & Callbacks

**Incoming:**
- WebSocket connections for live timing
  - Endpoint: `/live/{year}/{round_num}` (WebSocket)
  - Clients: iOS app, frontend (persistent connection)
  - Message type: `{"type": "positions", "data": [...]}`
  - Poll source: OpenF1 API every 8 seconds
  - Location: `backend/app/api/routes.py` (lines 860-898)

**Outgoing:**
- None

## Circuit Information

**Circuit Data Source:**
- Custom lookup via `backend/app/api/circuits.py`
- Data: Track layout, characteristics, speed profile details
- Used by: Schedule and race detail endpoints to enrich circuit info
- Location: `backend/app/api/circuits.py`, invoked from routes

## Background Tasks

**Race Detail Prefetcher:**
- Purpose: Preload completed race data to serve instantly
- Schedule: Every 30 minutes
- Process:
  1. Check F1 schedule
  2. Identify completed races (race + 3h buffer)
  3. Load one race at a time with 5-10 second pause
  4. Cache results in `race_detail_cache`
- Timeout: 60 seconds per race
- Lock: Thread lock to serialize FastF1 loads (not thread-safe)
- Location: `backend/main.py` (lines 29-93, managed by lifespan context manager)

## Frontend-to-Backend Communication

**Protocol:**
- HTTP/REST for data endpoints
- WebSocket for live timing

**Base URL:**
- Development: `http://localhost:8000`
- Production: `https://f1-ai.onrender.com` (configured in iOS and frontend)
- Location: `ios/F1AI/Services/APIClient.swift` (line with `baseURL`)

**CORS:**
- Middleware: FastAPI CORSMiddleware
- Configuration: `ALLOWED_ORIGINS` env var (comma-separated)
- Allows: credentials, all methods, all headers
- Location: `backend/main.py` (lines 116-125)

---

*Integration audit: 2026-02-16*
