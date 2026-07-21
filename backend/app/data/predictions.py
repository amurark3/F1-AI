"""
Race Prediction Engine
======================
Computes probabilistic race outcome predictions for all drivers using a
weighted heuristic scoring model.  Data sources:

  - Qualifying results (or practice session data as fallback)
  - Recent form (last 5 race results per driver)
  - Circuit history (driver's results at this track, last 3 editions)
  - Team strength (constructor championship position)
  - Grid-to-finish delta (historical overtaking pattern at circuit)

Confidence ranges are expressed as percentage pairs that widen when data
signals conflict and narrow when they agree.

Thread safety: All FastF1 session loads are wrapped with ``_fastf1_lock``
to prevent data corruption from concurrent loads.
"""

import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fastf1
import structlog
from fastf1.ergast import Ergast

from app.config import (
    CIRCUIT_HISTORY_WEIGHT,
    GRID_TO_FINISH_WEIGHT,
    ML_PREDICTION_BLEND_WEIGHT,
    PREDICTION_ADAPTIVE_WEIGHT,
    QUALIFYING_WEIGHT,
    RECENT_FORM_WEIGHT,
    TEAM_STRENGTH_WEIGHT,
)
from app.data.f1db_standings import (
    current_constructor_standings,
    current_driver_standings,
    driver_standings_detailed,
)
from app.data.store import DOCUMENT_PREDICTION_HISTORY, document_store
from app.ml.features import build_feature_row

logger = structlog.get_logger()
MODEL_PATH = Path(os.getenv("RACE_PREDICTOR_MODEL_PATH", "models/race_predictor.joblib"))
# Blend/adaptive weights live in app.config so the backtest harness and the live
# scorer share one source of truth. Kept as module-level aliases for callers.
ML_BLEND_WEIGHT = ML_PREDICTION_BLEND_WEIGHT
ADAPTIVE_CORRECTION_WEIGHT = PREDICTION_ADAPTIVE_WEIGHT

# ---------------------------------------------------------------------------
# Thread safety — same pattern as tools.py / routes.py
# ---------------------------------------------------------------------------
_fastf1_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory data caches — persist across requests within the same process
# ---------------------------------------------------------------------------
# (year, round_num) -> qualifying results dict
_qualifying_cache: dict[tuple[int, int], Any] = {}

# (year, round_num) -> practice results dict (fallback)
_practice_cache: dict[tuple[int, int], Any] = {}

# (driver_code, year, current_round) -> list of recent finishing positions
_recent_form_cache: dict[tuple[str, int, int], list[int]] = {}

# year -> {round: {driver_code: finishing position}} — whole-season results, loaded once
_season_results_cache: dict[int, dict[int, dict[str, int]]] = {}

# year -> {round: {driver_code: retirement reason or None}} — loaded once
_season_retirements_cache: dict[int, dict[int, dict[str, str | None]]] = {}

# (year,) -> driver_code -> list of (round, sprint finishing position) this season
_recent_sprint_form_cache: dict[tuple[int,], dict[str, list[tuple[int, int]]]] = {}

# (circuit_key, year) -> dict of driver_code -> list of past positions
_circuit_history_cache: dict[tuple[str, int], dict[str, list[int]]] = {}

# (year,) -> list of constructor standings dicts
_constructor_cache: dict[tuple[int,], list[dict]] = {}

# (year,) -> driver_code -> championship position
_driver_standings_cache: dict[tuple[int,], dict[str, int]] = {}

# (circuit_key,) -> dict of driver_code -> avg grid delta
_grid_delta_cache: dict[tuple[str,], dict[str, float]] = {}

# (year, round_num) -> sprint results dict (empty if no sprint that weekend)
_sprint_cache: dict[tuple[int, int], list[dict]] = {}

# (driver_code, year, round_num) -> recent incident profile
_incident_cache: dict[tuple[str, int, int], dict[str, Any]] = {}

_ml_model_cache: dict[str, Any] | None | bool = None

# ---------------------------------------------------------------------------
# Prediction history file lock for atomic writes
# ---------------------------------------------------------------------------
_history_file_lock = threading.Lock()


# ===================================================================
# FastF1 data loading helpers (all wrapped with _fastf1_lock)
# ===================================================================

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
            if pos is None or (hasattr(pos, "__float__") and pos != pos):  # NaN check
                continue
            drivers.append({
                "driver_code": str(row.get("Abbreviation", "")),
                "driver_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                "team": str(row.get("TeamName", "")),
                "position": int(pos),
            })

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
                driver_info = session.results[
                    session.results["Abbreviation"] == driver_code
                ]
                if not driver_info.empty:
                    row = driver_info.iloc[0]
                    name = f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()
                    team = str(row.get("TeamName", ""))
                else:
                    name = driver_code
                    team = ""

                drivers.append({
                    "driver_code": str(driver_code),
                    "driver_name": name,
                    "team": team,
                    "position": pos,
                })

            _practice_cache[cache_key] = drivers
            logger.info(
                "predictions.practice_loaded",
                year=year, round=round_num,
                session=session_name, drivers=len(drivers),
            )
            return drivers

        except Exception as exc:
            logger.debug(
                "predictions.practice_session_failed",
                year=year, round=round_num,
                session=session_name, error=str(exc),
            )
            continue

    logger.warning("predictions.no_practice_data", year=year, round=round_num)
    return None


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
            if pos is None or (hasattr(pos, "__float__") and pos != pos):
                continue
            drivers.append({
                "driver_code": str(row.get("Abbreviation", "")),
                "driver_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                "team": str(row.get("TeamName", "")),
                "position": int(pos),
            })

        _sprint_cache[cache_key] = drivers
        logger.info("predictions.sprint_loaded", year=year, round=round_num, drivers=len(drivers))
        return drivers

    except Exception:
        # No sprint session this weekend — not an error
        _sprint_cache[cache_key] = []
        return []


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
    except Exception:
        pass
    return None


def _load_circuit_history(
    year: int, round_num: int, circuit_key: str
) -> dict[str, list[int]]:
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
                circuit=circuit_key, year=past_year,
            )
            continue
        try:
            with _fastf1_lock:
                session = fastf1.get_session(past_year, past_round, "R")
                session.load(telemetry=False, laps=False, weather=False)

            results = session.results
            if results is None or results.empty:
                continue

            for _, row in results.iterrows():
                code = str(row.get("Abbreviation", ""))
                pos = row.get("Position")
                if code and pos is not None:
                    try:
                        pos_int = int(pos)
                        history.setdefault(code, []).append(pos_int)
                    except (ValueError, TypeError):
                        pass

        except Exception as exc:
            logger.debug(
                "predictions.circuit_history_year_failed",
                circuit=circuit_key, year=past_year, error=str(exc),
            )
            continue

    _circuit_history_cache[cache_key] = history
    logger.info(
        "predictions.circuit_history_loaded",
        circuit=circuit_key, years_loaded=len(history),
    )
    return history


