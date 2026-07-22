# F1 AI — Race Engineer Assistant

An AI-powered Formula 1 analyst and race engineer. Ask it about race results,
qualifying lap times, championship standings, pit strategy, FIA regulations,
race predictions, and any historical stat in F1 history — it answers with an
agentic LLM that calls real F1 data tools, including live text-to-SQL over the
entire 1950–present record.

Available as a **web app** (the primary surface), an **MCP server** for Claude
Desktop / Cursor, and a **legacy iOS companion app**.

---

## Architecture

```
F1-AI/
├── backend/    Python FastAPI + LangChain agent on Groq (Llama 3.3 70B)
├── frontend/   Next.js 16 + React 19 (TypeScript) — "Race Control" workspace
├── ios/        SwiftUI iOS companion (legacy — lags the web feature set)
└── render.yaml Render.com deployment config
```

```
Web App (Next.js "Race Control")  ─────────────┐
iOS App (legacy)  ─────────────────────────────┤
MCP clients (Claude Desktop / Cursor)  ────────┤
                                               ▼
                                       FastAPI Backend
                                               │
        ┌──────────────┬─────────────┬─────────┴────────┬───────────────┐
        │              │             │                  │               │
   Groq LLM       f1db SQLite    FastF1 / OpenF1    ChromaDB RAG    Postgres
   (Llama 3.3     (1950–present  (telemetry +       (FIA regs +    + pgvector
    70B + tools)   history)       live timing)       reranker)     (memory/cache)
        │
   Tavily Search
   (live news)
```

The chat backend runs an **agentic tool-use loop**: the model may call one or
more of 15 F1 tools per turn (up to `MAX_AGENT_TURNS`), the backend executes
them, feeds the results back, and repeats until the model returns a final
analysis. A recovery layer parses Llama's occasional malformed inline tool calls
so the loop keeps running.

---

## Features

### Web app (Race Control)

The web app opens on **Race Control**, an operational workspace styled like a pit
wall. Top-level navigation: Workspaces, Race Control, Consumer, Calendar,
Standings, Champions, Predictions, Live.

| Area | Description |
|---|---|
| **Race Engineer chat** | Streaming AI race-engineer persona with tool orchestration and per-user memory |
| **Race Control overview** | Season control board — standings, forecast, and battle context |
| **Teams** | Per-constructor breakdowns with charts and driver detail |
| **Debriefs** | LLM-generated post-race debriefs for completed rounds |
| **Intel** | Per-team strategic intelligence summaries |
| **Predictions** | Probabilistic finishing order with reasoning factors, snapshots, and post-mortems |
| **Rulebook** | Semantic search of FIA regulations (with reranking) |
| **Champions** | Every champion 1950→present, aggregate title leaderboards, per-season race winners |
| **Live timing** | Real-time position/gap/lap tracking + AI commentary over WebSocket |
| **Calendar** | Full season schedule with circuit info and session countdown |
| **Standings** | Live WDC and WCC tables |

### Agentic LLM tools

The chat agent can call any of these 15 tools:

`get_race_predictions` · `query_f1_database` (read-only text-to-SQL over f1db) ·
`get_race_anomalies` · `get_pit_strategy` · `get_weather_conditions` ·
`perform_web_search` (Tavily) · `get_sprint_results` ·
`get_sprint_qualifying_results` · `get_qualifying_results` · `compare_drivers` ·
`get_race_results` · `consult_rulebook` · `get_driver_standings` ·
`get_constructor_standings` · `get_season_schedule`.

### Personalization & memory (optional)

When `DATABASE_URL` is set, the backend persists a per-user profile (favourite
driver/team + free-form prefs) and every chat turn to Postgres. Past
conversation is embedded with the same sentence-transformers model as the
rulebook and recalled semantically via **pgvector** cosine search, so briefings
are tailored to the person on the pit wall. Everything degrades to a no-op
without a database.

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

Create `backend/.env` (see `.env.example`):

```env
GROQ_API_KEY=your_groq_key                        # required — the LLM engine
TAVILY_API_KEY=your_tavily_key                     # optional — web-search tool
OPENWEATHERMAP_API_KEY=your_openweathermap_key     # optional — weather tool
DATABASE_URL=postgresql://...                      # optional — memory + durable store
ALLOWED_ORIGINS=http://localhost:3000              # CORS (comma-separated)
```

