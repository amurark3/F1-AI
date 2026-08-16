"""Turning raw signals into a score, a confidence band and a risk profile.

Pure computation over already-loaded data — nothing here performs I/O, which is
what makes the weighting easy to reason about and to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import statistics
from typing import Any

import structlog

from app.data.predictions.incidents import _load_recent_incidents

logger = structlog.get_logger()


# Risk percentages at or above which a prediction counts as having called the
# incident. Shared so the post-race review and the rolling accuracy stats score
# the same prediction the same way.
DNF_RISK_THRESHOLD = 16
CRASH_RISK_THRESHOLD = 10


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


def _compute_confidence(inputs: list[float], is_pre_qualifying: bool = False) -> tuple[int, int]:
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


@dataclass(frozen=True)
class FactorInputs:
    """The signals the human-readable reasoning factors are drawn from."""

    quali_pos: int | None = None
    recent_positions: list[int] = field(default_factory=list)
    circuit_positions: list[int] = field(default_factory=list)
    team_pos: int = 10
    grid_delta: float = 0.0
    is_pre_qualifying: bool = False
    sprint_pos: int | None = None


# Each builder returns one weighted phrase, or None when it has nothing to say.
# The weight is what ranks it against the other factors, not a score input.
Factor = tuple[float, str]


def _sprint_factor(inputs: FactorInputs) -> Factor | None:
    """Sprint result — the heaviest signal available, being same-weekend data."""
    position = inputs.sprint_pos
    if position is None:
        return None
    if position == 1:
        return (6.0, "Won the sprint race this weekend")
    if position <= 3:
        return (5.0, f"Sprint race podium (P{position})")
    if position <= 8:
        return (3.5, f"Points finish in sprint (P{position})")
    return (1.5, f"Sprint race P{position}")


def _practice_factor(position: int) -> Factor:
    """Pace read from practice, before qualifying has run."""
    if position <= 3:
        return (3.0, f"Strong practice pace (P{position} in sessions)")
    if position <= 10:
        return (1.5, f"Midfield practice pace (P{position})")
    return (0.5, f"Practice pace P{position}")


def _qualifying_factor(inputs: FactorInputs) -> Factor | None:
    """Grid position, or practice pace when qualifying has not happened yet."""
    position = inputs.quali_pos
    if position is None:
        return None
    if inputs.is_pre_qualifying:
        return _practice_factor(position)
    if position == 1:
        return (5.0, "Pole position (qualifying P1)")
    if position <= 3:
        return (4.0, f"Front row start (qualifying P{position})")
    if position <= 5:
        return (2.5, f"Strong qualifying (P{position})")
    if position <= 10:
        return (1.5, f"Qualifying P{position}")
    return (0.5, f"Qualifying P{position}")


def _recent_form_factor(inputs: FactorInputs) -> Factor | None:
    """Form over the driver's most recent races."""
    positions = inputs.recent_positions
    if not positions:
        return None

    average = _safe_mean(positions)
    wins = sum(1 for position in positions if position == 1)
    podiums = sum(1 for position in positions if position <= 3)
    count = len(positions)

    if wins >= 2:
        return (4.0, f"Won {wins} of last {count} races")
    if podiums >= 2:
        return (3.0, f"{podiums} podiums in last {count} races")
    if average <= 5:
        return (2.5, f"Strong recent form (avg P{average:.0f})")
    if average <= 10:
        return (1.5, f"Consistent points finisher (avg P{average:.0f})")
    return (0.5, f"Recent average P{average:.0f}")


def _circuit_factor(inputs: FactorInputs) -> Factor:
    """Record at this circuit — an explicit note when there is no history."""
    positions = inputs.circuit_positions
    if not positions:
        return (0.3, "No prior results at this circuit")

    average = _safe_mean(positions)
    best = min(positions)
    count = len(positions)

    if best == 1:
        return (4.5, f"Previous winner at this circuit (best P1 in last {count} editions)")
    if best <= 3:
        return (3.5, f"Podium history here (best P{best} in last {count} editions)")
    if average <= 6:
        return (2.0, f"Good circuit record (avg P{average:.0f} over {count} editions)")
    return (1.0, f"Circuit history avg P{average:.0f}")