def _ergast_constructor_standings(year: int) -> list[dict]:
    """Live Ergast fallback for constructor standings (current or previous season)."""
    for season in (year, year - 1):
        try:
            data = Ergast().get_constructor_standings(season=season)
            if data.content:
                return [
                    {
                        "constructor_name": str(row.get("constructorName", "")),
                        "position": int(row.get("position", 10)),
                    }
                    for _, row in data.content[0].iterrows()
                ]
        except Exception as exc:
            logger.warning("predictions.constructor_standings_error", year=season, error=str(exc))
    return []


def _load_constructor_standings(year: int) -> list[dict]:
    """Constructor standings ([{constructor_name, position}]).

    Sourced from the local f1db dataset first (no rate limits); falls back to the
    live Ergast API when f1db lacks the season (e.g. a brand-new in-progress round).
    """
    cache_key = (year,)
    if cache_key in _constructor_cache:
        return _constructor_cache[cache_key]

    standings = current_constructor_standings(year) or _ergast_constructor_standings(year)
    _constructor_cache[cache_key] = standings
    return standings


def _ergast_driver_standings(year: int) -> dict[str, int]:
    """Live Ergast fallback for driver standings (current or previous season)."""
    for season in (year, year - 1):
        try:
            data = Ergast().get_driver_standings(season=season)
            if data.content:
                result = {
                    str(row.get("driverCode", "")): int(row.get("position", 10))
                    for _, row in data.content[0].iterrows()
                    if str(row.get("driverCode", ""))
                }
                if result:
                    return result
        except Exception as exc:
            logger.warning("predictions.driver_standings_error", year=season, error=str(exc))
    return {}


def _load_driver_standings(year: int) -> dict[str, int]:
    """Driver standings as {driver_code: position} — f1db first, Ergast fallback."""
    cache_key = (year,)
    if cache_key in _driver_standings_cache:
        return _driver_standings_cache[cache_key]

    standings = current_driver_standings(year) or _ergast_driver_standings(year)
    _driver_standings_cache[cache_key] = standings
    return standings


def _load_grid_to_finish_delta(
    year: int, round_num: int, circuit_key: str
) -> dict[str, float]:
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

            for _, row in results.iterrows():
                code = str(row.get("Abbreviation", ""))
                grid = row.get("GridPosition")
                finish = row.get("Position")
                if code and grid is not None and finish is not None:
                    try:
                        g = int(grid)
                        f = int(finish)
                        if g > 0:  # Exclude pit-lane starts
                            deltas.setdefault(code, []).append(g - f)
                    except (ValueError, TypeError):
                        pass

        except Exception:
            continue

    # Compute averages
    result: dict[str, float] = {}
    for code, ds in deltas.items():
        result[code] = statistics.mean(ds) if ds else 0.0

    _grid_delta_cache[cache_key] = result
    return result


def _load_ml_model() -> dict[str, Any] | None:
    """Load the trained finish-position model if runtime dependencies exist."""
    global _ml_model_cache
    if _ml_model_cache is False:
        return None
    if isinstance(_ml_model_cache, dict):
        return _ml_model_cache

    try:
        import joblib

        payload = joblib.load(MODEL_PATH)
        if isinstance(payload, dict) and payload.get("model") and payload.get("features"):
            _ml_model_cache = payload
            logger.info("predictions.ml_model_loaded", path=str(MODEL_PATH))
            return payload
    except Exception as exc:
        logger.warning("predictions.ml_model_unavailable", path=str(MODEL_PATH), error=str(exc))

    _ml_model_cache = False
    return None


def _ml_finish_score(features: dict[str, float]) -> float | None:
    payload = _load_ml_model()
    if not payload:
        return None

    model = payload["model"]
    feature_names = payload["features"]
    try:
        row = [[float(features.get(name, 0.0)) for name in feature_names]]
        prediction = model.predict(row)[0]
        return float(prediction)
    except Exception as exc:
        logger.warning("predictions.ml_inference_failed", error=str(exc))
        return None


def _ml_explanation(features: dict[str, float]):
    """Return the exact per-feature attribution for one driver's ML projection.

    Returns a list of :class:`FeatureContribution` (strongest first), or None
    when the model is unavailable or not a supported linear model.
    """
    payload = _load_ml_model()
    if not payload:
        return None
    try:
        from app.ml.explain import explain_prediction

        return explain_prediction(payload, features)
    except Exception as exc:
        logger.warning("predictions.ml_explanation_failed", error=str(exc))
        return None


def _classify_status(status: str) -> dict[str, bool]:
    text = status.lower()
    classified = bool(text) and "finished" not in text and "lap" not in text
    crash_terms = ("accident", "collision", "crash", "spun", "damage")
    mechanical_terms = (
        "engine", "gearbox", "hydraul", "electrical", "brake", "power unit",
        "transmission", "suspension", "overheating", "oil", "water", "fuel",
    )
    return {
        "dnf": classified,
        "crash": any(term in text for term in crash_terms),
        "mechanical": any(term in text for term in mechanical_terms),
    }


def _season_retirements(year: int) -> dict[int, dict[str, str | None]]:
    """Return ``{round: {driver_code: retirement reason or None}}`` for a season.

    Loaded once per season from f1db and cached.
    """
    cached = _season_retirements_cache.get(year)
    if cached is not None:
        return cached

    from app.data.f1db_results import race_retirements, race_schedule

    cached = {}
    try:
        for event in race_schedule(year):
            round_num = int(event["round"])
            statuses = race_retirements(year, round_num)
            if statuses:
                cached[round_num] = statuses
    except Exception as exc:
        logger.warning("predictions.season_retirements_error", year=year, error=str(exc))

    _season_retirements_cache[year] = cached
    return cached


