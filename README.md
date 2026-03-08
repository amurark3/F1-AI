# F1 AI — Race Engineer Assistant

An AI-powered Formula 1 analyst and race engineer. Ask it about race results,
qualifying lap times, championship standings, regulatory rules, predictions, and more.

Available as a **web app**, **iOS app**, and **MCP server** for Claude Desktop / Cursor.

---

## Architecture

```
F1-AI/
├── backend/    Python FastAPI + LangChain + Gemini 2.0 Flash
├── frontend/   Next.js 16 + React 19 (TypeScript)
├── ios/        SwiftUI iOS app
└── render.yaml Render.com deployment config
```

```
iOS App  ──────────────────────────────────────┐
Web App (Next.js)  ────────────────────────────┤
                                               ▼
                                       FastAPI Backend
                                               │
                          ┌────────────────────┼────────────────────┐
                          │                    │                    │
                   Gemini 2.0 Flash      FastF1 + Ergast      ChromaDB RAG
                   (LLM + tools)         (F1 data)            (FIA regulations)
                          │
                     Tavily Search
                     (live news)
```

---

## Features

| Feature | Web | iOS |
|---|---|---|
| **AI Chat (Pit Wall)** — streaming race-engineer persona | ✅ | ✅ |
| **Race Calendar** — full season schedule with circuit info | ✅ | ✅ |
| **Championship Standings** — live WDC and WCC tables | ✅ | ✅ |
| **Race Predictions** — probabilistic finishing order with reasoning factors | ✅ | ✅ |
| **Championship Scenarios** — points-to-clinch calculator | ✅ | ✅ |
| **Race & Qualifying Results** — full classification, Q1/Q2/Q3 | ✅ | ✅ |
| **Sprint Results** — sprint race and shootout results | ✅ | ✅ |
| **Driver Comparison** — sector-by-sector telemetry diff | ✅ | ✅ |
| **Live Timing** — real-time position tracking via WebSocket | — | ✅ |
| **Rulebook** — semantic search of FIA regulations (2024–2026) | ✅ | ✅ (via chat) |
| **Web Search** — real-time F1 news via Tavily | ✅ | ✅ (via chat) |
| **MCP Server** — all tools in Claude Desktop / Cursor | ✅ | — |

---

## Prerequisites

| Tool | Version |
|---|---|
| Node.js | 18+ |
| Python | 3.10+ |
| Xcode | 15+ (iOS only) |

---

## Running Locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GOOGLE_API_KEY=your_google_generative_ai_key
TAVILY_API_KEY=your_tavily_key
OPENWEATHERMAP_API_KEY=your_openweathermap_key   # optional — weather tool
```

- **GOOGLE_API_KEY** — [Google AI Studio](https://aistudio.google.com/app/apikey)
- **TAVILY_API_KEY** — [app.tavily.com](https://app.tavily.com)

```bash
python main.py
# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
# App available at http://localhost:3000
```

### iOS

Open the project in Xcode and run any simulator:

```bash
open ios/F1AI.xcodeproj
```

In **DEBUG builds** (Simulator / Xcode Run), the app points to `http://localhost:8000`.
In **Release builds** (Archive / TestFlight), it points to `https://f1-ai.onrender.com`.

> **Physical device**: iOS cannot reach `localhost` — update `APIClient.baseURL` to your Mac's local IP (e.g. `http://192.168.x.x:8000`).

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming AI chat with tool orchestration |
| `GET` | `/api/schedule/{year}` | Season calendar |
| `GET` | `/api/standings/drivers/{year}` | WDC standings |
| `GET` | `/api/standings/constructors/{year}` | WCC standings |
| `GET` | `/api/race/{year}/{round_num}` | Race + qualifying results |
| `GET` | `/api/compare/{year}/{driver1}/{driver2}` | Telemetry comparison |
| `GET` | `/api/predictions/{year}/{round_num}` | Race outcome predictions |
| `WS` | `/api/live/{year}/{round_num}` | Real-time position WebSocket |
| `GET` | `/api/health` | Liveness probe |

---

## One-Time Setup (Optional)

### FIA Regulations (rulebook search)

