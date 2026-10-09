"""Session-result loaders: qualifying, practice and sprint.

The three sources a race prediction starts from, plus the schedule checks
that gate them: whether the weekend has started (practice pace and the entry
list exist from FP1) and whether qualifying has run — which decides between the
qualifying-based and practice-based scoring paths.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import fastf1
import pandas as pd
import structlog

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


def _load_qualifying(year: int, round_num: int) -> list[dict] | None:
    """Load qualifying results for a specific round.

    Returns a list of dicts with keys: driver_code, driver_name, team,
    position.  Returns None if qualifying data is unavailable.
    """
    cache_key = (year, round_num)
    if cache_key in _qualifying_cache:
        return _qualifying_cache[cache_key]

    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "Q")
            session.load(telemetry=False, laps=False, weather=False)

        results = session.results
        if results is None or results.empty:
            return None

        drivers = []
        for _, row in results.sort_values("Position").iterrows():
            pos = row.get("Position")
            if pd.isna(pos):  # covers None and the NaN pandas uses for a missing position
                continue
            drivers.append(
                {
                    "driver_code": str(row.get("Abbreviation", "")),
                    "driver_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                    "team": str(row.get("TeamName", "")),
                    "position": int(pos),
                }
            )

        _qualifying_cache[cache_key] = drivers
        logger.info("predictions.qualifying_loaded", year=year, round=round_num, drivers=len(drivers))
        return drivers

    except Exception as exc:
        logger.warning("predictions.qualifying_unavailable", year=year, round=round_num, error=str(exc))
        return None


def load_qualifying(year: int, round_num: int) -> list[dict] | None:
    """Public view of the cached qualifying classification for a round.

    Exposed for :mod:`app.services.race_grid`, which needs the qualifying order
    as a *provisional* stand-in during the window after a session has run and
    before f1db publishes that round's official grid sheet. Sharing this
    module's cache keeps the grid panel from triggering a second FastF1 session
    load for data a prediction has usually already fetched.
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

            drivers = []
            for pos, (driver_code, _lap_time) in enumerate(best_laps.items(), 1):
                # Try to get full name/team from session results
                driver_info = session.results[session.results["Abbreviation"] == driver_code]
                if not driver_info.empty:
                    row = driver_info.iloc[0]
                    name = f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()
                    team = str(row.get("TeamName", ""))
                else:
                    name = driver_code
                    team = ""

                drivers.append(
                    {
                        "driver_code": str(driver_code),
                        "driver_name": name,
                        "team": team,
                        "position": pos,
                    }
                )

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


def _load_sprint_result(year: int, round_num: int) -> list[dict]:
    """Load sprint race results for the current weekend, if one was held.

    Returns a list of dicts with keys: driver_code, driver_name, team, position.
    Returns an empty list when no sprint was held that weekend.
    Sprint races exist at selected rounds from 2021 onward.
    """
    cache_key = (year, round_num)
    if cache_key in _sprint_cache:
        return _sprint_cache[cache_key]

    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "S")
            session.load(telemetry=False, laps=False, weather=False)

        results = session.results
        if results is None or results.empty:
            _sprint_cache[cache_key] = []
            return []

        drivers = []
        for _, row in results.sort_values("Position").iterrows():
            pos = row.get("Position")
            if pd.isna(pos):  # covers None and the NaN pandas uses for a missing position
                continue
            drivers.append(
                {
                    "driver_code": str(row.get("Abbreviation", "")),
                    "driver_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                    "team": str(row.get("TeamName", "")),
                    "position": int(pos),
                }
            )

        _sprint_cache[cache_key] = drivers
        logger.info("predictions.sprint_loaded", year=year, round=round_num, drivers=len(drivers))
        return drivers

    except Exception:
        # No sprint session this weekend — not an error
        _sprint_cache[cache_key] = []
        return []


def _to_utc(value: object) -> datetime | None:
    """Coerce a FastF1 schedule timestamp to an aware UTC datetime, or None."""
    if value is None or pd.isna(value):
        return None
    dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


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
        return min(stamps) <= datetime.now(timezone.utc)

    race_dt = _to_utc(event_row.get("EventDate"))
    if race_dt is not None:
        # FP1 is ~2 days before the race on a conventional weekend.
        return (race_dt - timedelta(days=2)) <= datetime.now(timezone.utc)

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
    now = datetime.now(timezone.utc)

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
