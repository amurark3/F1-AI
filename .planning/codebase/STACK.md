# Technology Stack

**Analysis Date:** 2026-02-16

## Languages

**Primary:**
- Python 3.10.12 - Backend API, data processing, LLM integration
- TypeScript 5 - Frontend application and utilities
- Swift 5.9 - iOS native application

**Secondary:**
- JavaScript - Frontend runtime (Next.js/React)

## Runtime

**Environment:**
- Node.js 16+ (Frontend via Next.js)
- Python 3.10.12 (Backend, specified in `backend/.python-version`)
- iOS 17.0+ (Mobile platform)

**Package Managers:**
- npm (Frontend) - Lockfile: present
- pip (Python Backend) - Lockfile: `backend/requirements.txt`
- Swift Package Manager / Xcode (iOS)

## Frameworks

**Backend:**
- FastAPI 0.100+ - REST API framework for race engineering endpoints
- Uvicorn - ASGI server (runs on port 8000)
- LangChain Core / LangChain Community - LLM orchestration and agentic loops
- Pydantic - Request/response validation and settings management

**Frontend:**
- Next.js 16.1.6 - React framework with SSR and file-based routing
- React 19.2.1 - UI component framework
- Tailwind CSS 4 - Styling via utility classes
- TailwindCSS PostCSS 4 - PostCSS integration

**Testing / Build:**
- ESLint 9 - JavaScript/TypeScript linting
- TypeScript 5 - Type checking

**iOS:**
- SwiftUI - Native UI framework
- SwiftData - Local persistence (CachedResponse model)
- WidgetKit - Home screen widgets

## Key Dependencies

**Critical - LLM & AI:**
- `langchain-google-genai` - Google Generative AI (Gemini) client
- `google-generativeai` - Direct Gemini API access
- `langchain-huggingface` - HuggingFace embeddings (sentence-transformers)
- `langchain-chroma` - Vector database client

**Critical - F1 Data:**
- `fastf1` - Formula 1 data fetching (telemetry, session data, schedules)
- `fastf1.ergast` - F1 historical data and standings via Ergast API

**Critical - Vector DB & Search:**
- `chromadb` - Vector database for regulations (rulebook RAG)
- `tavily-python` - Web search API for real-time F1 news
- `sentence-transformers` - Embeddings model (all-MiniLM-L6-v2) for RAG

**Infrastructure:**
- `httpx` - Async HTTP client (OpenF1 API polling)
- `requests` - HTTP client
- `pandas` - Data manipulation and analysis
- `pypdf` - PDF loading (regulations ingestion)

**Utilities:**
- `python-dotenv` - Environment variable loading
- `fastmcp` - MCP server (optional, Claude Desktop integration)

**Frontend UI:**
- `framer-motion` 12.34.0 - Animation library
- `lucide-react` 0.561.0 - Icon library
- `tailwind-merge` 3.4.0 - Merge Tailwind classes
- `clsx` 2.1.1 - Conditional CSS class composition
- `swr` 2.3.8 - React data fetching hook
- `ai` 5.0.113 - Vercel AI SDK
- `@ai-sdk/react` 2.0.115 - React hooks for AI SDK

## Configuration

**Environment Variables (Backend):**
- `GOOGLE_API_KEY` - Google Generative AI / Gemini API authentication
- `TAVILY_API_KEY` - Web search API key
- `ALLOWED_ORIGINS` - CORS allowlist (default: http://localhost:3000)
- `PYTHON_VERSION` - Python version (3.10.12 specified in render.yaml)

**Build Configuration:**
- `backend/requirements.txt` - Python dependencies
- `frontend/tsconfig.json` - TypeScript compiler options with path aliases (@/*)
- `frontend/next.config.ts` - Next.js configuration (minimal)
- `frontend/eslint.config.mjs` - ESLint configuration
- `ios/project.yml` - XcodeGen project specification

**Deployment Configuration:**
- `render.yaml` - Render.com deployment manifest
  - Build command: `pip install --upgrade pip && pip install -r requirements.txt && python app/rag/ingest.py`
  - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Root directory: `backend/`

## Platform Requirements

**Development:**
- Node.js 16+ for frontend
- Python 3.10.12 for backend
- Xcode 16.0 for iOS
- iOS 17.0+ for running iOS app

**Production:**
- Render.com (Web backend deployment)
- Web server: Uvicorn ASGI server
- Frontend: Vercel recommended (Next.js native) - endpoint configured as `https://f1-ai.onrender.com`

**Local Development:**
- Backend: Runs on `http://0.0.0.0:8000` with auto-reload via uvicorn
- Frontend: Runs on `http://localhost:3000` via Next.js dev server

---

*Stack analysis: 2026-02-16*