def _team_factor(inputs: FactorInputs) -> Factor:
    """Constructor strength."""
    position = inputs.team_pos
    if position <= 2:
        return (3.0, f"Top team (constructor P{position})")
    if position <= 5:
        return (1.5, f"Midfield team (constructor P{position})")
    return (0.5, f"Constructor standing P{position}")


def _grid_delta_factor(inputs: FactorInputs) -> Factor | None:
    """Whether this driver historically gains or loses places at this track."""
    delta = inputs.grid_delta
    if delta > 1.5:
        return (2.0, f"Historically gains ~{delta:.0f} positions at this track")
    if delta < -1.5:
        return (1.0, f"Tends to lose ~{abs(delta):.0f} positions here")
    return None


# Evaluation order is also the tie-break order: sorting is stable, so two
# factors of equal weight stay in the sequence listed here.
_FACTOR_BUILDERS = (
    _sprint_factor,
    _qualifying_factor,
    _recent_form_factor,
    _circuit_factor,
    _team_factor,
    _grid_delta_factor,
)


def _generate_factors(inputs: FactorInputs) -> list[str]:
    """Generate top 3 reasoning factors from dominant scoring components."""
    candidates = (builder(inputs) for builder in _FACTOR_BUILDERS)
    ranked = sorted((factor for factor in candidates if factor), key=lambda factor: factor[0], reverse=True)
    return [text for _, text in ranked[:3]]


def _get_team_position(team_name: str, standings: list[dict]) -> int:
    """Map a team name to its constructor championship position.

    Uses fuzzy matching since FastF1 and Ergast may use slightly different
    team names (e.g. 'Red Bull Racing' vs 'Red Bull').
    """
    team_lower = team_name.strip().lower()
    if not team_lower:
        return 10  # unknown team: the empty string substring-matches every name
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


@dataclass(frozen=True)
class RiskContext:
    """Per-driver inputs behind the risk narrative."""

    profile: dict[str, Any]
    quali_pos: int
    team_pos: int
    sprint_pos: int | None


def _risk_factors(context: RiskContext, dnf_risk: int, crash_risk: int) -> list[str]:
    profile = context.profile
    factors: list[str] = []
    if profile.get("dnfs", 0) > 0:
        factors.append(f"{profile['dnfs']} DNF events in recent history")
    if profile.get("crashes", 0) > 0:
        factors.append(f"{profile['crashes']} accident/collision flags in recent history")
    if 8 <= context.quali_pos <= 16:
        factors.append("Starts in the highest traffic band")
    elif context.quali_pos <= 4:
        factors.append("Front group restart exposure")
    if context.team_pos >= 7:
        factors.append(f"Lower constructor reliability proxy (P{context.team_pos})")
    if context.sprint_pos is None:
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
            6 + profile["dnf_rate"] * 31 + profile["mechanical_rate"] * 18 + constructor_risk + traffic_risk
        )
        crash_risk = round(3 + profile["crash_rate"] * 26 + traffic_risk * 1.2 + (2 if 10 <= quali_pos <= 18 else 0))
        mechanical_risk = round(max(2, dnf_risk - crash_risk * 0.45))

        dnf_risk = max(3, min(42, dnf_risk))
        crash_risk = max(1, min(30, crash_risk))
        mechanical_risk = max(2, min(35, mechanical_risk))

        risk_rows.append(
            {
                "driver_code": code,
                "driver_name": prediction["driver_name"],
                "team": prediction["team"],
                "projected_finish": prediction["position"],
                "dnf_risk_pct": dnf_risk,
                "crash_risk_pct": crash_risk,
                "mechanical_risk_pct": mechanical_risk,
                "risk_level": _risk_level(dnf_risk),
                "factors": _risk_factors(
                    RiskContext(
                        profile=profile,
                        quali_pos=quali_pos,
                        team_pos=team_pos,
                        sprint_pos=sprint_pos,
                    ),
                    dnf_risk,
                    crash_risk,
                ),
            }
        )

    risk_rows.sort(key=lambda row: (row["dnf_risk_pct"], row["crash_risk_pct"]), reverse=True)
    return risk_rows
