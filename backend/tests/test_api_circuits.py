"""Tests for app.api.circuits — the static circuit metadata lookup.

The table is keyed by FastF1's ``Location`` field, which is not stable across
seasons or endpoints: the same venue arrives as ``"Monte Carlo"``, ``"Monaco"``
or ``"Monte Carlo, Monaco"`` depending on the caller. The aliases and the
city-part fallback exist for that, and a lookup miss is not cosmetic — it is
what silently drops weather from a race weekend, since the GPS coordinates
used for the forecast come from here.
"""

from __future__ import annotations

import pytest

from app.api.circuits import CIRCUIT_DATA, get_circuit_gps, get_circuit_info

# Venues the calendar reports under more than one Location string. Each pair
# must resolve to the same circuit, or the same race gets two identities.
ALIAS_PAIRS = [
    ("Monte Carlo", "Monaco"),
    ("Miami", "Miami Gardens"),
    ("Mogyoród", "Budapest"),
    ("Spa-Francorchamps", "Stavelot"),
    ("Marina Bay", "Singapore"),
    ("Yas Island", "Abu Dhabi"),
    ("Yas Island", "Yas Marina"),
]


@pytest.mark.unit
def test_exact_location_is_returned_directly():
    info = get_circuit_info("Silverstone")

    assert info is not None
    assert info["circuit_name"] == "Silverstone Circuit"
    assert info["laps"] == 52


@pytest.mark.unit
def test_city_part_is_used_when_the_full_location_is_not_a_key():
    # The schedule reports "Sakhir, Bahrain"; only "Sakhir" is a table key.
    info = get_circuit_info("Sakhir, Bahrain")

    assert info is not None
    assert info["circuit_name"] == "Bahrain International Circuit"


@pytest.mark.unit
def test_city_part_lookup_tolerates_surrounding_whitespace():
    assert get_circuit_info("  Monza  , Italy") == CIRCUIT_DATA["Monza"]


@pytest.mark.unit
def test_unknown_location_returns_none_rather_than_a_guess():
    assert get_circuit_info("Nürburgring") is None
    assert get_circuit_info("") is None


@pytest.mark.unit
@pytest.mark.parametrize(("primary", "alias"), ALIAS_PAIRS)
def test_venue_aliases_resolve_to_the_same_circuit(primary, alias):
    assert get_circuit_info(primary) == get_circuit_info(alias)


@pytest.mark.unit
def test_gps_is_returned_as_a_lat_lon_pair():
    coords = get_circuit_gps("Monza")

    assert coords == (CIRCUIT_DATA["Monza"]["lat"], CIRCUIT_DATA["Monza"]["lon"])


@pytest.mark.unit
def test_gps_falls_back_to_the_city_part():
    assert get_circuit_gps("Austin, USA") == get_circuit_gps("Austin")


@pytest.mark.unit
def test_gps_returns_none_for_an_unknown_venue():
    assert get_circuit_gps("Nürburgring, Germany") is None


@pytest.mark.unit
def test_gps_returns_none_when_an_entry_carries_no_coordinates(monkeypatch):
    """A venue added without lat/lon must be skipped, not crash the forecast."""
    monkeypatch.setitem(CIRCUIT_DATA, "Testville", {"circuit_name": "Test Circuit"})

    assert get_circuit_gps("Testville") is None
    assert get_circuit_gps("Testville, Nowhere") is None


@pytest.mark.unit
def test_every_circuit_carries_coordinates_for_the_weather_lookup():
    missing = [name for name, data in CIRCUIT_DATA.items() if "lat" not in data or "lon" not in data]

    assert missing == [], f"circuits without GPS silently lose weather: {missing}"


@pytest.mark.unit
def test_every_circuit_has_plausible_coordinates():
    for name, data in CIRCUIT_DATA.items():
        assert -90 <= data["lat"] <= 90, f"{name} latitude out of range"
        assert -180 <= data["lon"] <= 180, f"{name} longitude out of range"


@pytest.mark.unit
def test_every_circuit_has_the_fields_the_race_detail_response_reads():
    required = {"circuit_name", "track_length_km", "laps", "lap_record", "first_gp", "circuit_type"}

    for name, data in CIRCUIT_DATA.items():
        assert required <= set(data), f"{name} is missing {required - set(data)}"


@pytest.mark.unit
def test_lap_records_name_a_driver_and_a_year():
    for name, data in CIRCUIT_DATA.items():
        record = data["lap_record"]
        assert set(record) == {"time", "driver", "year"}, f"{name} lap_record shape"
