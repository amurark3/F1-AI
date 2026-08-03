# Deployment Guide

How the F1-AI backend is built, deployed, and kept in sync — plus the secrets,
databases, and automation that make it run.

---

## 1. Architecture at a glance

```
Frontend (Next.js)  ──HTTPS──▶  Backend (FastAPI on Render)
                                   │
                 ┌─────────────────┼──────────────────────────┐
                 ▼                 ▼                          ▼
          Groq (Llama 3.3)   Supabase Postgres          FastF1 + f1db
          LLM + tools        + pgvector                 (F1 data; f1db.db
                             • prediction cache/history  downloaded on boot)
                             • conversation memory
                             • FIA rulebook vectors
```

- **Backend:** Python 3.10 / FastAPI, deployed on **Render** (`backend/` root).
- **LLM:** **Groq** (Llama 3.3 70B). Built lazily on first chat request.
- **Data store:** **Supabase Postgres** (with the `vector`/pgvector extension) holds
  the durable prediction cache + accuracy history, conversation memory, and the
  FIA rulebook embeddings. Falls back to local JSON when `DATABASE_URL` is unset.
- **F1 data:** the local **f1db** SQLite dump (auto-downloaded on first use) plus
  FastF1 for session telemetry.

---

## 2. Environment variables

Set these in **Render → the service → Environment** (all `sync: false` in
`render.yaml`, so their values live in the dashboard and survive Blueprint syncs).

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | **Yes** | LLM engine (get a free key at console.groq.com) |
| `DATABASE_URL` | **Yes** | Supabase Postgres + pgvector connection string — **must be the pooler host**, see below |
| `TAVILY_API_KEY` | No | Web-search tool |
| `OPENWEATHERMAP_API_KEY` | No | Live weather (falls back to historical averages) |
| `ALLOWED_ORIGINS` | Recommended | CORS — comma-separated frontend origin(s) |
| `HF_TOKEN` | No | Faster/rate-limit-free HuggingFace model downloads |
| `PYTHON_VERSION` | Set in yaml | Pinned to `3.10.12` |

> A missing `GROQ_API_KEY` no longer crashes the whole service — only the chat
> endpoint fails; health, predictions, standings, and rulebook still work.

### `DATABASE_URL` must use the pooler host

Supabase's **direct** endpoint, `db.<project-ref>.supabase.co`, publishes no A
record — it is IPv6-only. Render's egress is IPv4, so a service configured with
the direct host cannot reach the database at all. Verify with:

```bash
dig +short A    db.<project-ref>.supabase.co   # empty — no IPv4
dig +short AAAA db.<project-ref>.supabase.co   # resolves
```

Nothing about this failure is loud. The app boots, serves pages, and answers
`/api/health` with 200, because every store operation degrades gracefully onto a
local JSON file — on a container filesystem that is erased at every cold start.
Predictions look saved and silently disappear; the rulebook returns "no excerpts
matched" against a fully populated corpus.

Use the **Supavisor session pooler** instead, which is dual-stack:

```
postgresql://postgres.<project-ref>:<password>@aws-<n>-<region>.pooler.supabase.com:5432/postgres
```

Copy it from Supabase → Project Settings → Database → Connection string →
Session pooler. Use **session mode (port 5432)**, not transaction mode (6543):
psycopg promotes repeated statements to prepared ones, which transaction mode
rejects unless you also set `prepare_threshold=None`.

Confirm the deployed service can actually reach it:

```bash
curl -s https://<your-host>/api/health/deep     # 200 + "ok": true, or 503
```

That endpoint round-trips Postgres, unlike `/api/health`, which touches nothing.

---

## 3. Build & start commands

Defined in [`render.yaml`](render.yaml):

