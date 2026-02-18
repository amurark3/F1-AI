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
    PREDICTION_HISTORY_PATH,
    QUALIFYING_WEIGHT,
    RECENT_FORM_WEIGHT,
    TEAM_STRENGTH_WEIGHT,
)

logger = structlog.get_logger()

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

# (driver_code, year) -> list of recent finishing positions
_recent_form_cache: dict[tuple[str, int], list[int]] = {}

# (circuit_key, year) -> dict of driver_code -> list of past positions
_circuit_history_cache: dict[tuple[str, int], dict[str, list[int]]] = {}

# (year,) -> list of constructor standings dicts
_constructor_cache: dict[tuple[int,], list[dict]] = {}

# (circuit_key,) -> dict of driver_code -> avg grid delta
_grid_delta_cache: dict[tuple[str,], dict[str, float]] = {}

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


def _load_recent_form(driver_code: str, year: int, current_round: int) -> list[int]:
    """Get last 5 race finishing positions for a driver in the current season.

    Falls back to previous season if fewer than 2 results available.
    """
    cache_key = (driver_code, year)
    if cache_key in _recent_form_cache:
        return _recent_form_cache[cache_key]

    positions: list[int] = []

    try:
        ergast = Ergast()
        # Current season results
        data = ergast.get_race_results(season=year)
        if data.content:
            for race_results in data.content:
                for _, row in race_results.iterrows():
                    if str(row.get("driverCode", "")) == driver_code:
                        pos = row.get("position")
                        if pos is not None:
                            try:
                                positions.append(int(pos))
                            except (ValueError, TypeError):
                                pass

        # If we have fewer than 2 results, also check previous season
        if len(positions) < 2:
            prev_data = ergast.get_race_results(season=year - 1)
            if prev_data.content:
                prev_positions = []
                for race_results in prev_data.content:
                    for _, row in race_results.iterrows():
                        if str(row.get("driverCode", "")) == driver_code:
                            pos = row.get("position")
                            if pos is not None:
                                try:
                                    prev_positions.append(int(pos))
                                except (ValueError, TypeError):
                                    pass
                # Take last 5 from previous season + current
                positions = prev_positions[-5:] + positions

        # Keep only last 5
        positions = positions[-5:]

    except Exception as exc:
        logger.warning("predictions.recent_form_error", driver=driver_code, error=str(exc))

    _recent_form_cache[cache_key] = positions
    return positions


def _load_circuit_history(
    year: int, round_num: int, circuit_key: str
) -> dict[str, list[int]]:
    """Load driver results at this circuit for the last 3 editions.

    Returns dict of driver_code -> list of finishing positions.
    """
    cache_key = (circuit_key, year)
    if cache_key in _circuit_history_cache:
        return _circuit_history_cache[cache_key]

    history: dict[str, list[int]] = {}

    for past_year in range(year - 1, max(year - 4, 2018), -1):
        try:
            with _fastf1_lock:
                session = fastf1.get_session(past_year, round_num, "R")
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


def _load_constructor_standings(year: int) -> list[dict]:
    """Load constructor championship standings.

    Returns list of dicts with keys: constructor_name, position.
    """
    cache_key = (year,)
    if cache_key in _constructor_cache:
        return _constructor_cache[cache_key]

    standings: list[dict] = []
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        if data.content:
            df = data.content[0]
            for _, row in df.iterrows():
                standings.append({
                    "constructor_name": str(row.get("constructorName", "")),
                    "position": int(row.get("position", 10)),
                })
    except Exception as exc:
        logger.warning("predictions.constructor_standings_error", error=str(exc))
        # If current year fails, try previous year
        try:
            ergast = Ergast()
            data = ergast.get_constructor_standings(season=year - 1)
            if data.content:
                df = data.content[0]
                for _, row in df.iterrows():
                    standings.append({
                        "constructor_name": str(row.get("constructorName", "")),
                        "position": int(row.get("position", 10)),
                    })
        except Exception:
            pass

    _constructor_cache[cache_key] = standings
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
        try:
            with _fastf1_lock:
                session = fastf1.get_session(past_year, round_num, "R")
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


# ===================================================================
# Scoring engine
# ===================================================================

def _safe_mean(values: list[int | float], default: float = 10.0) -> float:
    """Compute mean of a list, returning default if empty."""
    if not values:
        return default
    return statistics.mean(values)


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
) -> list[str]:
    """Generate top 3 reasoning factors from dominant scoring components."""
    factors: list[tuple[float, str]] = []

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


