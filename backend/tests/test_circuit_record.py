"""Tests for app.data.profiles.circuit_record: a circuit's facts and its history.

The seed is Interlagos with five earlier Grands Prix (1973, 2022-2025), this
season's round still to run, and a 2027 edition that must not count as history.
Russell's 2022 win belongs to a 2026 *test* driver and Fittipaldi is not entered
at all, so neither may appear among this season's winners here.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from app.data.profiles.circuit_record import circuit_record

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

SCHEMA = """
CREATE TABLE circuit (
    id TEXT PRIMARY KEY, full_name TEXT, place_name TEXT, length REAL, turns INTEGER, direction TEXT
);
CREATE TABLE driver (id TEXT PRIMARY KEY, name TEXT, last_name TEXT);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race (
    id INTEGER PRIMARY KEY, year INTEGER, round INTEGER, circuit_id TEXT,
    laps INTEGER, distance REAL, course_length REAL, turns INTEGER, direction TEXT
);
CREATE TABLE race_data (
    race_id INTEGER, type TEXT, position_number INTEGER, driver_id TEXT, constructor_id TEXT,
    race_grid_position_number INTEGER, race_pole_position INTEGER
);
CREATE TABLE season_entrant_driver (year INTEGER, driver_id TEXT, test_driver INTEGER);
"""
CIRCUITS = [
    ("interlagos", "Autódromo José Carlos Pace", "São Paulo", 4.309, 15, "ANTI_CLOCKWISE"),
    ("melbourne", "Albert Park Circuit", "Melbourne", 5.278, 14, "CLOCKWISE"),
]
# (id, name, last_name), as f1db stores them.
DRIVERS = [
    ("max-verstappen", "Max Verstappen", "Verstappen"),
    ("lando-norris", "Lando Norris", "Norris"),
    ("george-russell", "George Russell", "Russell"),
    ("emerson-fittipaldi", "Emerson Fittipaldi", "Fittipaldi"),
    ("ronnie-peterson", "Ronnie Peterson", "Peterson"),
]
CONSTRUCTORS = [("red-bull", "Red Bull"), ("mclaren", "McLaren"), ("mercedes", "Mercedes"), ("lotus", "Lotus")]
# (id, year, round, circuit, laps, distance, course length, turns, direction)
RACES = [
    (1, 1973, 2, "interlagos", 40, 318.0, 7.96, 17, "ANTI_CLOCKWISE"),
    (2, 2022, 21, "interlagos", 71, 305.879, 4.309, 15, "ANTI_CLOCKWISE"),
    (3, 2023, 20, "interlagos", 71, 305.879, 4.309, 15, "ANTI_CLOCKWISE"),
    (4, 2024, 21, "interlagos", 69, 297.261, 4.309, 15, "ANTI_CLOCKWISE"),
    (5, 2025, 21, "interlagos", 71, 305.879, 4.309, 15, "ANTI_CLOCKWISE"),
    (6, 2026, 1, "melbourne", 58, 306.124, 5.278, 14, "CLOCKWISE"),
    (7, 2026, 20, "interlagos", 71, 305.879, 4.309, 15, "ANTI_CLOCKWISE"),
    (8, 2027, 20, "interlagos", None, None, None, None, None),
    # A scheduled round whose layout f1db has not filled in yet.
    (9, 2026, 21, "melbourne", None, None, None, None, None),
]
RACE = "RACE_RESULT"
# (race, type, position, driver, team, grid, pole)
RESULTS = [
    (1, RACE, 1, "emerson-fittipaldi", "lotus", 2, 0),
    (1, RACE, 2, "ronnie-peterson", "lotus", 1, 1),
    (2, RACE, 1, "george-russell", "mercedes", 1, 1),
    (3, RACE, 1, "max-verstappen", "red-bull", 1, 1),
    (4, RACE, 1, "max-verstappen", "red-bull", 17, 0),
    (4, RACE, 6, "lando-norris", "mclaren", 1, 1),
    (5, "SPRINT_RACE_RESULT", 1, "max-verstappen", "red-bull", 1, None),
    (5, RACE, 1, "lando-norris", "mclaren", 1, 1),
    (6, RACE, 1, "lando-norris", "mclaren", 3, 0),
]
ENTRANTS = [(2026, "max-verstappen", 0), (2026, "lando-norris", 0), (2026, "george-russell", 1)]


def _seed(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO circuit VALUES (?, ?, ?, ?, ?, ?)", CIRCUITS)
        conn.executemany("INSERT INTO driver VALUES (?, ?, ?)", DRIVERS)
        conn.executemany("INSERT INTO constructor VALUES (?, ?)", CONSTRUCTORS)
        conn.executemany("INSERT INTO race VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", RACES)
        conn.executemany("INSERT INTO race_data VALUES (?, ?, ?, ?, ?, ?, ?)", RESULTS)
        conn.executemany("INSERT INTO season_entrant_driver VALUES (?, ?, ?)", ENTRANTS)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture(autouse=True)
def f1db(tmp_path, monkeypatch):
    from app.data import f1db_source

    monkeypatch.setattr(f1db_source, "DB_PATH", _seed(tmp_path / "f1db.db"))


def test_the_record_carries_the_layout_this_round_runs_on():
    record = circuit_record(2026, 20)

    assert record is not None
    assert {key: value for key, value in record.items() if key not in {"editions", "active_winners"}} == {
        "circuit_id": "interlagos",
        "name": "Autódromo José Carlos Pace",
        "place": "São Paulo",
        "length_km": 4.309,
        "turns": 15,
        "direction": "anti-clockwise",
        "laps": 71,
        "distance_km": 305.879,
        "first_year": 1973,
        "races_held": 5,
        "pole_conversion": {"wins_from_pole": 3, "editions": 5},
    }


def test_editions_run_newest_first_with_the_winners_grid_slot_and_the_pole_sitter():
    editions = circuit_record(2026, 20)["editions"]

    assert [edition["year"] for edition in editions] == [2025, 2024, 2023, 2022, 1973]
    assert editions[1] == {
        "year": 2024,
        "winner": {
            "driver_id": "max-verstappen",
            "driver_name": "Max Verstappen",
            "last_name": "Verstappen",
            "team_id": "red-bull",
            "team_name": "Red Bull",
            "grid": 17,
        },
        "pole": {
            "driver_id": "lando-norris",
            "driver_name": "Lando Norris",
            "last_name": "Norris",
            "team_id": "mclaren",
            "team_name": "McLaren",
        },
        "won_from_pole": False,
    }
    assert editions[0]["won_from_pole"] is True


def test_only_this_seasons_race_drivers_are_listed_among_winners_here():
    assert circuit_record(2026, 20)["active_winners"] == [
        {
            "driver_id": "max-verstappen",
            "driver_name": "Max Verstappen",
            "last_name": "Verstappen",
            "wins": 2,
            "last_win": 2024,
        },
        {
            "driver_id": "lando-norris",
            "driver_name": "Lando Norris",
            "last_name": "Norris",
            "wins": 1,
            "last_win": 2025,
        },
    ]


def test_the_editions_list_can_be_shortened_without_changing_the_counts():
    record = circuit_record(2026, 20, editions=2)

    assert [edition["year"] for edition in record["editions"]] == [2025, 2024]
    assert record["races_held"] == 5
    assert record["pole_conversion"] == {"wins_from_pole": 1, "editions": 2}


def test_a_circuit_with_no_earlier_race_has_an_empty_history():
    record = circuit_record(2026, 1)

    assert record["direction"] == "clockwise"
    assert (record["first_year"], record["races_held"], record["editions"]) == (None, 0, [])
    assert record["pole_conversion"] == {"wins_from_pole": 0, "editions": 0}


def test_a_round_without_layout_details_falls_back_to_the_circuits_own():
    record = circuit_record(2026, 21)

    assert (record["length_km"], record["turns"], record["direction"]) == (5.278, 14, "clockwise")
    assert (record["laps"], record["distance_km"]) == (None, None)


def test_an_unknown_round_has_no_record():
    assert circuit_record(2026, 99) is None
