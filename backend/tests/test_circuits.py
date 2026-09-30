"""Tests for the static circuit metadata lookup.

The schedule names a venue by ``"<Location>, <Country>"``. The country follows
the Grand Prix, not the track: the 2026 Bahrain Grand Prix runs at Sepang, so
FastF1 files it as ``"Kuala Lumpur, Bahrain"``. The lookup must resolve on the
city alone so a relocated round still finds its circuit.
"""

import pytest

from app.api.circuits import get_circuit_gps, get_circuit_info, is_street_circuit

pytestmark = pytest.mark.unit

RELOCATED_BAHRAIN = "Kuala Lumpur, Bahrain"


def test_relocated_bahrain_grand_prix_resolves_to_sepang():
    circuit = get_circuit_info(RELOCATED_BAHRAIN)

    assert circuit is not None
    assert circuit["circuit_name"] == "Sepang International Circuit"
    assert circuit["laps"] == 56


def test_relocated_bahrain_grand_prix_has_sepang_coordinates_for_weather():
    coords = get_circuit_gps(RELOCATED_BAHRAIN)

    assert coords is not None
    lat, lon = coords
    # Sepang sits just north of the equator, south of Kuala Lumpur.
    assert lat == pytest.approx(2.76, abs=0.05)
    assert lon == pytest.approx(101.74, abs=0.05)


def test_sakhir_still_resolves_to_the_bahrain_international_circuit():
    circuit = get_circuit_info("Sakhir, Bahrain")

    assert circuit is not None
    assert circuit["circuit_name"] == "Bahrain International Circuit"


def test_unknown_venue_has_no_circuit_metadata():
    assert get_circuit_info("Nowhere, Atlantis") is None
    assert get_circuit_gps("Nowhere, Atlantis") is None


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Marina Bay, Singapore", True),
        ("Monte Carlo, Monaco", True),
        ("Baku, Azerbaijan", True),
        ("Las Vegas, United States", True),
        ("Sakhir, Bahrain", False),
        ("Kuala Lumpur, Bahrain", False),
        # Semi-street: public roads, but a short permanent-style pit lane.
        ("Montréal, Canada", False),
    ],
)
def test_is_street_circuit_reads_the_table_label(location, expected):
    assert is_street_circuit(get_circuit_info(location)) is expected


def test_venue_without_metadata_is_not_a_street_circuit():
    assert is_street_circuit(None) is False
