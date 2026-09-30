"""Street-circuit handling in the Race Control command centre.

The circuit table labels street venues ``"Street circuit"``, but the command
centre compared against ``"Street"``, so no venue ever planned as one: no
safety-car risk card, and permanent-circuit pit-loss and traffic heuristics at
Singapore, Monaco, Baku and Las Vegas.

These tests read the real circuit table rather than a fixture, because a
fixture that invents its own label is exactly how the mismatch went unnoticed.
"""

import pytest

from app.api.circuits import get_circuit_info
from app.services import race_control as rc

pytestmark = pytest.mark.unit

SAFETY_CAR_RISK = "Safety car exposure"
OFFLINE_WEATHER = {"rain_risk": None, "confidence": rc.WEATHER_FEED_OFFLINE}


def _race_at(location: str) -> dict:
    return {
        "round": 17,
        "name": "Test Grand Prix",
        "location": location,
        "status": "upcoming",
        "sessions": {},
        "is_sprint": False,
        "circuit": get_circuit_info(location),
    }


def _risk_titles(location: str) -> list[str]:
    return [
        risk["title"]
        for risk in rc.build_risk_register(_race_at(location), OFFLINE_WEATHER, [])
    ]


def _pit_model(location: str) -> dict:
    return rc.build_strategy_context(_race_at(location), [], None, None)["pit_model"]


def test_street_circuit_raises_the_safety_car_risk():
    assert SAFETY_CAR_RISK in _risk_titles("Marina Bay, Singapore")


def test_permanent_circuit_carries_no_safety_car_risk():
    assert SAFETY_CAR_RISK not in _risk_titles("Sakhir, Bahrain")


def test_street_circuit_plans_on_street_heuristics_without_telemetry():
    pit_model = _pit_model("Marina Bay, Singapore")

    assert pit_model["pit_loss_seconds"] == 24
    assert pit_model["traffic_threshold"] == "high"


def test_permanent_circuit_plans_on_permanent_heuristics_without_telemetry():
    pit_model = _pit_model("Kuala Lumpur, Bahrain")

    assert pit_model["pit_loss_seconds"] == 21
    assert pit_model["traffic_threshold"] == "medium"


def test_semi_street_circuit_plans_as_permanent():
    """Montréal's pit lane is short; the 24s street pit-loss estimate would overstate it."""
    assert _pit_model("Montréal, Canada")["pit_loss_seconds"] == 21
