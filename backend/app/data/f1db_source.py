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

The newest release is read from the release page's redirect, not the REST API.
That lesson cost five rounds: the API allows 60 unauthenticated requests an
hour per IP, Render's free tier shares its egress addresses, and every check
from production came back empty. The server fell through to the hardcoded
fallback (round 11) and, because a failed check resolved to "whatever is
installed", reported itself current on every check after. The redirect is not
metered against that limit; the API stays on as a backup. A failed check now
says so in its outcome, which ``/api/ready`` publishes as ``f1db_sync``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import zipfile

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
# Answers with a 302 to ``…/releases/tag/<tag>``. Not a REST API endpoint, so it
# does not count against the API rate limit that stranded production.
F1DB_LATEST_RELEASE_URL = "https://github.com/f1db/f1db/releases/latest"
RELEASE_TAG_MARKER = "/releases/tag/"
# A tag is spliced into the download URL and written to the version stamp, so
# anything that is not a plain tag (a path, a query string) is refused.
RELEASE_TAG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
DB_PATH = Path(os.getenv("F1DB_PATH", "data/f1db.db"))
# Which release the file on disk came from. Kept beside the database rather than
# in it so that reading it costs no SQLite connection.
VERSION_PATH = DB_PATH.with_name(DB_PATH.name + ".version")
DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("F1DB_DOWNLOAD_TIMEOUT_SECONDS", "120"))

# Floor on how often a release check may hit the GitHub API. The unauthenticated
# limit is 60 requests/hour per IP and Render's egress IPs are shared, so this
# guards against a caller that syncs more eagerly than intended.
F1DB_CHECK_INTERVAL_SECONDS = int(os.getenv("F1DB_CHECK_INTERVAL_SECONDS", "3600"))

# ``None`` means "no release check has run in this process yet". The sentinel is
# deliberately outside the number line: ``time.monotonic()`` counts from an
# arbitrary epoch — system boot on Linux — so a numeric ``0.0`` reads as
# "checked at boot". On a machine whose uptime is under the check interval that
# makes the very first sync of a process look recent and throttles it away,
# which on a container booting with a dataset already on disk is exactly the
# stale-dataset regression this module exists to prevent.
_last_check_at: float | None = None
_sync_lock = threading.Lock()


@dataclass(frozen=True)
class SyncOutcome:
    """What a freshness check did. Immutable — callers only report on it."""

    #: Release on disk after the check.
    version: str | None
    updated: bool
    reason: str
    #: Release the check resolved to track — the pin, or GitHub's newest.
    #: ``None`` when the lookup failed, which is the state worth alerting on.
    latest: str | None = None
    #: ISO-8601 UTC time of the check. Set when the outcome is recorded.
    checked_at: str | None = None

    @property
    def up_to_date(self) -> bool:
        """True only when the check succeeded and the disk holds that release."""
        return self.latest is not None and self.version == self.latest

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "latest": self.latest,
            "up_to_date": self.up_to_date,
            "updated": self.updated,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


# The last check that actually ran, for ``/api/ready``. Throttled calls never
# replace it: "checked recently" says nothing about whether the check worked.
_last_outcome: SyncOutcome | None = None


def last_sync_outcome() -> SyncOutcome | None:
    """The most recent release check of this process, or ``None`` before one."""
    return _last_outcome


def sqlite_url_for(version: str) -> str:
    """Build the f1db SQLite download URL for a release tag."""
    return f"https://github.com/f1db/f1db/releases/download/{version}/f1db-sqlite.zip"


def _valid_tag(tag: str) -> str:
    """``tag`` if it is a plain release tag, else ``""``."""
    return tag if RELEASE_TAG_PATTERN.fullmatch(tag) else ""


