# Oracle hosting: deferred

**Deferred 2026-11-23 (user):** "I don't have an Oracle VM yet and I might not get one either." Nothing here is scheduled. Don't start any of it unless the user says they have a VM. Production stays on **Render + Supabase**, kept warm by a cron-job.org GET on `/api/health/deep` every 5 minutes. Hugging Face Spaces is not an option (needs PRO, 2026-11-22).

## Where things stand

- **Branch `feat/oracle-backend`** (pushed, `3821aa5`) holds P0c.1–P0c.8, unmerged. Work on it only in a separate worktree, never on `dev`, and never cherry-pick from it (user, 2026-11-23: reimplement Render-safe parts on `dev` instead).
- **If Oracle resumes:** rebase that branch onto `dev` and drop P0c.7's frontend half (P3.5 reimplemented it on `dev`). Keep `backend.ts`'s 10 s budget and 429 retry while Render is production.
- History (evidence, audits, P0c.1–P0c.8 rows) is in [`../2026-11-redesign/STATUS-archive.md`](../2026-11-redesign/STATUS-archive.md).

| ID          | Task                                                                                                         | Status                   | Notes                              |
| ----------- | ------------------------------------------------------------------------------------------------------------ | ------------------------ | ---------------------------------- |
| P0c.1–P0c.8 | Always-on backend on Oracle (code, guide, migration)                                                         | done on branch, unmerged | `feat/oracle-backend` at `3821aa5` |
| —           | Cutover to the VM (`docs/deploy/ORACLE.md` on the branch)                                                    | deferred                 | Needs an A1 VM                     |
| P0c.9       | Decommission Render, Supabase and the Render-era workflows                                                   | deferred                 | After cutover + 7 stable days      |
| P0b.1b      | Diagnose the Open-Meteo failures from the VM's logs                                                          | deferred                 | After cutover                      |
| —           | Register `session_store.ensure_schema` and `fia_documents.store.ensure_schema` in `scripts/ensure_schema.py` | deferred                 | User step, after P0c merges        |

---

The sections below were moved verbatim from the redesign PLAN.md.

## Phase P0c — Always-on backend on Oracle Cloud (P0, own branch `feat/oracle-backend`, own PR)

**Branch (user, 2026-11-09):** P0c lives on `feat/oracle-backend` (pushed; P0c.1–P0c.8 at `3821aa5`). It is not on `dev`, and `dev` carries on with P0b and the UI phases. Its remaining work happens on that branch, in a separate git worktree: cutover fixes, then P0c.9. Whichever of the two merges to `main` second resolves the PLAN/STATUS conflicts.

Added 2026-11-08. The user: "the cold start cannot continue … the cost has to be 0", and every decision taken because of Render gets fixed. The evidence and the audit are in the `STATUS.md` log entry of 2026-11-08.

- **Why.**
  - Render's free plan sleeps after 15 idle minutes, so a visitor waits about 50 s.
  - `keep-warm.yml` runs every 4–7 hours in practice (GitHub throttles cron), so it never prevents this.
  - Render's limits also switched things off:
    - 512 MB: `ENABLE_LOCAL_MODELS=false` turns off rulebook search and chat-memory recall.
    - Wiped disk: the FastF1 cache, the f1db file and the in-memory caches are lost on every restart.
    - Shared IP: GitHub API and Open-Meteo throttling.
    - Unreliable cron.
