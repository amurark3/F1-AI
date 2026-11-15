"""Session-result loaders: qualifying, practice and sprint.

The three sources a race prediction starts from, plus the schedule checks
that gate them: whether the weekend has started (practice pace and the entry
list exist from FP1) and whether qualifying has run — which decides between the
qualifying-based and practice-based scoring paths.

None of them reads FastF1 (its 500-requests-an-hour cap, spent in minutes, is
why). The qualifying and sprint orders come from f1db once it holds the round,
else from OpenF1's ``session_result``; practice pace is the best lap of each
car in OpenF1's ``laps``. Every OpenF1 read of a finished session is served
from the read-through store (:mod:`app.data.openf1.session_store`) after its
first fetch. Each source reads only sessions that have ended, and a session
ends before the call that needs it: practice and the sprint precede qualifying,
and qualifying precedes the race.

Drivers and teams are printed under f1db's names ("Kimi Antonelli", "Racing
Bulls"); see :mod:`app.data.canonical_names`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from app.data.canonical_names import F1DB_READ_ERRORS
from app.data.f1db_sessions import KIND_QUALIFYING, KIND_RACE, TYPE_QUALIFYING, TYPE_SPRINT_RACE, session_classification
from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.session_laps import load_session_laps
from app.data.openf1.sessions import weekend_schedule
from app.data.predictions.openf1_qualifying import OPENF1_SOURCE, load_openf1_qualifying, order_row

logger = structlog.get_logger()

F1DB_SOURCE = "f1db"

# (year, round_num) -> qualifying results dict
_qualifying_cache: dict[tuple[int, int], Any] = {}

# (year, round_num) -> practice results dict (fallback)
_practice_cache: dict[tuple[int, int], Any] = {}

# (year, round_num) -> sprint results dict (empty if no sprint that weekend)
_sprint_cache: dict[tuple[int, int], list[dict]] = {}

# A practice session OpenF1 cannot give (not run, still live, unreachable) is skipped, not fatal.
_PRACTICE_ERRORS = (OpenF1UnavailableError, ValueError, KeyError, OSError)


def _f1db_order(year: int, round_num: int, result_type: str, kind: str) -> list[dict]:
    """A session's classified drivers from f1db, in order; ``[]`` until f1db holds the round or when it cannot be read."""
    try:
        entries = session_classification(year, round_num, result_type, kind)
    except F1DB_READ_ERRORS as exc:
        logger.warning(
            "predictions.f1db_session_unavailable", year=year, round=round_num, type=result_type, error=str(exc)
        )
        return []
    return [
        {"driver_code": e.driver_code, "driver_name": e.driver_name, "team": e.team, "position": e.position}
        for e in sorted((e for e in entries if e.position is not None), key=lambda e: e.position or 0)
    ]


def _load_qualifying(year: int, round_num: int) -> list[dict] | None:
    """Load qualifying results for a specific round.

    Returns a list of dicts with keys: driver_code, driver_name, team,
    position.  Returns None if qualifying data is unavailable.

    f1db's classification is read first (``docs/DATA_SOURCES.md``: it mirrors
    the FIA's), which holds a round only once it is complete. Until then
    OpenF1's ``session_result`` gives the order (:mod:`.openf1_qualifying`).
    An order neither source has yet is not cached, so the next compute retries
    instead of pinning the race to the practice proxy.
    """
    cache_key = (year, round_num)
    if cache_key in _qualifying_cache:
        return _qualifying_cache[cache_key]

    drivers, source = _f1db_order(year, round_num, TYPE_QUALIFYING, KIND_QUALIFYING), F1DB_SOURCE
    if not drivers:
        drivers, source = load_openf1_qualifying(year, round_num), OPENF1_SOURCE
    if not drivers:
        return None

    _qualifying_cache[cache_key] = drivers
    logger.info("predictions.qualifying_loaded", year=year, round=round_num, drivers=len(drivers), source=source)
    return drivers


def load_qualifying(year: int, round_num: int) -> list[dict] | None:
    """Public view of the cached qualifying classification for a round.

    Exposed for :mod:`app.services.race_grid`, which needs the qualifying order
    as a *provisional* stand-in during the window after a session has run and
    before f1db publishes that round's official grid sheet. Sharing this
    module's cache keeps the grid panel from reading f1db or OpenF1 again for
    data a prediction has usually already fetched.
    """
    return _load_qualifying(year, round_num)


def _practice_order(year: int, round_num: int, session_name: str) -> list[dict]:
    """One practice session's cars ranked by best lap (deleted laps struck off); ``[]`` when none set a time."""
    laps = load_session_laps(year, round_num, session_name)
    if laps is None:
        return []
    best: dict[int, float] = {}
    for lap in laps.laps:
        if lap.time is not None and not lap.deleted:
            best[lap.driver] = min(lap.time, best.get(lap.driver, lap.time))
    ranked = sorted(best, key=lambda number: (best[number], number))
    return [order_row(number, laps.drivers.get(number), pos, year) for pos, number in enumerate(ranked, 1)]


def _load_practice(year: int, round_num: int) -> list[dict] | None:
    """Load practice session best lap times as a qualifying proxy.

    Tries FP3 first, then FP2, then FP1.  Returns a list of dicts with
    driver_code, driver_name, team, position (ranked by best lap time).
    """
    cache_key = (year, round_num)
    if cache_key in _practice_cache:
        return _practice_cache[cache_key]

    for session_name in ("FP3", "FP2", "FP1"):
        try:
            drivers = _practice_order(year, round_num, session_name)
        except _PRACTICE_ERRORS as exc:
            logger.debug(
                "predictions.practice_session_failed", year=year, round=round_num, session=session_name, error=str(exc)
            )
            continue
        if drivers:
            _practice_cache[cache_key] = drivers
            logger.info(
                "predictions.practice_loaded",
                year=year,
                round=round_num,
                session=session_name,
                drivers=len(drivers),
                source=OPENF1_SOURCE,
            )
            return drivers

    logger.warning("predictions.no_practice_data", year=year, round=round_num)
    return None


