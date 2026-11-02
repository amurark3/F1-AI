"""A seeded f1db for the Teams & Drivers pages.

The shared ``f1db_fixture`` carries only the columns other modules read, and its
seed is pinned by many tests. The profile pages read more of ``race_data``
(car number, fastest lap, pole) and depend on a season shape it does not have:

* 2026, four rounds, three published. Round 2 is a sprint weekend.
* Red Bull swaps Hadjar out for Lawson at round 2 and back for round 3, and
  lists a reserve (``test_driver = 1``) who must never appear.
* Hadjar retires unclassified in round 1; Hamilton does not start round 2 and
  retires *classified* in round 3 — one retirement, not two.
* Cadillac is entered with a driver but has no result yet and no full name.
* Monaco hosted 2024 and 2025 before 2026, so the latest earlier edition is
  the one the Hub's glance card must pick.
* 2027 has an entry list and nothing else.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SCHEMA = """
CREATE TABLE country (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE grand_prix (id TEXT PRIMARY KEY, name TEXT, full_name TEXT, short_name TEXT);
CREATE TABLE driver (
    id TEXT PRIMARY KEY, name TEXT, full_name TEXT, abbreviation TEXT,
    permanent_number TEXT, nationality_country_id TEXT
);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT, full_name TEXT);
CREATE TABLE race (
    id INTEGER PRIMARY KEY, year INTEGER, round INTEGER, date TEXT,
    grand_prix_id TEXT, circuit_id TEXT
);
CREATE TABLE race_data (
    race_id INTEGER, type TEXT, position_display_order INTEGER,
    position_number INTEGER, position_text TEXT, driver_number TEXT,
    driver_id TEXT, constructor_id TEXT, race_points REAL,
    race_grid_position_number INTEGER, race_positions_gained INTEGER,
    race_reason_retired TEXT, race_fastest_lap INTEGER, race_pole_position INTEGER
);
CREATE TABLE race_driver_standing (race_id INTEGER, position_number INTEGER, driver_id TEXT, points REAL);
CREATE TABLE race_constructor_standing (
    race_id INTEGER, position_number INTEGER, constructor_id TEXT, points REAL
);
CREATE TABLE season_entrant_driver (
    year INTEGER, driver_id TEXT, constructor_id TEXT, rounds TEXT, test_driver INTEGER
);
"""

GRANDS_PRIX = [
    ("australia", "Australia", "Australian Grand Prix", "Australian GP"),
    ("monaco", "Monaco", "Monaco Grand Prix", "Monaco GP"),
    ("italy", "Italy", "Italian Grand Prix", None),
    ("singapore", "Singapore", "Singapore Grand Prix", "Singapore GP"),
]

DRIVERS = [
    ("max-verstappen", "Max Verstappen", "VER", "1", "netherlands"),
    ("isack-hadjar", "Isack Hadjar", "HAD", "6", "france"),
    ("liam-lawson", "Liam Lawson", "LAW", "30", "new-zealand"),
    ("ayumu-iwasa", "Ayumu Iwasa", "IWA", None, None),
    ("charles-leclerc", "Charles Leclerc", "LEC", "16", "monaco"),
    ("lewis-hamilton", "Lewis Hamilton", "HAM", "44", None),
    ("sergio-perez", "Sergio Pérez", "PER", "11", None),
]

CONSTRUCTORS = [
    ("red-bull", "Red Bull", "Red Bull Racing"),
    ("ferrari", "Ferrari", "Scuderia Ferrari"),
    ("cadillac", "Cadillac", None),
]

# (id, year, round, date, grand prix, circuit)
RACES = [
    (1, 2026, 1, "2026-03-08", "australia", "melbourne"),
    (2, 2026, 2, "2026-05-24", "monaco", "monaco"),
    (3, 2026, 3, "2026-09-06", "italy", "monza"),
    (4, 2026, 4, "2026-10-04", "singapore", "marina-bay"),
    (10, 2024, 8, "2024-05-26", "monaco", "monaco"),
    (11, 2025, 8, "2025-05-25", "monaco", "monaco"),
    # A 2025 Monza on the calendar with no result must not count as history.
    (12, 2025, 16, "2025-09-07", "italy", "monza"),
]

RACE = "RACE_RESULT"
SPRINT = "SPRINT_RACE_RESULT"

# (race, type, order, position, text, number, driver, team, points, grid,
#  gained, reason, fastest lap, pole)
RESULTS = [
    (1, RACE, 1, 1, "1", "1", "max-verstappen", "red-bull", 25, 1, 0, None, 1, 1),
    (1, RACE, 2, 2, "2", "16", "charles-leclerc", "ferrari", 18, 2, 0, None, 0, 0),
    (1, RACE, 3, 3, "3", "44", "lewis-hamilton", "ferrari", 15, 4, 1, None, 0, 0),
    (1, RACE, 4, None, "DNF", "6", "isack-hadjar", "red-bull", None, 3, None, "Engine", 0, 0),
    (2, SPRINT, 1, 1, "1", "1", "max-verstappen", "red-bull", 8, 1, 0, None, None, None),
    (2, SPRINT, 2, 2, "2", "30", "liam-lawson", "red-bull", 7, 3, 1, None, None, None),
    (2, RACE, 1, 1, "1", "16", "charles-leclerc", "ferrari", 25, 1, 0, None, 0, 1),
    (2, RACE, 2, 2, "2", "1", "max-verstappen", "red-bull", 18, 2, 0, None, 1, 0),
    (2, RACE, 3, 3, "3", "30", "liam-lawson", "red-bull", 15, 5, 2, None, 0, 0),
    (2, RACE, 4, None, "DNS", "44", "lewis-hamilton", "ferrari", None, None, None, "Hydraulics", 0, 0),
    (3, RACE, 1, 1, "1", "6", "isack-hadjar", "red-bull", 25, 5, 4, None, 0, 0),
    (3, RACE, 2, 2, "2", "16", "charles-leclerc", "ferrari", 18, 1, -1, None, 1, 1),
    (3, RACE, 3, 3, "3", "1", "max-verstappen", "red-bull", 15, 2, -1, None, 0, 0),
    (3, RACE, 4, 4, "4", "44", "lewis-hamilton", "ferrari", 12, 3, -1, "Gearbox", 0, 0),
    # A qualifying row must not be read as a result.
    (3, "QUALIFYING_RESULT", 1, 1, "1", "16", "charles-leclerc", "ferrari", None, None, None, None, None, None),
    (10, RACE, 1, 1, "1", "44", "lewis-hamilton", "ferrari", 25, 2, 1, None, 0, 0),
    (10, RACE, 2, 2, "2", "16", "charles-leclerc", "ferrari", 18, 1, -1, None, 0, 1),
    # 2025 Monaco: Leclerc wins from second, Verstappen took pole.
    (11, RACE, 1, 1, "1", "16", "charles-leclerc", "ferrari", 25, 2, 1, None, 0, 0),
    (11, RACE, 2, 2, "2", "1", "max-verstappen", "red-bull", 18, 1, -1, None, 1, 1),
]

DRIVER_STANDINGS = [
    (2, 1, "max-verstappen", 51.0),
    (2, 2, "charles-leclerc", 43.0),
    (3, 1, "max-verstappen", 66.0),
    (3, 2, "charles-leclerc", 61.0),
    (3, 3, "lewis-hamilton", 27.0),
    (3, 4, "isack-hadjar", 25.0),
    (3, 5, "liam-lawson", 22.0),
]

CONSTRUCTOR_STANDINGS = [
    (2, 1, "red-bull", 73.0),
    (2, 2, "ferrari", 58.0),
    (3, 1, "red-bull", 128.0),
    (3, 2, "ferrari", 88.0),
]

ENTRANTS = [
    (2026, "max-verstappen", "red-bull", "1;2;3", 0),
    (2026, "isack-hadjar", "red-bull", "1;3", 0),
    (2026, "liam-lawson", "red-bull", "2", 0),
    (2026, "ayumu-iwasa", "red-bull", "", 1),
    (2026, "charles-leclerc", "ferrari", "1;2;3", 0),
    (2026, "lewis-hamilton", "ferrari", "1;2;3", 0),
    (2026, "sergio-perez", "cadillac", "", 0),
    (2027, "max-verstappen", "red-bull", "", 0),
    (2027, "ayumu-iwasa", "red-bull", "", 1),
]


def build_profiles_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO country (id, name) VALUES (?, ?)",
            [("netherlands", "Netherlands"), ("france", "France"), ("monaco", "Monaco")],
        )
        conn.executemany("INSERT INTO grand_prix (id, name, full_name, short_name) VALUES (?, ?, ?, ?)", GRANDS_PRIX)
        conn.executemany(
            "INSERT INTO driver (id, name, abbreviation, permanent_number, nationality_country_id) VALUES (?, ?, ?, ?, ?)",
            DRIVERS,
        )
        conn.executemany("INSERT INTO constructor (id, name, full_name) VALUES (?, ?, ?)", CONSTRUCTORS)
        conn.executemany(
            "INSERT INTO race (id, year, round, date, grand_prix_id, circuit_id) VALUES (?, ?, ?, ?, ?, ?)", RACES
        )
        conn.executemany(
            """INSERT INTO race_data (race_id, type, position_display_order, position_number, position_text,
                                      driver_number, driver_id, constructor_id, race_points,
                                      race_grid_position_number, race_positions_gained, race_reason_retired,
                                      race_fastest_lap, race_pole_position)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            RESULTS,
        )
        conn.executemany(
            "INSERT INTO race_driver_standing (race_id, position_number, driver_id, points) VALUES (?, ?, ?, ?)",
            DRIVER_STANDINGS,
        )
        conn.executemany(
            "INSERT INTO race_constructor_standing (race_id, position_number, constructor_id, points) VALUES (?, ?, ?, ?)",
            CONSTRUCTOR_STANDINGS,
        )
        conn.executemany(
            "INSERT INTO season_entrant_driver (year, driver_id, constructor_id, rounds, test_driver) VALUES (?, ?, ?, ?, ?)",
            ENTRANTS,
        )
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def profiles_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point f1db at the profiles dataset, with no directory or table cached from elsewhere.

    The dataset is all there is: no OpenF1 round is published past it, so every
    standings table it serves is f1db's own, confirmed.
    """
    from app.data import current_standings, f1db_source, identity
    from app.utils.ttl_cache import TtlCache

    db_path = build_profiles_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    monkeypatch.setattr(current_standings, "later_rounds", lambda _year, _after: ())
    monkeypatch.setattr(current_standings, "_cache", TtlCache())
    identity.clear_cache()
    yield db_path
    identity.clear_cache()
