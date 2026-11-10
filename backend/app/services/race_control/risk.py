"""The risk register: weather exposure and championship-rival pressure.

The weather card is graded from the race session's Open-Meteo forecast and
nothing else. Until 9 Nov 2026 it graded whatever rain figure the weather card
held: with the forecast down that was OpenWeatherMap's current conditions, and
on 6 Nov it read "Dry conditions expected" (5 %) while Open-Meteo forecast ~90 %
for the São Paulo race window. With no race-day forecast the card says so and
why, with no percentage and no dry/wet grade.
"""

from __future__ import annotations

import structlog

from app.api.circuits import is_street_circuit
from app.services.race_control.session_weather import race_day_block
from app.services.race_control.weather import race_day_reason

logger = structlog.get_logger()

# Race-window peak rain probability (%) cut-offs used to grade the weather risk card.
RAIN_RISK_HIGH = 40
RAIN_RISK_MODERATE = 20

# Constructor championship point-gap cut-offs used to grade the rival-offset risk.
RIVAL_GAP_HIGH = 25
RIVAL_GAP_MODERATE = 60

# An unknown forecast is graded Medium: Low would read as dry, the misreading of
# 6 Nov, and High would alarm with nothing behind it. Medium asks for what an
# unknown forecast calls for, keeping both branches ready. The register's three
# grades are the only ones the web colours, and it lists cards in the order given.
NO_FORECAST_LEVEL = "Medium"
NO_FORECAST_TITLE = "Race-day forecast unavailable"
NO_FORECAST_ACTION = "No rain probability to grade: keep both the dry and wet branches ready."


def _rain_grade(rain_pct: int) -> tuple[str, str, str]:
    """The level, title and call for a race-window peak rain probability."""
    if rain_pct >= RAIN_RISK_HIGH:
        return "High", "Elevated rain risk", "prime the wet branch and intermediate crossover"
    if rain_pct >= RAIN_RISK_MODERATE:
        return "Medium", "Mixed conditions possible", "keep the dry/wet crossover branch ready"
    return "Low", "Dry conditions expected", "dry strategy holds as the primary branch"


def _weather_risk(session_weather: dict) -> dict:
    """Grade the weather risk from the race session's forecast in the weekend payload.

    The detail names its source as the race-day card does ("Race-day forecast
    (Open-Meteo)", with "as of HH:MM UTC" when it is the stored copy). With no
    race-day forecast it gives the race-day card's reason and no number.
    """
    block = race_day_block(session_weather)
    if block is None:
        return {
            "level": NO_FORECAST_LEVEL,
            "title": NO_FORECAST_TITLE,
            "detail": f"{race_day_reason(session_weather)} {NO_FORECAST_ACTION}",
        }

    rain_pct = round(block["rain_risk"])
    level, title, call = _rain_grade(rain_pct)
    return {
        "level": level,
        "title": title,
        "detail": f"{block['confidence']}: {rain_pct}% peak rain probability in the race window — {call}.",
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
    session_weather: dict,
    competitors: list[dict],
) -> list[dict]:
    """Assemble the risk register from real event, forecast, and standings state.

    Sprint and street risks come from the event profile; the weather risk is
    graded from the race session's forecast in ``session_weather`` (the weekend
    payload ``build_session_weather`` returns) and the rival risk from the
    constructor gap, so the cards reflect the current situation instead of fixed
    editorial copy.
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
    if is_street_circuit(event["circuit"]):
        risks.append(
            {
                "level": "High",
                "title": "Safety car exposure",
                "detail": "Street circuit profile raises track-position and pit-window volatility.",
            }
        )

    risks.append(_weather_risk(session_weather))
    rival_risk = _rival_risk(competitors)
    if rival_risk:
        risks.append(rival_risk)
    return risks
