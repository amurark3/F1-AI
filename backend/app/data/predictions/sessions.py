"""Session-result loaders: qualifying, practice and sprint.

The three sources a race prediction starts from, plus the schedule checks
that gate them: whether the weekend has started (practice pace and the entry
list exist from FP1) and whether qualifying has run — which decides between the
qualifying-based and practice-based scoring paths.

Drivers and teams are printed under f1db's names ("Kimi Antonelli", "Racing
Bulls"), not FastF1's ("Andrea Kimi Antonelli", "RB F1 Team"); the code stays
the feed's. See :mod:`app.data.canonical_names`. The qualifying order is read
from OpenF1 before FastF1 (:mod:`app.data.predictions.openf1_qualifying`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import fastf1
import pandas as pd
import structlog

from app.data.canonical_names import (
    CODE_UNRESOLVED,
    driver_identity,
    fastf1_driver,
    feed_code,
    feed_number,
    feed_text,
    team_display_name,
)
from app.data.predictions.openf1_qualifying import OPENF1_SOURCE, load_openf1_qualifying
from app.utils.fastf1_lock import FASTF1_LOCK

logger = structlog.get_logger()

# Aliased to the process-wide lock: a per-module lock does not serialise
# against the other modules sharing FastF1's SQLite cache.
_fastf1_lock = FASTF1_LOCK

# (year, round_num) -> qualifying results dict
_qualifying_cache: dict[tuple[int, int], Any] = {}

# (year, round_num) -> practice results dict (fallback)
_practice_cache: dict[tuple[int, int], Any] = {}

# (year, round_num) -> sprint results dict (empty if no sprint that weekend)
_sprint_cache: dict[tuple[int, int], list[dict]] = {}


def _fastf1_names(row: pd.Series, code: str, year: int) -> dict[str, str]:
    """A FastF1 row's driver and team as printed: f1db's names, else FastF1's words, else the code."""
    feed_name = " ".join(part for part in (feed_text(row.get("FirstName")), feed_text(row.get("LastName"))) if part)
    # The row's own cell, not ``code``: a missing abbreviation is NaN, which the resolver reads as no code.
    driver = driver_identity(year, code=row.get("Abbreviation", code), number=row.get("DriverNumber"), name=feed_name)
    return {"driver_name": driver.name or code, "team": team_display_name(year, row.get("TeamName"))}


def _classified_row(row: pd.Series, position: int, year: int) -> dict:
    """One classified driver, under FastF1's code, else f1db's.

    FastF1 sends some debutants and stand-ins with no abbreviation: Câmara, P13
    in São Paulo qualifying (2026 R20), came through as NaN, which ``str()``
    turned into the code ``nan``. The grid then dropped him as not entered and
    put him at the back. f1db names such a driver by car number or name once it has
    published a round they drove. Until then no source has the code, so the row
    keeps its place with an empty code, its car number and
    :data:`CODE_UNRESOLVED`, and the grid matches the car on the entry list.
    """
    driver = fastf1_driver(year, row)
    code = feed_code(row.get("Abbreviation")) or driver.code
    entry = {
        "driver_code": code or "",
        "driver_name": driver.name or code or "",
        "team": team_display_name(year, row.get("TeamName")),
        "position": position,
    }
    if code:
        return entry
    number = feed_number(row.get("DriverNumber"))
    logger.warning("predictions.driver_code_unresolved", year=year, number=number, name=driver.name, position=position)
    return {**entry, CODE_UNRESOLVED: True, "driver_number": number}


def _classified_order(results: pd.DataFrame | None, year: int) -> list[dict]:
    """A session's classification as driver dicts, in finishing order.

    A driver without a position (no time set, retired, or a session FastF1 has
    not classified yet) is left out rather than coerced to P0, which would put
    them first. A driver without a code keeps their position (see
    :func:`_classified_row`).
    """
    if results is None or results.empty:
        return []

    return [
        _classified_row(row, int(row["Position"]), year)
        for _, row in results.sort_values("Position").iterrows()
        # covers None and the NaN pandas uses for a missing position
        if not pd.isna(row.get("Position"))
    ]


def _fastf1_qualifying(year: int, round_num: int) -> list[dict] | None:
    """The qualifying order FastF1 can build: Jolpica's classification, else one derived from laps.

    Laps and race control messages are loaded because the Ergast mirror
    publishes a session's classification hours (sometimes days) after it ends.
    Until then FastF1 has only the driver list, and derives positions from lap
    times — striking off laps race control deleted — which it can only do with
    both loaded.
    """
    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "Q")
            session.load(telemetry=False, laps=True, weather=False, messages=True)
    except Exception as exc:
        # Includes FastF1's own hourly request cap ("any API: 500 calls/h").
        logger.warning("predictions.qualifying_unavailable", year=year, round=round_num, error=str(exc))
        return None

    drivers = _classified_order(session.results, year)
    if not drivers:
        logger.warning("predictions.qualifying_unclassified", year=year, round=round_num)
        return None
    return drivers