- **Target** (all $0; Oracle limits checked against Oracle's documentation 2026-11-08):
  - **The VM:**
    - One `VM.Standard.A1.Flex` with 2 OCPU and 6 GB, Ubuntu 24.04 arm64, on an **Always Free-only account**, so Oracle cannot charge it.
    - The A1 allowance is now 2 OCPU and 12 GB.
    - Oracle reclaims a VM only when CPU (95th percentile), network **and** memory all stay below 20% for 7 days. At 6 GB, the API with local models (measured at about 0.65 GB in P0c.3) plus Postgres, Caddy and the OS holds about 2 GB, roughly a third, so memory stays above 20%.
  - **Storage:** a 100 GB block volume at `/srv/f1ai` holds pgdata, `f1_cache`, f1db, the HuggingFace cache and `.env`.
  - **Containers (Docker Compose):**
    - `caddy`: Let's Encrypt on `<name>.duckdns.org`, WebSocket upgrade.
    - `api`: uvicorn, **one worker**, `ENABLE_LOCAL_MODELS=true`.
    - `postgres`: `pgvector/pgvector:pg17`, on the Docker network plus `127.0.0.1` only.
  - **systemd timers:** PU ingest, nightly `pg_dump` to OCI Object Storage plus a weekly restore check, DuckDNS refresh.
  - **Deploys:** a push to `main` builds on GitHub's free `ubuntu-24.04-arm` runner, pushes to GHCR, then runs a forced-command SSH `deploy.sh` that rolls back on its own.
  - **Unchanged:** the frontend stays on Vercel; CI and `retrain.yml` stay.
- **Stays** (not Render choices, or still right): f1db as SQLite, single-flight, lazy imports, Sentry `auto_enabling_integrations=False`, pgvector, readiness and `/api/ready`, one uvicorn worker. The FastF1 lock, the f1db sync, the lifespan loops and the whole-document stores all assume one process.
- **Merging is safe before the VM exists.** `deploy-oracle.yml` does nothing while `ORACLE_HOST` is unset, and all code stays host-agnostic, so Render plus Supabase keep running until cutover.

### P0c.1 Oracle guide, part 1: provisioning

- **Do:** write `docs/deploy/ORACLE.md` for the user (not an engineer audience), as numbered console steps:
  - **Account:**
    - Create it as Always Free only; never upgrade.
    - The home region is permanent. Choose one with A1 capacity; Vercel's function region is set to the nearest one at cutover.
  - **VM:**
    - `VM.Standard.A1.Flex`, 2 OCPU and 6 GB, Ubuntu 24.04 aarch64, 50 GB boot volume, public IPv4, an SSH key.
    - On "Out of host capacity", retry in another availability domain, or later.
  - **Disk:** a 100 GB block volume, attached and mounted at `/srv/f1ai` (`bootstrap.sh` in P0c.5 formats it and mounts it).
  - **Network:** VCN wizard. Ingress for 22, 80 and 443 in the security list; Ubuntu's own iptables rules come from `bootstrap.sh`.
  - **DuckDNS:** a subdomain pointed at the VM's IP, and the token.
  - **Backups:**
    - An Object Storage bucket `f1ai-backups` with a lifecycle rule deleting objects older than 14 days.
    - A dynamic group for the instance, and a policy that lets it manage objects in that bucket, so uploads use instance-principal auth with no keys on disk.
  - **Idle reclamation:** the rule, why 6 GB keeps us clear, and the week-1 check in OCI Monitoring that memory utilization stays at or above 25%.
  - **Hand-back:** what to send back (the IP and the DuckDNS name), and nothing secret in chat.
  - **Stubs:** sections 2–4 (cutover, rollback, operations) marked "written in P0c.8".
- **Accept:** every step names the exact console path and value; the Oracle limits in it match `STATUS.md`'s 2026-11-08 log; no secret values appear.
- **Verify:** Prettier on the file; links resolve.

### P0c.2 Backend container

- **Do:**
  - **Image:** `backend/Dockerfile` and `backend/.dockerignore`.
    - `python:3.13-slim` (matches `runtime.txt` 3.13.17), multi-arch, non-root user.
    - `pip install -r requirements.txt` plus `requirements-ingest.txt`: CPU torch, sentence-transformers, pypdf. torch's aarch64 wheels on PyPI are CPU-only; confirm the size.
    - `CMD uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --workers 1`.
    - `ARG GIT_COMMIT`, exposed as `GIT_COMMIT`.
  - **Paths from the environment:**
    - `FASTF1_CACHE_DIR` overrides `DEFAULT_CACHE_DIR` (`app/utils/fastf1_cache.py:21`).
    - Confirm `F1DB_PATH` covers the whole f1db directory (the `.version` stamp included).
    - `HF_HOME` for the model cache.
  - **Sentry:** the release reads `GIT_COMMIT`, then `RENDER_GIT_COMMIT` (`app/error_tracking.py:51`).
  - **Database host checks:**
    - `app/data/store.py` host classification and its warnings (`:76-145`, `:414-447`) and `scripts/ingest_power_units.py:71-76` learn a self-hosted host, such as `postgres` or `localhost`.
    - No Supabase pooler warning for it. The Supabase hosts stay classified until P0c.9.
- **Accept:**
  - Tests cover the env overrides, the release fallback order and the self-hosted classification.
  - `docker buildx build --platform linux/arm64 backend` succeeds, and the image size is recorded.
  - The container, run against a local `pgvector/pgvector:pg17` with `ENABLE_LOCAL_MODELS=true`, reaches every `/api/ready` stage.
- **Verify:** pytest (coverage 100%), `ruff check`, `ruff format --check`, module size; the build and run above.

### P0c.2c f1db download backs off after a failure (user, 2026-11-09)

- **Bug.**
  - With no f1db file on disk, every f1db read retries the GitHub release download.
  - During GitHub 504s the API started 637 downloads in about 4 minutes (2026-11-08), then 66 in a minute (2026-11-09 ~08:02 UTC).
  - On the VM this happens on a first boot, or after a lost volume, during an outage, and it would hammer GitHub from our IP.
- **Do:** after a failed download, `ensure_db` (`app/data/f1db_source.py`) refuses to try again until a backoff window passes. The window starts at 60 s and doubles up to 15 min, then resets on success. Readers in the window get the existing "f1db unavailable" path at once. One process-wide state, consistent with the existing per-process sync lock.
- **Accept:** a test shows that repeated reads after a failure make one download attempt per window, the window doubles and caps, and a success resets it.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.3 Rulebook RAG and chat-memory recall back on

- **Do:**
  - **Fix `consult_rulebook`** (`app/api/tools/reference.py:53-64`). When local models are off or embedding fails, it says rulebook search is unavailable, never "No regulations found". Mirror the guard in `services/rulebook.py:72-83`.
  - **One embedder:** `app/data/memory.py:98-129` uses `app.utils.embeddings` instead of loading its own `SentenceTransformer`.
  - **Backfill:** `scripts/backfill_chat_embeddings.py`, idempotent and batched. It embeds the `chat_message` rows whose `embedding IS NULL`, dry-run by default, `--apply` to write.
  - **Measure:** the API's memory with the models loaded after a rulebook query and a recall (`ps -o rss` or `/proc` in the container). Record it in STATUS.
- **Accept:**
  - With local models off, the tool's text says "unavailable".
  - With them on, results are cited.
  - The memory module never builds a second model, proven by a test spying on the loader.
  - The backfill updates only NULL rows and reports counts.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.4 Stores stay correct in a process that never restarts

- **Do:**
  - `services/prediction_cache.py`, `data/circuit_reference_cache.py` and `data/race_stints_store.py` load a whole `app_documents` document once and write it back whole, so a write from another process is overwritten. Examples: `scripts/backfill_predictions.py`, a VM job.
  - Give writes optimistic concurrency: re-read and compare the document's version or `updated_at` before writing; on conflict, merge per key (newest entry wins) and retry.
  - Remove the "restart after a backfill" rule: `PLAN.md` P0.3 Verify and the `STATUS.md` notes.
- **Accept:** a test writes from "another process" (a second store instance) between the running instance's read and write, and both updates survive; no regression in the existing store tests.
- **Verify:** pytest (100%), ruff, format, size.

### P0c.5 Deploy stack and scheduled jobs

- **Do:**
  - **`deploy/oracle/compose.yaml`:**
    - Services: `caddy`, `api` (image `ghcr.io/amurark3/f1-ai-api:${API_TAG}`, `env_file: /srv/f1ai/.env`), `postgres` (tuned for 6 GB: `shared_buffers=768MB`, `effective_cache_size=3GB`), and a `jobs` profile (same image, one-shot).
    - Volumes under `/srv/f1ai`.
    - Docker `json-file` log rotation.
    - Postgres published on `127.0.0.1:5432` only.
    - Health checks.
  - **`deploy/oracle/Caddyfile`:** `{$API_HOST}`, `reverse_proxy api:8000` (WebSocket works as-is), `encode zstd gzip`.
  - **`deploy/oracle/bootstrap.sh`** (idempotent, run once as root):
    - Docker Engine and the compose plugin.
    - A 2 GB swap file.
    - Format and mount the block volume at `/srv/f1ai` (fstab with `_netdev,nofail`).
    - iptables accept for 80 and 443, persisted.
    - unattended-upgrades.
    - `PasswordAuthentication no`.
    - A `deploy` user.
    - Install the systemd units.
  - **`deploy/oracle/deploy.sh`:** the only command the deploy key may run (`command=` in `authorized_keys`), which accepts only `deploy <sha>` or `ingest-rulebook`. It:
    1. Pulls the SHA tag.
    2. Records the previous tag.
    3. Runs `up -d`.
    4. Waits up to 120 s for `/api/ready`.
    5. On failure, restores the previous tag and exits non-zero.
  - **systemd units in `deploy/oracle/systemd/`:**
    - `f1ai-pu-ingest`: the same schedule as `ingest-power-units.yml` (`17 * * * 4,5,6,0,1` and `47 5 * * *` UTC), running `scripts.ingest_power_units --require-database`.
    - `f1ai-backup`: nightly `pg_dump -Fc` uploaded with the `oci` CLI under instance-principal auth.
    - `f1ai-restore-check`: weekly; restores the latest dump into a scratch database and compares row counts.
    - `f1ai-duckdns`: every 5 minutes.
  - **`.github/workflows/deploy-oracle.yml`:**
    1. Triggers on push to `main` (and `workflow_dispatch`).
    2. Skips when `vars.ORACLE_HOST` is empty.
    3. Builds on `ubuntu-24.04-arm` with `GIT_COMMIT` and pushes `ghcr.io/amurark3/f1-ai-api:{sha,latest}` (`packages: write`).
    4. SSHes `deploy <sha>`.
    5. When the push touched `backend/data/raw/**`, also SSHes `ingest-rulebook`, which replaces `ingest-rulebook.yml` after cutover.
- **Accept:**
  - `docker compose -f deploy/oracle/compose.yaml config` is valid.
  - `shellcheck` is clean on every script.
  - A local smoke run (the compose stack with a local `.env`; Caddy on `localhost` with an internal certificate) gives 200 on `/api/health/deep` and reaches `ready`.
  - `deploy.sh` rejects any other command.
  - A simulated failed health check rolls back.
- **Verify:** the commands above, plus `actionlint` on the workflow when it is installed.

### P0c.5d Promoted models deploy

- **Gap** (found in P0c.5):
  - `retrain.yml` merges the promoted model with `GITHUB_TOKEN`, and GitHub starts no workflow from such a push. So `deploy-oracle.yml` never ships a promoted model.
  - Render deployed on any push, so this worked before.
- **Do:** after its merge, `retrain.yml` dispatches the deploy (`gh workflow run deploy-oracle.yml --ref main`, `actions: write`). `workflow_dispatch` is exempt from the `GITHUB_TOKEN` rule. It is skipped when `vars.ORACLE_HOST` is empty, like the deploy job.
- **Accept:** actionlint is clean; the dispatch step runs only after a successful merge.
- **Verify:** actionlint (Docker image).

### P0c.6 Supabase → VM data migration

- **Do:**
  - `deploy/oracle/bin/migrate-from-supabase.sh [--dry-run] [--replace]`, run on the VM as `deploy`. As built (P0c.6, 2026-11-09): the source URL comes from the `SOURCE_DATABASE_URL` environment variable only (a URL argument would show in `ps`), the target is the stack's own Postgres, and `--replace` overwrites target tables that already hold rows.
    1. Requires the target schema to exist: the API has booted once, and the app creates the extension and its tables.
    2. Runs `pg_dump --data-only` of `app_documents`, `analysis_cache`, `chat_message`, `user_profile` and `rulebook_chunk` from the Supabase session pooler.
    3. Restores into the target in one transaction.
    4. Fixes sequences.
    5. Compares row counts per table and the `rulebook_chunk` vector dimension, and exits non-zero on any mismatch.
  - **Note from P0c.5:** only `app_documents` exists after the API boots. `analysis_cache`, `chat_message`, `user_profile` and `rulebook_chunk` are created on first use. So the script creates them first, by calling the app's own schema functions through the `jobs` container, not by copying the DDL.
  - `--dry-run` restores into a scratch database and drops it.
  - First check that no other table is created anywhere: `grep -rn "CREATE TABLE"`.
- **Accept:**
  - A rehearsal against a local source database seeded from fixtures passes, and a deliberate mismatch fails.
  - It never writes to the source; the source credentials are read from the environment, never from the command line.
- **Verify:** shellcheck; the rehearsal.

### P0c.7 Frontend: an always-on backend

- **Do:**
  - **`ServerWarmingGate`:** no `inert`, no scroll lock. A restart shows a small non-blocking notice ("Updating — back in a few seconds"), and the free-tier wording (`ServerWarmingOverlay.tsx:158`) goes.
  - **`app/lib/serverStatus.ts`:**
    - Only a failed probe counts as not ready. The rule that a first probe slower than 1.5 s means a cold server goes (`:36-41`).
    - The 60 s stale-tab recheck goes (`:42-43`, `:185-205`).
    - The back/forward-cache and online rechecks stay.
  - **`app/lib/server/backend.ts`:** the per-request budget shrinks from 10 s to 5 s; build budget unchanged. Retries stay for 502/503/504 (a restart); the 429 rationale and the comments are updated.
  - **`app/lib/server/champions.ts:108-116`:** prerender every season.
  - **Comments:** the Render text in `page.tsx`, `fetcher.ts` and `CommandCenterView.tsx` is updated.
  - **PLAN.md:** P3.5 rewritten to the 2026-11-08 Loading decision.
- **Accept:**
  - `serverStatus.ts` 100% (in the include list).
  - An e2e check: a page stays interactive while `/api/ready` reports warming.
  - No test for overlay code that P3.5 replaces (the no-coverage-for-rewrites rule).
- **As built (2026-11-09):** the gate became `ServerStatusNotice`, a sibling of the page in the root layout; `ServerWarmingOverlay` was deleted. The probe gives up after 2 minutes (deploy.sh's ready window). 429 is no longer retried (no rate limiter on the VM). Every champions season is prerendered. Details in the `STATUS.md` log.
- **Verify:** `npm run lint`, `typecheck`, `build`, `test:coverage`, `e2e`.

### P0c.8 Guide, part 2: cutover, rollback, operations; docs

- **Do:** finish `docs/deploy/ORACLE.md`.
  - **Cutover:**
    1. Run `bootstrap.sh`.
    2. Write `/srv/f1ai/.env` (chmod 600) from the variable list in `render.yaml`, plus the new `DATABASE_URL`, `ENABLE_LOCAL_MODELS=true`, `FASTF1_CACHE_DIR`, `HF_HOME`, `F1DB_PATH`, `API_HOST` and `DUCKDNS_*`.
    3. Set the GitHub variable `ORACLE_HOST` and the secret `ORACLE_SSH_KEY`.
    4. Run the first deploy.
    5. Freeze writes: disable the `ingest-power-units` and `ingest-rulebook` Actions, then suspend Render.
    6. Run the migration and check its counts.
    7. Run the chat-embedding backfill (`--apply`).
    8. In Vercel, set `NEXT_PUBLIC_API_URL` and `API_URL` to `https://<name>.duckdns.org`, set the function region nearest the Oracle region, and redeploy.
    9. Add a free UptimeRobot monitor on `/api/health/deep`.
    10. Run the smoke checklist.
  - **Rollback:** point Vercel's environment back at `https://f1-ai.onrender.com`, resume Render and re-enable the Actions. Supabase is untouched and keeps its data at least 90 days.
  - **Operations:**
    - Logs, restart and deploy-by-hand.
    - A `psql` shell over an SSH tunnel.
    - Restore from Object Storage.
    - Running scripts (`backfill_predictions`, rulebook ingest) with `docker compose run --rm jobs …`.
    - Rotating secrets.
    - Weekly checks: memory at or above 25%, $0, backups present.
  - **Docs:**
    - `DEPLOYMENT.md` is rewritten around the VM and points to the guide.
    - `README.md` loses its Render references.
    - P0b.1 drops the GitHub Actions refresher and diagnoses on the VM.
    - Close `.planning/todos/pending/2026-03-10-handle-render-cold-start-with-ui-loading-state.md`.
- **From P0c.5, the guide must also cover:**
  - **A separate deploy key** (`ssh-keygen -t ed25519 -N "" -f f1ai-deploy`). The public half is `bootstrap.sh`'s argument; the private half goes in the secret `ORACLE_SSH_KEY`.
  - **`ORACLE_KNOWN_HOSTS`** from `ssh-keyscan -t ed25519 <ORACLE_HOST>`, checked against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the VM.
  - **Make the GHCR package `f1-ai-api` public** after the first workflow run creates it (it starts private), then re-run that run.
  - **Fill `/srv/f1ai/.env` before the first deploy.** `bootstrap.sh` creates it from `env.example` (600, `deploy`). `POSTGRES_PASSWORD` comes from `openssl rand -hex 32`, and the same value goes in `DATABASE_URL`.
  - **Optional:** a UDP 443 security-list rule (HTTP/3).
  - **Operations:**
    - `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh …`, `systemctl list-timers 'f1ai-*'`, `journalctl -u f1ai-*`.
    - Re-run `bootstrap.sh` with no argument after unit changes.
    - Weekly `systemctl --failed`: nothing alerts on a failed timer.
    - Manual reboots for kernel updates.
    - `ALTER USER` when the Postgres password changes.
    - The first backup pulls the 1.36 GB OCI CLI image.
  - **What is only verifiable on the real VM** (the P0c.5 log lists it), as a first-boot checklist.
- **From P0c.6, cutover step 6 must say:**
  - **The command**, as `deploy` (`sudo -iu deploy`), with the URL typed into `read -rsp 'Supabase session pooler URL: ' SOURCE_DATABASE_URL; echo; export SOURCE_DATABASE_URL`, never pasted on a command line or into chat:
    - `/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --dry-run`, then
    - `/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --replace` (plain, without `--replace`, works only while the VM's five tables are empty; the dry run's last line says whether they are), then `unset SOURCE_DATABASE_URL`.
  - **The URL** is Supabase's **session pooler** string (Render's current `DATABASE_URL`, or Supabase → Connect → Session pooler): `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`, the password percent-encoded, `?sslmode=require` appended. Not the transaction pooler (port 6543; the script refuses it) or the direct `db.<ref>.supabase.co` host (IPv6-only).
  - **Run it only after step 5** (writes frozen). A mismatch table whose last line says "the source changed after it" means something still writes to Supabase.
  - **Expected output:** `dry run passed; would copy:` with one row count per table; then for the real run `verified: row counts equal the source's`, `migrated:` with the counts, and `api: ready`; exit 0. Any other ending is a failure that says why, and a failed restore is rolled back whole.
  - **Duration:** about 15 s for 35 MB (4,850 rulebook vectors) in the rehearsal, plus a few seconds for the API restart; allow 1–2 minutes on the VM. The API is stopped only for the restore and the check.
  - **Then step 7:** the chat-embedding backfill, since Render saved chat turns without vectors.
- **Accept:** every command in the guide matches the files from P0c.5–P0c.6; no secret values; no "Render" left in `DEPLOYMENT.md` except the rollback and history notes.
- **Verify:** Prettier; grep for `onrender` and `Render` in the docs touched.

### P0c.9 Decommission (after 7 stable days on the VM; goes into the next PR)

- **Do:**
  - Delete `render.yaml`, `keep-warm.yml`, `ingest-power-units.yml` and `ingest-rulebook.yml`.
  - Delete the dead `CHROMA_DB_PATH`, and the Supabase-only host branches in `store.py` and `ingest_power_units.py`.
  - The user deletes the GitHub secrets `DATABASE_URL` and `HF_TOKEN`, archives a final Supabase dump to Object Storage, deletes the Supabase project two weeks later, and deletes the Render service.
  - Update the memory notes about Supabase, Render, cold start and local runs.
- **Accept:** `grep -rni "onrender\|supabase" backend frontend .github` finds only history notes.
- **Verify:** the full backend and frontend gates.

- **PR:** `feat: always-on backend on Oracle Cloud` (P0c.1–P0c.8). P0c.9 goes into the next phase's PR.

#### P0b.1b Diagnose the Open-Meteo failures on the VM (blocked until the P0c cutover)

- **Do:**
  - After the cutover, with P0b.1a deployed, read the API's log on the VM: `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs api` (`docs/deploy/ORACLE.md` §4.2 on `feat/oracle-backend`). Sentry doesn't receive these warnings.
  - The suspects are 429s (Render's shared egress IPs were the likely trigger; the VM has its own IP) or the 8 s timeout. Write the cause in the log.
  - If the VM's calls still fail after the retry, record the evidence and propose the next step in the log.
- **Accept:** the production weather segment returns `ready` for the current round, and the hero's session cards show their forecasts.
