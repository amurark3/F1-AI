"""Local f1db dataset source.

f1db (https://github.com/f1db/f1db, MIT) publishes the entire 1950–present F1
dataset as a single SQLite file. Using it locally avoids the rate-limited live
Ergast API entirely and lets us query all of F1 history with stdlib ``sqlite3``.

Freshness is this module's job, not the caller's. ``sync_to_latest()`` resolves
the newest published release and re-downloads when the file on disk is older. It
runs on boot (the readiness warm-up) and on a slow background loop, so a
container that stays warm across a race weekend still picks up the new round.

That policy is deliberate and was learned the hard way. The dataset used to be
frozen at a version constant, and the only code that ever asked GitHub for a
newer release lived in the weekly *model-retraining* job — which refreshed a
copy on a CI runner, trained against it, and threw it away. Production therefore
re-downloaded the same pre-Hungary snapshot on every cold start and served
round-10 standings for four weeks. Live data freshness cannot hang off a machine
learning pipeline: those are different concerns with different cadences, and
only one of them is allowed to decide what a visitor sees.

``F1DB_VERSION`` remains available as an optional *pin*. Setting it freezes the
dataset at one release, which is what a reproducible training run or a
deterministic test wants. Leaving it unset — the default, and what production
runs — means "track the newest release".
"""

from __future__ import annotations

import io
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests
import structlog

logger = structlog.get_logger()

# Optional pin. Empty (the default) means "track the newest release".
F1DB_VERSION = os.getenv("F1DB_VERSION", "").strip()

# Last resort only: used when there is no dataset on disk *and* the GitHub API
# is unreachable, so a first boot behind a network failure still gets a database
# rather than none. Any successful release check supersedes it.
FALLBACK_F1DB_VERSION = "v2026.11.0"

F1DB_RELEASES_API = "https://api.github.com/repos/f1db/f1db/releases/latest"
DB_PATH = Path(os.getenv("F1DB_PATH", "data/f1db.db"))
# Which release the file on disk came from. Kept beside the database rather than
# in it so that reading it costs no SQLite connection.
VERSION_PATH = DB_PATH.with_name(DB_PATH.name + ".version")
DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("F1DB_DOWNLOAD_TIMEOUT_SECONDS", "120"))

# Floor on how often a release check may hit the GitHub API. The unauthenticated
# limit is 60 requests/hour per IP and Render's egress IPs are shared, so this
# guards against a caller that syncs more eagerly than intended.
F1DB_CHECK_INTERVAL_SECONDS = int(os.getenv("F1DB_CHECK_INTERVAL_SECONDS", "3600"))

_last_check_at = 0.0
_sync_lock = threading.Lock()


@dataclass(frozen=True)
class SyncOutcome:
    """What a freshness check did. Immutable — callers only report on it."""

    version: str | None
    updated: bool
    reason: str


def sqlite_url_for(version: str) -> str:
    """Build the f1db SQLite download URL for a release tag."""
    return f"https://github.com/f1db/f1db/releases/download/{version}/f1db-sqlite.zip"


