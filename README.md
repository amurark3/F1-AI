# F1 AI — Race Engineer Assistant

An AI-powered Formula 1 analyst and race engineer. Ask it about race results,
qualifying lap times, championship standings, regulatory rules, predictions, and more.
The assistant has access to real-time F1 data, the official FIA regulations, and an
ML model trained on historical race data.

---

## Architecture

```
F1-AI/
├── frontend/          Next.js 16 + React 19 (TypeScript)
├── backend/           Python FastAPI + LangChain + Gemini
└── render.yaml        Render.com deployment config
```

```
Browser (Next.js)
    │  SWR fetches (schedule, standings)
    │  Streaming POST /api/chat
    ▼
FastAPI Backend
    │
    ├─ Gemini 2.0 Flash   (LLM orchestration)
    ├─ FastF1              (qualifying, race, sprint data)
    ├─ Ergast API          (championship standings)
    ├─ Tavily              (web search)
    ├─ ChromaDB            (FIA regulations vector search)
    ├─ scikit-learn         (ML race predictions)
    └─ MCP Server          (Claude Desktop / Cursor integration)
```

---

## Features

| Feature | Description |
|---|---|
| **AI Chat (Pit Wall)** | Streaming chat with F1 race-engineer persona, multi-chat with localStorage persistence |
| **Race Predictions** | ML model predicts finishing order based on qualifying, form, and constructor strength |
| **Championship Scenarios** | Points-per-race needed calculator for any driver's title chances |
| **Race Calendar** | Full season schedule with timezone conversion for every F1 circuit |
| **Championship Standings** | Live WDC and WCC tables (2021–2026, with entry list fallback for unstarted seasons) |
| **Qualifying Results** | Q1/Q2/Q3 tables for any Grand Prix |
| **Race Results** | Full classification with grid deltas and DNF reasons |
| **Sprint Data** | Sprint race and Sprint Qualifying (Shootout) results |
| **Driver Comparison** | Sector-by-sector fastest-lap telemetry diff |
| **Rulebook** | Semantic search of FIA Sporting, Technical, and Financial Regulations (2024–2026) |
| **Web Search** | Real-time news via Tavily for post-cutoff information |
| **MCP Server** | All tools accessible via Claude Desktop or Cursor |

---

## Prerequisites

| Tool | Version |
|---|---|
| Node.js | 18 or later |
| Python | 3.10 or later |
| pip | latest |

---

## Backend Setup

All commands run from the `backend/` directory.

### 1. Create and activate a virtual environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> First run also downloads the `sentence-transformers/all-MiniLM-L6-v2`
> embedding model (~90 MB) used by the rulebook search.

### 3. Configure environment variables

Create a `.env` file in the `backend/` directory:

```env
GOOGLE_API_KEY=your_google_generative_ai_key
TAVILY_API_KEY=your_tavily_search_key
```

- **GOOGLE_API_KEY** — get one at [Google AI Studio](https://aistudio.google.com/app/apikey)
- **TAVILY_API_KEY** — get one at [app.tavily.com](https://app.tavily.com)

### 4. Ingest the FIA regulations (one-time setup)

```bash
python app/rag/ingest.py
```

This scans `data/raw/` for PDFs, splits them into chunks, generates embeddings,
and saves to `data/chroma/`. Re-run whenever you add/update regulation PDFs.

### 5. Train the ML model (one-time setup)

```bash
python -m app.ml.train
```

Trains a GradientBoostingRegressor on 2018–2025 historical data and saves to
`models/race_predictor.joblib`. This fetches data from the Ergast API and may
take a few minutes due to rate limiting.

### 6. Start the server

```bash
python main.py
```

The API will be available at **http://localhost:8000**.

#### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming AI chat with tool orchestration |
| `GET` | `/api/schedule/{year}` | Season calendar (UTC) |
| `GET` | `/api/standings/drivers/{year}` | WDC standings |
| `GET` | `/api/standings/constructors/{year}` | WCC standings |
| `GET` | `/api/predictions/{year}/{grand_prix}` | ML race prediction |
| `GET` | `/api/scenario/{year}/{driver}` | Championship scenario |
| `GET` | `/api/health` | Liveness probe |

Interactive API docs: http://localhost:8000/docs

---

## Frontend Setup

All commands run from the `frontend/` directory.

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. (Optional) Configure backend URL

The frontend defaults to `http://localhost:8000`. To change it, create
`frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://your-backend-url:8000
```

### 3. Start the development server

```bash
npm run dev
```

The app will be available at **http://localhost:3000**.

| Command | Description |
|---|---|
| `npm run dev` | Start development server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | Run ESLint |

---

## MCP Server Setup (Claude Desktop / Cursor)

The MCP server exposes all 13 F1 tools so Claude Desktop or Cursor can call them
directly without the web UI.

### Available MCP Tools

| # | Tool | Description |
|---|---|---|
| 1 | `get_season_schedule` | Full F1 calendar for any year |
| 2 | `get_race_results` | Race classification with grid delta and points |
| 3 | `get_qualifying_results` | Q1/Q2/Q3 qualifying results |
| 4 | `get_sprint_results` | Saturday sprint race results |
| 5 | `get_sprint_qualifying_results` | Sprint shootout SQ1/SQ2/SQ3 |
| 6 | `compare_drivers` | Sector-by-sector qualifying lap comparison |
| 7 | `get_driver_standings` | World Drivers' Championship table |
| 8 | `get_constructor_standings` | World Constructors' Championship table |
| 9 | `consult_rulebook` | Semantic search of FIA regulations (RAG) |
| 10 | `perform_web_search` | Real-time F1 news via Tavily |
| 11 | `predict_race_results` | ML-predicted finishing order |
| 12 | `calculate_championship_scenario` | Points-per-race title calculator |
| 13 | `health_check` | Backend and data source status |

### Claude Desktop Configuration

Add this to your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "f1-race-engineer": {
      "command": "/path/to/backend/.venv/bin/python",
      "args": ["/path/to/backend/mcp_server.py"],
      "env": {
        "GOOGLE_API_KEY": "your_key_here",
        "TAVILY_API_KEY": "your_key_here"
      }
    }
  }
}
```

Replace `/path/to/backend` with the actual absolute path to your `backend/` directory.

### Cursor Configuration

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "f1-race-engineer": {
      "command": "/path/to/backend/.venv/bin/python",
      "args": ["/path/to/backend/mcp_server.py"]
    }
  }
}
```

