# Codebase Structure

**Analysis Date:** 2026-02-16

## Directory Layout

```
F1-AI/
├── backend/                          # Python FastAPI backend
│   ├── main.py                       # FastAPI app entry point, lifespan, CORS setup
│   ├── app/                          # Application package
│   │   ├── __init__.py
│   │   ├── api/                      # API routes and tools
│   │   │   ├── __init__.py
│   │   │   ├── routes.py             # 8 REST endpoints + agentic chat loop
│   │   │   ├── tools.py              # 11 LLM-callable tools (@tool decorators)
│   │   │   ├── prompts.py            # System persona (RACE_ENGINEER_PERSONA)
│   │   │   └── circuits.py           # Static circuit metadata lookup table
│   │   └── rag/                      # Retrieval-Augmented Generation (rulebook search)
│   │       ├── __init__.py
│   │       └── ingest.py             # Populate ChromaDB with FIA regulations
│   ├── data/                         # Data storage
│   │   ├── chroma/                   # ChromaDB vector store (rulebook embeddings)
│   │   ├── raw/                      # Raw FIA regulation PDFs
│   │   └── [year]/                   # (if any season-specific data)
│   ├── f1_cache/                     # FastF1 disk cache
│   │   ├── 2024/
│   │   └── 2025/
│   ├── .venv/                        # Python virtual environment
│   ├── requirements.txt              # Python dependencies
│   └── mcp_server.py                 # (Not explored; possible MCP integration)
│
├── frontend/                         # Next.js React app
│   ├── app/                          # Next.js app directory
│   │   ├── layout.tsx                # Root HTML layout
│   │   ├── page.tsx                  # Home page (renders ChatScreen)
│   │   ├── calendar/
│   │   │   └── page.tsx              # /calendar route (placeholder)
│   │   ├── standings/
│   │   │   └── page.tsx              # /standings route (placeholder)
│   │   ├── components/               # Reusable React components
│   │   │   ├── ChatScreen.tsx        # Main chat UI container
│   │   │   ├── ChatMessages.tsx      # Message list display
│   │   │   ├── ChatInput.tsx         # Message input form
│   │   │   ├── ChatSidebar.tsx       # Conversation history sidebar
│   │   │   ├── ChatWelcome.tsx       # Empty state with prompt suggestions
│   │   │   ├── NavShell.tsx          # Top navigation wrapper
│   │   │   ├── RaceCard.tsx          # Race details card (large, multi-section)
│   │   │   ├── RaceCalendar.tsx      # Season calendar view
│   │   │   ├── RaceResults.tsx       # Race classification table
│   │   │   ├── QualifyingResults.tsx # Qualifying session results
│   │   │   ├── Standings.tsx         # Driver/Constructor championship standings
│   │   │   ├── PodiumDisplay.tsx     # Top 3 finish podium visual
│   │   │   ├── TrackInsights.tsx     # Circuit metadata display
│   │   │   ├── TelemetryCard.tsx     # Driver comparison telemetry
│   │   │   └── RaceJumpNav.tsx       # Race selection navigation
│   │   ├── constants/                # App-level constants
│   │   │   ├── api.ts                # API_BASE URL configuration
│   │   │   └── timeZone.ts           # Timezone utilities
│   │   ├── hooks/                    # React custom hooks
│   │   │   ├── useChat.ts            # Chat state, streaming, message handling
│   │   │   └── useLocalChats.ts      # localStorage persistence for chats
│   │   ├── utils/                    # Utility functions
│   │   │   └── fetcher.ts            # SWR fetcher for API calls
│   │   ├── globals.css               # Global Tailwind styles
│   │   └── middleware.ts             # (if any Next.js middleware)
│   ├── node_modules/                 # npm dependencies
│   ├── .next/                        # Next.js build output (generated)
│   ├── package.json                  # npm config and scripts
│   ├── tsconfig.json                 # TypeScript configuration
│   ├── next.config.js                # Next.js configuration
│   └── tailwind.config.js            # Tailwind CSS configuration
│
├── ios/                              # iOS app (SwiftUI)
│   ├── F1AI/                         # Main app bundle
│   │   ├── F1AIApp.swift             # App entry point
│   │   ├── Models/                   # Data models
│   │   ├── Views/                    # SwiftUI views
│   │   ├── ViewModels/               # MVVM view models
│   │   ├── Services/                 # API and networking services
│   │   ├── Widgets/                  # App widgets
│   │   └── Resources/                # Assets
│   ├── F1AIWidgets/                  # Widget extension
│   └── F1AI.xcodeproj/               # Xcode project
│
├── .planning/                        # GSD planning documents
│   └── codebase/                     # Architecture/structure analysis (THIS FILE)
│
├── .claude/                          # Claude workbench artifacts
│
├── .git/                             # Git repository
│
├── .gitignore
├── README.md
└── package.json                      # Root workspace package (if mono-repo)
```

