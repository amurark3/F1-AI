# F1 AI — Race Engineer Assistant

An AI-powered Formula 1 analyst and race engineer. Ask it about race results,
qualifying lap times, championship standings, pit strategy, power unit usage,
FIA regulations, race predictions, and any historical stat in F1 history — it
answers with an agentic LLM that calls real F1 data tools, including live
text-to-SQL over the entire 1950–present record.

Available as a **web app** (the primary surface), an **MCP server** for Claude
Desktop / Cursor, and a **legacy iOS companion app**.

---

## Architecture

```
F1-AI/
├── backend/    Python FastAPI + LangChain agent on Groq (GPT-OSS 120B)
├── frontend/   Next.js 16 + React 19 (TypeScript) — "Race Control" workspace
├── ios/        SwiftUI iOS companion (legacy — lags the web feature set)
└── render.yaml Reference copy of the Render config (NOT applied — the Render
                dashboard is the source of truth; see DEPLOYMENT.md §4)
```

```
Web App (Next.js "Race Control", Vercel)  ─────┐
iOS App (legacy)  ─────────────────────────────┤
MCP clients (Claude Desktop / Cursor)  ────────┤
                                               ▼
                                   FastAPI Backend (Render)
                                               │
     ┌──────────────┬──────────────┬───────────┴──────┬────────────────┐
     │              │              │                  │                │
  Groq LLM      f1db SQLite    FastF1 / OpenF1    Supabase Postgres  Tavily /
  (GPT-OSS      (1950–present  (sessions,         + pgvector         OpenWeatherMap
   120B + tools) history)       telemetry, live)   (store, memory,    (news, forecast)
                                                    rulebook vectors)
```

The chat backend runs an **agentic tool-use loop**: the model may call one or
more of 16 F1 tools per turn (up to `MAX_AGENT_TURNS`), the backend executes
them, feeds the results back, and repeats until the model returns a final
analysis. A recovery layer parses the model's occasional malformed inline tool
calls so the loop keeps running. Before an answer is sent, a claim checker
compares its driver↔team statements against the tool results and asks for one
repair if they disagree.

---

## Features

### Web app (Race Control)

The web app opens on the **Command Center**, an operational workspace styled
like a pit wall. The sidebar groups the screens into Operations, Decision Tools
and Reference. Older top-level routes (`/calendar`, `/standings`, `/champions`,
`/predictions`, `/consumer`, `/live`) redirect into `/race-control`.

| Screen | Route | Description |
|---|---|---|
| **Command Center** | `/race-control` | Next-race strategy baseline, projected podium, weather risk, championship picture, call sheet, stint plan, competitor matrix. The live timing tower appears here only while a session is live |
| **AI Engineer** | `/race-control/engineer` | Streaming race-engineer chat with tool status, saved chats, voice dictation and spoken replies, and per-user memory |
| **Grand Prix Hub** | `/race-control/grand-prix` | One race weekend at a time: Weekend, Sessions, Grid (with grid penalties), Stints, and Predictions (order, podium, risk, model factors, post-race review). Round, tab and view are kept in the URL |
| **Telemetry Lab** | `/race-control/telemetry` | Track speed map, head-to-head lap traces, and tyre degradation (raw slope beside the fuel-corrected one), from OpenF1 |
| **Standings** | `/race-control/teams` | WDC and WCC tables with charts |
| **Teams & Drivers** | `/race-control/constructors/[team]`, `/race-control/drivers/[driver]` | Current-season profiles: line-up, wins, per-round results, cumulative points, and the power units of each car |
| **Power Units** | `/race-control/power-units` | Element usage per car against the allowance, and the grid penalties it cost — every figure taken from an FIA document |
| **Champions** | `/race-control/champions` | Every champion 1950→present, title leaderboards, and every race winner per season |
| **Race Debriefs** | `/race-control/debriefs` | Post-race debrief built from the classification: podium, biggest movers, constructor impact |
| **Rules Search** | `/race-control/rulebook` | Semantic search of FIA regulations with reranking and page citations |

While the backend cold-starts on Render, the app is blocked behind a warm-up
screen that shows each startup stage, and rechecks when a stale tab comes back.

### Agentic LLM tools

The chat agent can call any of these 16 tools:

`get_race_predictions` · `query_f1_database` (read-only text-to-SQL over f1db) ·
`get_race_anomalies` · `get_pit_strategy` · `get_weather_conditions` ·
`get_power_unit_usage` · `perform_web_search` (Tavily) · `get_sprint_results` ·
`get_sprint_qualifying_results` · `get_qualifying_results` · `compare_drivers` ·
`get_race_results` · `consult_rulebook` · `get_driver_standings` ·
`get_constructor_standings` · `get_season_schedule`.

