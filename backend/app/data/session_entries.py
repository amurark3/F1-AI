"""Weekend entry list resolved from FastF1 session results.

Who is racing is a *per-weekend* fact, not a season one. Drivers are withdrawn
for injury, illness or penalty and reserves take the seat, so a grid built from
the season championship table predicts drivers who are not at the track.

FastF1's ``session.results`` lists every driver the FIA entered for that
session — including one who set no lap — so the moment any session of the
weekend has timing data, that list is the authoritative entry list.

Before the weekend's first session runs there is no such data, and no source in
this stack knows the lineup. ``load_weekend_entry_list`` reports that as an
explicit "unavailable" rather than guessing, so callers fall back to a
provisional roster and label it as provisional.

Thread safety: FastF1 session loads are wrapped with ``_fastf1_lock``, the same
per-module pattern used by ``app.data.predictions`` and ``app.data.strategy``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import fastf1
import structlog

logger = structlog.get_logger()

_fastf1_lock = threading.Lock()

# Tried newest-first: the latest session that has run carries the most current
# lineup, so a driver withdrawn after FP1 is already absent from qualifying.
# Sprint-weekend sessions sit between the two, and a name that does not exist
# for a given weekend simply fails its load and is skipped.
ENTRY_LIST_SESSIONS: tuple[str, ...] = ("Q", "S", "SQ", "FP3", "FP2", "FP1")

# A resolved entry list is re-read periodically rather than pinned for the life
# of the process: a driver can withdraw between sessions, and the newer session
# is what should then be believed.
ENTRY_LIST_TTL_SECONDS = 1800.0

# An unavailable entry list must never be cached like a resolved one. Doing so
# would pin "the weekend has not started" for the whole process, so the entry
# list would still be missing hours after the cars ran.
ENTRY_LIST_RETRY_SECONDS = 300.0


@dataclass(frozen=True)
class EntryListDriver:
    """One driver entered for a race weekend."""

    code: str
    name: str
    team: str


@dataclass(frozen=True)
class WeekendEntryList:
    """The drivers entered for a weekend, and which session said so.

    ``session`` is ``None`` when no session of the weekend has produced timing
    data yet. That is a different state from an empty entry list and callers
    must treat it as "unknown", never as "nobody is racing".
    """

    entries: tuple[EntryListDriver, ...] = ()
    session: str | None = None

    @property
    def available(self) -> bool:
        return self.session is not None and bool(self.entries)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(entry.code for entry in self.entries)

    def by_code(self) -> dict[str, EntryListDriver]:
        return {entry.code: entry for entry in self.entries}


UNAVAILABLE = WeekendEntryList()


@dataclass(frozen=True)
class _CacheEntry:
    value: WeekendEntryList
    expires_at: float


_cache: dict[tuple[int, int], _CacheEntry] = {}
_cache_lock = threading.Lock()


def _entries_from_results(results) -> tuple[EntryListDriver, ...]:
    """Extract entered drivers from a FastF1 results frame.

    Every row is kept regardless of classification or lap time — a driver who
    crashed in Q1, sat out with a technical problem or was disqualified was
    still entered, and dropping them is what makes a grid incomplete.
    """
    if results is None or results.empty:
        return ()

    entries: list[EntryListDriver] = []
    seen: set[str] = set()
    for _, row in results.iterrows():
        code = str(row.get("Abbreviation", "") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        name = f"{row.get('FirstName', '') or ''} {row.get('LastName', '') or ''}".strip()
        entries.append(EntryListDriver(
            code=code,
            name=name or code,
            team=str(row.get("TeamName", "") or "").strip(),
        ))
    return tuple(entries)


def _load_from_session(year: int, round_num: int, session_name: str) -> WeekendEntryList:
    """Read one session's entry list, or ``UNAVAILABLE`` if it has not run."""
    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, session_name)
            session.load(laps=False, telemetry=False, weather=False, messages=False)
        entries = _entries_from_results(session.results)
    except Exception as exc:
        logger.debug(
            "entry_list.session_unavailable",
            year=year, round=round_num, session=session_name, error=str(exc),
        )
        return UNAVAILABLE

    if not entries:
        return UNAVAILABLE
    return WeekendEntryList(entries=entries, session=session_name)


def _cached(key: tuple[int, int]) -> WeekendEntryList | None:
    with _cache_lock:
        entry = _cache.get(key)
    if entry is None or time.monotonic() >= entry.expires_at:
        return None
    return entry.value


def _store(key: tuple[int, int], value: WeekendEntryList) -> None:
    ttl = ENTRY_LIST_TTL_SECONDS if value.available else ENTRY_LIST_RETRY_SECONDS
    with _cache_lock:
        _cache[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)


def load_weekend_entry_list(year: int, round_num: int) -> WeekendEntryList:
    """Return the drivers entered for ``round_num``, from the newest session run.

    Returns :data:`UNAVAILABLE` when no session of the weekend has timing data.
    Callers must not attempt this for a weekend that has not started: every
    session load would be a slow failing network call.
    """
    key = (year, round_num)
    cached = _cached(key)
    if cached is not None:
        return cached

    for session_name in ENTRY_LIST_SESSIONS:
        entry_list = _load_from_session(year, round_num, session_name)
        if entry_list.available:
            _store(key, entry_list)
            logger.info(
                "entry_list.loaded",
                year=year, round=round_num,
                session=session_name, drivers=len(entry_list.entries),
            )
            return entry_list

    _store(key, UNAVAILABLE)
    logger.info("entry_list.unavailable", year=year, round=round_num)
    return UNAVAILABLE


def reset_cache() -> None:
    """Drop every cached entry list. Used by tests and manual recomputes."""
    with _cache_lock:
        _cache.clear()
