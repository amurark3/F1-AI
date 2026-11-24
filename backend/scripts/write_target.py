"""Shared guard for the scripts that write production documents.

Every run of a guarded script appends one line to ``RUN_LOG`` (time, script,
dry run or apply, store, database fingerprint), so "did someone run this against
prod?" has an answer later.

An ``--apply`` against Postgres goes ahead only when this process's database is
the one production reports in ``/api/ready`` (``store.database``, a short hash of
the Supabase project). On 2026-11-24 a regrade wrote to another app's Supabase
project because ``.env.production`` named it; this check refuses that write.
A file-store run (``DATABASE_URL`` unset) writes local files and is never refused.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

import requests

from app.data.store import BACKEND_POSTGRES, document_store

PRODUCTION_API_URL = os.getenv("PRODUCTION_API_URL", "https://f1-ai.onrender.com")
RUN_LOG = Path(os.getenv("SCRIPT_RUN_LOG", "data/backups/runs.log"))
# A Render free instance can take a minute to wake.
READY_TIMEOUT_SECONDS = 90


def production_database() -> str | None:
    """The database fingerprint production reports, or None when it can't be read."""
    try:
        response = requests.get(f"{PRODUCTION_API_URL}/api/ready", timeout=READY_TIMEOUT_SECONDS)
        return ((response.json() or {}).get("store") or {}).get("database")
    except (requests.RequestException, ValueError, AttributeError):
        return None


def _log_run(script: str, apply: bool, backend: str, database: str | None) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    mode = "apply" if apply else "dry-run"
    with RUN_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{stamp} {script} {mode} store={backend} database={database or '-'}\n")


def check_write_target(script: str, *, apply: bool) -> bool:
    """Log the run, then say whether it may write. Prints why when it may not."""
    health = document_store.health()
    _log_run(script, apply, health.backend, health.database)
    print(f"target: {health.backend} database {health.database or '-'}")
    if not apply or health.backend != BACKEND_POSTGRES:
        return True

    production = production_database()
    if production is not None and production == health.database:
        return True
    if production is None:
        print(
            f"ERROR: {PRODUCTION_API_URL}/api/ready did not report production's database "
            "(unreachable, or a build without the fingerprint); refusing to write."
        )
    else:
        print(
            f"ERROR: this DATABASE_URL is database {health.database}, but production uses "
            f"{production}; refusing to write. Fix .env.production."
        )
    return False
