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
├── backend/    Python FastAPI + LangChain agent on AMD Token Lab, Gemini fallback
├── frontend/   Next.js 16 + React 19 (TypeScript) — "Race Control" workspace
├── ios/        SwiftUI iOS companion (legacy — lags the web feature set)
├── deploy/oracle/  The always-on backend's VM: Compose stack, Caddy, deploy,
│                   backup and migration scripts, systemd timers
└── render.yaml Retired Render config, kept for rollback until the old host is
                decommissioned (see DEPLOYMENT.md §12)
```

```
Web App (Next.js "Race Control", Vercel)  ─────┐
iOS App (legacy)  ─────────────────────────────┤
MCP clients (Claude Desktop / Cursor)  ────────┤
                                               ▼
                                 FastAPI Backend (Oracle VM)
                                               │
     ┌──────────────┬──────────────┬───────────┴──────┬────────────────┬───────────────┐
     │              │              │                  │                │               │
  LLM engines   f1db SQLite    FastF1 / OpenF1    Postgres (on VM)   Open-Meteo /   Tavily
  (Token Lab    (1950–present  (sessions,         + pgvector         OpenWeatherMap (web
   → Gemini)     history)       telemetry, live)   (store, memory,    (weather),     search)
                                                    rulebook vectors)  MultiViewer
                                                                       (circuit maps)
```

In production the backend and its Postgres run on one always-on Oracle Cloud
Always Free VM, behind Caddy at a DuckDNS name; the web app stays on Vercel.
[DEPLOYMENT.md](DEPLOYMENT.md) describes the setup, and
[docs/deploy/ORACLE.md](docs/deploy/ORACLE.md) holds the procedures.

The chat backend runs an **agentic tool-use loop**: the model may call one or
more of 16 F1 tools per turn (up to `MAX_AGENT_TURNS`), the backend executes
them, feeds the results back, and repeats until the model returns a final
analysis. Every tool is offered on every tool turn. If the engine fails with
its own error (out of points or credit, rate-limited, down), the question
restarts on the next engine. Before an answer is sent, a claim checker
compares its driver↔team statements against the tool results and asks for one
repair if they disagree.

---

## Features

### Web app (Race Control)

The web app opens on the **Command Center**, an operational workspace styled
like a pit wall. The sidebar groups the screens into Operations, Decision Tools
and Reference. Older top-level routes (`/calendar`, `/standings`, `/champions`,
`/predictions`, `/consumer`, `/live`) redirect into `/race-control`.

| Screen              | Route                                                                 | Description                                                                                                                                                                                                                                                                                  |
| ------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Command Center**  | `/race-control`                                                       | The current race weekend at a glance: animated circuit map, countdown to the next session, the weather for every session, title stakes, projected podium, circuit history, and the baseline strategy with its risk register. The live timing tower appears here only while a session is live |
| **AI Engineer**     | `/race-control/engineer`                                              | Streaming race-engineer chat with tool status, saved chats, voice dictation and spoken replies, and per-user memory                                                                                                                                                                          |
| **Grand Prix Hub**  | `/race-control/grand-prix`                                            | One race weekend at a time: Weekend, Sessions, Grid (with grid penalties), Stints, and Predictions (order, podium, risk, model factors, post-race review). Round, tab and view are kept in the URL                                                                                           |
| **Telemetry Lab**   | `/race-control/telemetry`                                             | Track speed map, head-to-head lap traces, and tyre degradation (raw slope beside the fuel-corrected one), from OpenF1                                                                                                                                                                        |
| **Standings**       | `/race-control/teams`                                                 | WDC and WCC tables with charts                                                                                                                                                                                                                                                               |
| **Teams & Drivers** | `/race-control/constructors/[team]`, `/race-control/drivers/[driver]` | Current-season profiles: line-up, wins, per-round results, cumulative points, and the power units of each car                                                                                                                                                                                |
| **Power Units**     | `/race-control/power-units`                                           | Element usage per car against the allowance, and the grid penalties it cost — every figure taken from an FIA document                                                                                                                                                                        |
| **Champions**       | `/race-control/champions`                                             | Every champion 1950→present, title leaderboards, and every race winner per season                                                                                                                                                                                                            |
| **Race Debriefs**   | `/race-control/debriefs`                                              | Post-race debrief built from the classification: podium, biggest movers, constructor impact                                                                                                                                                                                                  |
| **Rules Search**    | `/race-control/rulebook`                                              | Semantic search of FIA regulations with reranking and page citations                                                                                                                                                                                                                         |

While the backend restarts (after a deploy) or cannot be reached, a small
notice at the bottom of every page says so and lights up each startup stage.
It never blocks the page.

#### Command Center data

Each panel says where its numbers come from, and shows a blank rather than a
guess when its source is down.

- **Weather** comes from Open-Meteo's hourly forecast (no API key; up to 16
  days ahead). Each session reads the hours it runs through: the worst hour for
  rain and wind, the average for temperature. A session too far out says when
  its forecast opens. The race session's forecast drives the rain figure and
  the risk register; OpenWeatherMap's current conditions are only a fallback.
  Track temperature is an estimate from air temperature and cloud.
- **Circuit map** is MultiViewer's outline and corner numbers. Layout facts and
  history (recent winners, the grid slot they won from, pole-to-win rate) come
  from f1db.
- **Title stakes** compare the f1db standings with the points still to be won.
  Those are counted from the last round the standings include, not from the
  calendar: f1db publishes a day or two after each race, and a race it has not
  published yet still counts.
- **Animations** are CSS and SVG, and stop for readers who prefer reduced
  motion.

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
wall. Semantic recall needs `ENABLE_LOCAL_MODELS=true`, which production sets
(see below); without it, messages are still stored but not recalled. Everything
degrades to a no-op without a database.

---

## Prerequisites

| Tool    | Version        |
| ------- | -------------- |
| Node.js | 20+            |
| Python  | 3.13           |
| Xcode   | 15+ (iOS only) |

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
TOKENLAB_API_KEY=your_tokenlab_key                 # primary chat engine (set at least one engine key)
GOOGLE_API_KEY=your_gemini_key                     # fallback chat engine — Gemini free tier
TAVILY_API_KEY=your_tavily_key                     # optional — web-search tool
OPENWEATHERMAP_API_KEY=your_openweathermap_key     # optional — weather tool + current-conditions fallback
DATABASE_URL=postgresql://...                      # optional — memory + durable store
ENABLE_LOCAL_MODELS=true                           # optional — rulebook search + memory recall
SENTRY_DSN=                                        # optional — backend error tracking
ALLOWED_ORIGINS=http://localhost:3000              # CORS (comma-separated)
```

