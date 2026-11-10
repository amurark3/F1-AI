"""Street-circuit handling in the Race Control command centre.

The circuit table labels street venues ``"Street circuit"``, but the command
centre compared against ``"Street"``, so no venue ever planned as one: no
safety-car risk card, and permanent-circuit pit-loss and traffic heuristics at
Singapore, Monaco, Baku and Las Vegas. Those heuristics went in P0b.4 (Nov 2026):
the baseline plan now shows only what the circuit's last edition measured, so
circuit shape sets no pit number at all.

These tests read the real circuit table rather than a fixture, because a
fixture that invents its own label is exactly how the mismatch went unnoticed.
"""

import pytest

from app.api.circuits import get_circuit_info
from app.services import race_control as rc
from app.services.race_control.baseline_plan import build_baseline

pytestmark = pytest.mark.unit

SAFETY_CAR_RISK = "Safety car exposure"
# The weekend forecast with the feed down: the register grades the race-day forecast only.
OFFLINE_FORECAST = {"status": "unavailable", "note": "The forecast feed is unavailable right now.", "sessions": []}


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
    return [risk["title"] for risk in rc.build_risk_register(_race_at(location), OFFLINE_FORECAST, [])]


def _pit_model(location: str) -> dict:
    baseline = build_baseline(2026, None, None)
    return rc.build_strategy_context(_race_at(location), [], baseline)["pit_model"]


def test_street_circuit_raises_the_safety_car_risk():
    assert SAFETY_CAR_RISK in _risk_titles("Marina Bay, Singapore")


def test_permanent_circuit_carries_no_safety_car_risk():
    assert SAFETY_CAR_RISK not in _risk_titles("Sakhir, Bahrain")


@pytest.mark.parametrize("location", ["Marina Bay, Singapore", "Kuala Lumpur, Bahrain", "Montréal, Canada"])
def test_no_circuit_shape_invents_a_pit_figure_without_an_edition(location):
    """Street 24 s and permanent 21 s were guesses; with no edition there is no figure."""
    assert _pit_model(location) == {"pit_lane_seconds": None, "pit_lane_stops": None}