def _has_sprint(year: int, round_num: int) -> bool | None:
    """Whether f1db's calendar gives the weekend a sprint; None when the calendar cannot be read."""
    try:
        return any(session.code == "S" for session in weekend_schedule(year, round_num))
    except F1DB_READ_ERRORS as exc:
        logger.warning("predictions.sprint_calendar_unavailable", year=year, round=round_num, error=str(exc))
        return None


def _load_sprint_result(year: int, round_num: int) -> list[dict]:
    """Load sprint race results for the current weekend, if one was held.

    Returns a list of dicts with keys: driver_code, driver_name, team, position.
    Returns an empty list when the weekend has no sprint, or its sprint has no
    classification yet. Sprint races exist at selected rounds from 2021 onward.

    f1db's sprint result is read first, then OpenF1's ``session_result`` for the
    sprint once it has ended. Only the absence of a sprint (per f1db's calendar)
    is cached as empty: a sprint that has not run, has not been classified, or
    whose calendar or feed failed to load is retried by the next compute.
    """
    cache_key = (year, round_num)
    if cache_key in _sprint_cache:
        return _sprint_cache[cache_key]

    drivers, source = _f1db_order(year, round_num, TYPE_SPRINT_RACE, KIND_RACE), F1DB_SOURCE
    if not drivers:
        has_sprint = _has_sprint(year, round_num)
        if has_sprint is False:
            _sprint_cache[cache_key] = []  # a conventional weekend stays one
            return []
        if has_sprint:
            drivers, source = load_openf1_qualifying(year, round_num, "S"), OPENF1_SOURCE

    if not drivers:
        logger.info("predictions.sprint_unclassified", year=year, round=round_num)
        return []

    _sprint_cache[cache_key] = drivers
    logger.info("predictions.sprint_loaded", year=year, round=round_num, drivers=len(drivers), source=source)
    return drivers


def _to_utc(value: object) -> datetime | None:
    """Coerce a calendar timestamp (naive UTC) to an aware UTC datetime, or None."""
    if value is None or pd.isna(value):
        return None
    dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _session_datetimes(event_row: pd.Series) -> list[datetime]:
    """Every scheduled session datetime on an event row, in UTC."""
    stamps = (_to_utc(event_row.get(f"Session{i}DateUtc")) for i in range(1, 6))
    return [stamp for stamp in stamps if stamp is not None]


def _weekend_has_started(event_row: pd.Series) -> bool:
    """Return True if any session of this event is in the past (UTC).

    The weekend entry list and the practice-pace proxy both become available
    from FP1, hours before qualifying, so neither may be gated on qualifying
    having run — doing so left the whole practice window with no session data
    and no real entry list.

    Falls back to True (attempt the load) whenever the schedule is unavailable.
    """
    stamps = _session_datetimes(event_row)
    if stamps:
        return min(stamps) <= datetime.now(UTC)

    race_dt = _to_utc(event_row.get("EventDate"))
    if race_dt is not None:
        # FP1 is ~2 days before the race on a conventional weekend.
        return (race_dt - timedelta(days=2)) <= datetime.now(UTC)

    return True


def _previous_started_round(schedule: pd.DataFrame | None, round_num: int) -> int | None:
    """The most recent round before ``round_num`` whose weekend has run.

    Not simply ``round_num - 1``: for a race weeks away the rounds in between
    have not run either, and asking FastF1 for their entry lists is a string of
    slow failing loads.
    """
    if schedule is None:
        return None
    earlier = schedule[schedule["RoundNumber"] < round_num]
    started = (int(row["RoundNumber"]) for _, row in earlier.iterrows() if _weekend_has_started(row))
    return max(started, default=None)


def _qualifying_has_occurred(event_row: pd.Series) -> bool:
    """Return True if this event's qualifying session is in the past (UTC).

    For an upcoming race weekend the qualifying session does not exist yet, so
    trying to load it from FastF1 just triggers a series of slow failing network
    calls (and can push a compute past its timeout). We gate the load on this
    check and go straight to the historical/pre-qualifying path when qualifying
    has not run.

    Falls back to True (attempt the load) whenever the schedule is unavailable,
    preserving the original behaviour.
    """
    now = datetime.now(UTC)

    # Prefer the explicit Qualifying session datetime.
    for i in range(1, 6):
        name = event_row.get(f"Session{i}")
        if isinstance(name, str) and name.strip().lower() == "qualifying":
            quali_dt = _to_utc(event_row.get(f"Session{i}DateUtc"))
            if quali_dt is not None:
                return quali_dt <= now

    # Fallback: assume qualifying is ~1 day before the race.
    race_dt = _to_utc(event_row.get("EventDate"))
    if race_dt is not None:
        return (race_dt - timedelta(days=1)) <= now

    return True  # unknown schedule → attempt the load (original behaviour)


def should_use_qualifying(event_row: Any, forced_pre_qualifying: bool) -> bool:
    """Whether this compute may load the qualifying result.

    A forced pre-qualifying call answers no even when the session has run —
    that is the whole point of the phase: it is the prediction the model would
    have made without the grid, kept alongside the one that uses it.
    """
    if forced_pre_qualifying:
        return False
    return _qualifying_has_occurred(event_row) if event_row is not None else True