- **TOKENLAB_API_KEY** — AMD Token Lab, through the AMD AI Developer Program, at
  [notebooks.amd.com/tokenlab](https://notebooks.amd.com/tokenlab). It is a beta
  with a points budget and a 30-day access window you extend from that page
- **GOOGLE_API_KEY** — Gemini free tier at [aistudio.google.com](https://aistudio.google.com).
  Create it in a project with no billing linked, or it is charged instead of free
- **TAVILY_API_KEY** — [app.tavily.com](https://app.tavily.com)
- **DATABASE_URL** — any Postgres with the `pgvector` extension, such as a local
  `pgvector/pgvector:pg17` container. Production uses the VM's own
  (DEPLOYMENT.md §3)
- **ENABLE_LOCAL_MODELS** — loads the torch embedder and reranker into the web
  process (about 0.65 GB at peak). Production turns it on; the code's default is
  off. With it off, rules search reports that it is unavailable and chat skips
  semantic recall

> **Which model?** Not an environment variable and not a secret — the engines,
> their models and their order are code constants, `LLM_PROVIDERS` in
> `backend/app/config.py`. Changing one is a code change and a deploy, not a
> dashboard edit.

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

> **Note:** the iOS app predates the Race Control / f1db / AI overhaul and does
> not yet expose the newer backend features. In **DEBUG builds** it points to
> `http://localhost:8000`; in **Release builds**, to the retired Render host
> `https://f1-ai.onrender.com`. The legacy app is no longer updated, so Release
> builds don't reach the current backend.
> On a physical device, update `APIClient.baseURL` to your Mac's LAN IP —
> iOS cannot reach `localhost`.

---

## API Endpoints

All endpoints are mounted under `/api`.

### Core

| Method | Path                                      | Description                                                  |
| ------ | ----------------------------------------- | ------------------------------------------------------------ |
| `POST` | `/api/chat`                               | Streaming agentic AI chat with tool orchestration            |
| `GET`  | `/api/schedule/{year}`                    | Season calendar with UTC session times                       |
| `GET`  | `/api/standings/drivers/{year}`           | WDC standings (f1db, Ergast fallback)                        |
| `GET`  | `/api/standings/constructors/{year}`      | WCC standings                                                |
| `GET`  | `/api/race/{year}/{round_num}`            | Enriched race + qualifying + sprint detail                   |
| `GET`  | `/api/compare/{year}/{driver1}/{driver2}` | Season head-to-head comparison                               |
| `WS`   | `/api/live/{year}/{round_num}`            | Real-time timing WebSocket                                   |
| `GET`  | `/api/health`                             | Liveness probe                                               |
| `GET`  | `/api/ready`                              | Warm-up progress, store health, and the f1db release on disk |
| `GET`  | `/api/health/deep`                        | Database reachability (503 when degraded)                    |

### Predictions

| Method | Path                                             | Description                       |
| ------ | ------------------------------------------------ | --------------------------------- |
| `GET`  | `/api/predictions/{year}/{round_num}`            | Race outcome predictions          |
| `GET`  | `/api/predictions/{year}/{round_num}/snapshot`   | Persisted pre-race snapshot       |
| `GET`  | `/api/predictions/{year}/{round_num}/postmortem` | Prediction vs. actual post-mortem |
| `POST` | `/api/predictions/{year}/{round_num}/compute`    | Force (re)computation             |

### Champions

| Method | Path                    | Description                                           |
| ------ | ----------------------- | ----------------------------------------------------- |
| `GET`  | `/api/champions`        | Every season's driver + constructor champions (1950→) |
| `GET`  | `/api/champions/stats`  | Aggregate title leaderboards                          |
| `GET`  | `/api/champions/{year}` | Champions + every race winner for a season            |

### Race Control

| Method | Path                                                  | Description                                                                                      |
| ------ | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `GET`  | `/api/race-control/overview/{year}`                   | Every Command Center segment in one response (the web app fetches the segments below instead)    |
| `GET`  | `/api/race-control/overview/{year}/shell`             | Schedule, standings, session state and championship stakes (no telemetry)                        |
| `GET`  | `/api/race-control/overview/{year}/weather`           | Forecast for every session of the weekend, the race-day summary, and the risk register it grades |
| `GET`  | `/api/race-control/overview/{year}/circuit`           | Circuit map (MultiViewer), layout facts, lap record and history at the circuit                   |
| `GET`  | `/api/race-control/overview/{year}/predictions`       | Projected podium from the stored model snapshot                                                  |
| `GET`  | `/api/race-control/overview/{year}/strategy`          | Baseline strategy context and workstreams                                                        |
| `GET`  | `/api/race-control/teams/{year}`                      | All teams for a season                                                                           |
| `GET`  | `/api/race-control/teams/{team_slug}/{year}`          | Single team breakdown                                                                            |
| `GET`  | `/api/race-control/drivers/{year}`                    | Driver grid                                                                                      |
| `GET`  | `/api/race-control/grid/{year}/{round_num}`           | Starting grid and the grid penalties applied to it                                               |
| `GET`  | `/api/race-control/sessions/{year}/{round_num}`       | Every session the weekend ran                                                                    |
| `GET`  | `/api/race-control/stints/{year}/{round_num}`         | Race tyre stints and pit stops                                                                   |
| `GET`  | `/api/race-control/forecast/{year}`                   | Championship forecast                                                                            |
| `GET`  | `/api/race-control/battle/{year}/{driver1}/{driver2}` | Driver battle                                                                                    |
| `GET`  | `/api/race-control/debrief/{year}/{round_num}`        | Post-race debrief                                                                                |
| `POST` | `/api/race-control/rulebook/search`                   | Regulation semantic search                                                                       |
| `GET`  | `/api/race-control/intel/{team_slug}`                 | Team championship picture                                                                        |
| `GET`  | `/api/race-control/glance/{year}/{round_num}`         | Last edition's winner and pole, this round's PU penalty decisions                                |
| `GET`  | `/api/race-control/power-units/{year}`                | Every car's element allowance, usage, and the grid penalties it cost                             |

### Telemetry Lab

| Method | Path                                                | Description                                                                  |
| ------ | --------------------------------------------------- | ---------------------------------------------------------------------------- |
| `GET`  | `/api/analysis/{year}/{round_num}/sessions`         | The round's sessions, from the calendar                                      |
| `GET`  | `/api/analysis/{year}/{round_num}/laps`             | Every driver's timed laps in a session, quickest first                       |
| `GET`  | `/api/analysis/{year}/{round_num}/track-map`        | One lap coloured by speed, with braking and high-speed zones                 |
| `GET`  | `/api/analysis/{year}/{round_num}/compare`          | Two laps side by side: traces, delta, and where each driver gains            |
| `GET`  | `/api/analysis/{year}/{round_num}/tyre-degradation` | Lap time against tyre age per stint and compound, with excluded laps and why |

### Teams & Drivers

| Method | Path                                       | Description                                                         |
| ------ | ------------------------------------------ | ------------------------------------------------------------------- |
| `GET`  | `/api/profiles/{year}/directory`           | Every driver and team of the season, by f1db id (with team aliases) |
| `GET`  | `/api/profiles/{year}/teams/{team_id}`     | Line-up, wins, results per round, cumulative points, power units    |
| `GET`  | `/api/profiles/{year}/drivers/{driver_id}` | Every round's result, wins, stats, and the PU of each car raced     |

### Memory (requires `DATABASE_URL`)

| Method | Path                            | Description                          |
| ------ | ------------------------------- | ------------------------------------ |
| `GET`  | `/api/profile/{user_id}`        | Fetch user profile                   |
| `PUT`  | `/api/profile/{user_id}`        | Upsert favourite driver/team + prefs |
| `GET`  | `/api/threads/{user_id}/recall` | Semantic recall of past messages     |

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
the backend deploy (`deploy-oracle.yml`) re-embeds the corpus automatically
whenever a push changes a PDF under `backend/data/raw/`.

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
PR and auto-merged; the job then dispatches the backend deploy that ships it.

The prediction blend is tunable via `ML_PREDICTION_BLEND_WEIGHT` (0 = pure
heuristic, 1 = pure model; default 0.65) and `PREDICTION_ADAPTIVE_WEIGHT`
(default 0.22).

---

## Scheduled Jobs

On the backend's VM (systemd timers, all times UTC; `deploy/oracle/systemd/`):

| Timer                  | Schedule                          | What it does                                                         |
| ---------------------- | --------------------------------- | -------------------------------------------------------------------- |
| `f1ai-pu-ingest`       | hourly at :17, Thursday to Monday | Reads new FIA documents into the Power Unit Tracker                  |
| `f1ai-pu-ingest-daily` | 05:47                             | The same, re-reading every event page of the season                  |
| `f1ai-backup`          | 03:30                             | `pg_dump` of the database, uploaded to OCI Object Storage (14 days)  |
| `f1ai-restore-check`   | Wednesdays 04:30                  | Restores the newest dump into a scratch database and compares counts |
| `f1ai-duckdns`         | every 5 min                       | Keeps the API's DuckDNS name on the VM's IP                          |

GitHub Actions:

| Workflow                                                         | When                                    | What it does                                                                                           |
| ---------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `deploy-oracle.yml`                                              | pushes to `main` that touch the backend | Builds the arm64 image, pushes it to GHCR, deploys it to the VM; re-embeds the rulebook on PDF changes |
| `retrain.yml`                                                    | Tuesdays                                | Retrains the race predictor; promotes only a better model, then deploys it                             |
| `dependency-audit.yml`                                           | Mondays + manifest changes              | pip-audit and npm audit-ci                                                                             |
| `codeql.yml`                                                     | Mondays + PRs to `main`                 | CodeQL security scan                                                                                   |
| `pr-auto-review.yml`                                             | PRs                                     | Frontend lint + build, backend Ruff + module-size check, tests at 100% coverage                        |
| `keep-warm.yml`, `ingest-power-units.yml`, `ingest-rulebook.yml` | disabled at cutover                     | Render-era jobs, replaced by the VM; kept for rollback until the old host is decommissioned            |

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
│   │   ├── llm.py            chat engines, failover classification, rest periods
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
│   │   ├── profiles/         team, driver and circuit records
│   │   ├── champions.py      champions + race winners
│   │   ├── open_meteo.py     hourly forecast behind the per-session weather
│   │   ├── weather.py        OpenWeatherMap current conditions (chat tool, fallback)
│   │   ├── multiviewer.py    circuit outlines and corner numbers
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
├── race-control/             Command Center (weekend/ holds its showcase panels),
│                             engineer, grand-prix, telemetry, teams
│                             (standings), constructors + drivers + profiles (Teams &
│                             Drivers), power-units, champions, debriefs, rulebook
├── calendar/  standings/  champions/  predictions/  consumer/   → redirects
├── components/               NavShell, chat, LiveTimingTower, ServerStatusNotice, …
├── hooks/                    useChat, useLocalChats, useLiveTiming, useServerStatus, useVoice
└── lib/  utils/              server-side prefetch, server status store, fetcher, error tracking

deploy/oracle/
├── compose.yaml              caddy, api, postgres, and the one-shot `jobs` profile
├── Caddyfile                 TLS on the DuckDNS name, reverse proxy, WebSocket
├── bootstrap.sh              one-time VM setup (Docker, volume, firewall, users, timers)
├── deploy.sh                 the deploy key's only command: deploy <sha> with rollback
├── bin/                      compose wrapper, backup, restore check, DuckDNS, PU ingest,
│                             Supabase migration
├── systemd/                  the timers and their services
└── env.example               every setting and secret the VM's .env holds

ios/F1AI/                     legacy SwiftUI companion (Calendar, Standings, Chat,
                              Compare, Live, Predictions, Settings)
```

---

## Tech Stack

| Layer              | Technology                                                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web framework      | Next.js 16, React 19, TypeScript 5                                                                                                                |
| Styling            | Tailwind CSS 4                                                                                                                                    |
| Web UI libs        | Recharts, Framer Motion, SWR, react-markdown, lucide-react                                                                                        |
| Backend            | FastAPI, Uvicorn, Python 3.13, structlog                                                                                                          |
| LLM                | AMD Token Lab (DeepSeek-V4-Flash), Gemini 3.5 Flash-Lite fallback                                                                                 |
| LLM orchestration  | LangChain (agentic tool-use loop)                                                                                                                 |
| F1 data            | f1db (SQLite, 1950–present), FastF1, OpenF1 (telemetry + live), Ergast/Jolpica (fallback), FIA documents (power units)                            |
| Weather & circuits | Open-Meteo (hourly forecast, [CC BY 4.0](https://open-meteo.com/en/license)), OpenWeatherMap (current conditions), MultiViewer (circuit outlines) |
| Vector search      | Postgres pgvector + sentence-transformers + cross-encoder reranker                                                                                |
| Storage            | Postgres + pgvector on the VM (optional locally; JSON fallback)                                                                                   |
| ML                 | scikit-learn Ridge regression + heuristic blend                                                                                                   |
| Web search         | Tavily                                                                                                                                            |
| MCP                | FastMCP                                                                                                                                           |
| Hosting            | Oracle Cloud Always Free VM (backend, Postgres, jobs; Docker Compose + Caddy), Vercel (frontend)                                                  |
| Observability      | Sentry (web + backend), Vercel Analytics, Vercel Speed Insights                                                                                   |
| iOS (legacy)       | SwiftUI, Swift 5.9, Observation framework                                                                                                         |