Every `query_f1_database` result comes with computed tallies (counts, points
sums, same-row matches), so the model doesn't have to add up rows itself.

### Personalization & memory (optional)

When `DATABASE_URL` is set, the backend persists a per-user profile (favourite
driver/team + free-form prefs) and every chat turn to Postgres, keyed by an
anonymous id stored in the browser. Past conversation is embedded with the same
sentence-transformers model as the rulebook and recalled semantically via
**pgvector** cosine search, so briefings are tailored to the person on the pit
wall. Semantic recall needs `ENABLE_LOCAL_MODELS=true` (see below); without it,
messages are still stored but not recalled. Everything degrades to a no-op
without a database.

---

## Prerequisites

| Tool | Version |
|---|---|
| Node.js | 20+ |
| Python | 3.13 |
| Xcode | 15+ (iOS only) |

---

## Running Locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-ingest.txt   # runtime + rulebook ingest deps
pip install -r requirements-dev.txt      # only to run tests and lint
cp .env.example .env                     # then fill in the keys
```

`backend/.env` (see `.env.example` for the full notes on each):

```env
GROQ_API_KEY=your_groq_key                         # required — authenticates the LLM engine
TAVILY_API_KEY=your_tavily_key                     # optional — web-search tool
OPENWEATHERMAP_API_KEY=your_openweathermap_key     # optional — weather tool
DATABASE_URL=postgresql://...                      # optional — memory + durable store
ENABLE_LOCAL_MODELS=true                           # optional — rulebook search + memory recall
SENTRY_DSN=                                        # optional — backend error tracking
ALLOWED_ORIGINS=http://localhost:3000              # CORS (comma-separated)
```

- **GROQ_API_KEY** — free, no card required, at [console.groq.com](https://console.groq.com)
- **TAVILY_API_KEY** — [app.tavily.com](https://app.tavily.com)
- **DATABASE_URL** — any Postgres with the `pgvector` extension (e.g. Supabase).
  On Supabase use the **session pooler** host: the direct `db.<ref>` host is
  IPv6-only and unreachable from Render and GitHub Actions
- **ENABLE_LOCAL_MODELS** — loads the torch embedder and reranker into the web
  process. Turn it on locally; it is off on Render's 512 MB instance, where one
  rulebook query once OOM-killed the server. With it off, rules search reports
  that it is disabled and chat skips semantic recall

> **Which model?** Not an environment variable and not a secret — the Groq model
> is a code constant, `GROQ_MODEL_NAME` in `backend/app/config.py`. Changing it
> is a code change and a deploy, not a dashboard edit.

```bash
python main.py
# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

On first run the backend downloads the **f1db** SQLite dataset (1950–present) to
`backend/data/f1db.db` and keeps it on the latest release — no live API rate
limits, all of F1 history queryable with `query_f1_database`. Without
`DATABASE_URL`, the store falls back to local JSON files in `backend/data/`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
# App available at http://localhost:3000  (redirects to /race-control)
```

`npm run lint` must be clean before committing; CI runs it on every PR.

### Tests

```bash
cd backend && .venv/bin/python -m pytest tests -q --cov   # coverage must stay at 100%
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
| `WS` | `/api/live/{year}/{round_num}` | Real-time timing WebSocket |
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/ready` | Warm-up progress, store health, and the f1db release on disk |
| `GET` | `/api/health/deep` | Database reachability (503 when degraded) |

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
| `GET` | `/api/race-control/overview/{year}/shell` | Schedule, standings and session state (no telemetry) |
| `GET` | `/api/race-control/overview/{year}/weather` | Live forecast for the circuit and the risk register it grades |
| `GET` | `/api/race-control/overview/{year}/predictions` | Projected podium from the stored model snapshot |
| `GET` | `/api/race-control/overview/{year}/strategy` | Baseline strategy context and workstreams |
| `GET` | `/api/race-control/teams/{year}` | All teams for a season |
| `GET` | `/api/race-control/teams/{team_slug}/{year}` | Single team breakdown |
| `GET` | `/api/race-control/drivers/{year}` | Driver grid |
| `GET` | `/api/race-control/grid/{year}/{round_num}` | Starting grid and the grid penalties applied to it |
| `GET` | `/api/race-control/sessions/{year}/{round_num}` | Every session the weekend ran |
| `GET` | `/api/race-control/stints/{year}/{round_num}` | Race tyre stints and pit stops |
| `GET` | `/api/race-control/forecast/{year}` | Championship forecast |
| `GET` | `/api/race-control/battle/{year}/{driver1}/{driver2}` | Driver battle |
| `GET` | `/api/race-control/debrief/{year}/{round_num}` | Post-race debrief |
| `POST` | `/api/race-control/rulebook/search` | Regulation semantic search |
| `GET` | `/api/race-control/intel/{team_slug}` | Team championship picture |
| `GET` | `/api/race-control/glance/{year}/{round_num}` | Last edition's winner and pole, this round's PU penalty decisions |
| `GET` | `/api/race-control/power-units/{year}` | Every car's element allowance, usage, and the grid penalties it cost |

### Telemetry Lab

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/analysis/{year}/{round_num}/sessions` | The round's sessions, from the calendar |
| `GET` | `/api/analysis/{year}/{round_num}/laps` | Every driver's timed laps in a session, quickest first |
| `GET` | `/api/analysis/{year}/{round_num}/track-map` | One lap coloured by speed, with braking and high-speed zones |
| `GET` | `/api/analysis/{year}/{round_num}/compare` | Two laps side by side: traces, delta, and where each driver gains |
| `GET` | `/api/analysis/{year}/{round_num}/tyre-degradation` | Lap time against tyre age per stint and compound, with excluded laps and why |