def _load_recent_incidents(driver_code: str, year: int, current_round: int) -> dict[str, Any]:
    """Return recent DNF/crash profile for a driver across current and prior season."""
    cache_key = (driver_code, year, current_round)
    if cache_key in _incident_cache:
        return _incident_cache[cache_key]

    starts = 0
    dnfs = 0
    crashes = 0
    mechanical = 0
    statuses: list[str] = []

    def _accumulate(season: int, before_round: int | None) -> None:
        nonlocal starts, dnfs, crashes, mechanical
        results = _season_retirements(season)
        for round_num in sorted(results):
            if before_round is not None and round_num >= before_round:
                continue
            if driver_code not in results[round_num]:
                continue
            starts += 1
            reason = results[round_num][driver_code]
            if not reason:  # classified finisher — no retirement
                continue
            flags = _classify_status(reason)
            if flags["dnf"]:
                dnfs += 1
                statuses.append(reason)
            if flags["crash"]:
                crashes += 1
            if flags["mechanical"]:
                mechanical += 1

    try:
        _accumulate(year, current_round)  # this season, before the current round
        _accumulate(year - 1, None)       # plus the whole prior season
    except Exception as exc:
        logger.warning("predictions.incident_history_error", driver=driver_code, error=str(exc))

    profile = {
        "starts": starts,
        "dnfs": dnfs,
        "crashes": crashes,
        "mechanical": mechanical,
        "dnf_rate": dnfs / starts if starts else 0.08,
        "crash_rate": crashes / starts if starts else 0.03,
        "mechanical_rate": mechanical / starts if starts else 0.04,
        "recent_statuses": statuses[-3:],
    }
    _incident_cache[cache_key] = profile
    return profile


def _adaptive_position_corrections() -> dict[str, dict[str, float]]:
    """Learn small driver-specific corrections from evaluated prediction misses.

    Positive correction means the model has been too optimistic and the score
    should move worse. Negative correction means the driver has usually beaten
    the model and the score can improve slightly.
    """
    history = _load_prediction_history()
    corrections: dict[str, list[float]] = {}

    for entry in history.values():
        snapshots = entry.get("snapshots")
        if not snapshots:
            snapshots = [{
                "predicted_positions": entry.get("predicted_positions") or {},
                "generated_at": entry.get("generated_at"),
            }]
        actual = entry.get("actual_positions") or {}
        if not actual:
            continue

        latest = snapshots[-1] if snapshots else {}
        predicted = latest.get("predicted_positions") or entry.get("predicted_positions") or {}
        for code, predicted_pos in predicted.items():
            actual_pos = actual.get(code)
            if actual_pos is None:
                continue
            try:
                miss = float(actual_pos) - float(predicted_pos)
            except (TypeError, ValueError):
                continue
            corrections.setdefault(code, []).append(max(-6.0, min(6.0, miss)))

    return {
        code: {
            "correction": statistics.mean(values[-6:]),
            "samples": len(values[-6:]),
        }
        for code, values in corrections.items()
        if values
    }


# ===================================================================
# Scoring engine
# ===================================================================

def _safe_mean(values: list[int | float], default: float = 10.0) -> float:
    """Compute mean of a list, returning default if empty."""
    if not values:
        return default
    return statistics.mean(values)