```bash
# Build
pip install torch --index-url https://download.pytorch.org/whl/cpu && \
pip install -r requirements.txt

# Start
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Why this build is fast:
- **CPU-only torch** — installed first from the PyTorch CPU index so pip doesn't
  pull the ~2 GB CUDA build via `sentence-transformers` (the biggest win).
- **Lean runtime deps** — the PDF/RAG-ingest packages live in
  `requirements-ingest.txt`, not in `requirements.txt`, so the web build skips them.
- **No build-time vector DB** — the rulebook lives in pgvector, so there is no
  ~9-minute ChromaDB rebuild at deploy time.

Health check path: `/api/health` (returns 200 immediately).

---

## 4. How the service is configured (dashboard-managed)

This is a **manually-created Render web service**, and the **Render dashboard is
the source of truth** for its settings. `render.yaml` is kept in the repo as
accurate reference documentation of the intended config, but Render does **not**
apply it automatically to a manual service.

> Render **Blueprints** (which *would* make `render.yaml` authoritative) require
> payment info on the account, so this project does not use them. Everything
> below is managed in the dashboard instead — no card needed.

Keep these dashboard settings in sync with `render.yaml` (Render → the service →
Settings):

| Setting | Value |
|---|---|
| **Build Command** | the `uv` + CPU-torch command in §3 |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Root Directory** | `backend` |
| **Health Check Path** | `/api/health` |
| **Auto-Deploy** | On Commit |
| **Environment** | the variables in §2 |

⚠️ The Build Command must **not** contain `python app/rag/ingest.py` — that step
fails now that the PDF libraries live in `requirements-ingest.txt`, and the
rulebook is populated separately in pgvector (§6).

---

## 5. Databases (Supabase)

One Postgres database backs several things; tables are auto-created on first use:

| Table | Written by | Purpose |
|---|---|---|
| `app_documents` | prediction cache + accuracy history | durable JSON docs (off Render's ephemeral disk) |
| `user_profile`, `chat_message` | chat memory | personalization + pgvector conversation recall |
| `rulebook_chunk` | `app.rag.ingest` | FIA regulation embeddings (pgvector, 384-dim, HNSW index) |

Requires the `vector` extension (auto-enabled by the app). Free-tier Supabase
pauses after ~1 week idle — first request after a pause is slow.

---

## 6. Rulebook (pgvector) — populate & auto-update

Regulation vectors live in Postgres, not a shipped file. Populate/refresh them:

```bash
# from backend/, with DATABASE_URL set
pip install -r requirements-ingest.txt
python -m app.rag.ingest            # skips if already populated
python -m app.rag.ingest --force    # wipe + re-embed the whole corpus
```

**Automated:** [`.github/workflows/ingest-rulebook.yml`](.github/workflows/ingest-rulebook.yml)
re-embeds automatically whenever a PDF under `backend/data/raw/**` changes on
`main` (the `paths:` filter is the change detection). Also runnable from the
Actions tab. Requires the `DATABASE_URL` GitHub Actions secret.

**To update regulations:** drop the new PDF in `backend/data/raw/<year>/`, commit,
merge → the workflow re-ingests to Supabase on its own.

---

## 7. Model retraining — auto PRs

[`.github/workflows/retrain.yml`](.github/workflows/retrain.yml) runs weekly (and
on demand): it refreshes f1db, retrains the race-finish model, and **promotes a
challenger only if it beats the grid-order baseline** (`app.ml.promote`). A
promoted model is opened as a PR, auto-approved (if a `RETRAIN_PAT` secret is set),
and auto-merged — merging redeploys the model. Requires branch protection to allow
Actions to open/merge PRs (0 required approvals, or a code-owner PAT).

---

## 8. GitHub Actions secrets

| Secret | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | ingest-rulebook | Supabase connection string |
| `RETRAIN_PAT` | retrain | Optional — only if `main` requires approvals |
| `HF_TOKEN` | ingest-rulebook | Optional — faster model downloads |

Set at **GitHub → Settings → Secrets and variables → Actions**.

---

## 9. Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-ingest.txt          # base + ingest deps for full local use
cp .env.example .env                             # then fill in the keys (see §2)
python main.py                                   # http://localhost:8000  (docs at /docs)
```

Without `DATABASE_URL`, the app runs against local JSON fallbacks; the rulebook
needs a database (local or Supabase) to answer.

---

## 10. Deploy flow & troubleshooting

- **Auto-deploy** fires on every commit to `main` (Render "On Commit").
- **First request after idle** is slow — free instance spins down (~50 s cold start).
- **"Port scan timeout / no open ports"** → the app didn't bind its port in time.
  Heavy libs (torch) are now imported lazily so boot is ~0.8 s; if this recurs,
  it's memory pressure on the free tier — upgrade the instance.
- **Build fails on `ingest.py`** → the dashboard Build Command still has
  `python app/rag/ingest.py`; remove it (see §3).
- **`uvicorn: command not found` / exit 127 at start** → the build used
  `uv pip install --system`, which puts console scripts off Render's runtime
  PATH. Use plain `pip` in the Build Command (§3).
- **Rulebook returns "unavailable"** → `DATABASE_URL` unset, or the corpus was
  never ingested (§6).
