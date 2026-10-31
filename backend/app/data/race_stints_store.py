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
"""

from __future__ import annotations

from dataclasses import asdict
import threading
import time

import structlog

from app.data.stint_model import Stint
from app.data.store import DOCUMENT_RACE_STINTS, document_store

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
        payload = result.payload or {}
        races = payload.get("races") if payload.get("version") == SCHEMA_VERSION else None
        self._races = dict(races) if isinstance(races, dict) else {}
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
        with self._lock:
            races = self._loaded()
            if races is None:
                logger.warning("race_stints_store.write_skipped", year=year, round=round_num, reason="unread")
                return
            updated = {**races, _key(year, round_num): [asdict(stint) for stint in stints]}
            # Held in memory either way: a failed Postgres write is retried by
            # the store on its next write, and this process can still serve it.
            self._races = updated
            result = document_store.write(DOCUMENT_RACE_STINTS, {"version": SCHEMA_VERSION, "races": updated})
        if not result.ok:
            logger.warning("race_stints_store.write_failed", year=year, round=round_num, error=result.error)


stint_store = RaceStintsStore()
