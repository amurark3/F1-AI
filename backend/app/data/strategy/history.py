"""Strategy patterns drawn from previous editions of the same circuit."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

import fastf1
import structlog

from app.data.strategy.session import (
    _extract_stint_data,
    _fastf1_lock,
    _load_race_data,
)

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

# (circuit_key, year_range_key) -> historical strategy summaries
_historical_cache: dict[str, Any] = {}

# (circuit_key,) -> safety car stats
_safety_car_cache: dict[str, dict] = {}


# Compound sequences are stored as initials so they can be counted cheaply; this
# maps them back for display.
_COMPOUND_NAMES = {"S": "Soft", "M": "Medium", "H": "Hard", "I": "Intermediate", "W": "Wet", "U": "Unknown"}


def _round_for_location(schedule: pd.DataFrame, location: str) -> int | None:
    """Round number for ``location`` in a season, exact match first then fuzzy.

    Circuit naming drifts between seasons, so an exact miss falls back to a
    substring match rather than dropping the edition from the history.
    """
    matching = schedule[schedule["Location"] == location]

    if matching.empty:
        for _, event in schedule.iterrows():
            if location.lower() in str(event.get("Location", "")).lower():
                matching = schedule[schedule.index == event.name]
                break

    if matching.empty:
        return None
    return int(matching.iloc[0]["RoundNumber"])


def _compound_sequence(stints: list[dict]) -> str:
    """Compound initials for a set of stints, e.g. ``"M-H-M"``."""
    return "-".join(stint["compound"][0] for stint in stints)


def _winner_strategy(laps: pd.DataFrame, results: pd.DataFrame | None) -> str:
    """The winner's compound sequence and stop count, as display text."""
    if results is None or results.empty:
        return "Unknown"

    winner = results.sort_values("Position").iloc[0]
    stints = _extract_stint_data(laps, str(winner.get("Abbreviation", "")))
    if not stints:
        return "Unknown"

    stops = len(stints) - 1
    return f"{_compound_sequence(stints)} ({stops} stop{'s' if stops != 1 else ''})"


def _field_strategies(laps: pd.DataFrame) -> tuple[list[int], list[str]]:
    """Stop counts and compound sequences for every driver with stint data."""
    stop_counts: list[int] = []
    sequences: list[str] = []

    for driver in laps["Driver"].unique():
        stints = _extract_stint_data(laps, driver)
        if not stints:
            continue
        stop_counts.append(len(stints) - 1)
        sequences.append(_compound_sequence(stints))

    return stop_counts, sequences


def _dominant_strategy(sequences: list[str], stop_counts: list[int]) -> str:
    """The most common compound sequence across all editions examined."""
    if not sequences:
        return "Insufficient historical data"

    most_common = Counter(sequences).most_common(1)[0][0]
    stops = Counter(stop_counts).most_common(1)[0][0] if stop_counts else 1
    full_compounds = "-".join(_COMPOUND_NAMES.get(letter, letter) for letter in most_common.split("-"))
    return f"{stops}-stop {full_compounds}"


def _get_historical_strategies(location: str, current_year: int) -> dict:
    """Load strategy data from last 3 editions of the same circuit.

    Returns dict with 'dominant_strategy', 'editions' list, and raw data for
    safety car analysis.
    """
    cache_key = f"{location}_{current_year}"
    if cache_key in _historical_cache:
        return _historical_cache[cache_key]

    editions = []
    all_stop_counts: list[int] = []
    all_compound_sequences: list[str] = []

    # Try last 3 years
    for past_year in range(current_year - 1, max(current_year - 4, 2018), -1):
        try:
            schedule = fastf1.get_event_schedule(past_year, include_testing=False)
            round_num = _round_for_location(schedule, location)
            if round_num is None:
                continue

            race_data = _load_race_data(past_year, round_num)
            if race_data is None:
                continue

            laps = race_data["laps"]
            stop_counts, sequences = _field_strategies(laps)
            all_stop_counts.extend(stop_counts)
            all_compound_sequences.extend(sequences)

            editions.append(
                {
                    "year": past_year,
                    "winner_strategy": _winner_strategy(laps, race_data["results"]),
                    "avg_stops": round(sum(stop_counts) / len(stop_counts), 1) if stop_counts else 0,
                }
            )

        except Exception as exc:
            logger.debug("strategy.historical_year_error", location=location, year=past_year, error=str(exc))
            continue

    result = {
        "dominant_strategy": _dominant_strategy(all_compound_sequences, all_stop_counts),
        "editions": editions,
    }

    _historical_cache[cache_key] = result
    return result


# FastF1 TrackStatus codes: 1=Track Clear, 2=Yellow, 4=SC, 5=Red, 6=VSC. A lap's
# status is a concatenation of the codes active during it, hence the substring test.
_SAFETY_CAR_CODES = ("4", "6")

# Editions sampled before the probability is considered settled.
_SAFETY_CAR_SAMPLE_LIMIT = 8

# Probability reported when no edition could be assessed either way.
_SAFETY_CAR_UNKNOWN_PROBABILITY = 50


def _had_safety_car(race_laps: pd.DataFrame) -> bool:
    """Whether any lap ran under a safety car or virtual safety car."""
    statuses = race_laps["TrackStatus"].dropna().astype(str)
    return any(code in status for status in statuses for code in _SAFETY_CAR_CODES)


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

            if "TrackStatus" not in race_laps.columns:
                # Without track status there is no way to tell whether a safety
                # car was deployed. Counting the race would put it in the
                # denominator and never the numerator, biasing the probability
                # down, so it is skipped rather than recorded as "no safety car".
                continue

            races_checked += 1
            if _had_safety_car(race_laps):
                races_with_sc += 1

            if races_checked >= _SAFETY_CAR_SAMPLE_LIMIT:
                break

        except Exception as exc:
            logger.debug("strategy.safety_car_year_failed", error=str(exc))
            continue

    if races_checked == 0:
        probability = _SAFETY_CAR_UNKNOWN_PROBABILITY
        context = f"Insufficient data for {location} safety car history"
    else:
        probability = round((races_with_sc / races_checked) * 100)
        context = f"{location} has had safety cars in {races_with_sc} of last {races_checked} races"

    _safety_car_cache[cache_key] = {"probability": probability, "context": context}
    return probability, context