def _latest_from_redirect() -> str:
    """Newest tag from the release page's redirect, or ``""``."""
    try:
        response = requests.head(
            F1DB_LATEST_RELEASE_URL,
            allow_redirects=False,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("f1db.latest_redirect_failed", error=str(exc))
        return ""

    location = response.headers.get("Location", "")
    _, marker, tag = location.partition(RELEASE_TAG_MARKER)
    valid = _valid_tag(tag) if marker else ""
    if not valid:
        logger.warning(
            "f1db.latest_redirect_unusable",
            status=response.status_code,
            location=location,
        )
    return valid


def _latest_from_api() -> str:
    """Newest tag from the REST API, or ``""``.

    The backup lookup. Uses ``GITHUB_TOKEN`` if present (5,000 requests an hour
    instead of 60), which CI has and the Render service does not.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(F1DB_RELEASES_API, headers=headers, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        tag = str(response.json()["tag_name"])
    # ValueError covers a body that is not JSON; KeyError/TypeError one that is
    # JSON but not a release object.
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("f1db.latest_api_failed", error=str(exc))
        return ""

    valid = _valid_tag(tag)
    if not valid:
        logger.warning("f1db.latest_api_unusable", tag=tag)
    return valid


def latest_release_version() -> str:
    """Newest f1db release tag, or ``""`` when GitHub cannot say.

    Asks the release page's redirect first and the REST API only if that fails
    (see the module docstring for why). Returning empty rather than raising
    keeps an unreachable GitHub a non-event for serving: the caller decides what
    to fall back to, and a running server keeps the dataset it already has.
    """
    return _latest_from_redirect() or _latest_from_api()


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
    return _published_version() or installed_version() or FALLBACK_F1DB_VERSION


def _published_version() -> str:
    """The release to track: the pin if set, else GitHub's newest (``""`` if unknown)."""
    return F1DB_VERSION or latest_release_version()


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
    stamp = VERSION_PATH if destination == DB_PATH else destination.with_name(f"{destination.name}.version")
    staging = stamp.with_name(f"{stamp.name}.incoming")
    staging.write_text(version)
    os.replace(staging, stamp)


def _checked_recently() -> bool:
    """Whether a release check already ran inside the throttle window.

    False until the first check of the process completes, whatever the clock
    happens to read — a fresh process must reach GitHub once before any
    throttling applies. See ``_last_check_at``.
    """
    if _last_check_at is None:
        return False
    return (time.monotonic() - _last_check_at) < F1DB_CHECK_INTERVAL_SECONDS


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

    Every check that runs is recorded for :func:`last_sync_outcome`; throttled
    calls are not.
    """
    global _last_check_at, _last_outcome

    with _sync_lock:
        current = installed_version()
        # A server with no dataset is never throttled: it has nothing to serve.
        if current and not force and _checked_recently():
            return SyncOutcome(current, False, "checked recently")

        _last_check_at = time.monotonic()
        published = _published_version() or None
        wanted = published or current or FALLBACK_F1DB_VERSION
        outcome = _keep(current, published) if current == wanted else _download(wanted, current, published)
        _last_outcome = replace(outcome, checked_at=datetime.now(timezone.utc).isoformat())
        return _last_outcome


def _keep(current: str, published: str | None) -> SyncOutcome:
    """Nothing to download — but only a check that succeeded may call that current."""
    if published is None:
        logger.error("f1db.sync.check_failed", installed=current)
        return SyncOutcome(current, False, f"release check failed, kept {current}")
    logger.info("f1db.sync.current", version=current)
    return SyncOutcome(current, False, "already on the newest release", latest=published)


def _download(wanted: str, current: str | None, published: str | None) -> SyncOutcome:
    """Fetch ``wanted``; on failure keep ``current``, or raise if there is none."""
    try:
        refresh_f1db(wanted)
    except Exception as exc:
        logger.exception("f1db.sync.failed", target=wanted, installed=current, error=str(exc))
        if current:
            return SyncOutcome(current, False, f"download failed, kept {current}: {exc}", latest=published)
        raise

    logger.info("f1db.sync.updated", version=wanted, previous=current)
    if published is None:
        logger.error("f1db.sync.check_failed", installed=wanted)
        return SyncOutcome(wanted, True, f"release check failed, installed fallback {wanted}")
    return SyncOutcome(wanted, True, f"updated from {current or 'no dataset'} to {wanted}", latest=published)


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