def safe_number(value: object) -> float:
    """Coerce optional numeric API/history fields for accuracy math."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _compute_confidence(
    inputs: list[float], is_pre_qualifying: bool = False
) -> tuple[int, int]:
    """Compute confidence range as (low, high) percentages.

    When data signals agree (low variance), confidence is tighter.
    When they conflict (high variance), confidence is wider.
    Pre-qualifying predictions get an additional 15pp widening.
    """
    if len(inputs) < 2:
        base_low = 40
        base_high = 60
    else:
        # Normalize inputs to 0-20 range (positions)
        std = statistics.stdev(inputs)
        # Lower std = more agreement = higher confidence
        # std of ~0 = 85-95% confidence; std of ~8+ = 35-55% confidence
        base_high = max(55, min(95, int(95 - std * 5)))
        base_low = max(35, base_high - 15)

    if is_pre_qualifying:
        base_low = max(20, base_low - 15)
        base_high = max(base_low + 5, base_high - 15)

    return (base_low, base_high)


def _generate_factors(
    driver_code: str,
    quali_pos: int | None,
    recent_positions: list[int],
    circuit_positions: list[int],
    team_pos: int,
    grid_delta: float,
    is_pre_qualifying: bool,
    sprint_pos: int | None = None,
) -> list[str]:
    """Generate top 3 reasoning factors from dominant scoring components."""
    factors: list[tuple[float, str]] = []

    # Sprint result factor — highest weight when available (same-weekend data)
    if sprint_pos is not None:
        if sprint_pos == 1:
            factors.append((6.0, "Won the sprint race this weekend"))
        elif sprint_pos <= 3:
            factors.append((5.0, f"Sprint race podium (P{sprint_pos})"))
        elif sprint_pos <= 8:
            factors.append((3.5, f"Points finish in sprint (P{sprint_pos})"))
        else:
            factors.append((1.5, f"Sprint race P{sprint_pos}"))

    # Qualifying / practice factor
    if quali_pos is not None:
        if is_pre_qualifying:
            if quali_pos <= 3:
                factors.append((3.0, f"Strong practice pace (P{quali_pos} in sessions)"))
            elif quali_pos <= 10:
                factors.append((1.5, f"Midfield practice pace (P{quali_pos})"))
            else:
                factors.append((0.5, f"Practice pace P{quali_pos}"))
        else:
            if quali_pos == 1:
                factors.append((5.0, "Pole position (qualifying P1)"))
            elif quali_pos <= 3:
                factors.append((4.0, f"Front row start (qualifying P{quali_pos})"))
            elif quali_pos <= 5:
                factors.append((2.5, f"Strong qualifying (P{quali_pos})"))
            elif quali_pos <= 10:
                factors.append((1.5, f"Qualifying P{quali_pos}"))
            else:
                factors.append((0.5, f"Qualifying P{quali_pos}"))

    # Recent form factor
    if recent_positions:
        avg = _safe_mean(recent_positions)
        wins = sum(1 for p in recent_positions if p == 1)
        podiums = sum(1 for p in recent_positions if p <= 3)
        n = len(recent_positions)

        if wins >= 2:
            factors.append((4.0, f"Won {wins} of last {n} races"))
        elif podiums >= 2:
            factors.append((3.0, f"{podiums} podiums in last {n} races"))
        elif avg <= 5:
            factors.append((2.5, f"Strong recent form (avg P{avg:.0f})"))
        elif avg <= 10:
            factors.append((1.5, f"Consistent points finisher (avg P{avg:.0f})"))
        else:
            factors.append((0.5, f"Recent average P{avg:.0f}"))

    # Circuit history factor
    if circuit_positions:
        avg = _safe_mean(circuit_positions)
        best = min(circuit_positions)
        n = len(circuit_positions)

        if best == 1:
            factors.append((4.5, f"Previous winner at this circuit (best P1 in last {n} editions)"))
        elif best <= 3:
            factors.append((3.5, f"Podium history here (best P{best} in last {n} editions)"))
        elif avg <= 6:
            factors.append((2.0, f"Good circuit record (avg P{avg:.0f} over {n} editions)"))
        else:
            factors.append((1.0, f"Circuit history avg P{avg:.0f}"))
    else:
        factors.append((0.3, "No prior results at this circuit"))

    # Team strength factor
    if team_pos <= 2:
        factors.append((3.0, f"Top team (constructor P{team_pos})"))
    elif team_pos <= 5:
        factors.append((1.5, f"Midfield team (constructor P{team_pos})"))
    else:
        factors.append((0.5, f"Constructor standing P{team_pos}"))

    # Grid-to-finish factor (overtaking circuit characteristic)
    if grid_delta > 1.5:
        factors.append((2.0, f"Historically gains ~{grid_delta:.0f} positions at this track"))
    elif grid_delta < -1.5:
        factors.append((1.0, f"Tends to lose ~{abs(grid_delta):.0f} positions here"))

    # Sort by importance and take top 3
    factors.sort(key=lambda x: x[0], reverse=True)
    return [f[1] for f in factors[:3]]


def _get_team_position(team_name: str, standings: list[dict]) -> int:
    """Map a team name to its constructor championship position.

    Uses fuzzy matching since FastF1 and Ergast may use slightly different
    team names (e.g. 'Red Bull Racing' vs 'Red Bull').
    """
    team_lower = team_name.lower()
    for entry in standings:
        if entry["constructor_name"].lower() in team_lower or team_lower in entry["constructor_name"].lower():
            return entry["position"]
    # Fallback: middle of pack
    return 10


def _risk_level(value: int) -> str:
    if value >= 22:
        return "high"
    if value >= 13:
        return "medium"
    return "low"


def _risk_factors(
    profile: dict[str, Any],
    quali_pos: int,
    team_pos: int,
    sprint_pos: int | None,
    dnf_risk: int,
    crash_risk: int,
) -> list[str]:
    factors: list[str] = []
    if profile.get("dnfs", 0) > 0:
        factors.append(f"{profile['dnfs']} DNF events in recent history")
    if profile.get("crashes", 0) > 0:
        factors.append(f"{profile['crashes']} accident/collision flags in recent history")
    if 8 <= quali_pos <= 16:
        factors.append("Starts in the highest traffic band")
    elif quali_pos <= 4:
        factors.append("Front group restart exposure")
    if team_pos >= 7:
        factors.append(f"Lower constructor reliability proxy (P{team_pos})")
    if sprint_pos is None:
        factors.append("No same-weekend sprint reliability signal")
    if not factors:
        factors.append("Low recent incident profile")
    if dnf_risk >= 22 and crash_risk < 10:
        factors.append("Risk leans mechanical rather than contact")
    return factors[:3]


def _compute_risk_predictions(
    predictions: list[dict],
    scored_by_code: dict[str, dict],
    year: int,
    round_num: int,
) -> list[dict]:
    """Build separate DNF/crash risk predictions for every classified driver."""
    risk_rows: list[dict] = []

    for prediction in predictions:
        code = prediction["driver_code"]
        scored = scored_by_code.get(code, {})
        quali_pos = int(scored.get("quali_pos") or prediction.get("position") or 10)
        team_pos = int(scored.get("team_pos") or 10)
        sprint_pos = scored.get("sprint_pos")
        profile = _load_recent_incidents(code, year, round_num)

        traffic_risk = 4 if 8 <= quali_pos <= 16 else 2 if quali_pos <= 4 else 1
        constructor_risk = max(0, team_pos - 5) * 1.1
        dnf_risk = round(
            6
            + profile["dnf_rate"] * 31
            + profile["mechanical_rate"] * 18
            + constructor_risk
            + traffic_risk
        )
        crash_risk = round(
            3
            + profile["crash_rate"] * 26
            + traffic_risk * 1.2
            + (2 if 10 <= quali_pos <= 18 else 0)
        )
        mechanical_risk = round(max(2, dnf_risk - crash_risk * 0.45))

        dnf_risk = max(3, min(42, dnf_risk))
        crash_risk = max(1, min(30, crash_risk))
        mechanical_risk = max(2, min(35, mechanical_risk))

        risk_rows.append({
            "driver_code": code,
            "driver_name": prediction["driver_name"],
            "team": prediction["team"],
            "projected_finish": prediction["position"],
            "dnf_risk_pct": dnf_risk,
            "crash_risk_pct": crash_risk,
            "mechanical_risk_pct": mechanical_risk,
            "risk_level": _risk_level(dnf_risk),
            "factors": _risk_factors(profile, quali_pos, team_pos, sprint_pos, dnf_risk, crash_risk),
        })

    risk_rows.sort(key=lambda row: (row["dnf_risk_pct"], row["crash_risk_pct"]), reverse=True)
    return risk_rows


# ===================================================================
# Main prediction function
# ===================================================================

def _qualifying_has_occurred(event_row) -> bool:
    """Return True if this event's qualifying session is in the past (UTC).

    For an upcoming race weekend the qualifying and practice sessions do not
    exist yet, so trying to load them from FastF1 just triggers a series of slow
    failing network calls (and can push a compute past its timeout). We gate the
    session loads on this check and go straight to the historical/pre-qualifying
    path when the weekend has not run.

    Falls back to True (attempt the load) whenever the schedule is unavailable,
    preserving the original behaviour.
    """
    import pandas as pd

    now = datetime.now(timezone.utc)

    def _to_utc(value):
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


def compute_race_predictions(year: int, round_num: int) -> dict:
    """Compute probabilistic race outcome predictions for all drivers.

    Args:
        year: Season year (e.g. 2025).
        round_num: Round number in the season calendar.

    Returns:
        Dict matching the REST response shape with predictions for all
        drivers sorted by predicted finishing position, including
        confidence ranges and reasoning factors.
    """
    warnings: list[str] = []
    data_sources: list[str] = []
    is_pre_qualifying = False

    # ------------------------------------------------------------------
    # 1. Get event info (needed for circuit key AND to gate session loads)
    # ------------------------------------------------------------------
    circuit_key = f"round_{round_num}"
    gp_name = f"Round {round_num}"
    event_row = None
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        event = schedule[schedule["RoundNumber"] == round_num]
        if not event.empty:
            event_row = event.iloc[0]
            gp_name = str(event_row.get("EventName", gp_name))
            circuit_key = str(event_row.get("Location", circuit_key))
    except Exception as exc:
        warnings.append(f"Could not load event schedule: {exc}")

    # ------------------------------------------------------------------
    # 2. Load qualifying (or practice fallback) — only if the weekend has run.
    #    Skipping futile loads for upcoming races avoids slow failing FastF1
    #    calls and keeps the compute well under its timeout.
    # ------------------------------------------------------------------
    sessions_occurred = _qualifying_has_occurred(event_row) if event_row is not None else True
    quali_data = None
    if sessions_occurred:
        quali_data = _load_qualifying(year, round_num)
        if quali_data:
            data_sources.append("qualifying")
        else:
            quali_data = _load_practice(year, round_num)
            if quali_data:
                data_sources.append("practice")
                is_pre_qualifying = True
                warnings.append("Qualifying data unavailable; using practice session pace as proxy")

    if not quali_data:
        is_pre_qualifying = True
        if sessions_occurred:
            warnings.append("No qualifying or practice data available; using historical data only")
        else:
            warnings.append("Race weekend has not started; using historical form only")

    # ------------------------------------------------------------------
    # 3. Load supporting data
    # ------------------------------------------------------------------
    constructor_standings = _load_constructor_standings(year)
    if constructor_standings:
        data_sources.append("constructor_standings")
    else:
        warnings.append("Constructor standings unavailable")

    driver_standings = _load_driver_standings(year)
    if driver_standings:
        data_sources.append("driver_standings")

    circuit_history = _load_circuit_history(year, round_num, circuit_key)
    if circuit_history:
        data_sources.append("circuit_history")

    grid_deltas = _load_grid_to_finish_delta(year, round_num, circuit_key)

    # Sprint result — only available if the sprint has already been run
    sprint_data = _load_sprint_result(year, round_num)
    sprint_positions: dict[str, int] = {d["driver_code"]: d["position"] for d in sprint_data}
    if sprint_data:
        data_sources.append("sprint_result")

    # Sprint finishes from earlier rounds this season — feeds recent_sprint_avg,
    # matching the season accumulator used at training time.
    recent_sprint_form = _load_recent_sprint_form(year, round_num)

    adaptive_corrections = _adaptive_position_corrections()
    if adaptive_corrections:
        data_sources.append("adaptive_history")

    # ------------------------------------------------------------------
    # 4. Build driver list (from qualifying/practice or fallback to schedule)
    # ------------------------------------------------------------------
    drivers_input: list[dict] = []
    if quali_data:
        drivers_input = quali_data
    else:
        # Last resort (e.g. an upcoming race with no qualifying yet): build a
        # rough grid from the latest championship standings. f1db gives real
        # driver names + teams and has no rate limits.
        try:
            for row in driver_standings_detailed(year):
                drivers_input.append({
                    "driver_code": row["code"],
                    "driver_name": row["name"],
                    "team": row["team"],
                    "position": row["position"],
                })
            if drivers_input:
                data_sources.append("championship_position")
        except Exception as exc:
            warnings.append(f"Could not load driver standings for fallback: {exc}")

    if not drivers_input:
        logger.error("predictions.no_driver_data", year=year, round=round_num)
        return {
            "year": year,
            "round": round_num,
            "grand_prix": gp_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": data_sources,
            "accuracy": get_accuracy_stats(),
            "predictions": [],
            "risk_predictions": [],
            "prediction_review": get_prediction_review(year, round_num),
            "weather_impact": "unknown",
            "wet_scenario": None,
            "warnings": warnings + ["No driver data available for predictions"],
        }

    # ------------------------------------------------------------------
    # 5. Score each driver
    # ------------------------------------------------------------------
    # Determine active weights (adjust proportionally if data is missing)
    active_weights = {}
    if sprint_data:
        # Sprint result is same-weekend race pace — strongest available signal
        active_weights["sprint"] = 0.30
    if quali_data:
        if is_pre_qualifying:
            active_weights["qualifying"] = 0.10
        else:
            # Reduce qualifying weight slightly when sprint result is also available
            active_weights["qualifying"] = 0.20 if sprint_data else QUALIFYING_WEIGHT
    active_weights["recent_form"] = RECENT_FORM_WEIGHT
    if circuit_history:
        active_weights["circuit_history"] = CIRCUIT_HISTORY_WEIGHT
    if constructor_standings:
        active_weights["team_strength"] = TEAM_STRENGTH_WEIGHT
    if grid_deltas:
        active_weights["grid_delta"] = GRID_TO_FINISH_WEIGHT

    # Normalize weights to sum to 1.0
    total_weight = sum(active_weights.values())
    if total_weight > 0:
        for k in active_weights:
            active_weights[k] /= total_weight

    scored_drivers: list[dict] = []
    scored_by_code: dict[str, dict] = {}
    ml_used = False
    adaptive_used = False

    for driver in drivers_input:
        code = driver["driver_code"]

        # Qualifying / practice position
        quali_pos = driver.get("position", 10)

        # Sprint result this weekend (if available)
        sprint_pos = sprint_positions.get(code)

        # Recent form
        recent_positions = _load_recent_form(code, year, round_num)
        if recent_positions:
            if "last_5_races" not in data_sources:
                data_sources.append("last_5_races")
        recent_avg = _safe_mean(recent_positions)

        # Circuit history for this driver
        driver_circuit = circuit_history.get(code, [])
        circuit_avg = _safe_mean(driver_circuit)

        # Team strength
        team_pos = _get_team_position(driver.get("team", ""), constructor_standings)
        driver_standing = driver_standings.get(code, 10)

        # Grid-to-finish delta
        driver_delta = grid_deltas.get(code, 0.0)

        # Compute weighted score (lower = better predicted position)
        score = 0.0
        if "sprint" in active_weights and sprint_pos is not None:
            score += active_weights["sprint"] * sprint_pos
        elif "sprint" in active_weights:
            # Driver has no sprint result (DNF/DNS) — penalise slightly
            score += active_weights["sprint"] * 18.0
        if "qualifying" in active_weights:
            score += active_weights["qualifying"] * quali_pos
        if "recent_form" in active_weights:
            score += active_weights["recent_form"] * recent_avg
        if "circuit_history" in active_weights:
            score += active_weights["circuit_history"] * circuit_avg
        if "team_strength" in active_weights:
            score += active_weights["team_strength"] * team_pos
        if "grid_delta" in active_weights:
            # Positive delta means driver gains positions, so subtract
            score -= active_weights["grid_delta"] * driver_delta

        heuristic_score = score
        ml_features = build_feature_row(
            grid_position=quali_pos,
            sprint_position=sprint_pos,
            had_sprint=bool(sprint_data),
            recent_finishes=recent_positions,
            recent_sprint_finishes=recent_sprint_form.get(code, []),
            circuit_finishes=driver_circuit,
            circuit_grid_deltas=[driver_delta] if driver_delta else [],
            team_standing=team_pos,
            driver_standing=driver_standing,
        )
        ml_score = _ml_finish_score(ml_features)
        if ml_score is not None:
            score = (ML_BLEND_WEIGHT * ml_score) + ((1 - ML_BLEND_WEIGHT) * heuristic_score)
            ml_used = True

        correction = adaptive_corrections.get(code)
        if correction and correction.get("samples", 0) > 0:
            score += ADAPTIVE_CORRECTION_WEIGHT * correction["correction"]
            adaptive_used = True

        # Confidence range based on variance of input signals
        # Sprint result tightens confidence because it's same-weekend race pace
        input_signals = [float(quali_pos)]
        if sprint_pos is not None:
            input_signals.append(float(sprint_pos))
        if recent_positions:
            input_signals.append(recent_avg)
        if driver_circuit:
            input_signals.append(circuit_avg)
        input_signals.append(float(team_pos))
        if ml_score is not None:
            input_signals.append(ml_score)

        confidence_low, confidence_high = _compute_confidence(
            input_signals, is_pre_qualifying
        )

        # Factors
        heuristic_factors = _generate_factors(
            code, quali_pos, recent_positions, driver_circuit,
            team_pos, driver_delta, is_pre_qualifying,
            sprint_pos=sprint_pos,
        )

        # Model attribution — exact per-feature contributions from the linear
        # model, so the reasoning shown is the model's own, not a heuristic guess.
        model_attribution = None
        model_phrases: list[str] = []
        if ml_score is not None:
            contributions = _ml_explanation(ml_features)
            if contributions:
                from app.ml.explain import attribution_dicts, attribution_phrases

                model_attribution = attribution_dicts(contributions)
                model_phrases = attribution_phrases(contributions, top_n=2)

        factors = list(heuristic_factors)
        if ml_score is not None:
            factors = [f"Trained model projects P{ml_score:.1f}"] + model_phrases + factors
        if correction and abs(correction["correction"]) >= 1:
            direction = "downgrades" if correction["correction"] > 0 else "upgrades"
            factors.append(f"Adaptive history {direction} by {abs(correction['correction']):.1f} places")
        # Keep more factors when the model contributes reasoning; heuristic-only
        # predictions stay at the original 3.
        factors = factors[:5] if ml_score is not None else factors[:3]

        scored = {
            "driver_code": code,
            "driver_name": driver.get("driver_name", code),
            "team": driver.get("team", ""),
            "score": score,
            "heuristic_score": heuristic_score,
            "ml_score": ml_score,
            "adaptive_correction": correction,
            "quali_pos": quali_pos,
            "sprint_pos": sprint_pos,
            "team_pos": team_pos,
            "driver_standing": driver_standing,
            "confidence_low": confidence_low,
            "confidence_high": confidence_high,
            "factors": factors,
            "model_attribution": model_attribution,
        }
        scored_drivers.append(scored)
        scored_by_code[code] = scored

    if ml_used:
        data_sources.append("trained_ml_model")
    if adaptive_used and "adaptive_history" not in data_sources:
        data_sources.append("adaptive_history")

    # ------------------------------------------------------------------
    # 6. Sort by score and assign positions
    # ------------------------------------------------------------------
    scored_drivers.sort(key=lambda d: d["score"])

    predictions = []
    for pos, driver in enumerate(scored_drivers, 1):
        predictions.append({
            "position": pos,
            "driver_code": driver["driver_code"],
            "driver_name": driver["driver_name"],
            "team": driver["team"],
            "confidence_low": driver["confidence_low"],
            "confidence_high": driver["confidence_high"],
            "factors": driver["factors"],
            "model_attribution": driver.get("model_attribution"),
        })

    risk_predictions = _compute_risk_predictions(predictions, scored_by_code, year, round_num)

    # ------------------------------------------------------------------
    # 7. Build response
    # ------------------------------------------------------------------
    result = {
        "year": year,
        "round": round_num,
        "grand_prix": gp_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": sorted(set(data_sources)),
        "accuracy": get_accuracy_stats(),
        "predictions": predictions,
        "risk_predictions": risk_predictions,
        "prediction_review": get_prediction_review(year, round_num),
        "prediction_phase": "pre_qualifying" if is_pre_qualifying else "post_qualifying",
        "weather_impact": "dry",  # Weather module (Plan 02) will populate this
        "wet_scenario": None,
        "warnings": warnings if warnings else None,
    }

    # ------------------------------------------------------------------
    # 8. Save prediction for accuracy tracking
    # ------------------------------------------------------------------
    try:
        save_prediction(year, round_num, result)
    except Exception as exc:
        logger.warning("predictions.save_failed", error=str(exc))

    logger.info(
        "predictions.computed",
        year=year, round=round_num,
        drivers=len(predictions),
        data_sources=data_sources,
        pre_qualifying=is_pre_qualifying,
    )

    return result


# ===================================================================
# Accuracy tracking — JSON persistence
# ===================================================================

def _load_prediction_history() -> dict:
    """Load prediction history from the document store (Postgres or JSON fallback).

    Returns an empty dict if absent or malformed.
    Never raises — graceful degradation is paramount.
    """
    data = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not isinstance(data, dict):
        return {}
    return data


def _save_prediction_history(data: dict) -> None:
    """Persist prediction history via the document store (Postgres or JSON fallback).

    Durable when DATABASE_URL is configured; falls back to an atomic local file
    write otherwise.  Never raises.
    """
    document_store.write(DOCUMENT_PREDICTION_HISTORY, data)


def save_prediction(year: int, round_num: int, predictions: dict) -> None:
    """Save a prediction to the history file for later accuracy comparison.

    Stores predicted positions keyed by ``"(year,round)"`` along with
    metadata.  Thread-safe via ``_history_file_lock``.
    """
    key = f"({year},{round_num})"

    # Extract predicted positions: driver_code -> predicted position
    predicted_positions = {}
    for entry in predictions.get("predictions", []):
        code = entry.get("driver_code", "")
        pos = entry.get("position")
        if code and pos is not None:
            predicted_positions[code] = pos

    if not predicted_positions:
        return

    risk_predictions = {
        entry.get("driver_code", ""): {
            "dnf_risk_pct": entry.get("dnf_risk_pct"),
            "crash_risk_pct": entry.get("crash_risk_pct"),
            "mechanical_risk_pct": entry.get("mechanical_risk_pct"),
            "risk_level": entry.get("risk_level"),
        }
        for entry in predictions.get("risk_predictions", [])
        if entry.get("driver_code")
    }
    snapshot = {
        "generated_at": predictions.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "prediction_phase": predictions.get("prediction_phase"),
        "data_sources": predictions.get("data_sources") or [],
        "predicted_positions": predicted_positions,
        "risk_predictions": risk_predictions,
    }

    with _history_file_lock:
        history = _load_prediction_history()
        existing = history.get(key, {})
        snapshots = list(existing.get("snapshots") or [])
        snapshots.append(snapshot)
        history[key] = {
            **existing,
            "predicted_positions": predicted_positions,
            "risk_predictions": risk_predictions,
            "generated_at": snapshot["generated_at"],
            "prediction_phase": snapshot["prediction_phase"],
            "data_sources": snapshot["data_sources"],
            "actual_positions": existing.get("actual_positions"),
            "actual_statuses": existing.get("actual_statuses"),
            "actual_incidents": existing.get("actual_incidents"),
            "snapshots": snapshots[-8:],
        }
        _save_prediction_history(history)

    logger.info("predictions.saved", key=key, drivers=len(predicted_positions))


def record_actual_result(year: int, round_num: int) -> None:
    """Load actual race finishing positions from FastF1 and store in history.

    Called lazily when accuracy stats are requested and actual data is
    missing for a past race.
    """
    key = f"({year},{round_num})"

    with _history_file_lock:
        history = _load_prediction_history()

        # Only update if we have a prediction but no actual result yet
        entry = history.get(key)
        if not entry or entry.get("actual_positions"):
            return

    # Load actual results (outside the file lock to avoid holding it during I/O)
    actual_positions = {}
    actual_statuses = {}
    actual_incidents = {}
    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "R")
            session.load(telemetry=False, laps=False, weather=False)

        results = session.results
        if results is not None and not results.empty:
            for _, row in results.iterrows():
                code = str(row.get("Abbreviation", ""))
                pos = row.get("Position")
                if code and pos is not None:
                    try:
                        actual_positions[code] = int(pos)
                        status = str(row.get("Status", "") or row.get("status", ""))
                        actual_statuses[code] = status
                        actual_incidents[code] = _classify_status(status)
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        logger.warning(
            "predictions.actual_result_load_error",
            year=year, round=round_num, error=str(exc),
        )
        return

    if not actual_positions:
        return

    # Write back with file lock
    with _history_file_lock:
        history = _load_prediction_history()
        if key in history:
            history[key]["actual_positions"] = actual_positions
            history[key]["actual_statuses"] = actual_statuses
            history[key]["actual_incidents"] = actual_incidents
            _save_prediction_history(history)
            logger.info("predictions.actual_recorded", key=key, drivers=len(actual_positions))


def _latest_prediction_snapshot(entry: dict) -> dict:
    snapshots = entry.get("snapshots") or []
    if snapshots:
        return snapshots[-1]
    return {
        "generated_at": entry.get("generated_at"),
        "prediction_phase": entry.get("prediction_phase"),
        "data_sources": entry.get("data_sources") or [],
        "predicted_positions": entry.get("predicted_positions") or {},
        "risk_predictions": entry.get("risk_predictions") or {},
    }


def get_prediction_review(year: int, round_num: int) -> dict:
    """Compare the latest saved prediction with actual race data when available."""
    key = f"({year},{round_num})"
    record_actual_result(year, round_num)

    history = _load_prediction_history()
    entry = history.get(key)
    if not entry:
        return {"evaluated": False, "reason": "No stored prediction snapshot for this race."}

    snapshot = _latest_prediction_snapshot(entry)
    predicted = snapshot.get("predicted_positions") or {}
    actual = entry.get("actual_positions") or {}
    if not predicted:
        return {"evaluated": False, "reason": "Stored prediction has no finishing order."}
    if not actual:
        return {"evaluated": False, "reason": "Actual race result is not available yet."}

    common_drivers = set(predicted) & set(actual)
    if not common_drivers:
        return {"evaluated": False, "reason": "Prediction and result do not share driver codes."}

    predicted_winner = min(predicted, key=predicted.get)
    actual_winner = min(actual, key=actual.get)
    predicted_top3 = {code for code, pos in predicted.items() if pos <= 3}
    actual_top3 = {code for code, pos in actual.items() if pos <= 3}
    predicted_top10 = {code for code, pos in predicted.items() if pos <= 10}
    actual_top10 = {code for code, pos in actual.items() if pos <= 10}
    exact_hits = sum(1 for code in common_drivers if predicted[code] == actual[code])
    position_errors = [abs(float(predicted[code]) - float(actual[code])) for code in common_drivers]

    incidents = entry.get("actual_incidents") or {}
    actual_dnfs = {code for code, flags in incidents.items() if flags.get("dnf")}
    actual_crashes = {code for code, flags in incidents.items() if flags.get("crash")}
    risks = snapshot.get("risk_predictions") or {}
    predicted_dnfs = {
        code for code, risk in risks.items()
        if safe_number(risk.get("dnf_risk_pct")) >= 16
    }
    predicted_crashes = {
        code for code, risk in risks.items()
        if safe_number(risk.get("crash_risk_pct")) >= 10
    }

    return {
        "evaluated": True,
        "generated_at": snapshot.get("generated_at"),
        "prediction_phase": snapshot.get("prediction_phase"),
        "winner_correct": predicted_winner == actual_winner,
        "predicted_winner": predicted_winner,
        "actual_winner": actual_winner,
        "top3_correct": len(predicted_top3 & actual_top3),
        "top3_possible": min(3, len(actual_top3)),
        "top10_correct": len(predicted_top10 & actual_top10),
        "top10_possible": min(10, len(actual_top10)),
        "exact_position_hits": exact_hits,
        "drivers_compared": len(common_drivers),
        "avg_position_error": round(statistics.mean(position_errors), 1) if position_errors else 0.0,
        "dnf_correct": len(predicted_dnfs & actual_dnfs),
        "dnf_predicted": len(predicted_dnfs),
        "dnf_actual": len(actual_dnfs),
        "crash_correct": len(predicted_crashes & actual_crashes),
        "crash_predicted": len(predicted_crashes),
        "crash_actual": len(actual_crashes),
    }


def get_accuracy_stats(last_n_races: int = 8) -> dict:
    """Compute rolling accuracy over the last N races with both prediction and actual data.

    Returns:
        Dict with keys: recent_top3_pct, recent_top10_pct,
        avg_position_error, races_evaluated.

    Gracefully returns ``{"races_evaluated": 0}`` if no data is available.
    """
    try:
        history = _load_prediction_history()
    except Exception:
        return {"races_evaluated": 0}

    if not history:
        return {"races_evaluated": 0}

    # Collect entries that have both predicted and actual positions
    evaluated: list[dict] = []
    for key, entry in history.items():
        snapshot = _latest_prediction_snapshot(entry)
        predicted = snapshot.get("predicted_positions")
        actual = entry.get("actual_positions")
        if predicted and actual:
            evaluated.append({
                "predicted": predicted,
                "actual": actual,
                "risk_predictions": snapshot.get("risk_predictions") or {},
                "actual_incidents": entry.get("actual_incidents") or {},
                "generated_at": snapshot.get("generated_at") or entry.get("generated_at", ""),
            })

    if not evaluated:
        # Try to lazily fill in actual results for entries that are missing them
        for key, entry in history.items():
            if entry.get("predicted_positions") and not entry.get("actual_positions"):
                # Parse key "(year,round)"
                try:
                    parts = key.strip("()").split(",")
                    y, r = int(parts[0]), int(parts[1])
                    record_actual_result(y, r)
                except (ValueError, IndexError):
                    pass

        # Re-load after attempting to fill actuals
        try:
            history = _load_prediction_history()
        except Exception:
            return {"races_evaluated": 0}

        for key, entry in history.items():
            snapshot = _latest_prediction_snapshot(entry)
            predicted = snapshot.get("predicted_positions")
            actual = entry.get("actual_positions")
            if predicted and actual:
                evaluated.append({
                    "predicted": predicted,
                    "actual": actual,
                    "risk_predictions": snapshot.get("risk_predictions") or {},
                    "actual_incidents": entry.get("actual_incidents") or {},
                    "generated_at": snapshot.get("generated_at") or entry.get("generated_at", ""),
                })

    if not evaluated:
        return {"races_evaluated": 0}

    # Sort by generated_at descending and take last N
    evaluated.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    evaluated = evaluated[:last_n_races]

    # Compute metrics
    total_top3_correct = 0
    total_top3_possible = 0
    total_top10_correct = 0
    total_top10_possible = 0
    total_winner_correct = 0
    total_exact_positions = 0
    total_drivers_compared = 0
    total_dnf_correct = 0
    total_dnf_actual = 0
    total_crash_correct = 0
    total_crash_actual = 0
    total_position_errors: list[float] = []

    for race in evaluated:
        predicted = race["predicted"]
        actual = race["actual"]

        # Find common drivers
        common_drivers = set(predicted.keys()) & set(actual.keys())
        if not common_drivers:
            continue

        # Top-3 accuracy: predicted top 3 who actually finished top 3
        predicted_top3 = {d for d, p in predicted.items() if p <= 3 and d in common_drivers}
        actual_top3 = {d for d, p in actual.items() if p <= 3 and d in common_drivers}
        top3_correct = len(predicted_top3 & actual_top3)
        total_top3_correct += top3_correct
        total_top3_possible += min(3, len(predicted_top3))

        # Top-10 accuracy: predicted top 10 who actually finished top 10
        predicted_top10 = {d for d, p in predicted.items() if p <= 10 and d in common_drivers}
        actual_top10 = {d for d, p in actual.items() if p <= 10 and d in common_drivers}
        top10_correct = len(predicted_top10 & actual_top10)
        total_top10_correct += top10_correct
        total_top10_possible += min(10, len(predicted_top10))

        predicted_winner = min(predicted, key=predicted.get)
        actual_winner = min(actual, key=actual.get)
        if predicted_winner == actual_winner:
            total_winner_correct += 1

        # Average position error across all common drivers
        for driver in common_drivers:
            error = abs(predicted[driver] - actual[driver])
            total_position_errors.append(error)
            if predicted[driver] == actual[driver]:
                total_exact_positions += 1
        total_drivers_compared += len(common_drivers)

        incidents = race.get("actual_incidents") or {}
        actual_dnfs = {code for code, flags in incidents.items() if flags.get("dnf")}
        actual_crashes = {code for code, flags in incidents.items() if flags.get("crash")}
        risks = race.get("risk_predictions") or {}
        predicted_dnfs = {
            code for code, risk in risks.items()
            if safe_number(risk.get("dnf_risk_pct")) >= 16
        }
        predicted_crashes = {
            code for code, risk in risks.items()
            if safe_number(risk.get("crash_risk_pct")) >= 10
        }
        total_dnf_correct += len(predicted_dnfs & actual_dnfs)
        total_dnf_actual += len(actual_dnfs)
        total_crash_correct += len(predicted_crashes & actual_crashes)
        total_crash_actual += len(actual_crashes)

    races_evaluated = len(evaluated)

    top3_pct = (
        round(total_top3_correct / total_top3_possible * 100)
        if total_top3_possible > 0 else 0
    )
    top10_pct = (
        round(total_top10_correct / total_top10_possible * 100)
        if total_top10_possible > 0 else 0
    )
    avg_error = (
        round(statistics.mean(total_position_errors), 1)
        if total_position_errors else 0.0
    )
    winner_pct = round(total_winner_correct / races_evaluated * 100) if races_evaluated else 0
    exact_pct = round(total_exact_positions / total_drivers_compared * 100) if total_drivers_compared else 0
    dnf_capture_pct = round(total_dnf_correct / total_dnf_actual * 100) if total_dnf_actual else None
    crash_capture_pct = round(total_crash_correct / total_crash_actual * 100) if total_crash_actual else None

    return {
        "recent_winner_pct": winner_pct,
        "recent_top3_pct": top3_pct,
        "recent_top10_pct": top10_pct,
        "exact_position_pct": exact_pct,
        "avg_position_error": avg_error,
        "dnf_capture_pct": dnf_capture_pct,
        "crash_capture_pct": crash_capture_pct,
        "races_evaluated": races_evaluated,
        "rolling_window": last_n_races,
    }
