"""Strategy patterns drawn from previous editions of the same circuit."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

import structlog

from app.data.canonical_names import feed_code
from app.data.f1db_calendar import season_schedule
from app.data.openf1.race_control import SAFETY_CAR, VIRTUAL_SAFETY_CAR
from app.data.openf1.session_laps import load_session_laps
from app.data.strategy.session import _SOURCE_ERRORS, _extract_stint_data, _load_race_data

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

# OpenF1 publishes laps and race control from the 2023 season on. Earlier races
# were read from FastF1, which cannot load them on a cold cache (F1's archive
# needs a login since 15 Oct 2026), so they are left out (plan decision 3).
OPENF1_FIRST_SEASON = 2023

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

    # A winner FastF1 sent without a code has laps without one too.
    code = feed_code(results.sort_values("Position").iloc[0].get("Abbreviation"))
    stints = _extract_stint_data(laps, code) if code else []
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
    missing_years: list[int] = []
    all_stop_counts: list[int] = []
    all_compound_sequences: list[str] = []

    # The last 3 editions, never before OpenF1's first season.
    for past_year in range(current_year - 1, max(current_year - 4, OPENF1_FIRST_SEASON - 1), -1):
        try:
            round_num = _round_for_location(season_schedule(past_year), location)
        except _SOURCE_ERRORS as exc:
            logger.warning("strategy.historical_year_error", location=location, year=past_year, error=str(exc))
            missing_years.append(past_year)
            continue
        if round_num is None:
            continue

        race_data = _load_race_data(past_year, round_num)
        if race_data is None:
            missing_years.append(past_year)
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

    result = {
        "dominant_strategy": _dominant_strategy(all_compound_sequences, all_stop_counts),
        "editions": editions,
        # An edition that exists but could not be read is missing, not an empty one.
        "missing_years": missing_years,
    }

    # An answer that left an edition unread is retried on the next call.
    if not missing_years:
        _historical_cache[cache_key] = result
    return result


# Race control windows that count as a neutralisation by safety car.
_SAFETY_CAR_KINDS = frozenset({SAFETY_CAR, VIRTUAL_SAFETY_CAR})

# Probability reported when no edition could be assessed either way.
_SAFETY_CAR_UNKNOWN_PROBABILITY = 50


def _race_had_safety_car(year: int, round_num: int) -> bool | None:
    """Whether race control deployed a safety car or VSC; None when the race cannot be read."""
    try:
        loaded = load_session_laps(year, round_num, "R")
    except _SOURCE_ERRORS as exc:
        logger.warning("strategy.safety_car_year_failed", year=year, error=str(exc))
        return None
    if loaded is None or not loaded.laps:
        return None
    return any(window.kind in _SAFETY_CAR_KINDS for window in loaded.windows)


def _safety_car_context(location: str, with_sc: list[int], without_sc: list[int], missing: list[int]) -> str:
    """The figure in words, always with how many races it is drawn from."""
    checked = len(with_sc) + len(without_sc)
    if checked == 0:
        context = (
            f"Insufficient data for {location} safety car history (no race since {OPENF1_FIRST_SEASON} could be read)"
        )
    else:
        years = ", ".join(str(year) for year in sorted(with_sc + without_sc))
        context = (
            f"{location} had a safety car or virtual safety car in {len(with_sc)} of {checked} "
            f"race{'s' if checked != 1 else ''} since {OPENF1_FIRST_SEASON} ({years})"
        )
    if missing:
        context += f"; {', '.join(str(year) for year in sorted(missing))} could not be read"
    return context


def _calculate_safety_car_probability(location: str, current_year: int) -> tuple[int, str]:
    """Safety car probability from this circuit's races since 2023.

    Returns (probability_pct, context_string); the context states the sample size.
    """
    if location in _safety_car_cache:
        cached = _safety_car_cache[location]
        return cached["probability"], cached["context"]

    with_sc: list[int] = []
    without_sc: list[int] = []
    missing: list[int] = []

    for past_year in range(current_year - 1, OPENF1_FIRST_SEASON - 1, -1):
        try:
            schedule = season_schedule(past_year)
        except _SOURCE_ERRORS as exc:
            logger.warning("strategy.safety_car_year_failed", year=past_year, error=str(exc))
            missing.append(past_year)
            continue

        matching = schedule[schedule["Location"] == location]
        if matching.empty:
            continue

        had = _race_had_safety_car(past_year, int(matching.iloc[0]["RoundNumber"]))
        if had is None:
            missing.append(past_year)
        else:
            (with_sc if had else without_sc).append(past_year)

    checked = len(with_sc) + len(without_sc)
    probability = round(len(with_sc) / checked * 100) if checked else _SAFETY_CAR_UNKNOWN_PROBABILITY
    context = _safety_car_context(location, with_sc, without_sc, missing)

    # A year that could not be read is retried on the next call.
    if not missing:
        _safety_car_cache[location] = {"probability": probability, "context": context}
    return probability, context
