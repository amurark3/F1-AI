"""
Pit Strategy Analysis Engine
=============================
Computes pit strategy breakdowns for any driver or circuit overview using
FastF1 session data.  Includes:

  - Current race stint data (compound, lap ranges, degradation curves)
  - Historical strategy data from last 3 editions of the circuit
  - Undercut/overcut analysis between adjacent drivers
  - Safety car probability from circuit history

Thread safety: All FastF1 session loads are wrapped with ``_fastf1_lock``
to prevent data corruption from concurrent loads.
"""

import threading
import time
from collections import Counter
from typing import Any

import fastf1
import pandas as pd
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Thread safety — same pattern as predictions.py
# ---------------------------------------------------------------------------
_fastf1_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory caches
# ---------------------------------------------------------------------------
# (year, round_num) -> race session laps/results data
_race_data_cache: dict[tuple[int, int], dict[str, Any]] = {}

# (circuit_key, year_range_key) -> historical strategy summaries
_historical_cache: dict[str, Any] = {}

# (circuit_key,) -> safety car stats
_safety_car_cache: dict[str, dict] = {}


# ===================================================================
# FastF1 data loading helpers
# ===================================================================

def _fmt_laptime(td) -> str:
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
    for stint_num in sorted(driver_laps["Stint"].dropna().unique()):
        stint_laps = driver_laps[driver_laps["Stint"] == stint_num].copy()
        if stint_laps.empty:
            continue

        # Get compound — take mode (most frequent) in case of mixed data
        compounds = stint_laps["Compound"].dropna()
        if compounds.empty:
            compound = "UNKNOWN"
        else:
            compound = compounds.mode().iloc[0] if not compounds.mode().empty else str(compounds.iloc[0])

        # Lap range
        lap_numbers = stint_laps["LapNumber"].dropna()
        if lap_numbers.empty:
            continue
        start_lap = int(lap_numbers.min())
        end_lap = int(lap_numbers.max())
        stint_length = end_lap - start_lap + 1

        # Average lap time (exclude outliers: pit in/out laps often have extreme times)
        valid_times = stint_laps["LapTime"].dropna()
        if not valid_times.empty:
            # Filter out laps > 2x the median (pit stop laps)
            median_time = valid_times.median()
            filtered = valid_times[valid_times < median_time * 1.5]
            if not filtered.empty:
                avg_time = filtered.mean()
            else:
                avg_time = valid_times.mean()
            avg_time_str = _fmt_laptime(avg_time)
        else:
            avg_time_str = "-"

        # Degradation: compare first 3 laps vs last 3 laps average
        degradation_sec = 0.0
        if len(valid_times) >= 6:
            sorted_by_lap = stint_laps.sort_values("LapNumber")
            valid_mask = sorted_by_lap["LapTime"].notna()
            valid_sorted = sorted_by_lap[valid_mask]

            if len(valid_sorted) >= 6:
                first_3 = valid_sorted.head(3)["LapTime"]
                last_3 = valid_sorted.tail(3)["LapTime"]

                # Filter out pit stop outliers
                first_3_mean = first_3.mean()
                last_3_mean = last_3.mean()

                if pd.notna(first_3_mean) and pd.notna(last_3_mean):
                    degradation_sec = round(
                        (last_3_mean - first_3_mean).total_seconds(), 2
                    )

        # Fresh tyres
        fresh_tyre_col = stint_laps.get("FreshTyre")
        if fresh_tyre_col is not None and not fresh_tyre_col.dropna().empty:
            fresh_tyres = bool(fresh_tyre_col.iloc[0])
        else:
            # First stint is usually not fresh (carried from quali); others are
            fresh_tyres = stint_num > 1

        stints.append({
            "stint": int(stint_num),
            "compound": compound.upper(),
            "laps": f"{start_lap}-{end_lap}",
            "stint_length": stint_length,
            "avg_lap_time": avg_time_str,
            "degradation_sec": degradation_sec,
            "fresh_tyres": fresh_tyres,
        })

    return stints


def _extract_pit_stops(laps: pd.DataFrame, results: pd.DataFrame, driver_code: str) -> list[dict]:
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

            pit_stops.append({
                "lap": lap_num,
                "position_before": pos_int,
                "position_after": pos_int,  # Approximate; exact in/out tracking requires more data
            })

        prev_stint = current_stint

    return pit_stops


