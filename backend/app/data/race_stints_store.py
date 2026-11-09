"""Resolved tyre stints, kept across restarts in the document store.

A finished race's stints never change, but both sources can be out of reach
when someone asks. OpenF1 refuses unauthenticated clients for the whole of
every live session, and FastF1 has no lap data on Render's always-cold cache.
Keeping resolved stints in the store (Supabase in production, a JSON file
locally) means a race shown once keeps showing through a live session, a rate
limit or a restart, and is fetched from OpenF1 once rather than per process.

Only non-empty answers are stored: "no stints" means "not yet" and is retried
by :mod:`app.data.race_stints`.

A write after a failed read is refused, for the reason
:mod:`app.data.circuit_reference_cache` gives: it would upload a document
holding only this process's races and silently drop every other one.

The document is read once per process, but other processes write it too, so a
write is a change applied to the latest stored document
(:meth:`~app.data.store_types.DocumentStore.update`), never this process's copy.
Merge rule: races another process stored are kept; stint rows carry no
timestamp, so for a race this process puts or drops, this process's write wins.
"""

from __future__ import annotations

from dataclasses import asdict
import threading
import time
from typing import TYPE_CHECKING

import structlog

from app.data.stint_model import Stint
from app.data.store import DOCUMENT_RACE_STINTS, document_store

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.data.store_types import UpdateResult

    RacesChange = Callable[[dict[str, list[dict]]], dict[str, list[dict]]]

logger = structlog.get_logger()

# Bump when a Stint field changes meaning, so a stored document written under
# the old meaning is ignored rather than served.
SCHEMA_VERSION = 1

# How long to wait before retrying a failed read. Without it one failed read
# would leave the store unusable for the life of the process.
RELOAD_BACKOFF_SECONDS = 30.0

_clock = time.monotonic


def _key(year: int, round_num: int) -> str:
    return f"{year}-{round_num}"


def _races_of(document: dict | None) -> dict[str, list[dict]]:
    """The races of a stored document; none from another schema version."""
    payload = document or {}
    races = payload.get("races") if payload.get("version") == SCHEMA_VERSION else None
    return dict(races) if isinstance(races, dict) else {}


class RaceStintsStore:
    """Stints by race, read from the document store once per process."""

    def __init__(self) -> None:
        # None until a read succeeds; writes are refused until then.
        self._races: dict[str, list[dict]] | None = None
        self._next_load_attempt = 0.0
        self._lock = threading.Lock()

    def _loaded(self) -> dict[str, list[dict]] | None:
        """The stored races, reading the document on first use. Call under the lock."""
        if self._races is not None:
            return self._races
        now = _clock()
        if now < self._next_load_attempt:
            return None
        result = document_store.read(DOCUMENT_RACE_STINTS)
        if not result.ok:
            self._next_load_attempt = now + RELOAD_BACKOFF_SECONDS
            logger.warning("race_stints_store.read_failed", error=result.error)
            return None
        self._races = _races_of(result.payload)
        return self._races

    def get(self, year: int, round_num: int) -> tuple[Stint, ...] | None:
        """The stored stints of a race, or ``None`` when none are stored."""
        with self._lock:
            races = self._loaded()
            rows = None if races is None else races.get(_key(year, round_num))
        if not rows:
            return None
        try:
            return tuple(Stint(**row) for row in rows)
        except TypeError as exc:
            logger.warning("race_stints_store.bad_row", year=year, round=round_num, error=str(exc))
            return None

    def put(self, year: int, round_num: int, stints: tuple[Stint, ...]) -> None:
        """Keep a race's stints. An empty answer is never kept."""
        if not stints:
            return
        key = _key(year, round_num)
        rows = [asdict(stint) for stint in stints]
        with self._lock:
            races = self._loaded()
            if races is None:
                logger.warning("race_stints_store.write_skipped", year=year, round=round_num, reason="unread")
                return
            result = self._update(races, lambda latest: {**latest, key: rows})
        if not result.ok:
            logger.warning("race_stints_store.write_failed", year=year, round=round_num, error=result.error)

    def drop(self, year: int, round_num: int) -> None:
        """Forget a race's stints: kept for a race that had not run, they came from another session."""
        dropped = _key(year, round_num)
        with self._lock:
            races = self._loaded()
            if races is None or dropped not in races:
                return
            result = self._update(races, lambda latest: {key: rows for key, rows in latest.items() if key != dropped})
        logger.warning("race_stints_store.dropped", year=year, round=round_num)
        if not result.ok:
            logger.warning("race_stints_store.write_failed", year=year, round=round_num, error=result.error)

    def _update(self, races: dict[str, list[dict]], change: RacesChange) -> UpdateResult:
        """Apply ``change`` to the latest stored races; ``races`` is this process's copy. Call under the lock."""
        result = document_store.update(
            DOCUMENT_RACE_STINTS,
            lambda document: {"version": SCHEMA_VERSION, "races": change(_races_of(document))},
        )
        # Stored: hold what is stored now, other processes' races included.
        # Not stored: hold the change in memory so this process still serves it;
        # a Postgres store has queued it and re-applies it on its next write.
        self._races = _races_of(result.payload) if result.ok else change(races)
        return result


stint_store = RaceStintsStore()
