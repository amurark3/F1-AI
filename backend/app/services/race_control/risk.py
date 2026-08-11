"""The risk register: weather exposure and championship-rival pressure."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# Rain probability (%) cut-offs used to grade the live weather risk card.
RAIN_RISK_HIGH = 40
RAIN_RISK_MODERATE = 20

# Constructor championship point-gap cut-offs used to grade the rival-offset risk.
RIVAL_GAP_HIGH = 25
RIVAL_GAP_MODERATE = 60


def _weather_risk(weather: dict | None) -> dict:
    """Grade the weather risk from the live forecast block.

    Falls back to an honest "feed offline" Medium risk when no live rain
    probability is available, rather than asserting a confirmation task that
    may already be resolved.
    """
    rain = (weather or {}).get("rain_risk")
    if not isinstance(rain, (int, float)):
        return {
            "level": "Medium",
            "title": "Weather feed offline",
            "detail": "Live forecast unavailable — confirm dry/wet branches manually before lock.",
        }

    rain_pct = round(rain)
    if rain_pct >= RAIN_RISK_HIGH:
        return {
            "level": "High",
            "title": "Elevated rain risk",
            "detail": f"Live forecast shows {rain_pct}% rain probability — prime the wet branch and intermediate crossover.",
        }
    if rain_pct >= RAIN_RISK_MODERATE:
        return {
            "level": "Medium",
            "title": "Mixed conditions possible",
            "detail": f"Live forecast shows {rain_pct}% rain probability — keep the dry/wet crossover branch ready.",
        }
    return {
        "level": "Low",
        "title": "Dry conditions expected",
        "detail": f"Live forecast shows {rain_pct}% rain probability — dry strategy holds as the primary branch.",
    }


def _rival_risk(competitors: list[dict]) -> dict | None:
    """Grade the rival-offset risk from the real constructor championship gap.

    Returns ``None`` when there is no trailing rival to plan against (e.g. an
    empty standings snapshot), so the panel never shows a rival task that no
    data supports.
    """
    rivals = [row for row in (competitors or []) if row.get("rank", 0) > 1]
    if not rivals:
        return None

    closest = min(rivals, key=lambda row: row.get("gap_to_leader", float("inf")))
    gap = closest.get("gap_to_leader")
    team = closest.get("team", "the nearest rival")
    if not isinstance(gap, (int, float)):
        return None

    gap_pts = round(gap)
    if gap_pts <= RIVAL_GAP_HIGH:
        return {
            "level": "High",
            "title": "Rival offset plans",
            "detail": f"{team} is within {gap_pts} pts — rehearse undercut and overcut responses for direct track battles.",
        }
    if gap_pts <= RIVAL_GAP_MODERATE:
        return {
            "level": "Medium",
            "title": "Rival offset plans",
            "detail": f"{team} trails by {gap_pts} pts — prepare undercut and overcut responses for the closest rival.",
        }
    return {
        "level": "Low",
        "title": "Rival offset plans",
        "detail": f"Nearest rival ({team}) trails by {gap_pts} pts — lower direct championship pressure this round.",
    }


def build_risk_register(
    event: dict | None,
    weather: dict | None,
    competitors: list[dict],
) -> list[dict]:
    """Assemble the risk register from real event, weather, and standings state.

    Sprint and street risks come from the event profile; the weather and rival
    risks are graded from the live forecast block and the constructor gap so the
    cards reflect the current situation instead of fixed editorial copy.
    """
    if not event:
        return []

    risks = []
    if event["is_sprint"]:
        risks.append(
            {
                "level": "High",
                "title": "Sprint format compression",
                "detail": "Reduced practice time increases setup and parc ferme decision pressure.",
            }
        )
    if event["circuit"] and event["circuit"].get("circuit_type") == "Street":
        risks.append(
            {
                "level": "High",
                "title": "Safety car exposure",
                "detail": "Street circuit profile raises track-position and pit-window volatility.",
            }
        )

    risks.append(_weather_risk(weather))
    rival_risk = _rival_risk(competitors)
    if rival_risk:
        risks.append(rival_risk)
    return risks
