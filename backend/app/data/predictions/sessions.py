"""Session-result loaders: qualifying, practice and sprint.

The three sources a race prediction starts from, plus the check for whether
qualifying has actually run yet — which decides between the qualifying-based
and practice-based scoring paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import fastf1
import pandas as pd
import structlog

from app.data.predictions.fastf1_lock import _fastf1_lock

logger = structlog.get_logger()

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


def _qualifying_has_occurred(event_row: pd.Series) -> bool:
    """Return True if this event's qualifying session is in the past (UTC).

    For an upcoming race weekend the qualifying and practice sessions do not
    exist yet, so trying to load them from FastF1 just triggers a series of slow
    failing network calls (and can push a compute past its timeout). We gate the
    session loads on this check and go straight to the historical/pre-qualifying
    path when the weekend has not run.

    Falls back to True (attempt the load) whenever the schedule is unavailable,
    preserving the original behaviour.
    """
    now = datetime.now(timezone.utc)

    def _to_utc(value: object) -> pd.Timestamp | None:
        if value is None or pd.isna(value):
            return None
        dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

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
        from datetime import timedelta

        return (race_dt - timedelta(days=1)) <= now

    return True  # unknown schedule → attempt the load (original behaviour)
