"""Tests for the Results tab payload (app.services.race_results), on real f1db and OpenF1 rows.

Mexico City 2026 (R19): FIA document 86 put Lawson 7th, Piastri 13th, Colapinto 15th and Gasly
17th after time penalties, with five retirements.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data import race_classification as classification_module
from app.data.f1db_grid import GridSlot
from app.services import race_results as module
from app.services.race_results import build_race_results, clock
from tests.openf1_support import make_session, serve

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
DNFS = {"LIN": ("Collision", 58), "BEA": ("Collision damage", 47), "BOT": ("Accident", 42)}


def by_code(session: dict) -> dict[str, dict]:
    return {row["driver_code"]: row for row in session["classification"]}


@pytest.fixture
def no_openf1(monkeypatch):
    monkeypatch.setattr(module, "openf1_session_result", lambda *_args: ([], {}))


@pytest.fixture
def mexico(race_results_f1db, no_openf1):
    return build_race_results(2026, 19)


def test_mexico_is_final_and_has_no_sprint(mexico):
    assert mexico["race"]["final"] is True
    assert mexico["race"]["sources"][0]["source"] == "f1db"
    assert mexico["sprint"] is None


def test_mexico_retirements_have_no_place_but_a_reason_and_laps(mexico):
    rows = by_code(mexico["race"])
    dnfs = [row for row in mexico["race"]["classification"] if row["status"] == "DNF"]

    assert [row["driver_code"] for row in dnfs] == ["LIN", "BEA", "BOT", "STR", "ALO"]
    assert all(row["position"] is None for row in dnfs)
    for code, (reason, laps) in DNFS.items():
        assert (rows[code]["reason"], rows[code]["laps"]) == (reason, laps)
    assert mexico["race"]["classification"][-5:] == dnfs


def test_mexico_winner_has_the_time_and_the_rest_a_gap(mexico):
    rows = by_code(mexico["race"])

    assert (rows["VER"]["position"], rows["VER"]["time"], rows["VER"]["gap"], rows["VER"]["points"]) == (
        1,
        "2:20:28.772",
        None,
        25,
    )
    assert (rows["HAM"]["time"], rows["HAM"]["gap"], rows["HAM"]["points"]) == (None, "+0.799", 18)
    assert rows["LAW"]["points"] == 6
    assert rows["ALB"]["points"] == 0


def test_mexico_time_penalties_carry_the_road_position(mexico):
    rows = by_code(mexico["race"])

    assert [
        (code, rows[code]["position"], rows[code]["time_penalty"], rows[code]["road_position"])
        for code in ("PIA", "COL", "GAS")
    ] == [
        ("PIA", 13, 10, 7),
        ("COL", 15, 10, 8),
        ("GAS", 17, 30, 10),
    ]
    assert rows["VER"]["time_penalty"] is None
    assert rows["VER"]["road_position"] is None


def test_mexico_lists_who_each_penalty_let_past(mexico):
    changes = {change["driver_code"]: change for change in mexico["race"]["changed_after_flag"]}

    assert list(changes) == ["PIA", "COL", "GAS"]
    piastri = changes["PIA"]
    assert (piastri["road_position"], piastri["position"], piastri["time_penalty"]) == (7, 13, 10)
    assert [car["driver_code"] for car in piastri["moved_up"]] == ["LAW", "BOR", "HAD", "HIR", "ALB", "SAI"]
    assert [car["driver_code"] for car in changes["GAS"]["moved_up"]][-1] == "PER"


def test_mexico_fastest_lap_is_hamiltons(mexico):
    rows = by_code(mexico["race"])

    assert mexico["race"]["fastest_lap"] == {
        "driver_code": "HAM",
        "driver_name": "Lewis Hamilton",
        "team": "Ferrari",
        "lap": 50,
        "time": "1:19.268",
    }
    assert [code for code, row in rows.items() if row["fastest_lap"]] == ["HAM"]


def test_a_lapped_car_reads_its_laps_down(race_results_f1db, no_openf1):
    rows = by_code(build_race_results(2026, 18)["race"])

    assert (rows["BOR"]["position"], rows["BOR"]["gap"], rows["BOR"]["laps_down"], rows["BOR"]["time"]) == (
        13,
        "+1 lap",
        1,
        None,
    )


def test_a_sprint_weekend_carries_the_sprint_beside_the_race(race_results_f1db, no_openf1):
    result = build_race_results(2026, 2)

    assert result["race"] is None
    sprint = result["sprint"]
    assert sprint["final"] is True
    assert sprint["fastest_lap"] is None
    assert [(row["driver_code"], row["points"]) for row in sprint["classification"][:3]] == [
        ("RUS", 8),
        ("LEC", 7),
        ("HAM", 6),
    ]


def test_an_unknown_round_has_no_session(race_results_f1db, no_openf1):
    assert build_race_results(2026, 99) == {"year": 2026, "round": 99, "race": None, "sprint": None}


@pytest.mark.parametrize(
    ("text", "status"),
    [("DNF", "DNF"), ("NC", "NC"), ("DNS", "DNS"), ("DSQ", "DSQ"), ("EX", "DSQ"), ("DNQ", "DNS"), ("???", "NC")],
)
def test_every_unclassified_word_reads_as_one_status(text, status):
    row = module.ResultRow("X", "X", "T", None, text, None, None, None, None, None, None, None, None, False)

    assert module._status(row) == status


def test_rows_run_classified_then_nc_then_dnf_by_laps_then_dns_then_dsq():
    def car(code, status, position=None, laps=None):
        return module._Car(code, code, "T", status, position, laps, None, None, None, None, None, 0, False)

    cars = [
        car("S", "DSQ"),
        car("D", "DNS"),
        car("A", "DNF", laps=3),
        car("B", "DNF", laps=40),
        car("N", "NC", laps=60),
    ]
    cars.append(car("W", "Finished", 1, 70))

    session = module._session(2026, cars, {}, None)

    assert [row["driver_code"] for row in session["classification"]] == ["W", "N", "B", "A", "D", "S"]


@pytest.mark.parametrize(
    ("millis", "text"), [(8428772, "2:20:28.772"), (79268, "1:19.268"), (5000, "5.000"), (3_600_000, "1:00:00.000")]
)
def test_clock(millis, text):
    assert clock(millis) == text


# --- OpenF1, before f1db has the race ----------------------------------------------


@pytest.fixture
def openf1(race_results_f1db, monkeypatch):
    """OpenF1 serving Mexico's finished race (and no sprint) for a round f1db does not hold."""
    routes = {
        "session_result": json.loads((FIXTURES / "openf1_session_result.json").read_text()),
        "drivers": json.loads((FIXTURES / "openf1_drivers.json").read_text()),
    }
    sessions = {"R": make_session("R"), "S": None}
    monkeypatch.setattr(classification_module, "find_session", lambda _client, _year, _round, code: sessions[code])
    serve(monkeypatch, classification_module, routes)
    return sessions