### Teams & Drivers

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/profiles/{year}/directory` | Every driver and team of the season, by f1db id (with team aliases) |
| `GET` | `/api/profiles/{year}/teams/{team_id}` | Line-up, wins, results per round, cumulative points, power units |
| `GET` | `/api/profiles/{year}/drivers/{driver_id}` | Every round's result, wins, stats, and the PU of each car raced |

### Memory (requires `DATABASE_URL`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/profile/{user_id}` | Fetch user profile |
| `PUT` | `/api/profile/{user_id}` | Upsert favourite driver/team + prefs |
| `GET` | `/api/threads/{user_id}/recall` | Semantic recall of past messages |

---

## One-Time Setup (Optional)

### FIA Regulations (rulebook search)

Regulation vectors live in Postgres (pgvector), so this needs `DATABASE_URL`.
Place regulation PDFs in `backend/data/raw/{year}/` (name them to contain
`sporting`, `technical`, or `financial`), then run:

```bash
cd backend && source .venv/bin/activate
python -m app.rag.ingest            # skips if already populated
python -m app.rag.ingest --force    # wipe and re-embed the whole corpus
```

Rulebook search reranks results with a cross-encoder for relevance. On `main`,
the `ingest-rulebook.yml` Action re-embeds automatically whenever a PDF under
`backend/data/raw/` changes.

### ML Prediction Model

Predictions blend a trained **Ridge regression** (over standardized features)
with a transparent heuristic (qualifying position, recent form, circuit history,
team strength, grid-to-finish delta) plus a learned per-driver adaptive
correction. Because the model is linear, each prediction carries an exact
per-feature attribution. The trained model ships in
`backend/models/race_predictor.joblib`.

Retrain and evaluate locally:

```bash
cd backend && source .venv/bin/activate
pip install -r requirements-train.txt
python -m app.ml.train       # train on f1db history
python -m app.ml.evaluate    # backtest against the grid-order baseline
python -m app.ml.promote     # promote only if it beats the baseline
```

A GitHub Action (`.github/workflows/retrain.yml`) runs weekly after race
weekends: it retrains on the current f1db release and promotes a new model
**only if it beats the grid-order baseline**. A promoted model is opened as a
PR and auto-merged, and the merge redeploys it.

The prediction blend is tunable via `ML_PREDICTION_BLEND_WEIGHT` (0 = pure
heuristic, 1 = pure model; default 0.65) and `PREDICTION_ADAPTIVE_WEIGHT`
(default 0.22).

---

## Scheduled Jobs (GitHub Actions)

| Workflow | Schedule | What it does |
|---|---|---|
| `keep-warm.yml` | every 13 min | Pings the Render backend so it doesn't spin down |
| `ingest-power-units.yml` | hourly on race weekends, daily otherwise | Reads FIA documents into the Power Unit Tracker (needs the `DATABASE_URL` secret) |
| `retrain.yml` | Tuesdays | Retrains the race predictor; promotes only a better model |
| `ingest-rulebook.yml` | on PDF changes | Re-embeds the FIA regulations into pgvector |
| `dependency-audit.yml` | Mondays + manifest changes | pip-audit and npm audit-ci |
| `codeql.yml` | Mondays + PRs to `main` | CodeQL security scan |
| `pr-auto-review.yml` | PRs | Frontend lint + build, backend Ruff + module-size check, tests at 100% coverage |

---

## MCP Server (Claude Desktop / Cursor)

