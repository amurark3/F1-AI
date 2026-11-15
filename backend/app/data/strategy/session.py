"""Loading a race session and extracting stints and pit stops from it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from app.data.f1db_calendar import season_schedule
from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.session_laps import SessionLaps, load_session_laps
from app.data.race_classification import race_classification
from app.data.race_stints import race_stints

if TYPE_CHECKING:
    from app.data.stint_model import Stint

logger = structlog.get_logger()

# (year, round_num) -> race laps/results data; only a race that was read is kept.
_race_data_cache: dict[tuple[int, int], dict[str, Any]] = {}

# Reads that fail without meaning the race has no data: f1db's calendar raises
# CalendarUnavailableError (a ValueError), the rest are the usual I/O.
_SOURCE_ERRORS = (OpenF1UnavailableError, ValueError, KeyError, OSError)


def _fmt_laptime(td: pd.Timedelta | None) -> str:
    """Format a pandas Timedelta to a clean lap time string like '1:15.432'."""
    if pd.isna(td):
        return "-"
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    return f"{seconds:.3f}"


def _calendar_event(year: int, round_num: int) -> tuple[str, str]:
    """The round's name and Location on f1db's calendar, the one the history matches past seasons on."""
    schedule = season_schedule(year)
    event = schedule[schedule["RoundNumber"] == round_num]
    if event.empty:
        return f"Round {round_num}", ""
    return str(event.iloc[0].get("EventName") or f"Round {round_num}"), str(event.iloc[0]["Location"])


def _laps_frame(session: SessionLaps, stints: tuple[Stint, ...]) -> pd.DataFrame:
    """OpenF1's laps in the shape the strategy maths reads: one row per lap, tagged with its stint."""
    by_driver: dict[str, list[Stint]] = {}
    for stint in stints:
        by_driver.setdefault(stint.driver_code, []).append(stint)

    rows = []
    for lap in session.laps:
        entry = session.drivers.get(lap.driver)
        if entry is None:
            continue
        stint = next((s for s in by_driver.get(entry.code, []) if s.start_lap <= lap.number <= s.end_lap), None)
        rows.append(
            {
                "Driver": entry.code,
                "LapNumber": float(lap.number),
                "Stint": None if stint is None else float(stint.stint),
                "Compound": None if stint is None else stint.compound,
                "LapTime": pd.NaT if lap.time is None else pd.to_timedelta(lap.time, unit="s"),
                "FreshTyre": None if stint is None else stint.fresh,
            }
        )
    return pd.DataFrame(rows, columns=["Driver", "LapNumber", "Stint", "Compound", "LapTime", "FreshTyre"])


def _results_frame(year: int, round_num: int) -> pd.DataFrame:
    """The classification as the Abbreviation/Position frame the maths reads."""
    rows = [
        {"Abbreviation": driver.driver_code, "Position": float(driver.position)}
        for driver in race_classification(year, round_num).drivers
        if driver.position is not None
    ]
    return pd.DataFrame(rows, columns=["Abbreviation", "Position"])


def _load_race_data(year: int, round_num: int) -> dict[str, Any] | None:
    """Load a race's laps, stints and classification for strategy analysis.

    Laps come from OpenF1 through the store, stints from ``race_stints`` and the
    order from the classification; no FastF1 request is made. Returns a dict with
    'laps', 'results', 'event_name' and 'location', or None when the race cannot
    be read. Only a race that was read is cached.
    """
    cache_key = (year, round_num)
    if cache_key in _race_data_cache:
        return _race_data_cache[cache_key]

    try:
        session = load_session_laps(year, round_num, "R")
        stints = race_stints(year, round_num) if session is not None else ()
        event_name, location = _calendar_event(year, round_num)
    except _SOURCE_ERRORS as exc:
        logger.warning("strategy.race_data_error", year=year, round=round_num, error=str(exc))
        return None

    if session is None or not session.laps or not stints:
        logger.warning("strategy.no_laps_data", year=year, round=round_num)
        return None

    data = {
        "laps": _laps_frame(session, stints),
        "results": _results_frame(year, round_num),
        "event_name": event_name,
        "location": location,
    }
    _race_data_cache[cache_key] = data
    logger.info("strategy.race_data_loaded", year=year, round=round_num)
    return data


# Laps needed at both ends of a stint before degradation is worth reporting.
_DEGRADATION_SAMPLE_LAPS = 3


def _stint_compound(stint_laps: pd.DataFrame) -> str:
    """Compound for a stint — the mode, since mixed rows do occur in the feed."""
    compounds = stint_laps["Compound"].dropna()
    if compounds.empty:
        return "UNKNOWN"
    mode = compounds.mode()
    return mode.iloc[0] if not mode.empty else str(compounds.iloc[0])


