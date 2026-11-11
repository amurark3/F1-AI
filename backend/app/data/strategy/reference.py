"""Which edition of a circuit the pre-race baseline plan is read from, and keeping the answer.

The Command Center plans an *upcoming* race, which has no laps of its own, so
its "Base race plan" is the latest same-circuit edition's measured strategy
(:mod:`app.data.strategy.edition_plan`, read by
:mod:`app.data.strategy.edition_sources`).

**The latest edition, from data that loads.** The search reads the planning
season's own edition once its race has been run, else the season before, and
so on back to 2023, OpenF1's first season. Until Nov 2026 it kept the first
edition whose FastF1 laps loaded; with F1's live-timing archive behind a login
since 15 Oct 2026, 2023-2025 no longer loaded on a cold cache and São Paulo
2026 (R20) was planned from 2022: the previous regulations and a sprint weekend.

**An edition that cannot be read now is retried, never passed over for good.**
OpenF1 refuses every request while a session is live and Jolpica publishes
stops hours after the flag. When a newer edition cannot be read, an older one
answers this request with the unread years named (``unread_years``), or none
does, and the answer is held for :data:`UNREAD_RETRY_SECONDS` only, never
stored. Only a search that read every edition it reached is persisted.

**Persisted answers** live in the durable circuit reference cache under (city,
planning season). Its schema version moved to 2 with this module, so the
FastF1-era entries (São Paulo 2026 → 2022) are never served again.

What :func:`circuit_strategy_reference` returns:

* the edition's plan (``source_year`` set) with ``unread_years``;
* ``{"source_year": None, "unread_years": [...]}`` when editions exist but none
  could be read right now;
* ``None`` when the circuit has no raced edition since :data:`OPENF1_FIRST_SEASON`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import fastf1
import pandas as pd
import structlog

from app.data.circuit_reference_cache import (
    CircuitReferenceCacheUnavailableError,
    circuit_reference_cache,
)
from app.data.strategy.edition_plan import Edition
from app.data.strategy.edition_sources import edition_reference
from app.utils.ttl_cache import TtlCache

logger = structlog.get_logger()

# OpenF1 publishes stints from the 2023 season on, so no earlier edition can be read.
OPENF1_FIRST_SEASON = 2023

# A race is only a usable reference once it has actually been run. Sessions are
# scheduled in UTC and a grand prix takes about two hours, so an edition is
# treated as complete this long after its scheduled start.
RACE_COMPLETE_AFTER_HOURS = 3

# How long an answer that left an edition unread is held before the sources are
# asked again: long enough to spare them on every page view, short enough to
# pick the edition up soon after a live session ends.
UNREAD_RETRY_SECONDS = 5 * 60


@dataclass(frozen=True)
class _Search:
    reference: dict | None
    unread_years: tuple[int, ...]


_unread: TtlCache[tuple[str, int], _Search] = TtlCache()


def circuit_strategy_reference(location: str, current_year: int) -> dict | None:
    """The baseline plan for a circuit, from its latest raced edition (see the module docstring).

    Args:
        location: Circuit location, e.g. ``"São Paulo, Brazil"`` or ``"São Paulo"``.
        current_year: The season being planned; editions are searched backwards
            from here (its own edition included, once its race has been run).
    """
    city = location.split(",", maxsplit=1)[0].strip() if location else ""
    if not city:
        return None

    cached = circuit_reference_cache.get(city, current_year)
    if cached is not None:
        return cached.reference
    key = (city.lower(), current_year)
    held = _unread.get(key)
    if held is not None:
        return held.reference

    search = _search_circuit_editions(city, current_year)
    source_year = (search.reference or {}).get("source_year")
    if search.unread_years:
        _unread.put(key, search, UNREAD_RETRY_SECONDS)
        logger.warning(
            "strategy.reference_unread",
            location=city,
            year=current_year,
            unread_years=list(search.unread_years),
            source_year=source_year,
        )
        return search.reference

    try:
        circuit_reference_cache.set(city, current_year, search.reference)
    except CircuitReferenceCacheUnavailableError as exc:
        # The reference is still valid for this request; only its durability is
        # lost, and the next process will recompute it. Say so rather than fail.
        logger.warning("strategy.reference_not_persisted", location=city, error=str(exc))

    logger.info("strategy.reference_ready", location=city, year=current_year, source_year=source_year)
    return search.reference


def _edition_race_finished(event: Any, now_utc: datetime) -> bool:
    """Whether this event's race has been run, so its results can exist.

    Reading an unraced (or in-progress) edition can only fail, and OpenF1 has
    answered a race's query with practice stints the night before it ran.
    """
    race_start = _scheduled_race_start(event)
    if race_start is None:
        return False
    return now_utc > race_start + timedelta(hours=RACE_COMPLETE_AFTER_HOURS)


def _scheduled_race_start(event: Any) -> datetime | None:
    """Return the event's scheduled race start (UTC, naive), if the row has one."""
    for index in range(1, 6):
        if str(event.get(f"Session{index}", "")).strip().lower() != "race":
            continue
        session_date = event.get(f"Session{index}DateUtc")
        if session_date is not None and not pd.isna(session_date):
            return pd.Timestamp(session_date).to_pydatetime()

    event_date = event.get("EventDate")
    if event_date is not None and not pd.isna(event_date):
        return pd.Timestamp(event_date).to_pydatetime()
    return None


def _matching_event(schedule: pd.DataFrame, city: str) -> Any | None:
    """Find the schedule row for a circuit city, exact match first."""
    exact = schedule[schedule["Location"] == city]
    if not exact.empty:
        return exact.iloc[0]

    for _, event in schedule.iterrows():
        if city.lower() in str(event.get("Location", "")).lower():
            return event
    return None


def _edition(event: Any, year: int) -> Edition:
    return Edition(year=year, round=int(event["RoundNumber"]), name=str(event.get("EventName") or "").strip())


def _search_circuit_editions(city: str, current_year: int) -> _Search:
    """Walk seasons back from the planning one to the first edition that reads."""
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    unread: list[int] = []

    for year in range(current_year, OPENF1_FIRST_SEASON - 1, -1):
        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as exc:
            # FastF1's schedule backend fails in more ways than it documents; a
            # season it cannot list may still hold this circuit, so it is unread.
            logger.warning("strategy.reference_schedule_error", year=year, error=str(exc))
            unread.append(year)
            continue

        event = _matching_event(schedule, city)
        if event is None:
            continue
        if not _edition_race_finished(event, now_utc):
            logger.debug("strategy.reference_edition_unraced", city=city, year=year)
            continue

        reference = edition_reference(_edition(event, year))
        if reference is not None:
            return _Search({**reference, "unread_years": list(unread)}, tuple(unread))
        unread.append(year)

    reference = {"source_year": None, "unread_years": list(unread)} if unread else None
    return _Search(reference, tuple(unread))
