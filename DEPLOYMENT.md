# Deployment Guide

How the F1-AI backend runs in production, the settings it needs, and how a change reaches it. The step-by-step procedures (building the VM, the cutover, rollback, and day-to-day operations) are in [`docs/deploy/ORACLE.md`](docs/deploy/ORACLE.md).

---

## 1. Architecture at a glance

```
Browser ──▶ Vercel (Next.js frontend)
               │ HTTPS (NEXT_PUBLIC_API_URL, API_URL)
               ▼
https://<name>.duckdns.org        DuckDNS: the name → the VM's public IP
               │
┌──────────────▼── Oracle Cloud VM: Always Free A1, 2 OCPU / 6 GB, Ubuntu 24.04 arm64 ──┐
│ caddy     :80 / :443, Let's Encrypt certificate, WebSocket upgrade                     │
│   └▶ api  FastAPI, one uvicorn worker, local models on                                 │
│        └▶ postgres  pgvector/pgvector:pg17 (documents, chat memory, rulebook vectors)  │
│ systemd timers: PU ingest · nightly pg_dump · weekly restore check · DuckDNS refresh   │
│ /srv/f1ai on a 100 GB block volume: pgdata, f1db, FastF1 cache, model cache, .env      │
└──────────────────────────────────────┬─────────────────────────────────────────────────┘
                                       ▼
                     OCI Object Storage bucket f1ai-backups (dumps kept 14 days)
```

- **Backend:** Python 3.13 / FastAPI in a container image built from `backend/Dockerfile` (arm64, CPU-only torch, non-root user `10001`), published as `ghcr.io/amurark3/f1-ai-api`. The VM runs it with Docker Compose from `deploy/oracle/`. It never sleeps, so there is no cold start.
- **LLM:** **AMD Token Lab** (DeepSeek-V4-Flash) first, **Gemini** free tier (3.5 Flash-Lite) as the fallback. Gemini's free tier caps requests per day (20 a day on the Flash models), so it is a backup, not a second primary. A question that fails on one engine with that engine's own error restarts on the next, and the failed engine rests for 1–10 minutes. Built lazily on the first chat request.
- **Data store:** Postgres with the `vector` (pgvector) extension, on the VM, holds the prediction cache and accuracy history, the Telemetry Lab's kept OpenF1 loads, conversation memory and the FIA rulebook embeddings. Without `DATABASE_URL` (local development) the app falls back to local JSON files.
- **F1 data:** the **f1db** SQLite dataset, downloaded to the volume and kept on the latest release, plus FastF1 for session telemetry (its cache is on the volume too).
- **Local models:** the image sets `ENABLE_LOCAL_MODELS=true`, so rulebook search (embedder plus cross-encoder reranker) and chat-memory recall run inside the API (§3).
- **Frontend:** Next.js on Vercel, unchanged by the move; it reads the API's address at build time.
- **Cost:** $0. The Oracle account is Always Free only and everything fits its allowances ([`docs/deploy/ORACLE.md`](docs/deploy/ORACLE.md) §0 and §1.9).

---

## 2. Where things run