- **GROQ_API_KEY** — free, no card required, at [console.groq.com](https://console.groq.com)
- **TAVILY_API_KEY** — [app.tavily.com](https://app.tavily.com)
- **DATABASE_URL** — any Postgres with the `pgvector` extension (e.g. Supabase)

```bash
python main.py
# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

On first run the backend downloads the **f1db** SQLite dataset (1950–present) to
`backend/data/f1db.db` — no live API rate limits, all of F1 history queryable
with `query_f1_database`.

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
# App available at http://localhost:3000  (redirects to /race-control)
```

### iOS (legacy)

```bash
open ios/F1AI.xcodeproj
```

> **Note:** the iOS app predates the Race Control / f1db / Groq overhaul and does
> not yet expose the newer backend features. In **DEBUG builds** it points to
> `http://localhost:8000`; in **Release builds**, to `https://f1-ai.onrender.com`.
> On a physical device, update `APIClient.baseURL` to your Mac's LAN IP —
> iOS cannot reach `localhost`.

---

## API Endpoints

All endpoints are mounted under `/api`.

### Core

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming agentic AI chat with tool orchestration |
| `GET` | `/api/schedule/{year}` | Season calendar with UTC session times |
| `GET` | `/api/standings/drivers/{year}` | WDC standings (f1db, Ergast fallback) |
| `GET` | `/api/standings/constructors/{year}` | WCC standings |
| `GET` | `/api/race/{year}/{round_num}` | Enriched race + qualifying + sprint detail |
| `GET` | `/api/compare/{year}/{driver1}/{driver2}` | Season head-to-head comparison |
| `WS` | `/api/live/{year}/{round_num}` | Real-time timing + commentary WebSocket |
| `GET` | `/api/health` | Liveness probe |

### Predictions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/predictions/{year}/{round_num}` | Race outcome predictions |
| `GET` | `/api/predictions/{year}/{round_num}/snapshot` | Persisted pre-race snapshot |
| `GET` | `/api/predictions/{year}/{round_num}/postmortem` | Prediction vs. actual post-mortem |
| `POST` | `/api/predictions/{year}/{round_num}/compute` | Force (re)computation |

### Champions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/champions` | Every season's driver + constructor champions (1950→) |
| `GET` | `/api/champions/stats` | Aggregate title leaderboards |
| `GET` | `/api/champions/{year}` | Champions + every race winner for a season |

### Race Control

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/race-control/overview/{year}` | Season control board |
| `GET` | `/api/race-control/teams/{year}` | All teams for a season |
| `GET` | `/api/race-control/teams/{team_slug}/{year}` | Single team breakdown |
| `GET` | `/api/race-control/drivers/{year}` | Driver grid |
| `GET` | `/api/race-control/forecast/{year}` | Championship forecast |
| `GET` | `/api/race-control/battle/{year}/{driver1}/{driver2}` | Driver battle |
| `GET` | `/api/race-control/debrief/{year}/{round_num}` | LLM race debrief |
| `POST` | `/api/race-control/rulebook/search` | Regulation semantic search |
| `GET` | `/api/race-control/intel/{team_slug}` | Team intel summary |

### Memory (requires `DATABASE_URL`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/profile/{user_id}` | Fetch user profile |
| `PUT` | `/api/profile/{user_id}` | Upsert favourite driver/team + prefs |
| `GET` | `/api/threads/{user_id}/recall` | Semantic recall of past messages |

---

## One-Time Setup (Optional)

### FIA Regulations (rulebook search)

Place regulation PDFs in `backend/data/raw/{year}/` (name them to contain
`sporting`, `technical`, or `financial`), then run:

```bash
cd backend && source .venv/bin/activate
python app/rag/ingest.py
```

This generates a ChromaDB vector database at `backend/data/chroma/`. Rulebook
search reranks results with a cross-encoder for relevance. Re-run whenever you
add or update PDFs.

### ML Prediction Model

Predictions blend a trained **GradientBoosting** race predictor with a
transparent heuristic (qualifying position, recent form, circuit history, team
strength, grid-to-finish delta) plus a learned per-driver adaptive correction.
The trained model ships in `backend/models/race_predictor.joblib`.

Retrain and evaluate locally:

```bash
cd backend && source .venv/bin/activate
pip install -r requirements-train.txt
python -m app.ml.train       # train on f1db history
python -m app.ml.evaluate    # backtest against the grid-order baseline
python -m app.ml.promote     # promote only if it beats the baseline
```

A GitHub Action (`.github/workflows/retrain.yml`) runs weekly after race
weekends: it pulls the latest f1db release, retrains, and promotes a new model
**only if it beats the grid-order baseline** — committing it back and triggering
a Render redeploy.

The prediction blend is tunable via `ML_PREDICTION_BLEND_WEIGHT` (0 = pure
heuristic, 1 = pure model; default 0.65) and `PREDICTION_ADAPTIVE_WEIGHT`.

---

## MCP Server (Claude Desktop / Cursor)

Exposes a subset of F1 tools so Claude Desktop or Cursor can call them directly.

Add to your Claude Desktop config
(`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "f1-race-engineer": {
      "command": "/absolute/path/to/backend/.venv/bin/python",
      "args": ["/absolute/path/to/backend/mcp_server.py"],
      "env": {
        "GROQ_API_KEY": "your_key",
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
├── main.py                   FastAPI entry point + CORS + background prefetch/self-improvement
├── mcp_server.py             MCP server for Claude Desktop / Cursor
├── requirements.txt          runtime deps
├── requirements-train.txt    ML training deps
├── app/
│   ├── config.py             all env-configurable constants (LLM, timeouts, weights)
│   ├── api/
│   │   ├── routes.py         router aggregation + race detail + live WebSocket + compare
│   │   ├── routers/          chat, season, predictions, champions, race_control, memory
│   │   ├── llm.py            Groq chat model factory
│   │   ├── tools.py          15 LangChain tools (data, predictions, rulebook, SQL, search)
│   │   ├── tool_recovery.py  recovers Llama malformed inline tool calls
│   │   ├── prompts.py        race-engineer system persona
│   │   ├── schemas/          request/response models
│   │   └── circuits.py       circuit GPS coordinates
│   ├── data/
│   │   ├── f1db_source.py     downloads/pins the f1db SQLite dataset
│   │   ├── f1db_query.py      read-only SQL access for query_f1_database
│   │   ├── f1db_results.py    race/qualifying result helpers
│   │   ├── f1db_standings.py  standings from f1db
│   │   ├── champions.py       champions + race winners
│   │   ├── predictions.py     heuristic scoring engine
│   │   ├── strategy.py        pit strategy analysis
│   │   ├── weather.py         circuit weather
│   │   ├── memory.py          Postgres + pgvector conversation memory/personalization
│   │   └── store.py           durable Postgres document store (JSON fallback)
│   ├── services/             predictions, prediction_cache, race_control(+battles/
│   │                         championship/debriefs/standings), rulebook, anomaly,
│   │                         self_improvement
│   ├── ml/                   train, evaluate, promote, features, explain
│   ├── rag/                  ingest (PDF → ChromaDB), rerank (cross-encoder)
│   └── evals/                dataset, judge, run — LLM answer evals
├── data/
│   ├── f1db.db               f1db SQLite dataset (downloaded, gitignored)
│   ├── raw/{year}/           FIA regulation PDFs
│   └── chroma/               ChromaDB vector DB (generated)
├── models/                   trained race predictor (shipped)
└── f1_cache/                 FastF1 disk cache

frontend/app/
├── page.tsx                  → redirects to /race-control
├── race-control/             engineer, teams, debriefs, intel, live, predictions,
│                             rulebook, champions — the operational workspace
├── calendar/  standings/  champions/  predictions/  live/  consumer/
└── components/               NavShell, chat, live tower, prediction/telemetry cards, …

ios/F1AI/                     legacy SwiftUI companion (Calendar, Standings, Chat,
                              Compare, Live, Predictions, Settings)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Next.js 16, React 19, TypeScript 5 |
| Styling | Tailwind CSS 4 |
| Web UI libs | Recharts, Framer Motion, SWR, Vercel AI SDK, lucide-react |
| Backend | FastAPI, Uvicorn, Python 3.10+, structlog |
| LLM | Groq — Llama 3.3 70B Versatile |
| LLM orchestration | LangChain (agentic tool-use loop) |
| F1 data | f1db (SQLite, 1950–present), FastF1, OpenF1 (live), Ergast (fallback) |
| Vector database | ChromaDB + sentence-transformers + cross-encoder reranker |
| Memory / storage | Postgres + pgvector (optional; JSON fallback) |
| ML | scikit-learn GradientBoosting + heuristic blend |
| Web search | Tavily |
| MCP | FastMCP |
| iOS (legacy) | SwiftUI, Swift 5.9, Observation framework |
</content>
