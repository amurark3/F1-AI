"""Local f1db dataset source.

f1db (https://github.com/f1db/f1db, MIT) publishes the entire 1950–present F1
dataset as a single SQLite file. Using it locally avoids the rate-limited live
Ergast API entirely and lets us query all of F1 history with stdlib ``sqlite3``.

The database is downloaded once to ``data/f1db.db`` (gitignored) and queried
read-only. Bump ``F1DB_VERSION`` and re-run ``python -m app.data.f1db_source`` to
refresh to a newer release (which also pulls in new races of the current season).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import sqlite3
import zipfile

import requests
import structlog

logger = structlog.get_logger()

# Pinned f1db release. Bumping this + re-running refresh_f1db() updates all
# history including newly completed rounds of the in-progress season.
F1DB_VERSION = os.getenv("F1DB_VERSION", "v2026.10.0")
F1DB_RELEASES_API = "https://api.github.com/repos/f1db/f1db/releases/latest"
DB_PATH = Path(os.getenv("F1DB_PATH", "data/f1db.db"))
DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("F1DB_DOWNLOAD_TIMEOUT_SECONDS", "120"))


def sqlite_url_for(version: str) -> str:
    """Build the f1db SQLite download URL for a release tag."""
    return f"https://github.com/f1db/f1db/releases/download/{version}/f1db-sqlite.zip"


F1DB_SQLITE_URL = sqlite_url_for(F1DB_VERSION)


def latest_release_version() -> str:
    """Resolve the newest f1db release tag via the GitHub API.

    Uses ``GITHUB_TOKEN`` if present (higher rate limit in CI); falls back to the
    pinned ``F1DB_VERSION`` if the API is unreachable.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(F1DB_RELEASES_API, headers=headers, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        return str(response.json()["tag_name"])
    except Exception as exc:
        logger.warning("f1db.latest_version_failed", error=str(exc), fallback=F1DB_VERSION)
        return F1DB_VERSION


def refresh_f1db(url: str = F1DB_SQLITE_URL, dest: Path = DB_PATH) -> Path:
    """Download the f1db SQLite dump and extract it to ``dest`` (overwriting)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("f1db.download.start", url=url, dest=str(dest))

    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        db_member = next((n for n in archive.namelist() if n.endswith(".db")), None)
        if db_member is None:
            raise ValueError(f"No .db file found inside {url}")
        with archive.open(db_member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)

    logger.info("f1db.download.done", path=str(dest), bytes=dest.stat().st_size)
    return dest


def ensure_db() -> Path:
    """Return the path to the local f1db database, downloading it if missing."""
    if not DB_PATH.exists():
        logger.info("f1db.missing_downloading", path=str(DB_PATH))
        refresh_f1db()
    return DB_PATH


def connect() -> sqlite3.Connection:
    """Open a new read-only connection to the f1db database.

    Connections are cheap and short-lived; callers should use this via a ``with``
    block. The higher-level ``app.data.champions`` service caches computed results,
    so the database is touched only rarely.
    """
    ensure_db()
    uri = f"file:{DB_PATH.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    path = refresh_f1db()
    with connect() as c:
        (min_year,), (max_year,) = (
            c.execute("SELECT MIN(year) FROM season").fetchone(),
            c.execute("SELECT MAX(year) FROM season").fetchone(),
        )
