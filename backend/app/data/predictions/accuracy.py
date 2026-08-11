"""Rolling accuracy statistics across recent completed races."""

from __future__ import annotations

from dataclasses import dataclass, fields
import statistics

import structlog

from app.data.predictions.history import _load_prediction_history, record_actual_result
from app.data.predictions.review import _latest_prediction_snapshot
from app.data.predictions.scoring import CRASH_RISK_THRESHOLD, DNF_RISK_THRESHOLD, safe_number

logger = structlog.get_logger()

# Podium and points-paying cut-offs the top-N metrics are scored against.
_TOP3 = 3
_TOP10 = 10


def _no_stats() -> dict:
    """The shape returned when there is nothing to evaluate."""
    return {"races_evaluated": 0}


@dataclass(frozen=True)
class RaceTally:
    """Per-race counts that roll up into the accuracy summary.

    Summed rather than accumulated in place: every race produces its own tally
    and the totals are the sum, so no scoring step can corrupt a running total
    that a later step depends on.
    """

    top3_correct: int = 0
    top3_possible: int = 0
    top10_correct: int = 0
    top10_possible: int = 0
    winner_correct: int = 0
    exact_positions: int = 0
    drivers_compared: int = 0
    dnf_correct: int = 0
    dnf_actual: int = 0
    crash_correct: int = 0
    crash_actual: int = 0
    position_errors: tuple[float, ...] = ()

    def __add__(self, other: RaceTally) -> RaceTally:
        """Field-wise sum — ints add, the error tuple concatenates."""
        return RaceTally(
            **{field.name: getattr(self, field.name) + getattr(other, field.name) for field in fields(self)}
        )


def _evaluated_entries(history: dict) -> list[dict]:
    """History entries that carry both a prediction and a recorded result."""
    evaluated = []
    for entry in history.values():
        snapshot = _latest_prediction_snapshot(entry)
        predicted = snapshot.get("predicted_positions")
        actual = entry.get("actual_positions")
        if predicted and actual:
            evaluated.append(
                {
                    "predicted": predicted,
                    "actual": actual,
                    "risk_predictions": snapshot.get("risk_predictions") or {},
                    "actual_incidents": entry.get("actual_incidents") or {},
                    "generated_at": snapshot.get("generated_at") or entry.get("generated_at", ""),
                }
            )
    return evaluated


def _backfill_actuals(history: dict) -> None:
    """Lazily load results for predictions that have none recorded yet."""
    for key, entry in history.items():
        if not entry.get("predicted_positions") or entry.get("actual_positions"):
            continue
        try:
            # Keys are stored as "(year,round)".
            year, round_num = (int(part) for part in key.strip("()").split(","))
            record_actual_result(year, round_num)
        except (ValueError, IndexError) as exc:
            logger.debug("predictions.accuracy_key_unparsable", key=key, error=str(exc))


def _score_race(race: dict) -> RaceTally:
    """Score one race's prediction against what actually happened.

    A race with no driver codes in common contributes an empty tally: it still
    counts as evaluated, but nothing it holds can be compared.
    """
    predicted = race["predicted"]
    actual = race["actual"]
    common = set(predicted) & set(actual)
    if not common:
        return RaceTally()

    predicted_top3 = {code for code, pos in predicted.items() if pos <= _TOP3 and code in common}
    actual_top3 = {code for code, pos in actual.items() if pos <= _TOP3 and code in common}
    predicted_top10 = {code for code, pos in predicted.items() if pos <= _TOP10 and code in common}
    actual_top10 = {code for code, pos in actual.items() if pos <= _TOP10 and code in common}

    incidents = race.get("actual_incidents") or {}
    actual_dnfs = {code for code, flags in incidents.items() if flags.get("dnf")}
    actual_crashes = {code for code, flags in incidents.items() if flags.get("crash")}

    risks = race.get("risk_predictions") or {}
    predicted_dnfs = {
        code for code, risk in risks.items() if safe_number(risk.get("dnf_risk_pct")) >= DNF_RISK_THRESHOLD
    }
    predicted_crashes = {
        code for code, risk in risks.items() if safe_number(risk.get("crash_risk_pct")) >= CRASH_RISK_THRESHOLD
    }

    return RaceTally(
        top3_correct=len(predicted_top3 & actual_top3),
        top3_possible=min(_TOP3, len(predicted_top3)),
        top10_correct=len(predicted_top10 & actual_top10),
        top10_possible=min(_TOP10, len(predicted_top10)),
        winner_correct=int(min(predicted, key=predicted.get) == min(actual, key=actual.get)),
        exact_positions=sum(1 for code in common if predicted[code] == actual[code]),
        drivers_compared=len(common),
        dnf_correct=len(predicted_dnfs & actual_dnfs),
        dnf_actual=len(actual_dnfs),
        crash_correct=len(predicted_crashes & actual_crashes),
        crash_actual=len(actual_crashes),
        position_errors=tuple(abs(predicted[code] - actual[code]) for code in common),
    )


def _percentage(correct: int, possible: int, default: int | None = 0) -> int | None:
    """``correct`` as a percentage of ``possible``, or ``default`` if none were."""
    if possible <= 0:
        return default
    return round(correct / possible * 100)


def _summarise(tally: RaceTally, races_evaluated: int, window: int) -> dict:
    """Turn the summed tally into the reported percentages."""
    return {
        "recent_winner_pct": _percentage(tally.winner_correct, races_evaluated),
        "recent_top3_pct": _percentage(tally.top3_correct, tally.top3_possible),
        "recent_top10_pct": _percentage(tally.top10_correct, tally.top10_possible),
        "exact_position_pct": _percentage(tally.exact_positions, tally.drivers_compared),
        "avg_position_error": round(statistics.mean(tally.position_errors), 1) if tally.position_errors else 0.0,
        # None rather than 0: no DNFs to catch is not a failure to catch them.
        "dnf_capture_pct": _percentage(tally.dnf_correct, tally.dnf_actual, default=None),
        "crash_capture_pct": _percentage(tally.crash_correct, tally.crash_actual, default=None),
        "races_evaluated": races_evaluated,
        "rolling_window": window,
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
        return _no_stats()

    if not history:
        return _no_stats()

    evaluated = _evaluated_entries(history)

    if not evaluated:
        # Nothing scored yet — the results may simply never have been loaded.
        _backfill_actuals(history)
        try:
            history = _load_prediction_history()
        except Exception:
            return _no_stats()
        evaluated = _evaluated_entries(history)

    if not evaluated:
        return _no_stats()

    # Most recent first, then the rolling window.
    evaluated.sort(key=lambda entry: entry.get("generated_at", ""), reverse=True)
    evaluated = evaluated[:last_n_races]

    tally = sum((_score_race(race) for race in evaluated), RaceTally())
    return _summarise(tally, len(evaluated), last_n_races)
