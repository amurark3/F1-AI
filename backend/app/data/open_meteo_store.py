"""The last good Open-Meteo hourly series per venue, kept across restarts in the document store.

On 6 Nov 2026 the live Open-Meteo call failed in production, the weekend's
session forecasts went blank, and the race-day card fell back on
OpenWeatherMap's current conditions: 5 % rain before a race Open-Meteo put at
~90 %. Keeping the last series that did arrive lets the weekend forecast stand
through an outage, labelled with when it was fetched rather than passed off as
current.

Each venue keeps Open-Meteo's own ``hourly`` block exactly as it arrived, so
the copy is read back through the same parser as the live feed and trusted no
more than it.

A write after a failed read is refused, for the reason
:mod:`app.data.race_stints_store` gives: it would upload a document holding
only this venue and silently drop every other one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading
import time
from typing import TYPE_CHECKING

import structlog

from app.data.store import DOCUMENT_OPEN_METEO_FORECASTS, document_store
from app.utils.f1_values import utc_isoformat

if TYPE_CHECKING:
    from app.data.store_types import WriteResult

logger = structlog.get_logger()

# Bump when an entry's fields change meaning, so a document written under the
# old meaning is ignored rather than served.
SCHEMA_VERSION = 1

# How long to wait before retrying a failed read. Without it one failed read
# would leave the store unusable for the life of the process.
RELOAD_BACKOFF_SECONDS = 30.0

# A series fetched longer ago than this cannot overlap any window Open-Meteo
# serves (92 days back, 15 ahead), so it is pruned on the next write.
KEEP_DAYS = 120

_clock = time.monotonic


@dataclass(frozen=True)
class StoredSeries:
    """A venue's last good answer: Open-Meteo's ``hourly`` block and when it arrived."""

    fetched_at: datetime
    hourly: dict


def venue_key(lat: float, lon: float) -> str:
    """A venue as the store names it: its coordinates to four places (about 11 m)."""
    return f"{lat:.4f},{lon:.4f}"


def _stamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _entry(value: object) -> StoredSeries | None:
    """A stored entry, or None when it is not the shape this schema writes."""
    if not isinstance(value, dict):
        return None
    fetched_at = _stamp(value.get("fetched_at"))
    hourly = value.get("hourly")
    if fetched_at is None or not isinstance(hourly, dict):
        return None
    return StoredSeries(fetched_at=fetched_at, hourly=hourly)


def _servable(value: object, now: datetime) -> bool:
    entry = _entry(value)
    return entry is not None and now - entry.fetched_at <= timedelta(days=KEEP_DAYS)


class ForecastStore:
    """The last good series by venue, read from the document store once per process."""

    def __init__(self) -> None:
        # None until a read succeeds; writes are refused until then.
        self._venues: dict[str, object] | None = None
        self._next_load_attempt = 0.0
        self._lock = threading.Lock()

    def _loaded(self) -> dict[str, object] | None:
        """The stored venues, reading the document on first use. Call under the lock."""
        if self._venues is not None:
            return self._venues
        now = _clock()
        if now < self._next_load_attempt:
            return None
        result = document_store.read(DOCUMENT_OPEN_METEO_FORECASTS)
        if not result.ok:
            self._next_load_attempt = now + RELOAD_BACKOFF_SECONDS
            logger.warning("open_meteo_store.read_failed", error=result.error)
            return None
        payload = result.payload or {}
        venues = payload.get("venues") if payload.get("version") == SCHEMA_VERSION else None
        self._venues = dict(venues) if isinstance(venues, dict) else {}
        return self._venues

    def last_good(self, venue: str) -> StoredSeries | None:
        """The venue's last good series, or None when none is stored or it cannot be read."""
        with self._lock:
            venues = self._loaded()
            value = None if venues is None else venues.get(venue)
        return _entry(value)

    def keep(self, venue: str, fetched_at: datetime, hourly: dict) -> None:
        """Keep a good series as the venue's last, pruning any too old to serve again."""
        with self._lock:
            venues = self._loaded()
            if venues is None:
                logger.warning("open_meteo_store.write_skipped", venue=venue, reason="unread")
                return
            entry = {"fetched_at": utc_isoformat(fetched_at), "hourly": hourly}
            kept = {key: value for key, value in venues.items() if _servable(value, fetched_at)}
            result = self._write({**kept, venue: entry})
        if not result.ok:
            logger.warning("open_meteo_store.write_failed", venue=venue, error=result.error)

    def _write(self, venues: dict[str, object]) -> WriteResult:
        """Replace the stored venues. Call under the lock, after a successful read."""
        # Held in memory either way: a failed Postgres write is retried by the
        # store on its next write, and this process can still serve it.
        self._venues = venues
        return document_store.write(DOCUMENT_OPEN_METEO_FORECASTS, {"version": SCHEMA_VERSION, "venues": venues})


forecast_store = ForecastStore()
