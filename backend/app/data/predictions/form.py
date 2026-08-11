"""Driver form signals derived from results across a season.

Recent finishing positions, sprint form, per-circuit history and the
grid-to-finish delta that captures how much overtaking a track allows.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

import fastf1
import structlog

from app.data.predictions.fastf1_lock import _fastf1_lock

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

# (driver_code, year, current_round) -> list of recent finishing positions
_recent_form_cache: dict[tuple[str, int, int], list[int]] = {}

# year -> {round: {driver_code: finishing position}} — whole-season results, loaded once
_season_results_cache: dict[int, dict[int, dict[str, int]]] = {}

# (year,) -> driver_code -> list of (round, sprint finishing position) this season
_recent_sprint_form_cache: dict[tuple[int,], dict[str, list[tuple[int, int]]]] = {}

# (circuit_key, year) -> dict of driver_code -> list of past positions
_circuit_history_cache: dict[tuple[str, int], dict[str, list[int]]] = {}

# (circuit_key,) -> dict of driver_code -> avg grid delta
_grid_delta_cache: dict[tuple[str,], dict[str, float]] = {}


def _season_race_positions(year: int) -> dict[int, dict[str, int]]:
    """Return ``{round: {driver_code: finishing_position}}`` for a season from f1db.

    Loaded once per season and cached. Uses the same ``race_results`` helper the
    training pipeline uses, so inference recent-form matches training exactly.
    """
    cached = _season_results_cache.get(year)
    if cached is not None:
        return cached

    from app.data.f1db_results import race_results, race_schedule

    cached = {}
    try:
        for event in race_schedule(year):
            round_num = int(event["round"])
            positions = race_results(year, round_num)
            if positions:
                cached[round_num] = positions
    except Exception as exc:
        logger.warning("predictions.season_results_error", year=year, error=str(exc))

    _season_results_cache[year] = cached
    return cached


def _load_recent_form(driver_code: str, year: int, current_round: int) -> list[int]:
    """Get a driver's last 5 race finishing positions *before* ``current_round``.

    Sourced from f1db (no rate limits). Bounding to rounds before the current one
    mirrors the ``season_results_so_far`` accumulator used at training time, so
    the recent_form feature is consistent between training and serving. Falls back
    to the previous season when fewer than 2 results are available.
    """
    cache_key = (driver_code, year, current_round)
    if cache_key in _recent_form_cache:
        return _recent_form_cache[cache_key]

    def _driver_positions(season: int, before_round: int | None) -> list[int]:
        results = _season_race_positions(season)
        out: list[int] = []
        for round_num in sorted(results):
            if before_round is not None and round_num >= before_round:
                continue
            pos = results[round_num].get(driver_code)
            if pos is not None:
                out.append(pos)
        return out

    positions = _driver_positions(year, current_round)

    # Fewer than 2 results this season — pad with the tail of the previous season.
    if len(positions) < 2:
        prev_positions = _driver_positions(year - 1, None)
        positions = prev_positions[-5:] + positions

    positions = positions[-5:]
    _recent_form_cache[cache_key] = positions
    return positions


def _load_recent_sprint_form(year: int, current_round: int) -> dict[str, list[int]]:
    """Get each driver's sprint finishing positions from earlier rounds this season.

    Returns ``driver_code -> [sprint finishes]`` in chronological order, covering
    only rounds *before* ``current_round`` so it mirrors the ``season_sprints_so_far``
    accumulator used at training time (the current weekend's sprint is fed
    separately as the ``sprint_position`` feature). Returns an empty mapping when
    no sprints have been held yet this season.
    """
    cache_key = (year,)
    cached = _recent_sprint_form_cache.get(cache_key)
    if cached is None:
        cached = {}
        try:
            from app.data.f1db_results import race_schedule, sprint_positions

            for event in race_schedule(year):
                sprint_round = int(event["round"])
                for code, pos in sprint_positions(year, sprint_round).items():
                    cached.setdefault(code, []).append((sprint_round, pos))
        except Exception as exc:
            logger.warning("predictions.recent_sprint_form_error", year=year, error=str(exc))
        _recent_sprint_form_cache[cache_key] = cached

    result: dict[str, list[int]] = {}
    for code, entries in cached.items():
        finishes = [pos for rnd, pos in sorted(entries) if rnd < current_round]
        if finishes:
            result[code] = finishes
    return result


def _find_round_for_location(year: int, location: str) -> int | None:
    """Return the round number where ``location`` was held in ``year``.

    Uses the FastF1 event schedule so the lookup is correct even when the
    calendar order changes between seasons (e.g. Miami added in 2022, Las
    Vegas in 2023, China returning in 2024).  Returns None if the location
    was not on the calendar that year.
    """
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        match = schedule[schedule["Location"].str.lower() == location.lower()]
        if not match.empty:
            return int(match.iloc[0]["RoundNumber"])
    except Exception as exc:
        logger.warning("predictions.round_lookup_failed", year=year, location=location, error=str(exc))
    return None


def _finish_positions(results: pd.DataFrame) -> dict[str, int]:
    """Driver code -> finishing position for one race, skipping unusable rows.

    A row without a code, or with a position that will not coerce to an int, is
    missing data rather than a failure: it is dropped so the rest of the race
    still contributes history.
    """
    positions: dict[str, int] = {}
    for _, row in results.iterrows():
        code = str(row.get("Abbreviation", ""))
        position = row.get("Position")
        if not code or position is None:
            continue
        try:
            positions[code] = int(position)
        except (ValueError, TypeError):
            continue
    return positions


def _grid_to_finish_deltas(results: pd.DataFrame) -> dict[str, int]:
    """Driver code -> places gained for one race; positive means places gained.

    Pit-lane starts (grid 0) are excluded — the notional gain from last on the
    grid would swamp the average.
    """
    deltas: dict[str, int] = {}
    for _, row in results.iterrows():
        code = str(row.get("Abbreviation", ""))
        grid = row.get("GridPosition")
        finish = row.get("Position")
        if not code or grid is None or finish is None:
            continue
        try:
            grid_position = int(grid)
            finish_position = int(finish)
        except (ValueError, TypeError):
            continue
        if grid_position > 0:
            deltas[code] = grid_position - finish_position
    return deltas


def _load_circuit_history(year: int, _round_num: int, circuit_key: str) -> dict[str, list[int]]:
    """Load driver results at this circuit for the last 3 editions.

    Returns dict of driver_code -> list of finishing positions.
    Looks up the correct round number for each past year so that calendar
    changes (new venues, dropped venues, reordered rounds) don't cause the
    wrong race to be loaded.
    """
    cache_key = (circuit_key, year)
    if cache_key in _circuit_history_cache:
        return _circuit_history_cache[cache_key]

    history: dict[str, list[int]] = {}

    for past_year in range(year - 1, max(year - 4, 2018), -1):
        past_round = _find_round_for_location(past_year, circuit_key)
        if past_round is None:
            logger.debug(
                "predictions.circuit_not_on_calendar",
                circuit=circuit_key,
                year=past_year,
            )
            continue
        try:
            with _fastf1_lock:
                session = fastf1.get_session(past_year, past_round, "R")
                session.load(telemetry=False, laps=False, weather=False)

            results = session.results
            if results is None or results.empty:
                continue

            for code, position in _finish_positions(results).items():
                history.setdefault(code, []).append(position)

        except Exception as exc:
            logger.debug(
                "predictions.circuit_history_year_failed",
                circuit=circuit_key,
                year=past_year,
                error=str(exc),
            )
            continue

    _circuit_history_cache[cache_key] = history
    logger.info(
        "predictions.circuit_history_loaded",
        circuit=circuit_key,
        years_loaded=len(history),
    )
    return history


def _load_grid_to_finish_delta(year: int, _round_num: int, circuit_key: str) -> dict[str, float]:
    """Compute average grid-to-finish position change at this circuit.

    Positive = driver tends to gain positions; negative = loses positions.
    Returns dict of driver_code -> avg delta (generic avg if driver has no data).
    """
    cache_key = (circuit_key,)
    if cache_key in _grid_delta_cache:
        return _grid_delta_cache[cache_key]

    deltas: dict[str, list[float]] = {}

    for past_year in range(year - 1, max(year - 4, 2018), -1):
        past_round = _find_round_for_location(past_year, circuit_key)
        if past_round is None:
            continue
        try:
            with _fastf1_lock:
                session = fastf1.get_session(past_year, past_round, "R")
                session.load(telemetry=False, laps=False, weather=False)

            results = session.results
            if results is None or results.empty:
                continue

            for code, delta in _grid_to_finish_deltas(results).items():
                deltas.setdefault(code, []).append(delta)

        except Exception as exc:
            logger.debug("predictions.circuit_history_year_failed", error=str(exc))
            continue

    # Compute averages
    result: dict[str, float] = {}
    for code, ds in deltas.items():
        result[code] = statistics.mean(ds) if ds else 0.0

    _grid_delta_cache[cache_key] = result
    return result
