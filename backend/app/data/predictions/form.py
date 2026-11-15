"""Driver form signals derived from results across a season.

Recent finishing positions, sprint form, per-circuit history and the
grid-to-finish delta that captures how much overtaking a track allows.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics

import structlog

from app.data.f1db_grid import starting_grid
from app.data.f1db_results import race_results, race_schedule

logger = structlog.get_logger()

# Past editions of a circuit that feed its history and grid-to-finish change.
CIRCUIT_EDITIONS = 3
FIRST_SEASON = 2018

# (driver_code, year, current_round) -> list of recent finishing positions
_recent_form_cache: dict[tuple[str, int, int], list[int]] = {}

# year -> {round: {driver_code: finishing position}} — whole-season results, loaded once
_season_results_cache: dict[int, dict[int, dict[str, int]]] = {}

# (year,) -> driver_code -> list of (round, sprint finishing position) this season
_recent_sprint_form_cache: dict[tuple[int,], dict[str, list[tuple[int, int]]]] = {}

# (circuit_id, year) -> the circuit's past editions, read from f1db
_circuit_editions_cache: dict[tuple[str, int], CircuitEditions] = {}


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


@dataclass(frozen=True)
class CircuitEditions:
    """A circuit's last editions as f1db has them.

    ``missing`` maps each year without a usable edition to why, so a gap is
    reported rather than read as "nobody scored here".
    """

    history: dict[str, list[int]]
    deltas: dict[str, float]
    missing: dict[int, str]


def _edition_round(past_year: int, circuit_id: str) -> int | None:
    """The round at which ``circuit_id`` hosted a Grand Prix in ``past_year``."""
    for event in race_schedule(past_year):
        if event["location"] == circuit_id:
            return int(event["round"])
    return None


def _edition_deltas(past_year: int, past_round: int, finishes: dict[str, int]) -> dict[str, int]:
    """Driver code -> places gained from the published grid; positive means gained.

    A pit-lane start holds no grid slot (``position`` is ``None``) and is left
    out: the notional gain from last on the grid would swamp the average.
    """
    return {
        slot.driver_code: slot.position - finishes[slot.driver_code]
        for slot in starting_grid(past_year, past_round)
        if slot.position is not None and slot.driver_code in finishes
    }


def _read_editions(year: int, circuit_id: str) -> tuple[CircuitEditions, bool]:
    """Read the editions, and whether every one was answered by f1db."""
    history: dict[str, list[int]] = {}
    grid_deltas: dict[str, list[float]] = {}
    missing: dict[int, str] = {}
    answered = True
    for past_year in range(year - 1, year - 1 - CIRCUIT_EDITIONS, -1):
        if past_year < FIRST_SEASON:
            break
        try:
            past_round = _edition_round(past_year, circuit_id)
            finishes = {} if past_round is None else race_results(past_year, past_round)
            deltas = {} if not finishes or past_round is None else _edition_deltas(past_year, past_round, finishes)
        except Exception as exc:
            logger.warning("predictions.circuit_edition_unreadable", circuit=circuit_id, year=past_year, error=str(exc))
            missing[past_year] = f"f1db could not be read: {exc}"
            answered = False
            continue
        if past_round is None:
            missing[past_year] = "f1db has no Grand Prix at this circuit that season"
        elif not finishes:
            missing[past_year] = f"f1db has no race result for round {past_round}"
        for code, position in finishes.items():
            history.setdefault(code, []).append(position)
        for code, delta in deltas.items():
            grid_deltas.setdefault(code, []).append(delta)
    averages = {code: statistics.mean(values) for code, values in grid_deltas.items()}
    return CircuitEditions(history, averages, missing), answered


def circuit_editions(year: int, circuit_id: str) -> CircuitEditions:
    """The last three editions of ``circuit_id`` before ``year``, found by f1db's circuit id.

    Every edition is a past season, so it ended before any cutoff a recompute
    of ``year`` can have. Calendar moves (Miami added, China returning) cannot
    point at the wrong race the way a round number would.

    An answer is cached only when f1db answered for every edition and at least
    one had a result: an unreadable f1db or a circuit with no history is read
    again next time instead of being remembered as an empty answer.
    """
    key = (circuit_id, year)
    cached = _circuit_editions_cache.get(key)
    if cached is not None:
        return cached
    editions, answered = _read_editions(year, circuit_id)
    if answered and editions.history:
        _circuit_editions_cache[key] = editions
    logger.info(
        "predictions.circuit_history_loaded",
        circuit=circuit_id,
        drivers=len(editions.history),
        missing_years=sorted(editions.missing),
    )
    return editions
