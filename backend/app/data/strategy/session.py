"""Loading a race session and extracting stints and pit stops from it."""

from __future__ import annotations

import threading
from typing import Any

import fastf1
import pandas as pd
import structlog

logger = structlog.get_logger()

# Only allow ONE FastF1 session load at a time — they are heavy I/O and FastF1
# itself is not thread-safe for concurrent session loads. Same pattern as the
# prediction engine.
_fastf1_lock = threading.Lock()

# (year, round_num) -> race session laps/results data
_race_data_cache: dict[tuple[int, int], dict[str, Any]] = {}


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


def _load_race_data(year: int, round_num: int) -> dict[str, Any] | None:
    """Load race session with laps data for strategy analysis.

    Returns a dict with 'session', 'laps', 'results' keys, or None on failure.
    Caches the processed data.
    """
    cache_key = (year, round_num)
    if cache_key in _race_data_cache:
        return _race_data_cache[cache_key]

    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "R")
            session.load(telemetry=False, laps=True, weather=False)

        laps = session.laps
        results = session.results

        if laps is None or laps.empty:
            logger.warning("strategy.no_laps_data", year=year, round=round_num)
            return None

        data = {
            "session": session,
            "laps": laps,
            "results": results,
            "event_name": str(session.event.get("EventName", f"Round {round_num}")),
            "location": str(session.event.get("Location", "")),
        }

        _race_data_cache[cache_key] = data
        logger.info("strategy.race_data_loaded", year=year, round=round_num)
        return data

    except Exception as exc:
        logger.warning("strategy.race_data_error", year=year, round=round_num, error=str(exc))
        return None


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