def _get_historical_strategies(
    location: str, current_year: int
) -> dict:
    """Load strategy data from last 3 editions of the same circuit.

    Returns dict with 'dominant_strategy', 'editions' list, and raw data for
    safety car analysis.
    """
    cache_key = f"{location}_{current_year}"
    if cache_key in _historical_cache:
        return _historical_cache[cache_key]

    editions = []
    all_stop_counts = []
    all_compound_sequences = []

    # Try last 3 years
    for past_year in range(current_year - 1, max(current_year - 4, 2018), -1):
        try:
            # Find the round number for this location in the past year
            schedule = fastf1.get_event_schedule(past_year, include_testing=False)
            matching = schedule[schedule["Location"] == location]

            if matching.empty:
                # Try fuzzy match on EventName
                for _, evt in schedule.iterrows():
                    if location.lower() in str(evt.get("Location", "")).lower():
                        matching = schedule[schedule.index == evt.name]
                        break

            if matching.empty:
                continue

            round_num = int(matching.iloc[0]["RoundNumber"])

            race_data = _load_race_data(past_year, round_num)
            if race_data is None:
                continue

            laps = race_data["laps"]
            results = race_data["results"]

            # Get winner's strategy
            if results is not None and not results.empty:
                winner = results.sort_values("Position").iloc[0]
                winner_code = str(winner.get("Abbreviation", ""))
                winner_stints = _extract_stint_data(laps, winner_code)

                if winner_stints:
                    compounds = [s["compound"][0] for s in winner_stints]  # First letter
                    compound_seq = "-".join(compounds)
                    num_stops = len(winner_stints) - 1
                    winner_strategy = f"{compound_seq} ({num_stops} stop{'s' if num_stops != 1 else ''})"
                else:
                    winner_strategy = "Unknown"
                    num_stops = 0
                    compound_seq = ""
            else:
                winner_strategy = "Unknown"
                num_stops = 0
                compound_seq = ""

            # Calculate average number of stops across all drivers
            all_drivers = laps["Driver"].unique()
            driver_stop_counts = []
            driver_sequences = []

            for drv in all_drivers:
                drv_stints = _extract_stint_data(laps, drv)
                if drv_stints:
                    stops = len(drv_stints) - 1
                    driver_stop_counts.append(stops)
                    all_stop_counts.append(stops)
                    seq = "-".join([s["compound"][0] for s in drv_stints])
                    driver_sequences.append(seq)
                    all_compound_sequences.append(seq)

            avg_stops = round(sum(driver_stop_counts) / len(driver_stop_counts), 1) if driver_stop_counts else 0

            editions.append({
                "year": past_year,
                "winner_strategy": winner_strategy,
                "avg_stops": avg_stops,
            })

        except Exception as exc:
            logger.debug("strategy.historical_year_error", location=location, year=past_year, error=str(exc))
            continue

    # Determine dominant strategy
    if all_compound_sequences:
        seq_counter = Counter(all_compound_sequences)
        most_common_seq = seq_counter.most_common(1)[0][0]
        if all_stop_counts:
            most_common_stops = Counter(all_stop_counts).most_common(1)[0][0]
        else:
            most_common_stops = 1

        # Map single letters back to compound names
        compound_map = {"S": "Soft", "M": "Medium", "H": "Hard", "I": "Intermediate", "W": "Wet", "U": "Unknown"}
        full_compounds = "-".join([compound_map.get(c, c) for c in most_common_seq.split("-")])
        dominant = f"{most_common_stops}-stop {full_compounds}"
    else:
        dominant = "Insufficient historical data"

    result = {
        "dominant_strategy": dominant,
        "editions": editions,
    }

    _historical_cache[cache_key] = result
    return result