# ===================================================================
# Main prediction function
# ===================================================================

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
    # 1. Load qualifying (or practice fallback)
    # ------------------------------------------------------------------
    quali_data = _load_qualifying(year, round_num)
    if quali_data:
        data_sources.append("qualifying")
    else:
        # Pre-qualifying fallback
        quali_data = _load_practice(year, round_num)
        if quali_data:
            data_sources.append("practice")
            is_pre_qualifying = True
            warnings.append("Qualifying data unavailable; using practice session pace as proxy")
        else:
            warnings.append("No qualifying or practice data available; using historical data only")

    # ------------------------------------------------------------------
    # 2. Get event info for circuit key
    # ------------------------------------------------------------------
    circuit_key = f"round_{round_num}"
    gp_name = f"Round {round_num}"
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        event = schedule[schedule["RoundNumber"] == round_num]
        if not event.empty:
            gp_name = str(event.iloc[0].get("EventName", gp_name))
            circuit_key = str(event.iloc[0].get("Location", circuit_key))
    except Exception as exc:
        warnings.append(f"Could not load event schedule: {exc}")

    # ------------------------------------------------------------------
    # 3. Load supporting data
    # ------------------------------------------------------------------
    constructor_standings = _load_constructor_standings(year)
    if constructor_standings:
        data_sources.append("constructor_standings")
    else:
        warnings.append("Constructor standings unavailable")

    circuit_history = _load_circuit_history(year, round_num, circuit_key)
    if circuit_history:
        data_sources.append("circuit_history")

    grid_deltas = _load_grid_to_finish_delta(year, round_num, circuit_key)

    # ------------------------------------------------------------------
    # 4. Build driver list (from qualifying/practice or fallback to schedule)
    # ------------------------------------------------------------------
    drivers_input: list[dict] = []
    if quali_data:
        drivers_input = quali_data
    else:
        # Last resort: use constructor standings to generate a rough grid
        # based on championship position
        try:
            ergast = Ergast()
            standings_data = ergast.get_driver_standings(season=year)
            if standings_data.content:
                df = standings_data.content[0]
                for _, row in df.iterrows():
                    drivers_input.append({
                        "driver_code": str(row.get("driverCode", "")),
                        "driver_name": str(row.get("driverCode", "")),
                        "team": ", ".join(row.get("constructorNames", [])) if isinstance(row.get("constructorNames"), list) else str(row.get("constructorNames", "")),
                        "position": int(row.get("position", 20)),
                    })
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
            "weather_impact": "unknown",
            "wet_scenario": None,
            "warnings": warnings + ["No driver data available for predictions"],
        }

    # ------------------------------------------------------------------
    # 5. Score each driver
    # ------------------------------------------------------------------
    # Determine active weights (adjust proportionally if data is missing)
    active_weights = {}
    if quali_data:
        if is_pre_qualifying:
            # Practice data is a weak signal
            active_weights["qualifying"] = 0.10
        else:
            active_weights["qualifying"] = QUALIFYING_WEIGHT
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

    for driver in drivers_input:
        code = driver["driver_code"]

        # Qualifying / practice position
        quali_pos = driver.get("position", 10)

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

        # Grid-to-finish delta
        driver_delta = grid_deltas.get(code, 0.0)

        # Compute weighted score (lower = better predicted position)
        score = 0.0
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

        # Confidence range based on variance of input signals
        input_signals = [float(quali_pos)]
        if recent_positions:
            input_signals.append(recent_avg)
        if driver_circuit:
            input_signals.append(circuit_avg)
        input_signals.append(float(team_pos))

        confidence_low, confidence_high = _compute_confidence(
            input_signals, is_pre_qualifying
        )

        # Factors
        factors = _generate_factors(
            code, quali_pos, recent_positions, driver_circuit,
            team_pos, driver_delta, is_pre_qualifying,
        )

        scored_drivers.append({
            "driver_code": code,
            "driver_name": driver.get("driver_name", code),
            "team": driver.get("team", ""),
            "score": score,
            "confidence_low": confidence_low,
            "confidence_high": confidence_high,
            "factors": factors,
        })

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
        })

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
# Accuracy tracking (stubs — implemented fully in Task 2)
# ===================================================================

def save_prediction(year: int, round_num: int, predictions: dict) -> None:
    """Save a prediction to the history file. Full implementation in Task 2."""
    pass


def get_accuracy_stats(last_n_races: int = 5) -> dict:
    """Compute rolling accuracy stats. Full implementation in Task 2."""
    return {"races_evaluated": 0}


def record_actual_result(year: int, round_num: int) -> None:
    """Record actual race result. Full implementation in Task 2."""
    pass