## Directory Purposes

**backend/app/api/:**
- Purpose: REST API endpoints and LLM tool definitions
- Contains: Route handlers, tool decorators, prompts, static data
- Key files:
  - `routes.py`: 8 endpoints (chat, schedule, race, standings, compare, live, health) + agentic loop
  - `tools.py`: 11 LLM-callable tools for F1 data access
  - `prompts.py`: System persona injection
  - `circuits.py`: Static circuit lookup (27 venues)

**backend/app/rag/:**
- Purpose: Retrieval-Augmented Generation for rulebook queries
- Contains: Ingest script to populate ChromaDB with FIA regulations
- Key files:
  - `ingest.py`: Parse regulation PDFs, chunk, embed with HuggingFace, store in ChromaDB

**backend/data/:**
- Purpose: Persistent data storage
- Contains:
  - `chroma/`: ChromaDB vector store with FIA regulations metadata
  - `raw/`: Raw FIA regulation PDFs organized by year
  - `[year]/`: (optional) Season-specific data

**backend/f1_cache/:**
- Purpose: FastF1 disk cache for performance
- Contains: Cached session data organized by year
- Auto-populated by FastF1 library on first access

**frontend/app/components/:**
- Purpose: React components for UI
- Organized by feature:
  - Chat-related: ChatScreen, ChatMessages, ChatInput, ChatSidebar, ChatWelcome
  - Race data: RaceCard, RaceCalendar, RaceResults, QualifyingResults, Standings, PodiumDisplay
  - Navigation: NavShell, RaceJumpNav
  - Other: TrackInsights, TelemetryCard

**frontend/app/hooks/:**
- Purpose: React custom hooks for reusable logic
- Key files:
  - `useChat.ts`: Drives entire chat state machine (send, stream, tool status, regenerate)
  - `useLocalChats.ts`: Manages localStorage persistence of chat history

**frontend/app/constants/:**
- Purpose: App-wide constants
- Key files:
  - `api.ts`: API_BASE URL from env var NEXT_PUBLIC_API_URL
  - `timeZone.ts`: Timezone utility functions

## Key File Locations

**Entry Points:**

- `backend/main.py`: Backend server start (FastAPI app init)
- `frontend/app/page.tsx`: Frontend home page (renders ChatScreen)
- `backend/app/api/routes.py:81-198`: Chat endpoint (agentic LLM loop)
- `frontend/app/hooks/useChat.ts:63-130`: sendMessage function (orchestrates chat flow)

**Configuration:**

- `backend/main.py:117`: CORS origins from ALLOWED_ORIGINS env var
- `frontend/app/constants/api.ts:1`: API_BASE from NEXT_PUBLIC_API_URL env var
- `backend/.env`: (not in repo) Contains GOOGLE_API_KEY, TAVILY_API_KEY
- `frontend/.env.local`: (if used) Contains NEXT_PUBLIC_API_URL

**Core Logic:**

- `backend/app/api/routes.py:118-198`: Agentic loop implementation (max 5 turns of reasoning)
- `backend/app/api/tools.py:615-630`: TOOL_LIST and TOOL_MAP definitions
- `backend/app/api/prompts.py:10-42`: Race Engineer persona system prompt
- `frontend/app/hooks/useChat.ts:63-130`: Chat message handling and streaming
- `frontend/app/hooks/useLocalChats.ts:17-29`: localStorage read/write functions

**Testing:**

- Not detected in codebase (no test files found)

**Utilities:**

- `backend/app/api/tools.py:49-65`: _fmt_timedelta helper (time formatting)
- `backend/app/api/routes.py:392-401`: _fmt_td helper (time formatting for race results)
- `frontend/app/utils/fetcher.ts`: SWR fetcher wrapper for API calls
- `frontend/app/constants/timeZone.ts`: Timezone conversion utilities

## Naming Conventions

**Files:**

- Components: PascalCase.tsx (e.g., `ChatScreen.tsx`, `RaceCard.tsx`)
- Hooks: camelCase with 'use' prefix (e.g., `useChat.ts`, `useLocalChats.ts`)
- Pages: lowercase with trailing directory (e.g., `app/calendar/page.tsx`)
- Routes (backend): routes.py (single file, all endpoints)
- Tools (backend): tools.py (single file, all @tool decorators)
- Constants: lowercase (e.g., `api.ts`, `timeZone.ts`)
- Utils: lowercase (e.g., `fetcher.ts`)