def _analyze_undercut_overcut(
    laps: pd.DataFrame, results: pd.DataFrame, driver_code: str
) -> list[dict]:
    """Analyze undercut/overcut attempts for a specific driver.

    Compares pit stop timing with cars immediately ahead and behind.
    Undercut = pitting 1-3 laps before the car ahead.
    Overcut = pitting 1-3 laps after the car ahead.
    """
    if results is None or results.empty:
        return []

    # Get finishing order to find cars ahead/behind
    sorted_results = results.sort_values("Position")
    driver_positions = {
        str(row.get("Abbreviation", "")): int(row["Position"])
        for _, row in sorted_results.iterrows()
        if pd.notna(row.get("Position"))
    }

    if driver_code not in driver_positions:
        return []

    driver_pos = driver_positions[driver_code]

    # Find drivers immediately ahead and behind (by final position)
    adjacent_drivers = []
    for code, pos in driver_positions.items():
        if abs(pos - driver_pos) in (1, 2) and code != driver_code:
            adjacent_drivers.append(code)

    if not adjacent_drivers:
        return []

    # Get pit stop laps for our driver
    driver_pit_laps = _get_pit_stop_laps(laps, driver_code)
    if not driver_pit_laps:
        return []

    undercut_overcut = []

    for adj_code in adjacent_drivers:
        adj_pit_laps = _get_pit_stop_laps(laps, adj_code)
        if not adj_pit_laps:
            continue

        for d_pit in driver_pit_laps:
            for a_pit in adj_pit_laps:
                delta = d_pit - a_pit  # Negative = driver pitted first

                if -3 <= delta < 0:
                    # Driver pitted 1-3 laps before adjacent driver -> undercut attempt
                    adj_pos = driver_positions.get(adj_code, 0)
                    if driver_pos < adj_pos:
                        result_str = f"gained position over {adj_code}"
                    else:
                        result_str = f"did not gain on {adj_code}"

                    undercut_overcut.append({
                        "type": "undercut",
                        "target_driver": adj_code,
                        "lap": d_pit,
                        "result": result_str,
                    })
                    break  # Only one analysis per driver pair

                elif 0 < delta <= 3:
                    # Driver pitted 1-3 laps after adjacent driver -> overcut attempt
                    adj_pos = driver_positions.get(adj_code, 0)
                    if driver_pos < adj_pos:
                        result_str = f"gained position over {adj_code}"
                    else:
                        result_str = f"did not gain on {adj_code}"

                    undercut_overcut.append({
                        "type": "overcut",
                        "target_driver": adj_code,
                        "lap": d_pit,
                        "result": result_str,
                    })
                    break

    return undercut_overcut


def _get_pit_stop_laps(laps: pd.DataFrame, driver_code: str) -> list[int]:
    """Get the lap numbers where a driver made pit stops."""
    driver_laps = laps[laps["Driver"] == driver_code].sort_values("LapNumber")
    if driver_laps.empty:
        return []

    pit_laps = []
    prev_stint = None

    for _, lap in driver_laps.iterrows():
        current_stint = lap.get("Stint")
        if pd.isna(current_stint):
            continue
        if prev_stint is not None and current_stint != prev_stint:
            pit_laps.append(int(lap["LapNumber"]))
        prev_stint = current_stint

    return pit_laps


def _calculate_safety_car_probability(location: str, current_year: int) -> tuple[int, str]:
    """Calculate safety car probability from circuit history.

    Checks the last 5 years (or as many as available) at this circuit.
    Returns (probability_pct, context_string).
    """
    cache_key = location
    if cache_key in _safety_car_cache:
        cached = _safety_car_cache[cache_key]
        return cached["probability"], cached["context"]

    races_checked = 0
    races_with_sc = 0
    years_range = range(current_year - 1, max(current_year - 9, 2018), -1)

    for past_year in years_range:
        try:
            schedule = fastf1.get_event_schedule(past_year, include_testing=False)
            matching = schedule[schedule["Location"] == location]

            if matching.empty:
                continue

            round_num = int(matching.iloc[0]["RoundNumber"])

            with _fastf1_lock:
                session = fastf1.get_session(past_year, round_num, "R")
                session.load(telemetry=False, laps=True, weather=False)

            race_laps = session.laps
            if race_laps is None or race_laps.empty:
                continue

            races_checked += 1

            # Check for safety car: look for laps with TrackStatus containing SC indicators
            # TrackStatus codes: 1=Track Clear, 2=Yellow, 4=SC, 5=Red, 6=VSC
            if "TrackStatus" in race_laps.columns:
                track_statuses = race_laps["TrackStatus"].dropna().astype(str)
                has_sc = any("4" in s or "6" in s for s in track_statuses)
                if has_sc:
                    races_with_sc += 1
            else:
                # If no TrackStatus column, check if there are significant
                # gaps in lap times (indicative of SC/VSC periods)
                # This is a rough heuristic
                pass

            if races_checked >= 8:
                break

        except Exception:
            continue

    if races_checked == 0:
        probability = 50  # Default assumption
        context = f"Insufficient data for {location} safety car history"
    else:
        probability = round((races_with_sc / races_checked) * 100)
        context = (
            f"{location} has had safety cars in {races_with_sc} of last "
            f"{races_checked} races"
        )

    _safety_car_cache[cache_key] = {"probability": probability, "context": context}
    return probability, context