| What                  | Where                                                                                                 | Defined in                                                       |
| --------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| API                   | container `api` on the VM; no published port, only Caddy reaches it                                   | `backend/Dockerfile`, `deploy/oracle/compose.yaml`               |
| Postgres + pgvector   | container `postgres`; the Compose network plus `127.0.0.1:5432` on the VM                             | `deploy/oracle/compose.yaml`                                     |
| TLS and reverse proxy | container `caddy`, ports 80 and 443                                                                   | `deploy/oracle/Caddyfile`                                        |
| One-off scripts       | the `jobs` profile: the API's image, env and data, one command                                        | `deploy/oracle/compose.yaml`                                     |
| Power-unit ingest     | timers `f1ai-pu-ingest` (hourly at :17, Thursday to Monday) and `f1ai-pu-ingest-daily` (05:47 UTC)    | `deploy/oracle/systemd/`, `deploy/oracle/bin/pu-ingest.sh`       |
| Backups               | timer `f1ai-backup` (03:30 UTC, `pg_dump` to Object Storage); `f1ai-restore-check` (Wednesdays 04:30) | `deploy/oracle/bin/backup.sh`, `bin/restore-check.sh`            |
| DNS                   | timer `f1ai-duckdns` (every 5 minutes)                                                                | `deploy/oracle/bin/duckdns.sh`                                   |
| Build and deploy      | GitHub Actions `deploy-oracle.yml` (arm64 runner → GHCR → SSH)                                        | `.github/workflows/deploy-oracle.yml`, `deploy/oracle/deploy.sh` |
| Model retraining      | GitHub Actions `retrain.yml` (Tuesdays)                                                               | `.github/workflows/retrain.yml`                                  |
| Frontend              | Vercel                                                                                                | `frontend/`                                                      |
| Uptime and errors     | UptimeRobot on `/api/health/deep`; Sentry (backend and web projects)                                  | the two services' dashboards                                     |

---

## 3. Environment variables

The stack reads `/srv/f1ai/.env` on the VM (mode 600, owner `deploy`). Its template, with a note on every variable, is [`deploy/oracle/env.example`](deploy/oracle/env.example). After editing it, recreate the container ([`ORACLE.md`](docs/deploy/ORACLE.md) §4.3); a plain restart keeps the old values.

