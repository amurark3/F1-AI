"""Tests for app.services.profiles and app.services.race_glance.

The f1db side runs against the seeded profiles dataset; the power-unit payload
is a fixture, because what is under test is how cars are chosen for a page:

* a team page shows its own cars, in car-number order;
* a driver page shows every car the driver raced, the rounds that were theirs,
  and who else raced it (FIA B8.2.7: usage belongs to the car);
* a power-unit failure degrades to a reason without taking the page down.
"""

from __future__ import annotations

import pytest

from app.services import profiles
from app.services.profiles import (
    POWER_UNITS_FAILED,
    build_directory,
    build_driver_profile,
    build_team_profile,
)
from app.services.race_glance import build_race_glance

HADJAR = {"id": "isack-hadjar", "name": "Isack Hadjar", "code": "HAD", "car_number": 6}
LAWSON = {"id": "liam-lawson", "name": "Liam Lawson", "code": "LAW", "car_number": 30}
VERSTAPPEN = {"id": "max-verstappen", "name": "Max Verstappen", "code": "VER", "car_number": 1}
LECLERC = {"id": "charles-leclerc", "name": "Charles Leclerc", "code": "LEC", "car_number": 16}


def decision(outcome: str, places: int | None = None) -> dict:
    return {
        "title": "Doc 41 - Decision - Car 6",
        "url": "https://www.fia.com/doc-41.pdf",
        "published": "2026-05-23",
        "number": 41,
        "session": "Race",
        "outcome": outcome,
        "places": places,
        "nominal_places": None,
        "summary": "New ICE beyond the allowance",
        "elements": [{"code": "ICE", "number": 4}],
    }


def event(round_num: int, driver: dict | None, decisions: list[dict] | None = None) -> dict:
    return {"round": round_num, "driver": driver, "decisions": decisions or []}


def car(seat_id: str, number: int, team_id: str, drivers: list[tuple[dict, list[int]]], events: list[dict]) -> dict:
    return {
        "seat_id": seat_id,
        "car_number": number,
        "team": team_id.title(),
        "team_id": team_id,
        "driver": drivers[-1][0],
        "drivers": [{**driver, "rounds": rounds} for driver, rounds in drivers],
        "elements": [],
        "events": events,
        "penalties": {},
    }


CARS = [
    car(
        "red-bull-6",
        6,
        "red-bull",
        [(HADJAR, [1, 3]), (LAWSON, [2])],
        [event(1, HADJAR), event(2, LAWSON, [decision("grid_drop", 10)]), event(3, HADJAR)],
    ),
    car("ferrari-16", 16, "ferrari", [(LECLERC, [1, 2, 3])], [event(2, None, [decision("pit_lane")])]),
    car("red-bull-1", 1, "red-bull", [(VERSTAPPEN, [1, 2, 3])], [event(2, VERSTAPPEN)]),
]

PAYLOAD = {
    "year": 2026,
    "available": True,
    "as_of": {"round": 3, "title": "Doc 50"},
    "elements": [{"code": "ICE", "name": "Internal combustion engine", "allowance": 4}],
    "cars": CARS,
}


@pytest.fixture
def power_units(monkeypatch):
    def install(payload=PAYLOAD):
        monkeypatch.setattr(profiles, "build_power_units", lambda year: payload)

    install()
    return install


def _boom(year):
    raise RuntimeError("store unreachable at db.internal:5432")


@pytest.mark.integration
def test_directory_is_the_season_directory_with_a_status(profiles_f1db):
    payload = build_directory(2027)

    assert payload["status"] == "ok"
    assert payload["year"] == 2027
    assert [driver["id"] for driver in payload["drivers"]] == ["max-verstappen"]


@pytest.mark.integration
def test_team_profile_carries_its_own_cars_in_number_order(profiles_f1db, power_units):
    payload = build_team_profile(2026, "red-bull")

    assert payload["status"] == "ok"
    assert payload["team"]["id"] == "red-bull"
    assert [item["seat_id"] for item in payload["power_units"]["cars"]] == ["red-bull-1", "red-bull-6"]
    assert payload["power_units"]["available"] is True
    assert payload["power_units"]["as_of"] == {"round": 3, "title": "Doc 50"}
    assert payload["power_units"]["elements"] == PAYLOAD["elements"]


@pytest.mark.integration
def test_team_profile_names_the_intel_slug_the_way_intel_keys_teams(profiles_f1db, power_units):
    assert build_team_profile(2026, "red-bull")["intel_slug"] == "red-bull"