def _load_qualifying(year: int, round_num: int) -> list[dict] | None:
    """Load qualifying results for a specific round.

    Returns a list of dicts with keys: driver_code, driver_name, team,
    position.  Returns None if qualifying data is unavailable.

    OpenF1's ``session_result`` is read first (``docs/DATA_SOURCES.md``: the
    classification's first source once the session has run), then FastF1. OpenF1
    is outside FastF1's hourly request cap, which a booting production process
    spends within minutes; with FastF1 alone, R20's post-qualifying recompute of
    2026-11-11 had no order and was refused (:mod:`.openf1_qualifying`). An order
    neither source has yet is not cached, so the next compute retries instead of
    pinning the race to the practice proxy.
    """
    cache_key = (year, round_num)
    if cache_key in _qualifying_cache:
        return _qualifying_cache[cache_key]

    drivers, source = load_openf1_qualifying(year, round_num), OPENF1_SOURCE
    if not drivers:
        drivers, source = _fastf1_qualifying(year, round_num), "fastf1"
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
    module's cache keeps the grid panel from reading OpenF1 or FastF1 again for
    data a prediction has usually already fetched.
    """
    return _load_qualifying(year, round_num)


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
            with _fastf1_lock:
                session = fastf1.get_session(year, round_num, session_name)
                session.load(telemetry=False, laps=True, weather=False)

            laps = session.laps
            if laps is None or laps.empty:
                continue

            # Get best lap time per driver
            best_laps = laps.groupby("Driver")["LapTime"].min().dropna().sort_values()
            if best_laps.empty:
                continue

            drivers = [
                _practice_row(session.results, str(driver_code), pos, year)
                for pos, driver_code in enumerate(best_laps.index, 1)
            ]

            _practice_cache[cache_key] = drivers
            logger.info(
                "predictions.practice_loaded",
                year=year,
                round=round_num,
                session=session_name,
                drivers=len(drivers),
            )
            return drivers

        except Exception as exc:
            logger.debug(
                "predictions.practice_session_failed",
                year=year,
                round=round_num,
                session=session_name,
                error=str(exc),
            )
            continue

    logger.warning("predictions.no_practice_data", year=year, round=round_num)
    return None


def _practice_row(results: pd.DataFrame, driver_code: str, position: int, year: int) -> dict:
    """A practice pace rank, named from the session results.

    A Friday rookie can run laps without a results row; f1db still names them
    by their code, and only a code it does not know is printed as the code.
    """
    matches = results[results["Abbreviation"] == driver_code]
    row = matches.iloc[0] if not matches.empty else pd.Series(dtype=object)
    return {"driver_code": driver_code, **_fastf1_names(row, driver_code, year), "position": position}


def _sprint_session(year: int, round_num: int) -> Any | None:
    """The weekend's sprint session, or None when the weekend has no sprint.

    FastF1 answers a session identifier the event does not have with
    ValueError. Anything else (the schedule fetch failing, say) propagates, so
    an outage is not mistaken for a conventional weekend.
    """
    try:
        return fastf1.get_session(year, round_num, "S")
    except ValueError:
        return None


def _load_sprint_result(year: int, round_num: int) -> list[dict]:
    """Load sprint race results for the current weekend, if one was held.

    Returns a list of dicts with keys: driver_code, driver_name, team, position.
    Returns an empty list when the weekend has no sprint, or its sprint has no
    classification yet. Sprint races exist at selected rounds from 2021 onward.

    Laps and race control messages are loaded for the same reason as
    qualifying: the Ergast mirror publishes the sprint classification hours
    after it ends, and until then FastF1 derives it from lap timing. Only the
    absence of a sprint is cached as empty — a sprint that has not run, has not
    been classified, or failed to load is retried by the next compute.
    """
    cache_key = (year, round_num)
    if cache_key in _sprint_cache:
        return _sprint_cache[cache_key]

    try:
        with _fastf1_lock:
            session = _sprint_session(year, round_num)
            if session is None:
                _sprint_cache[cache_key] = []  # a conventional weekend stays one
                return []
            session.load(telemetry=False, laps=True, weather=False, messages=True)
        drivers = _classified_order(session.results, year)
    except Exception as exc:
        logger.warning("predictions.sprint_unavailable", year=year, round=round_num, error=str(exc))
        return []

    if not drivers:
        logger.info("predictions.sprint_unclassified", year=year, round=round_num)
        return []

    _sprint_cache[cache_key] = drivers
    logger.info("predictions.sprint_loaded", year=year, round=round_num, drivers=len(drivers))
    return drivers


def _to_utc(value: object) -> datetime | None:
    """Coerce a FastF1 schedule timestamp to an aware UTC datetime, or None."""
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
