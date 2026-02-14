# F1 AI — Race Engineer Assistant

An AI-powered Formula 1 analyst and race engineer.  Ask it about race results,
qualifying lap times, championship standings, regulatory rules, and more.
The assistant has access to real-time F1 data and the official FIA regulations.

---

## Architecture

```
F1-AI/
├── frontend/          Next.js 16 + React 19 (TypeScript)
└── backend/           Python FastAPI + LangChain + Gemini
```

```
Browser (Next.js)
    │  SWR fetches (schedule, standings)
    │  Streaming POST /api/chat
    ▼
FastAPI Backend
    │
    ├─ Gemini 2.0 Flash (LLM orchestration)
    ├─ FastF1          (qualifying, race, sprint data)
    ├─ Ergast API      (championship standings)
    ├─ Tavily          (web search)
    └─ ChromaDB        (FIA regulations vector search)
```

---

## Features

| Feature | Description |
|---|---|
| **Race Calendar** | Full season schedule with timezone conversion for every F1 circuit |
| **Championship Standings** | Live WDC and WCC tables (2021–2026) |
| **AI Chat** | Streaming chat with an F1 race-engineer persona |
| **Qualifying Results** | Q1/Q2/Q3 tables for any Grand Prix |
| **Race Results** | Full classification with grid deltas and DNF reasons |
| **Sprint Data** | Sprint race and Sprint Qualifying (Shootout) results |
| **Driver Comparison** | Sector-by-sector fastest-lap telemetry diff |
| **Rulebook** | Semantic search of FIA Sporting, Technical, and Financial Regulations |
| **Web Search** | Real-time news via Tavily for post-cutoff information |

---

## Prerequisites

| Tool | Version |
|---|---|
| Node.js | 18 or later |
| Python | 3.10 or later |
| pip | latest |

---

## Backend Setup

All commands are run from the `backend/` directory.

### 1. Create and activate a virtual environment (recommended)

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

> The first run will also download the `sentence-transformers/all-MiniLM-L6-v2`
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

The `consult_rulebook` AI tool requires a local vector database built from the
official FIA PDF regulations. The PDFs are already included in `data/raw/`.

```bash
python app/rag/ingest.py
```

This scans `data/raw/` for PDFs, splits them into chunks, generates embeddings,
and saves the database to `data/chroma/`. Re-run this whenever you add or
update regulation PDFs.

> Expected output: `✅ Knowledge base updated successfully!`

### 5. Start the server

```bash
python main.py
```

The API will be available at **http://localhost:8000**.

To verify it's running, open http://localhost:8000 — you should see:
```json
{"status": "Backend is running", "service": "F1 Race Engineer"}
```

#### Available endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming AI chat |
| `GET` | `/api/schedule/{year}` | Season calendar (UTC) |
| `GET` | `/api/standings/drivers/{year}` | WDC standings |
| `GET` | `/api/standings/constructors/{year}` | WCC standings |
| `GET` | `/api/health` | Liveness probe |

Interactive API docs: http://localhost:8000/docs

---

## Frontend Setup

All commands are run from the `frontend/` directory.

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Start the development server

```bash
npm run dev
```

The app will be available at **http://localhost:3000**.

> The frontend expects the backend at `http://localhost:8000`. If you change
> the backend port, update the hardcoded URLs in:
> - `app/chat/page.tsx`
> - `app/components/RaceCalendar.tsx`
> - `app/components/Standings.tsx`

### 3. Other scripts

| Command | Description |
|---|---|
| `npm run dev` | Start development server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | Run ESLint |

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

Then open **http://localhost:3000** in your browser.

---

## Project Structure

```
backend/
├── main.py                   Entry point — FastAPI app, CORS, router
├── requirements.txt          Python dependencies
├── .env                      API keys (not committed)
├── f1_cache/                 FastF1 disk cache (auto-created)
├── data/
│   ├── raw/
│   │   ├── 2024/             FIA regulation PDFs for 2024
│   │   ├── 2025/             FIA regulation PDFs for 2025
│   │   └── 2026/             FIA regulation PDFs for 2026
│   └── chroma/               ChromaDB vector database (generated by ingest.py)
└── app/
    ├── api/
    │   ├── routes.py         HTTP endpoints + agentic chat loop
    │   ├── tools.py          11 LLM-callable tools
    │   └── prompts.py        Race-engineer system prompt
    └── rag/
        └── ingest.py         PDF → ChromaDB ingestion script

frontend/
├── package.json
└── app/
    ├── layout.tsx            Root layout (fonts, metadata)
    ├── page.tsx              Home page (calendar + standings tabs)
    ├── globals.css           Tailwind CSS base styles
    ├── chat/
    │   └── page.tsx          Streaming chat interface
    ├── components/
    │   ├── RaceCalendar.tsx  Race weekend card grid with timezone conversion
    │   ├── Standings.tsx     WDC / WCC standings table
    │   └── TelemetryCard.tsx Driver telemetry comparison card
    ├── constants/
    │   └── timeZone.tsx      IANA timezone list for F1 circuits
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
| Vector database | ChromaDB |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Web search | Tavily |
| Language | Python 3.10+ |