| Variable                          | Required             | Purpose                                                                                                                                                                                                                                          |
| --------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `POSTGRES_PASSWORD`               | **Yes**              | The VM's Postgres password (`openssl rand -hex 32`). Read only when the database is first created; changing it later also needs `ALTER USER` (ORACLE.md §4.8)                                                                                    |
| `DATABASE_URL`                    | **Yes**              | `postgresql://f1ai:<POSTGRES_PASSWORD>@postgres:5432/f1ai`. The app classifies the `postgres` host as self-hosted                                                                                                                                |
| `API_HOST`                        | **Yes**              | The name Caddy serves and certifies: `<name>.duckdns.org`                                                                                                                                                                                        |
| `DUCKDNS_DOMAIN`, `DUCKDNS_TOKEN` | **Yes**              | The DuckDNS refresh timer                                                                                                                                                                                                                        |
| `OCI_BUCKET`, `OCI_NAMESPACE`     | Bucket yes           | The nightly backup's bucket (`f1ai-backups`) and Object Storage namespace (looked up when empty). Uploads use instance-principal auth: no OCI key on the VM                                                                                      |
| `ENVIRONMENT`                     | **Yes**              | `production`: JSON log lines, and the label on Sentry events                                                                                                                                                                                     |
| `ALLOWED_ORIGINS`                 | **Yes**              | CORS: the frontend's origin(s), comma-separated                                                                                                                                                                                                  |
| `TOKENLAB_API_KEY`                | **One of these two** | Primary chat engine — AMD Token Lab ([notebooks.amd.com/tokenlab](https://notebooks.amd.com/tokenlab)). Beta: extend its 30-day access from that page before it lapses                                                                           |
| `GOOGLE_API_KEY`                  | **One of these two** | Fallback chat engine — Gemini free tier. The key must come from an AI Studio project with **no billing linked**                                                                                                                                  |
| `TAVILY_API_KEY`                  | No                   | Web-search tool                                                                                                                                                                                                                                  |
| `OPENWEATHERMAP_API_KEY`          | No                   | The chat agent's weather tool, and the Command Center's current-conditions fallback when Open-Meteo has no race-day forecast. Without it those show as offline. The per-session forecast (Open-Meteo) and circuit maps (MultiViewer) need no key |
| `SENTRY_DSN`                      | No                   | The backend Sentry project's DSN; error tracking is off without it                                                                                                                                                                               |
| `HF_TOKEN`                        | No                   | Faster, rate-limit-free model downloads from Hugging Face (the models are cached on the volume after the first)                                                                                                                                  |
| `GITHUB_TOKEN`                    | No                   | A token with no scopes: raises the f1db release lookup's GitHub API limit from 60 to 5,000 requests an hour (§8)                                                                                                                                 |

- **Set by the image** (`backend/Dockerfile`), so not in `.env`: `ENABLE_LOCAL_MODELS=true`, `FASTF1_CACHE_DIR=/var/lib/f1ai/f1_cache`, `HF_HOME=/var/lib/f1ai/huggingface`, `F1DB_PATH=/var/lib/f1ai/f1db/f1db.db`, and `GIT_COMMIT` (the build's commit, used as Sentry's release). Compose mounts the matching `/srv/f1ai` directories over the three paths.
- **Never set in production:** `F1DB_VERSION` (§8), and `ENABLE_LOCAL_MODELS=false`, which would turn rulebook search and recall off.
- **The engines' models** are not variables: they are code constants, `LLM_PROVIDERS` in `backend/app/config.py`. Changing one is a code change and a deploy.

> Missing engine keys do not crash the service — only the chat endpoint fails; health, predictions, standings, and rulebook still work. Set both keys so the chat survives Token Lab's points or access window running out.

**Frontend** (Vercel → the project → **Settings** → **Environment Variables**, Production): `NEXT_PUBLIC_API_URL` and `API_URL` are both `https://<name>.duckdns.org` (`API_URL` is for server renders and falls back to `NEXT_PUBLIC_API_URL`); `NEXT_PUBLIC_SENTRY_DSN`, plus `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` for source maps. These are read at build time, so a change needs a redeploy. Set the project's function region (**Settings** → **Functions**) to the one nearest the VM ([`ORACLE.md`](docs/deploy/ORACLE.md) §1.1).

### `ENABLE_LOCAL_MODELS`

Rulebook search and conversation-memory recall need two torch models in-process: a sentence-transformers embedder (`all-MiniLM-L6-v2`, 384 dimensions, also used to embed chat turns) and a cross-encoder reranker. The image installs them (`requirements-ingest.txt`) and switches them on. They load on first use, not at boot; measured, the API peaks at about 0.65 GB with both loaded, which the 6 GB VM holds easily alongside Postgres.

The code's default is `false`, for local development. With the flag off, nothing imports torch:

- **Rulebook search** reports that it is unavailable, rather than claiming no regulations matched; the query never ran.
- **Chat** works normally and messages are still stored, without vectors; only semantic recall and personalisation are skipped. `scripts/backfill_chat_embeddings.py` embeds such turns later.
- **Predictions, standings, champions, health** are unaffected.

With the flag on but `sentence-transformers` missing, the lazy import raises, is caught, and embeddings return `None`: degraded, not crashed.

---

## 4. Deploy flow

1. **A push to `main`** that touches `backend/**`, `deploy/oracle/**` or the workflow file starts `.github/workflows/deploy-oracle.yml`. A frontend-only merge deploys only on Vercel; restarting the API for it would show visitors the restart notice for nothing.
2. **Build:** on GitHub's free `ubuntu-24.04-arm` runner, with `GIT_COMMIT=<sha>` and the GitHub Actions layer cache; pushed to GHCR as `ghcr.io/amurark3/f1-ai-api:<sha>` and `:latest`. The package is public, because the VM pulls without credentials.
3. **Deploy:** the job SSHes to the VM as `deploy` with the deploy key and the pinned host key, and asks for `deploy <sha>`. That key can run only `deploy/oracle/deploy.sh` (a forced command), which:
   1. checks out `deploy/oracle` at that commit, so the stack definition always matches the image;
   2. pulls the image and restarts the stack on it;
   3. waits up to 180 s for `/api/ready` to report ready and `/api/health/deep` to answer 200;
   4. on failure, puts the previous image back and exits 1, which fails the job.
4. **Rulebook:** when the push changed `backend/data/raw/**` (the regulation PDFs), the job then asks for `ingest-rulebook`, which re-embeds them into pgvector with the deployed image.
5. **Promoted models:** `retrain.yml` merges with `GITHUB_TOKEN`, which starts no workflow, so once its PR has merged it dispatches `deploy-oracle.yml` itself.

The workflow does nothing while the repository variable `ORACLE_HOST` is unset. Deploying by hand, going back one deploy, and re-running `bootstrap.sh` after a change to the systemd units are in [`ORACLE.md`](docs/deploy/ORACLE.md) §4.4 and §4.10.

---

## 5. Database

One Postgres database on the VM. Each module creates its tables on first use (`CREATE TABLE IF NOT EXISTS`), so right after boot only `app_documents` exists; `scripts/ensure_schema.py` creates all of them at once.

| Table                          | Written by                                                            | Purpose                                                                  |
| ------------------------------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `app_documents`                | prediction cache and history, power units, stints, circuit references | whole JSON documents, with a `version` column for safe concurrent writes |
| `analysis_cache`               | Telemetry Lab                                                         | OpenF1 loads kept once a session has settled                             |
| `user_profile`, `chat_message` | chat memory                                                           | personalisation and pgvector conversation recall                         |
| `rulebook_chunk`               | `app.rag.ingest`                                                      | FIA regulation embeddings (pgvector, 384-dim, HNSW index)                |

- **Access:** Postgres listens on the Compose network and the VM's loopback only. A `psql` shell runs in the container or over an SSH tunnel ([`ORACLE.md`](docs/deploy/ORACLE.md) §4.5).
- **Backups:** nightly `pg_dump -Fc` to the VM and to Object Storage (14 days), with the row counts taken around each dump; a weekly check restores the newest into a scratch database and compares. Restoring by hand: [`ORACLE.md`](docs/deploy/ORACLE.md) §4.6.
- **Row-level security:** the schema DDL in `app/data/store.py`, `app/data/memory.py` and `app/rag/pgvector_store.py` enables RLS with no policies on every table. That was written for Supabase, whose PostgREST API published every `public` table. On the VM nothing but the app connects, and the app is the tables' owner, which bypasses RLS, so it is harmless. Do not add a permissive `USING (true)` policy.

---

## 6. Rulebook (pgvector)

Regulation vectors live in Postgres, embedded from the PDFs in `backend/data/raw/<year>/`.

- **Automatic:** a push to `main` that changes `backend/data/raw/**` re-embeds the corpus after the deploy (§4).
- **By hand:** Actions → **Deploy backend to the Oracle VM** → **Run workflow** with **Also re-embed the regulation PDFs into pgvector** ticked, or on the VM `deploy.sh ingest-rulebook` ([`ORACLE.md`](docs/deploy/ORACLE.md) §4.7).
- **Locally**, from `backend/` with `DATABASE_URL` set:

```bash
pip install -r requirements-ingest.txt
python -m app.rag.ingest            # skips if already populated
python -m app.rag.ingest --force    # wipe + re-embed the whole corpus
```

**To update regulations:** drop the new PDF in `backend/data/raw/<year>/`, commit, merge.

---

## 7. Model retraining — auto PRs

[`.github/workflows/retrain.yml`](.github/workflows/retrain.yml) runs weekly (and on demand): it retrains the race-finish model and **promotes a challenger only if it beats the grid-order baseline** (`app.ml.promote`). It reads whatever release `app.data.f1db_source` says is current — it does **not** own dataset freshness. The running server keeps its own copy up to date (§8), so a rejected challenger never leaves production serving stale standings. A promoted model is opened as a PR, auto-approved (if a `RETRAIN_PAT` secret is set) and auto-merged; once GitHub reports it merged, the job dispatches the deploy (§4). Requires branch protection to allow Actions to open and merge PRs (0 required approvals, or a code-owner PAT).

---

## 8. F1 dataset freshness (f1db)

Standings, results, and championship history are read from the f1db SQLite dump, which f1db re-publishes as a tagged GitHub release within a day or two of every race. `app.data.f1db_source` keeps the local copy on the newest release:

| When       | What runs                                                     |
| ---------- | ------------------------------------------------------------- |
| Every boot | the readiness warm-up calls `sync_to_latest()` before serving |
| Every 6 h  | the `_refresh_f1db_dataset` loop in `main.py` re-checks       |

Both paths are cheap when nothing changed — one small request, no download. The newest tag is read from the redirect at `https://github.com/f1db/f1db/releases/latest` (→ `/releases/tag/<tag>`), which is **not** metered against the REST API's 60-requests/hour unauthenticated limit. The REST API is only a backup: relying on it alone once left production on the hardcoded `FALLBACK_F1DB_VERSION` (round 11) from round 12 to round 16, because the old host's shared egress IPs exhausted that limit. A new release is fetched to a temp file and moved into place with `os.replace`, so open reader connections are never overwritten underneath. The tag on disk is stamped beside the file (`f1db.db.version`), on the VM's volume. After a failed download, further downloads wait 60 s, doubling up to 15 minutes, so a GitHub outage can't turn into a download storm.

`GET /api/ready` reports both the tag on disk (`f1db_version`) and the last release check (`f1db_sync`):

```jsonc
"f1db_sync": {
  "version": "v2026.16.1",       // on disk
  "latest": "v2026.16.1",        // what GitHub said is newest; null = check failed
  "up_to_date": true,            // the field to alert on
  "updated": true,
  "reason": "updated from no dataset to v2026.16.1",
  "checked_at": "2026-10-09T16:32:42+00:00"
}
```

**`F1DB_VERSION` must stay unset in `/srv/f1ai/.env`.** Setting it pins the dataset to one release and disables all of the above. That is a deliberate escape hatch for reproducible training runs, not a production setting — a stale pin is what once left the standings page four weeks behind.

If standings, results or the Grand Prix Hub grid ever look behind again (a "not in our dataset yet" grid warning on a finished round is the tell):

```bash
curl -s https://<name>.duckdns.org/api/ready | jq .f1db_sync
```

- `up_to_date: true` — the server has the newest release, so f1db has not published the round yet. That is normal for a few hours after a race.
- `latest: null` — the release check itself is failing. Look for `f1db.latest_redirect_failed` / `f1db.latest_api_failed` / `f1db.sync.check_failed` in the API's log ([`ORACLE.md`](docs/deploy/ORACLE.md) §4.2). Setting `GITHUB_TOKEN` raises the API backup's limit to 5,000/hour.
- `latest` set but different from `version` — the download is failing. Look for `f1db.sync.failed` and `f1db.download.backoff`.

---

## 9. GitHub Actions settings

Repository **Settings → Secrets and variables → Actions**:

| Name                 | Kind     | Used by                                 | Notes                                                                                                    |
| -------------------- | -------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ORACLE_HOST`        | variable | `deploy-oracle`, `retrain`              | The VM's DuckDNS name. While it is unset, neither deploys                                                |
| `ORACLE_KNOWN_HOSTS` | variable | `deploy-oracle`                         | The VM's SSH host key line for exactly that name (`ssh-keyscan -t ed25519 <ORACLE_HOST>`)                |
| `ORACLE_SSH_KEY`     | secret   | `deploy-oracle`                         | The deploy key's private half; the VM accepts it only for `deploy.sh`                                    |
| `RETRAIN_PAT`        | secret   | `retrain`                               | Optional — only if `main` requires approvals                                                             |
| `DATABASE_URL`       | secret   | `ingest-power-units`, `ingest-rulebook` | History: the Supabase URL for the two Render-era ingest workflows, disabled at cutover; deleted in P0c.9 |

`deploy-oracle` pushes to GHCR with the job's own `GITHUB_TOKEN` (`packages: write`); no other secret is needed. The setup, including how to check the host key, is [`ORACLE.md`](docs/deploy/ORACLE.md) §2.2 and §2.5.

---

## 10. Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-ingest.txt          # base + ingest deps for full local use
cp .env.example .env                             # then fill in the keys (see §3)
python main.py                                   # http://localhost:8000  (docs at /docs)
```

Without `DATABASE_URL`, the app runs against local JSON fallbacks; the rulebook and chat memory need a Postgres with pgvector. Set `ENABLE_LOCAL_MODELS=true` locally to use rulebook search and recall.

---

## 11. Troubleshooting

Commands for each of these are in [`ORACLE.md`](docs/deploy/ORACLE.md) §4.

- **The site says "Server isn't responding"** → `curl https://<name>.duckdns.org/api/ready`; on the VM, `bin/compose.sh ps` and `bin/compose.sh logs --tail 200 api`. UptimeRobot will have emailed if `/api/health/deep` failed.
- **A deploy failed and rolled back** → the Actions log of "Deploy on the VM" says which check failed; the API's log says why. The previous image keeps serving.
- **`/api/health/deep` answers 503** → the API can't reach Postgres: `bin/compose.sh ps` (is `postgres` healthy?), `bin/compose.sh logs postgres`, `df -h /srv/f1ai`.
- **Certificate errors** → `bin/compose.sh logs caddy`; check that `<name>.duckdns.org` resolves to the VM (`journalctl -u f1ai-duckdns`) and that ports 80 and 443 are open.
- **Rulebook search says unavailable** (`"source": "fallback"`) → the response's `error` says why: `ENABLE_LOCAL_MODELS` overridden in `.env`, the database unreachable, or an empty `rulebook_chunk` table (re-ingest, §6).
- **A timer failed** → `systemctl --failed`, then `journalctl -u <unit> -n 50`. Nothing alerts on this; the weekly check looks ([`ORACLE.md`](docs/deploy/ORACLE.md) §4.9).
- **Standings look behind** → §8.

---

## 12. History: the Render era

Until the P0c cutover (November 2026) the backend ran on a free **Render** web service, with **Supabase** Postgres + pgvector as its database. Plan phase P0c moved it to the Oracle VM because of what the free tier forced:

- **Cold starts:** Render's free plan slept after 15 idle minutes, and the first visitor then waited about 50 s. `keep-warm.yml` pinged it on a `*/13` cron, but GitHub throttles scheduled workflows on shared runners, so it ran every few hours in practice and never kept it awake.
- **512 MB:** `ENABLE_LOCAL_MODELS` had to stay `false`; a single rulebook query with it on OOM-killed the container, and every endpoint was down until Render restarted it. Rulebook search and chat recall were off, and chat turns were stored without vectors (backfilled at cutover).
- **Wiped disk and shared IPs:** the FastF1 cache and f1db were lost on every restart, and Render's shared egress IPs ran into GitHub's API rate limit (they are also the main suspect in the Open-Meteo failures that plan task P0b.1 diagnoses).
- **Supabase's direct host is IPv6-only** and Render's egress was IPv4, so `DATABASE_URL` had to be the Supavisor **session pooler** (`aws-<n>-<region>.pooler.supabase.com:5432`). With the direct host, the app silently fell back to a local JSON file that every restart erased.
- **`render.yaml` was never applied:** Render reads it only for Blueprint services, which need payment details, so the dashboard was the source of truth and the file was reference documentation.
- **The PyTorch-index build failure.** Render's build once installed CPU torch with `pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt` and broke with no repo change. Render's image shipped pip 23.0.1, which resolved torch's _dependencies_ on that flat index too, rejected a `typing_extensions` wheel over an unnormalised name, fell back to the sdist, and could not find its build backend there. `backend/Dockerfile` avoids the trap: it takes only torch's own `+cpu` wheel from that index (`--no-deps`), and everything else from PyPI.

Until P0c.9 decommissions them (after 7 stable days on the VM), the Render service and the Supabase project remain as the rollback path: [`ORACLE.md`](docs/deploy/ORACLE.md) §3.