def test_before_f1db_has_the_race_openf1_answers_provisional(openf1):
    result = build_race_results(2026, 21)
    race = result["race"]
    rows = by_code(race)

    assert (race["final"], race["sources"], result["sprint"]) == (
        False,
        [{"source": "openf1-session-result", "role": "classification"}],
        None,
    )
    assert (rows["VER"]["position"], rows["VER"]["time"], rows["VER"]["points"]) == (1, "2:20:28.772", 25)
    assert rows["HAM"]["gap"] == "+0.799"
    assert race["changed_after_flag"] == []
    assert race["fastest_lap"] is None


def test_openf1_retirements_have_no_place_and_no_reason(openf1):
    dnfs = [row for row in build_race_results(2026, 21)["race"]["classification"] if row["status"] == "DNF"]

    assert [(row["driver_code"], row["position"], row["reason"], row["laps"]) for row in dnfs] == [
        ("LIN", None, None, 58),
        ("BEA", None, None, 47),
        ("BOT", None, None, 42),
        ("STR", None, None, 5),
        ("ALO", None, None, 5),
    ]
    assert all(row["time_penalty"] is None and row["road_position"] is None for row in dnfs)


def test_openf1_gap_to_leader_reads_seconds_or_laps():
    assert module._openf1_gap(75.5) == ("+1:15.500", None)
    assert module._openf1_gap("+2 LAPS") == ("+2 lap", 2)
    assert module._openf1_gap("DNF") == (None, None)
    assert module._openf1_gap(0) == (None, None)
    assert module._openf1_gap(None) == (None, None)


def test_openf1_car_without_an_entry_keeps_its_number(race_results_f1db):
    row = {"driver_number": 99, "position": 3, "number_of_laps": 70, "dnf": False, "dns": False, "dsq": False}

    car = module._openf1_car(2026, row, {})

    assert (car.code, car.position, car.team, car.time_millis, car.points) == ("99", 3, "", None, None)


# --- the published grid and one session at a time (D1.9) --------------------------


def test_the_official_grid_maps_each_code_to_its_slot_and_a_pit_lane_start_to_none(monkeypatch):
    slots = [
        GridSlot(code, code, "Team", position, None, None, False, position is None)
        for code, position in (("VER", 3), ("LIN", None))
    ]
    monkeypatch.setattr(module, "starting_grid", lambda *_args: tuple(slots))

    assert module.official_grid(2026, 19) == {"VER": 3, "LIN": None}


def test_an_unreadable_grid_is_empty_not_invented(race_results_f1db):
    """The captured results database has no grid columns, so reading the grid fails."""
    assert module.official_grid(2026, 19) == {}


def test_one_session_is_read_without_asking_for_the_other(race_results_f1db, no_openf1):
    assert module.build_session_result(2026, 2, "sprint")["classification"][0]["driver_code"] == "RUS"
    assert module.build_session_result(2026, 19, "sprint") is None