### Claude Code Configuration

Add to your Claude Code settings (`.claude/settings.json` or project CLAUDE.md):

```json
{
  "mcpServers": {
    "f1-race-engineer": {
      "command": "/path/to/backend/.venv/bin/python",
      "args": ["/path/to/backend/mcp_server.py"]
    }
  }
}
```

### Testing the MCP Server

Run it directly to verify it starts:

```bash
cd backend
source .venv/bin/activate
python mcp_server.py
```

The server communicates via stdio by default. You should see no errors on startup.
Claude Desktop / Cursor will connect automatically once configured.

---

## Running Both Servers Together

Open two terminal tabs:

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
python main.py
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open **http://localhost:3000**.

---

## Project Structure

```
backend/
├── main.py                   Entry point — FastAPI app, CORS, router
├── mcp_server.py             MCP server (13 tools for Claude/Cursor)
├── requirements.txt          Python dependencies
├── .env                      API keys (not committed)
├── f1_cache/                 FastF1 disk cache (auto-created)
├── models/                   Trained ML models (.joblib)
├── scripts/
│   └── test_models.py        API key verification script
├── data/
│   ├── raw/
│   │   ├── 2024/             FIA regulation PDFs for 2024
│   │   ├── 2025/             FIA regulation PDFs for 2025
│   │   └── 2026/             FIA regulation PDFs for 2026
│   └── chroma/               ChromaDB vector database (generated by ingest.py)
└── app/
    ├── api/
    │   ├── routes.py         HTTP endpoints + agentic chat loop
    │   ├── tools.py          13 LLM-callable tools
    │   └── prompts.py        Race-engineer system prompt
    ├── ml/
    │   ├── features.py       Feature engineering from Ergast data
    │   ├── train.py          Offline model training script
    │   ├── predict.py        Inference — predicts race finishing order
    │   └── scenario.py       Championship scenario calculator
    └── rag/
        └── ingest.py         PDF → ChromaDB ingestion script

frontend/
├── package.json
└── app/
    ├── layout.tsx            Root layout (fonts, metadata)
    ├── page.tsx              Home — AI chat (Pit Wall) with multi-chat
    ├── globals.css           Tailwind CSS base styles
    ├── calendar/
    │   └── page.tsx          Race calendar page
    ├── standings/
    │   └── page.tsx          Championship standings page
    ├── predictions/
    │   └── page.tsx          ML predictions + scenario calculator
    ├── components/
    │   ├── NavShell.tsx      Shared navigation header
    │   ├── ChatSidebar.tsx   Multi-chat sidebar
    │   ├── RaceCalendar.tsx  Race weekend card grid with timezone conversion
    │   ├── Standings.tsx     WDC/WCC standings with team colors
    │   └── TelemetryCard.tsx Driver telemetry comparison card
    ├── constants/
    │   ├── api.ts            Backend URL configuration
    │   └── timeZone.ts       IANA timezone list for F1 circuits
    ├── hooks/
    │   └── useLocalChats.ts  localStorage-based chat persistence
    └── utils/
        └── fetcher.ts        SWR fetch wrapper
```

---

## Adding New FIA Regulation PDFs

1. Place the PDF in the correct year folder, e.g. `backend/data/raw/2026/`.
2. Name it so that it contains `sporting`, `technical`, or `financial`
   (case-insensitive) for automatic type detection.
3. Re-run the ingestion script:
   ```bash
   cd backend
   python app/rag/ingest.py
   ```
4. Restart the backend server.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend framework | Next.js 16, React 19 |
| Styling | Tailwind CSS 4 |
| Data fetching | SWR 2 |
| Language | TypeScript 5 |
| Backend framework | FastAPI + Uvicorn |
| LLM | Google Gemini 2.0 Flash |
| LLM orchestration | LangChain |
| F1 data | FastF1, Ergast API |
| ML predictions | scikit-learn (GradientBoostingRegressor) |
| Vector database | ChromaDB |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Web search | Tavily |
| MCP | FastMCP (Model Context Protocol) |
| Language | Python 3.10+ |