@pytest.mark.integration
def test_driver_profile_shows_the_car_with_their_rounds_and_who_shared_it(profiles_f1db, power_units):
    cars = build_driver_profile(2026, "isack-hadjar")["power_units"]["cars"]

    assert [item["seat_id"] for item in cars] == ["red-bull-6"]
    assert cars[0]["driver_rounds"] == [1, 3]
    assert cars[0]["shared_with"] == [{"id": "liam-lawson", "name": "Liam Lawson", "rounds": [2], "rounds_label": "R2"}]


@pytest.mark.integration
def test_a_stand_in_sees_the_regular_drivers_car(profiles_f1db, power_units):
    cars = build_driver_profile(2026, "liam-lawson")["power_units"]["cars"]

    assert cars[0]["seat_id"] == "red-bull-6"
    assert cars[0]["driver_rounds"] == [2]
    assert cars[0]["shared_with"][0]["rounds_label"] == "R1, R3"


@pytest.mark.integration
def test_a_car_raced_by_one_driver_is_shared_with_nobody(profiles_f1db, power_units):
    cars = build_driver_profile(2026, "max-verstappen")["power_units"]["cars"]

    assert [item["seat_id"] for item in cars] == ["red-bull-1"]
    assert cars[0]["shared_with"] == []


@pytest.mark.integration
def test_a_season_without_power_unit_data_says_why(profiles_f1db, power_units):
    power_units({"available": False, "reason": "No FIA documents for 2026 yet.", "cars": []})

    section = build_team_profile(2026, "red-bull")["power_units"]

    assert section == {
        "available": False,
        "reason": "No FIA documents for 2026 yet.",
        "as_of": None,
        "elements": [],
        "cars": [],
    }


@pytest.mark.integration
def test_a_power_unit_failure_leaves_the_rest_of_the_page_standing(profiles_f1db, monkeypatch):
    monkeypatch.setattr(profiles, "build_power_units", _boom)

    payload = build_driver_profile(2026, "isack-hadjar")

    assert payload["status"] == "ok"
    assert payload["driver"]["id"] == "isack-hadjar"
    assert payload["power_units"]["available"] is False
    # The client sees a plain reason, never the exception text.
    assert payload["power_units"]["reason"] == POWER_UNITS_FAILED


@pytest.mark.integration
@pytest.mark.parametrize(
    ("build", "entity_id", "key"),
    [(build_team_profile, "brawn", "team"), (build_driver_profile, "nobody", "driver")],
    ids=["team", "driver"],
)
def test_an_unknown_id_is_not_found_and_skips_the_power_unit_load(profiles_f1db, monkeypatch, build, entity_id, key):
    monkeypatch.setattr(profiles, "build_power_units", _boom)

    assert build(2026, entity_id) == {"year": 2026, "status": "not_found", key: None}


# ---------------------------------------------------------------------------
# race glance
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_glance_lists_the_rounds_decisions_by_car_naming_who_raced_it(profiles_f1db, power_units):
    glance = build_race_glance(2026, 2)

    assert glance["previous"]["year"] == 2025
    assert glance["power_units"]["available"] is True
    decisions = glance["power_units"]["decisions"]
    assert [(item["car_number"], item["outcome"]) for item in decisions] == [(6, "grid_drop"), (16, "pit_lane")]
    # Car 6 was Lawson's that round, not its regular driver's.
    assert decisions[0]["driver"]["id"] == "liam-lawson"
    # No occupant recorded for the round: the car's current driver stands in.
    assert decisions[1]["driver"]["id"] == "charles-leclerc"
    assert decisions[0]["url"] == "https://www.fia.com/doc-41.pdf"
    assert decisions[0]["team_id"] == "red-bull"


@pytest.mark.integration
def test_glance_for_a_round_without_decisions_is_an_empty_list(profiles_f1db, power_units):
    assert build_race_glance(2026, 3)["power_units"] == {"available": True, "reason": None, "decisions": []}


@pytest.mark.integration
def test_glance_without_power_unit_data_still_carries_history(profiles_f1db, monkeypatch):
    monkeypatch.setattr(profiles, "build_power_units", _boom)

    glance = build_race_glance(2026, 2)

    assert glance["previous"]["winner"]["driver_id"] == "charles-leclerc"
    assert glance["power_units"] == {"available": False, "reason": POWER_UNITS_FAILED, "decisions": []}