def latest_release_version() -> str:
    """Newest f1db release tag, or ``""`` when the GitHub API is unreachable.

    Uses ``GITHUB_TOKEN`` if present (higher rate limit in CI). Returning empty
    rather than raising keeps an unreachable API a non-event: the caller decides
    what to fall back to, and a running server keeps the dataset it already has.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(
            F1DB_RELEASES_API, headers=headers, timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return str(response.json()["tag_name"])
    except Exception as exc:
        logger.warning("f1db.latest_version_failed", error=str(exc))
        return ""


def installed_version() -> str | None:
    """Release tag of the dataset on disk, or ``None`` if there isn't one.

    Also ``None`` for a database left by an older build that wrote no stamp — it
    is a dataset of unknown age, which is exactly the thing this module refuses
    to keep serving indefinitely.
    """
    if not DB_PATH.exists():
        return None
    try:
        return VERSION_PATH.read_text().strip() or None
    except OSError:
        return None


def target_version() -> str:
    """The release this process should be running.

    A pin wins outright. Otherwise the newest release, degrading to whatever is
    already installed and finally to ``FALLBACK_F1DB_VERSION`` — a GitHub outage
    must never take the dataset away from a server that has one.
    """
    if F1DB_VERSION:
        return F1DB_VERSION
    return latest_release_version() or installed_version() or FALLBACK_F1DB_VERSION


def refresh_f1db(version: str, dest: Path | None = None) -> Path:
    """Download release ``version`` and swap it into place atomically.

    The archive lands on a temporary file beside the destination and is moved
    with ``os.replace``. Writing the SQLite file in place would corrupt reads on
    every connection already holding it open, which is precisely what a refresh
    that runs while the server is serving traffic would otherwise do. Readers
    holding the old file keep a valid handle to it; new connections get the new
    one.
    """
    destination = dest or DB_PATH
    url = sqlite_url_for(version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.info("f1db.download.start", url=url, dest=str(destination))

    staging = destination.with_name(f"{destination.name}.incoming")
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            member = next((n for n in archive.namelist() if n.endswith(".db")), None)
            if member is None:
                raise ValueError(f"No .db file found inside {url}")
            with archive.open(member) as src, open(staging, "wb") as out:
                shutil.copyfileobj(src, out)

        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)

    # Stamped only after the swap succeeds. The reverse order could claim a
    # release the file on disk is not; this order can at worst cost one
    # redundant re-download, which is the harmless direction to fail in.
    _write_version_stamp(version, destination)

    logger.info(
        "f1db.download.done",
        path=str(destination),
        version=version,
        bytes=destination.stat().st_size,
    )
    return destination


def _write_version_stamp(version: str, destination: Path) -> None:
    stamp = (
        VERSION_PATH
        if destination == DB_PATH
        else destination.with_name(f"{destination.name}.version")
    )
    staging = stamp.with_name(f"{stamp.name}.incoming")
    staging.write_text(version)
    os.replace(staging, stamp)


def sync_to_latest(*, force: bool = False) -> SyncOutcome:
    """Bring the on-disk dataset up to the release it should be on.

    Safe to call repeatedly. Checks are throttled to
    ``F1DB_CHECK_INTERVAL_SECONDS`` unless forced, a check that finds nothing new
    touches no files, and a failed refresh leaves the previous release serving
    rather than taking the app down. The one case that does raise is a failure
    with no dataset at all on disk — there is nothing to degrade to, and the
    caller needs to know the server cannot answer data requests.

    The lock serialises refreshes so two callers cannot download at once. It is
    deliberately not held by ``connect()``/``ensure_db()``, so a refresh never
    blocks request serving.
    """
    global _last_check_at

    with _sync_lock:
        current = installed_version()
        elapsed = time.monotonic() - _last_check_at
        # A server with no dataset is never throttled: it has nothing to serve.
        if current and not force and elapsed < F1DB_CHECK_INTERVAL_SECONDS:
            return SyncOutcome(current, False, "checked recently")

        _last_check_at = time.monotonic()
        wanted = target_version()
        if current == wanted:
            logger.info("f1db.sync.current", version=current)
            return SyncOutcome(current, False, "already on the newest release")

        try:
            refresh_f1db(wanted)
        except Exception as exc:
            logger.error("f1db.sync.failed", target=wanted, installed=current, error=str(exc))
            if current:
                return SyncOutcome(current, False, f"download failed, kept {current}: {exc}")
            raise

        logger.info("f1db.sync.updated", version=wanted, previous=current)
        return SyncOutcome(wanted, True, f"updated from {current or 'no dataset'} to {wanted}")


def ensure_db() -> Path:
    """Return the path to the local f1db database, downloading it if missing.

    Deliberately does no release check: this sits on the ``connect()`` hot path,
    where a network round-trip would be paid by a request. Keeping the dataset
    current is ``sync_to_latest()``'s job.
    """
    if not DB_PATH.exists():
        logger.info("f1db.missing_downloading", path=str(DB_PATH))
        refresh_f1db(target_version())
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
    outcome = sync_to_latest(force=True)
    with connect() as c:
        (min_year,), (max_year,) = (
            c.execute("SELECT MIN(year) FROM season").fetchone(),
            c.execute("SELECT MAX(year) FROM season").fetchone(),
        )
    print(f"f1db {outcome.version} at {DB_PATH} — {outcome.reason}")
    print(f"seasons {min_year}–{max_year}")