Place regulation PDFs in `backend/data/raw/{year}/` (name them to contain
`sporting`, `technical`, or `financial`), then run:

```bash
cd backend && source .venv/bin/activate
python app/rag/ingest.py
```

This generates a ChromaDB vector database at `backend/data/chroma/`. Re-run
whenever you add or update PDFs.

### ML Model Training (improved predictions)

The prediction engine works out of the box using a heuristic scoring model
(qualifying position, recent form, circuit history, team strength). Optionally
train a GradientBoostingRegressor on 2018–2024 historical data for improved
accuracy:

```bash
cd backend && source .venv/bin/activate
pip install scikit-learn joblib   # if not already installed
python -m app.ml.train
```

This fetches data from FastF1 and Ergast — expect 30–60 minutes on first run
due to API rate limiting. Subsequent runs are fast (data is disk-cached in
`f1_cache/`). The trained model is saved to `backend/models/race_predictor.joblib`.

> The heuristic model is always the active prediction engine. The trained model
> is available for future wiring into the prediction API.

---

## MCP Server (Claude Desktop / Cursor)

Exposes all F1 tools so Claude Desktop or Cursor can call them directly.

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "f1-race-engineer": {
      "command": "/absolute/path/to/backend/.venv/bin/python",
      "args": ["/absolute/path/to/backend/mcp_server.py"],
      "env": {
        "GOOGLE_API_KEY": "your_key",
        "TAVILY_API_KEY": "your_key"
      }
    }
  }
}
```

Test it starts cleanly:

```bash
cd backend && source .venv/bin/activate && python mcp_server.py
```

---

## Project Structure

```
backend/
├── main.py                   FastAPI entry point + CORS + router
├── mcp_server.py             MCP server for Claude Desktop / Cursor
├── requirements.txt
├── app/
│   ├── api/
│   │   ├── routes.py         HTTP + WebSocket endpoints, agentic chat loop
│   │   ├── tools.py          LangChain tools (F1 data, predictions, rulebook, search)
│   │   ├── prompts.py        Race-engineer system prompt
│   │   └── circuits.py       Circuit GPS coordinates
│   ├── data/
│   │   ├── predictions.py    Heuristic race prediction engine
│   │   ├── strategy.py       Pit strategy analysis
│   │   └── weather.py        Circuit weather
│   ├── ml/
│   │   └── train.py          Optional ML training script (GradientBoostingRegressor)
│   └── rag/
│       └── ingest.py         PDF → ChromaDB ingestion
├── data/
│   ├── raw/{year}/           FIA regulation PDFs
│   └── chroma/               ChromaDB vector DB (generated)
├── models/                   Trained ML models (generated)
└── f1_cache/                 FastF1 disk cache (auto-created)

frontend/
└── app/
    ├── page.tsx              AI Chat (Pit Wall)
    ├── calendar/             Race calendar
    ├── standings/            WDC + WCC standings
    ├── predictions/          Race predictions + championship scenarios
    └── components/           Shared UI components

ios/F1AI/
├── Views/
│   ├── Tabs/                 Tab bar (Calendar, Standings, Chat, Compare, Live)
│   ├── Calendar/             Race schedule views
│   ├── Standings/            WDC + WCC + Predictions tabs
│   ├── Chat/                 Streaming AI chat
│   ├── Compare/              Driver telemetry comparison
│   ├── Live/                 Real-time timing (WebSocket)
│   ├── Predictions/          Race predictions + Championship scenarios
│   └── Settings/             Notifications + preferences
├── Services/
│   ├── APIClient.swift       REST API client (localhost in DEBUG, production in Release)
│   ├── ChatStreamService.swift Streaming chat over URLSession
│   └── LiveTimingService.swift WebSocket live timing
└── Models/                   Codable response models
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| iOS | SwiftUI, Swift 5.9, Observation framework |
| Web framework | Next.js 16, React 19, TypeScript 5 |
| Styling | Tailwind CSS 4 |
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| LLM | Google Gemini 2.0 Flash |
| LLM orchestration | LangChain |
| F1 data | FastF1, Ergast API |
| Vector database | ChromaDB + sentence-transformers |
| Web search | Tavily |
| MCP | FastMCP |
