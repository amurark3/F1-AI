"""The prediction entry point: assemble every signal into a ranked grid.

``compute_race_predictions`` is a pipeline, and each stage it used to inline is
now a named function returning a frozen value: event context, session data,
supporting data, the driver roster, the weight set. The per-driver scoring that
follows lives in ``driver_score``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import fastf1
import structlog

from app.config import (
    CIRCUIT_HISTORY_WEIGHT,
    GRID_TO_FINISH_WEIGHT,
    ML_PREDICTION_BLEND_WEIGHT,
    PREDICTION_ADAPTIVE_WEIGHT,
    QUALIFYING_WEIGHT,
    RECENT_FORM_WEIGHT,
    TEAM_STRENGTH_WEIGHT,
)
from app.data.f1db_standings import driver_standings_detailed
from app.data.predictions.accuracy import get_accuracy_stats
from app.data.predictions.driver_score import RaceSignals, score_driver
from app.data.predictions.form import (
    _load_circuit_history,
    _load_grid_to_finish_delta,
    _load_recent_sprint_form,
)
from app.data.predictions.history import save_prediction
from app.data.predictions.model import _adaptive_position_corrections
from app.data.predictions.review import get_prediction_review
from app.data.predictions.scoring import _compute_risk_predictions
from app.data.predictions.sessions import (
    _load_practice,
    _load_qualifying,
    _load_sprint_result,
    _qualifying_has_occurred,
)
from app.data.predictions.standings import _load_constructor_standings, _load_driver_standings
from app.data.predictions.version import PREDICTION_LOGIC_VERSION

logger = structlog.get_logger()

# Blend/adaptive weights live in app.config so the backtest harness and the live
# scorer share one source of truth. Kept as module-level aliases for callers.
ML_BLEND_WEIGHT = ML_PREDICTION_BLEND_WEIGHT
ADAPTIVE_CORRECTION_WEIGHT = PREDICTION_ADAPTIVE_WEIGHT

# Weight given to a same-weekend sprint result — the strongest signal available,
# because it is actual race pace on this car at this circuit.
_SPRINT_WEIGHT = 0.30

# Qualifying weight when practice pace is standing in for a session that has not
# run, and when a sprint result is already carrying most of the race-pace signal.
_PRE_QUALIFYING_WEIGHT = 0.10
_QUALIFYING_WEIGHT_WITH_SPRINT = 0.20


@dataclass(frozen=True)
class Stage:
    """What a loading stage produced, alongside what it wants reported.

    Warnings and data sources accumulate across stages, so each returns its own
    rather than mutating a shared list — the caller decides the final order.
    """

    warnings: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EventContext(Stage):
    """Circuit and event identity for the round being predicted."""

    gp_name: str = ""
    circuit_key: str = ""
    event_row: Any = None


@dataclass(frozen=True)
class SessionData(Stage):
    """Qualifying or practice pace, and whether qualifying has actually run."""

    quali_data: list[dict] | None = None
    is_pre_qualifying: bool = False


@dataclass(frozen=True)
class SupportingData(Stage):
    """Everything loaded once per race that is not session pace."""

    constructor_standings: list[dict] = field(default_factory=list)
    driver_standings: dict[str, int] = field(default_factory=dict)
    circuit_history: dict[str, list[int]] = field(default_factory=dict)
    grid_deltas: dict[str, float] = field(default_factory=dict)
    sprint_positions: dict[str, int] = field(default_factory=dict)
    had_sprint: bool = False
    recent_sprint_form: dict[str, list] = field(default_factory=dict)
    adaptive_corrections: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class Roster(Stage):
    """The drivers to predict, in their starting order."""

    drivers: list[dict] = field(default_factory=list)


def _load_event_context(year: int, round_num: int) -> EventContext:
    """Resolve the event's name and circuit, falling back to round identifiers.

    The circuit key gates circuit-history lookups, and the event row gates
    session loads, so a schedule failure degrades the prediction rather than
    failing it.
    """
    circuit_key = f"round_{round_num}"
    gp_name = f"Round {round_num}"
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        event = schedule[schedule["RoundNumber"] == round_num]
        if not event.empty:
            event_row = event.iloc[0]
            return EventContext(
                gp_name=str(event_row.get("EventName", gp_name)),
                circuit_key=str(event_row.get("Location", circuit_key)),
                event_row=event_row,
            )
    except Exception as exc:
        return EventContext(
            gp_name=gp_name,
            circuit_key=circuit_key,
            warnings=[f"Could not load event schedule: {exc}"],
        )
    return EventContext(gp_name=gp_name, circuit_key=circuit_key)


def _load_session_data(year: int, round_num: int, event_row: Any) -> SessionData:
    """Load qualifying, falling back to practice pace, then to history alone.

    Sessions are only attempted once the weekend has run: probing FastF1 for an
    upcoming race is a slow failure that eats the compute budget for nothing.
    """
    sessions_occurred = _qualifying_has_occurred(event_row) if event_row is not None else True
    if sessions_occurred:
        quali_data = _load_qualifying(year, round_num)
        if quali_data:
            return SessionData(quali_data=quali_data, data_sources=["qualifying"])

        practice = _load_practice(year, round_num)
        if practice:
            return SessionData(
                quali_data=practice,
                is_pre_qualifying=True,
                data_sources=["practice"],
                warnings=["Qualifying data unavailable; using practice session pace as proxy"],
            )

    reason = (
        "No qualifying or practice data available; using historical data only"
        if sessions_occurred
        else "Race weekend has not started; using historical form only"
    )
    return SessionData(is_pre_qualifying=True, warnings=[reason])


def _load_supporting_data(year: int, round_num: int, circuit_key: str) -> SupportingData:
    """Load standings, circuit history, sprint results and adaptive corrections."""
    warnings: list[str] = []
    data_sources: list[str] = []

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

    sprint_data = _load_sprint_result(year, round_num)
    if sprint_data:
        data_sources.append("sprint_result")

    adaptive_corrections = _adaptive_position_corrections()
    if adaptive_corrections:
        data_sources.append("adaptive_history")

    return SupportingData(
        warnings=warnings,
        data_sources=data_sources,
        constructor_standings=constructor_standings,
        driver_standings=driver_standings,
        circuit_history=circuit_history,
        grid_deltas=_load_grid_to_finish_delta(year, round_num, circuit_key),
        sprint_positions={d["driver_code"]: d["position"] for d in sprint_data},
        had_sprint=bool(sprint_data),
        # Sprint finishes from earlier rounds this season — feeds
        # recent_sprint_avg, matching the season accumulator used at training.
        recent_sprint_form=_load_recent_sprint_form(year, round_num),
        adaptive_corrections=adaptive_corrections,
    )


def _build_roster(year: int, quali_data: list[dict] | None) -> Roster:
    """Return every entered driver, back-filling those without a session time.

    A missing qualifying time (crash, DNS, no lap set) must NOT drop a driver
    from the grid: unless the field is genuinely reduced, the full roster of
    entered drivers should be predicted. The roster comes from the season's
    championship entry list, which gives real names and teams from f1db with no
    rate limits.
    """
    drivers: list[dict] = list(quali_data) if quali_data else []

    try:
        roster = driver_standings_detailed(year)
    except Exception as exc:
        return Roster(drivers=drivers, warnings=[f"Could not load full-grid roster: {exc}"])

    if not roster:
        return Roster(drivers=drivers)

    present = {d["driver_code"] for d in drivers}
    missing = sorted((r for r in roster if r["code"] not in present), key=lambda r: r["position"])
    if not missing:
        return Roster(drivers=drivers)

    # Back-filled drivers line up behind the slowest actual qualifier (or from
    # P1 when there's no session yet), in championship order, so they start from
    # a realistic slot rather than an arbitrary one.
    next_pos = max((d.get("position", 0) for d in drivers), default=0) + 1
    for entry in missing:
        drivers.append(
            {
                "driver_code": entry["code"],
                "driver_name": entry["name"],
                "team": entry["team"],
                "position": next_pos,
                "no_qualifying_time": True,
            }
        )
        next_pos += 1

    warnings = (
        [
            f"{len(missing)} entered driver(s) had no qualifying time; "
            "included from championship entry list at back of grid"
        ]
        if quali_data
        else []
    )
    return Roster(drivers=drivers, warnings=warnings, data_sources=["championship_position"])


def _active_weights(session: SessionData, support: SupportingData) -> dict[str, float]:
    """Return the signal weights in play, normalised to sum to 1.0.

    Only signals with data get a weight, and the rest are scaled up to fill the
    gap — so a missing signal redistributes its influence rather than shrinking
    every score toward zero.
    """
    weights: dict[str, float] = {}
    if support.had_sprint:
        weights["sprint"] = _SPRINT_WEIGHT
    if session.quali_data:
        if session.is_pre_qualifying:
            weights["qualifying"] = _PRE_QUALIFYING_WEIGHT
        else:
            weights["qualifying"] = _QUALIFYING_WEIGHT_WITH_SPRINT if support.had_sprint else QUALIFYING_WEIGHT
    weights["recent_form"] = RECENT_FORM_WEIGHT
    if support.circuit_history:
        weights["circuit_history"] = CIRCUIT_HISTORY_WEIGHT
    if support.constructor_standings:
        weights["team_strength"] = TEAM_STRENGTH_WEIGHT
    if support.grid_deltas:
        weights["grid_delta"] = GRID_TO_FINISH_WEIGHT

    total = sum(weights.values())
    if total <= 0:
        return weights
    return {signal: weight / total for signal, weight in weights.items()}


def _rank(scored_drivers: list[dict]) -> list[dict]:
    """Sort by score, lowest first, and assign finishing positions."""
    ordered = sorted(scored_drivers, key=lambda d: d["score"])
    return [
        {
            "position": pos,
            "driver_code": driver["driver_code"],
            "driver_name": driver["driver_name"],
            "team": driver["team"],
            "confidence_low": driver["confidence_low"],
            "confidence_high": driver["confidence_high"],
            "factors": driver["factors"],
            "model_attribution": driver.get("model_attribution"),
        }
        for pos, driver in enumerate(ordered, 1)
    ]


def _response(
    year: int,
    round_num: int,
    gp_name: str,
    body: dict[str, Any],
) -> dict:
    """Wrap a prediction body in the fields every response carries."""
    return {
        "year": year,
        "round": round_num,
        "grand_prix": gp_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logic_version": PREDICTION_LOGIC_VERSION,
        "accuracy": get_accuracy_stats(),
        "prediction_review": get_prediction_review(year, round_num),
        **body,
    }


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
    event = _load_event_context(year, round_num)
    session = _load_session_data(year, round_num, event.event_row)
    support = _load_supporting_data(year, round_num, event.circuit_key)
    roster = _build_roster(year, session.quali_data)

    stages = (event, session, support, roster)
    warnings = [warning for stage in stages for warning in stage.warnings]
    data_sources = [source for stage in stages for source in stage.data_sources]

    if not roster.drivers:
        logger.error("predictions.no_driver_data", year=year, round=round_num)
        return _response(
            year,
            round_num,
            event.gp_name,
            {
                "data_sources": data_sources,
                "predictions": [],
                "risk_predictions": [],
                "weather_impact": "unknown",
                "wet_scenario": None,
                "warnings": [*warnings, "No driver data available for predictions"],
            },
        )

    signals = RaceSignals(
        year=year,
        round_num=round_num,
        active_weights=_active_weights(session, support),
        ml_blend_weight=ML_BLEND_WEIGHT,
        adaptive_weight=ADAPTIVE_CORRECTION_WEIGHT,
        circuit_history=support.circuit_history,
        constructor_standings=support.constructor_standings,
        driver_standings=support.driver_standings,
        grid_deltas=support.grid_deltas,
        sprint_positions=support.sprint_positions,
        had_sprint=support.had_sprint,
        recent_sprint_form=support.recent_sprint_form,
        adaptive_corrections=support.adaptive_corrections,
        is_pre_qualifying=session.is_pre_qualifying,
    )

    results = [score_driver(driver, signals) for driver in roster.drivers]
    scored_drivers = [result.scored for result in results]
    scored_by_code = {result.scored["driver_code"]: result.scored for result in results}

    if any(result.used_recent_form for result in results):
        data_sources.append("last_5_races")
    if any(result.used_model for result in results):
        data_sources.append("trained_ml_model")
    if any(result.used_adaptive for result in results):
        data_sources.append("adaptive_history")

    predictions = _rank(scored_drivers)
    result = _response(
        year,
        round_num,
        event.gp_name,
        {
            "data_sources": sorted(set(data_sources)),
            "predictions": predictions,
            "risk_predictions": _compute_risk_predictions(predictions, scored_by_code, year, round_num),
            "prediction_phase": "pre_qualifying" if session.is_pre_qualifying else "post_qualifying",
            "weather_impact": "dry",  # Weather module (Plan 02) will populate this
            "wet_scenario": None,
            "warnings": warnings or None,
        },
    )

    try:
        save_prediction(year, round_num, result)
    except Exception as exc:
        logger.warning("predictions.save_failed", error=str(exc))

    logger.info(
        "predictions.computed",
        year=year,
        round=round_num,
        drivers=len(predictions),
        data_sources=data_sources,
        pre_qualifying=session.is_pre_qualifying,
    )

    return result
