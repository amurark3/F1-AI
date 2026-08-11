"""Side-by-side comparison of a stored prediction against the real result."""

from __future__ import annotations

from dataclasses import dataclass
import statistics

import structlog

from app.data.predictions.history import _load_prediction_history, record_actual_result
from app.data.predictions.scoring import CRASH_RISK_THRESHOLD, DNF_RISK_THRESHOLD, safe_number

logger = structlog.get_logger()


@dataclass(frozen=True)
class ReviewLookups:
    """Per-driver detail joined onto each predicted-vs-actual row.

    All three are keyed by driver code and all three are optional per driver,
    so they travel together rather than as parallel arguments of the same shape.
    """

    statuses: dict
    incidents: dict
    risks: dict


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


def _position_value(value: object) -> int | None:
    """Coerce a stored position (int, float or string) to an int, else None."""
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _build_driver_results(predicted: dict, actual: dict, lookups: ReviewLookups) -> list[dict]:
    """Per-driver predicted-vs-actual rows, ordered by where the driver finished.

    Drivers appear even when only one side has them (a non-starter that was
    predicted, or a substitute that raced) so the table never silently drops a
    call the model made.
    """
    rows = []
    for code in set(predicted) | set(actual):
        predicted_position = _position_value(predicted.get(code))
        actual_position = _position_value(actual.get(code))
        delta = (
            actual_position - predicted_position
            if predicted_position is not None and actual_position is not None
            else None
        )
        flags = lookups.incidents.get(code) or {}
        risk = lookups.risks.get(code) or {}
        rows.append(
            {
                "driver_code": code,
                "predicted_position": predicted_position,
                "actual_position": actual_position,
                # Positive means the driver finished lower down than predicted.
                "position_delta": delta,
                "exact": delta == 0,
                "status": lookups.statuses.get(code) or None,
                "dnf": bool(flags.get("dnf")),
                "crash": bool(flags.get("crash")),
                "predicted_dnf_risk_pct": risk.get("dnf_risk_pct"),
            }
        )

    # Unclassified drivers sort last, keeping the finishing order readable.
    rows.sort(
        key=lambda row: (
            row["actual_position"] is None,
            row["actual_position"] if row["actual_position"] is not None else 0,
            row["predicted_position"] if row["predicted_position"] is not None else 0,
        )
    )
    return rows


def get_prediction_review(year: int, round_num: int) -> dict:
    """Post-race review, loading the actual result first when it is missing.

    Use :func:`build_prediction_review` on request paths that must not pay for
    a FastF1 session load.
    """
    record_actual_result(year, round_num)
    return build_prediction_review(year, round_num)


def build_prediction_review(year: int, round_num: int) -> dict:
    """Compare the latest saved prediction with the recorded race result.

    Reads stored history only — never fetches the actual result — so it is safe
    to call while serving a request.
    """
    key = f"({year},{round_num})"

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
        code for code, risk in risks.items() if safe_number(risk.get("dnf_risk_pct")) >= DNF_RISK_THRESHOLD
    }
    predicted_crashes = {
        code for code, risk in risks.items() if safe_number(risk.get("crash_risk_pct")) >= CRASH_RISK_THRESHOLD
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
        "driver_results": _build_driver_results(
            predicted,
            actual,
            ReviewLookups(
                statuses=entry.get("actual_statuses") or {},
                incidents=incidents,
                risks=risks,
            ),
        ),
    }