def _representative_lap_time(valid_times: pd.Series) -> str:
    """Average lap time for a stint, with pit in/out laps filtered out.

    Those laps run far slower than a green-flag lap, so an unfiltered mean
    describes the pit stop rather than the stint.
    """
    if valid_times.empty:
        return "-"
    median_time = valid_times.median()
    filtered = valid_times[valid_times < median_time * 1.5]
    return _fmt_laptime(filtered.mean() if not filtered.empty else valid_times.mean())


def _stint_degradation(stint_laps: pd.DataFrame, valid_times: pd.Series) -> float:
    """Seconds lost between the first and last laps of a stint.

    Returns 0.0 for stints too short to read a trend from.
    """
    if len(valid_times) < _DEGRADATION_SAMPLE_LAPS * 2:
        return 0.0

    sorted_by_lap = stint_laps.sort_values("LapNumber")
    valid_sorted = sorted_by_lap[sorted_by_lap["LapTime"].notna()]
    if len(valid_sorted) < _DEGRADATION_SAMPLE_LAPS * 2:
        return 0.0

    # Both means are over timed laps only, so neither can come back as NaT.
    opening = valid_sorted.head(_DEGRADATION_SAMPLE_LAPS)["LapTime"].mean()
    closing = valid_sorted.tail(_DEGRADATION_SAMPLE_LAPS)["LapTime"].mean()
    return round((closing - opening).total_seconds(), 2)


def _fresh_tyres(stint_laps: pd.DataFrame, stint_num: float) -> bool:
    """Whether the stint started on new tyres, inferred when the feed omits it."""
    fresh_tyre_col = stint_laps.get("FreshTyre")
    if fresh_tyre_col is not None and not fresh_tyre_col.dropna().empty:
        return bool(fresh_tyre_col.iloc[0])
    # First stint is usually not fresh (carried from quali); others are.
    return stint_num > 1


def _extract_stint_data(laps: pd.DataFrame, driver_code: str) -> list[dict]:
    """Extract stint summaries for a specific driver from laps DataFrame.

    Groups by (Stint, Compound) and computes:
      - Lap range (start to end)
      - Stint length
      - Average lap time
      - Degradation (delta between first 3 and last 3 laps)
      - Fresh tyres indicator
    """
    driver_laps = laps[laps["Driver"] == driver_code].copy()
    if driver_laps.empty:
        return []

    # Sort by lap number
    driver_laps = driver_laps.sort_values("LapNumber")

    stints = []
    # Stint numbers come from this frame, so every one of them selects rows.
    for stint_num in sorted(driver_laps["Stint"].dropna().unique()):
        stint_laps = driver_laps[driver_laps["Stint"] == stint_num].copy()

        # Lap range
        lap_numbers = stint_laps["LapNumber"].dropna()
        if lap_numbers.empty:
            continue
        start_lap = int(lap_numbers.min())
        end_lap = int(lap_numbers.max())

        valid_times = stint_laps["LapTime"].dropna()

        stints.append(
            {
                "stint": int(stint_num),
                "compound": _stint_compound(stint_laps).upper(),
                "laps": f"{start_lap}-{end_lap}",
                "stint_length": end_lap - start_lap + 1,
                "avg_lap_time": _representative_lap_time(valid_times),
                "degradation_sec": _stint_degradation(stint_laps, valid_times),
                "fresh_tyres": _fresh_tyres(stint_laps, stint_num),
            }
        )

    return stints


def _extract_pit_stops(laps: pd.DataFrame, _results: pd.DataFrame, driver_code: str) -> list[dict]:
    """Extract pit stop information for a driver.

    Identifies laps where the stint number changes and records the pit stop
    lap, plus position before and after if available.
    """
    driver_laps = laps[laps["Driver"] == driver_code].sort_values("LapNumber")
    if driver_laps.empty:
        return []

    pit_stops = []
    prev_stint = None

    for _, lap in driver_laps.iterrows():
        current_stint = lap.get("Stint")
        if pd.isna(current_stint):
            continue

        if prev_stint is not None and current_stint != prev_stint:
            lap_num = int(lap["LapNumber"])

            # Try to get position info around the pit stop
            position = lap.get("Position")
            pos_int = int(position) if pd.notna(position) else None

            pit_stops.append(
                {
                    "lap": lap_num,
                    "position_before": pos_int,
                    "position_after": pos_int,  # Approximate; exact in/out tracking requires more data
                }
            )

        prev_stint = current_stint

    return pit_stops