Exposes 10 F1 tools (schedule, race/qualifying/sprint results, driver
comparison, standings, rulebook, web search) plus a health check, so Claude
Desktop or Cursor can call them directly.

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
├── main.py                   FastAPI entry point + CORS + warm-up + background prefetch
├── mcp_server.py             MCP server for Claude Desktop / Cursor
├── requirements*.txt         runtime, ingest, dev (tests/lint), train
├── app/
│   ├── config.py             all env-configurable constants (LLM, timeouts, weights)
│   ├── error_tracking.py     Sentry init, off without SENTRY_DSN (no auto integrations —
│   │                         they would import torch)
│   ├── api/
│   │   ├── routes.py         router aggregation
│   │   ├── routers/          chat, season, predictions, champions, race_control,
│   │   │                     analysis, power_units, profiles, memory, readiness
│   │   ├── tools/            16 LangChain tools + SQL result tallies
│   │   ├── live/             live-timing WebSocket + connection manager
│   │   ├── race_detail.py    race + qualifying + sprint detail
│   │   ├── compare.py        season head-to-head
│   │   ├── llm.py            Groq chat model factory
│   │   ├── tool_recovery.py  recovers malformed inline tool calls
│   │   ├── claim_check.py    checks driver↔team claims against tool results
│   │   ├── answer_repair.py  one repair pass for flagged answers
│   │   ├── single_flight.py  one compute per key, shared by concurrent callers
│   │   └── prompts.py        race-engineer system persona
│   ├── data/
│   │   ├── f1db_*.py         f1db dataset: download, release tracking, SQL, results,
│   │   │                     standings, grid, pit stops, sessions
│   │   ├── identity.py       canonical driver/team names and ids per season
│   │   ├── predictions/      heuristic scoring, form, history, accuracy, review
│   │   ├── strategy/         pit strategy analysis
│   │   ├── openf1/           OpenF1 client, sessions, laps, race control, telemetry
│   │   ├── power_units/      FIA document fetch, parsing, decisions, allowances
│   │   ├── profiles/         team and driver profile data
│   │   ├── champions.py      champions + race winners
│   │   ├── weather.py        circuit weather
│   │   ├── memory.py         Postgres + pgvector conversation memory/personalization
│   │   └── store.py          durable Postgres document store (JSON fallback)
│   ├── services/             predictions, prediction_cache, race_control*, analysis/
│   │                         (Telemetry Lab), power_units/, profiles, race_grid,
│   │                         weekend_sessions, rulebook, anomaly, self_improvement,
│   │                         readiness, live_timing
│   ├── ml/                   train, evaluate, promote, features, explain
│   ├── rag/                  ingest (PDF → pgvector), pgvector_store, rerank (cross-encoder)
│   └── evals/                dataset, judge, run — LLM answer evals
├── scripts/                  eval_answers, backfill_predictions, ingest_power_units,
│                             power_unit_allowances, migrations and admin tools
├── data/
│   ├── f1db.db               f1db SQLite dataset (downloaded, gitignored)
│   └── raw/{year}/           FIA regulation PDFs
├── models/                   trained race predictor (shipped)
└── f1_cache/                 FastF1 disk cache

frontend/app/
├── page.tsx                  → redirects to /race-control
├── race-control/             Command Center, engineer, grand-prix, telemetry, teams
│                             (standings), constructors + drivers + profiles (Teams &
│                             Drivers), power-units, champions, debriefs, rulebook
├── calendar/  standings/  champions/  predictions/  consumer/   → redirects
├── components/               NavShell, chat, LiveTimingTower, ServerWarmingGate, …
├── hooks/                    useChat, useLocalChats, useLiveTiming, useServerStatus, useVoice
└── lib/  utils/              server-side prefetch, server status store, fetcher, error tracking

ios/F1AI/                     legacy SwiftUI companion (Calendar, Standings, Chat,
                              Compare, Live, Predictions, Settings)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Next.js 16, React 19, TypeScript 5 |
| Styling | Tailwind CSS 4 |
| Web UI libs | Recharts, Framer Motion, SWR, react-markdown, lucide-react |
| Backend | FastAPI, Uvicorn, Python 3.13, structlog |
| LLM | Groq — GPT-OSS 120B |
| LLM orchestration | LangChain (agentic tool-use loop) |
| F1 data | f1db (SQLite, 1950–present), FastF1, OpenF1 (telemetry + live), Ergast/Jolpica (fallback), FIA documents (power units) |
| Vector search | Postgres pgvector + sentence-transformers + cross-encoder reranker |
| Storage | Supabase Postgres (optional; JSON fallback) |
| ML | scikit-learn Ridge regression + heuristic blend |
| Web search | Tavily |
| MCP | FastMCP |
| Hosting | Render (backend), Vercel (frontend), Supabase (database) |
| Observability | Sentry (web + backend), Vercel Analytics, Vercel Speed Insights |
| iOS (legacy) | SwiftUI, Swift 5.9, Observation framework |