# ===================================================================
# Main function
# ===================================================================

def analyze_pit_strategy(
    year: int, round_num: int, driver_code: str | None = None
) -> dict:
    """Analyze pit strategy for a specific race.

    Args:
        year: Season year (e.g. 2024).
        round_num: Round number in the season calendar.
        driver_code: Optional 3-letter driver abbreviation (e.g. 'VER').
                     If provided, returns detailed analysis for that driver.
                     If None, returns a circuit-level strategy overview.

    Returns:
        Dict with stint breakdowns, historical strategies, undercut/overcut
        analysis, and safety car probability.
    """
    logger.info(
        "strategy.analyze",
        year=year, round=round_num, driver=driver_code,
    )

    # Load race data
    race_data = _load_race_data(year, round_num)
    if race_data is None:
        return {
            "year": year,
            "round": round_num,
            "error": f"Race data not available for {year} Round {round_num}. "
                     "The race may not have occurred yet or data is not loaded.",
        }

    laps = race_data["laps"]
    results = race_data["results"]
    event_name = race_data["event_name"]
    location = race_data["location"]

    # Validate driver if specified
    if driver_code is not None:
        available_drivers = laps["Driver"].unique()
        if driver_code not in available_drivers:
            return {
                "year": year,
                "round": round_num,
                "grand_prix": event_name,
                "error": f"Driver '{driver_code}' not found in race data. "
                         f"Available: {', '.join(sorted(available_drivers))}",
            }

    # Build response
    response: dict[str, Any] = {
        "year": year,
        "round": round_num,
        "grand_prix": event_name,
        "driver": driver_code,
    }

    # Stint data
    if driver_code:
        stints = _extract_stint_data(laps, driver_code)
        response["stints"] = stints
        response["pit_stops"] = _extract_pit_stops(laps, results, driver_code)

        # Undercut/overcut analysis
        response["undercut_overcut"] = _analyze_undercut_overcut(
            laps, results, driver_code
        )
    else:
        # Circuit overview: show strategy distribution across all drivers
        all_drivers = laps["Driver"].unique()
        strategy_distribution: dict[str, int] = {}
        all_stints_summary = []

        for drv in all_drivers:
            drv_stints = _extract_stint_data(laps, drv)
            if drv_stints:
                compounds = "-".join([s["compound"] for s in drv_stints])
                num_stops = len(drv_stints) - 1
                key = f"{num_stops}-stop ({compounds})"
                strategy_distribution[key] = strategy_distribution.get(key, 0) + 1
                all_stints_summary.append({
                    "driver": drv,
                    "strategy": key,
                    "num_stops": num_stops,
                })

        response["strategy_distribution"] = dict(
            sorted(strategy_distribution.items(), key=lambda x: x[1], reverse=True)
        )
        response["drivers"] = all_stints_summary

    # Historical strategies
    try:
        response["historical_strategies"] = _get_historical_strategies(
            location, year
        )
    except Exception as exc:
        logger.warning("strategy.historical_error", error=str(exc))
        response["historical_strategies"] = {
            "dominant_strategy": "Data unavailable",
            "editions": [],
        }

    # Safety car probability
    try:
        sc_prob, sc_context = _calculate_safety_car_probability(location, year)
        response["safety_car_probability"] = sc_prob
        response["safety_car_context"] = sc_context
    except Exception as exc:
        logger.warning("strategy.safety_car_error", error=str(exc))
        response["safety_car_probability"] = 50
        response["safety_car_context"] = "Unable to calculate safety car probability"

    logger.info(
        "strategy.complete",
        year=year, round=round_num, driver=driver_code,
        stints=len(response.get("stints", [])),
    )

    return response