**Directories:**

- Feature-based: `components/`, `hooks/`, `constants/`, `utils/`, `api/`, `rag/`
- Flat structure for small apps; Next.js convention for pages under app/

**Functions:**

- Backend: snake_case (e.g., `_build_race_detail_sync`, `_fmt_timedelta`, `get_season_schedule`)
- Frontend: camelCase (e.g., `sendMessage`, `handleSubmit`, `getDriverCode`)
- LLM tools: snake_case matching tool names (e.g., `get_race_results`, `compare_drivers`)

**Variables:**

- Backend: snake_case (e.g., `max_turns`, `tool_result`, `race_detail_cache`)
- Frontend: camelCase (e.g., `isLoading`, `toolStatus`, `activeChatId`)
- React state: camelCase with 'set' prefix for setters (e.g., `messages`, `setMessages`)

**Types/Interfaces:**

- Frontend: PascalCase (e.g., `Message`, `Chat`)
- Backend: Pydantic BaseModel (PascalCase like `ChatRequest`)
- LangChain types: Capitalized (SystemMessage, HumanMessage, ToolMessage)

## Where to Add New Code

**New Chat Feature (e.g., star/pin message):**
- State logic: Add to `frontend/app/hooks/useChat.ts` (new useState, useCallback)
- Persistence: Extend Chat interface in `frontend/app/hooks/useLocalChats.ts`
- UI: New component in `frontend/app/components/` or modify `ChatMessages.tsx`
- Backend: If needed, new endpoint in `backend/app/api/routes.py` under router.get/post

**New F1 Data Tool (e.g., tire strategy analyzer):**
- Tool function: Add @tool in `backend/app/api/tools.py` (must be before TOOL_LIST definition at line 615)
- Add to TOOL_LIST and TOOL_MAP at bottom of tools.py
- Documentation: Update docstring with usage guidelines for LLM
- Test: Call tool manually or ask chat endpoint with prompt

**New Endpoint (e.g., /api/driver/{code}):**
- Route handler: Add @router.get in `backend/app/api/routes.py`
- Data access: Use FastF1 or Ergast as needed (pattern from existing endpoints)
- Caching: Add to cache dict if applicable (like race_detail_cache)
- CORS: Already configured in main.py

**New Component (e.g., DriverComparison page):**
- Component file: Create `frontend/app/components/DriverComparison.tsx`
- Page route: Create `frontend/app/driver/page.tsx` to mount component
- Styling: Use Tailwind classes (globals.css already imported)
- Data fetching: Use fetch or SWR fetcher in component or custom hook

**New UI Page (e.g., /driver/{driverCode}):**
- Page file: Create `frontend/app/driver/[driverCode]/page.tsx`
- Component: Import component in page.tsx, wrap in NavShell
- Hook: If stateful, create `frontend/app/hooks/useDriver.ts`

**New Database Model (e.g., save user preferences):**
- Currently no server-side DB. Consider:
  - Add SQLite/PostgreSQL and ORM to backend
  - Create models in `backend/app/models/`
  - Add routes in `backend/app/api/routes.py`
  - Add CORS tokens/auth if needed

**New Environment Variable:**
- Backend: Add to `backend/.env` and reference with `os.getenv("VAR_NAME")`
- Frontend: Add to `frontend/.env.local` as `NEXT_PUBLIC_*` to access in browser

## Special Directories

**backend/f1_cache/:**
- Purpose: FastF1 library caches session data here to avoid re-downloading
- Generated: Yes (auto-created by FastF1.Cache.enable_cache() at line 66 in routes.py)
- Committed: No (add to .gitignore if not already)
- Typical size: Grows over season as more races are cached

**backend/data/chroma/:**
- Purpose: ChromaDB vector database for rulebook RAG
- Generated: Yes (populated by `python app/rag/ingest.py`)
- Committed: Possibly (depends on whether PDFs are in repo)
- Required: Yes, for consult_rulebook tool to work

**frontend/.next/:**
- Purpose: Next.js build artifacts and cache
- Generated: Yes (created by `npm run build` or `npm run dev`)
- Committed: No (.gitignore excludes)
- Temporary: Yes, can be deleted and regenerated

**frontend/node_modules/:**
- Purpose: npm package dependencies
- Generated: Yes (created by `npm install` from package-lock.json)
- Committed: No (.gitignore excludes)
- Size: Large (~1GB typical for modern React apps)

**ios/F1AI.xcodeproj/:**
- Purpose: Xcode project metadata and build configuration
- Generated: No (manually created, part of source)
- Committed: Partial (*.xcworkspace committed; .xcuserdata is .gitignored)

---

*Structure analysis: 2026-02-16*
