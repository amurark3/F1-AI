"""Tests for the team shown against each driver in the season standings.

f1db lists one ``season_entrant_driver`` row per team a driver raced for that
season. The standings used to join them all and keep whichever row came back
first — which, through the table's primary key, is alphabetical by *entrant*.
"oracle-red-bull-racing" sorts before "visa-cash-app-racing-bulls…", so Lawson
stayed at Red Bull after returning to Racing Bulls, and would have forever.

The team shown is the one the driver raced for most recently.
"""

import sqlite3

import pytest

from app.data import f1db_standings
from app.data.f1db_standings import driver_standings_detailed

SCHEMA = """
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
CREATE TABLE driver (
    id TEXT PRIMARY KEY, name TEXT, abbreviation TEXT, nationality_country_id TEXT
);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE country (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race_data (
    race_id INTEGER, type TEXT, position_number INTEGER,
    driver_id TEXT, constructor_id TEXT
);
CREATE TABLE race_driver_standing (
    race_id INTEGER, driver_id TEXT, position_number INTEGER, points REAL
);
CREATE TABLE season_entrant_driver (
    year INTEGER, entrant_id TEXT, constructor_id TEXT, driver_id TEXT, rounds TEXT,
    PRIMARY KEY (year, entrant_id, constructor_id, driver_id)
);
"""

# (race id, round) — Hadjar out injured for round 2, back for round 3.
RACES = [(1, 1), (2, 2), (3, 3)]

# (round, driver, team) for every race start.
STARTS = [
    (1, "hadjar", "red-bull"),
    (1, "lawson", "racing-bulls"),
    (2, "lawson", "red-bull"),
    (2, "tsunoda", "racing-bulls"),
    (3, "hadjar", "red-bull"),
    (3, "lawson", "racing-bulls"),
]


RED_BULL_ENTRANT = "oracle-red-bull-racing"
RACING_BULLS_ENTRANT = "visa-cash-app-racing-bulls-formula-one-team"

# (entrant, team, driver, rounds) — keyed like the real table, so a join walks
# them in entrant order and meets Lawson's Red Bull spell first.
SEASON_ENTRIES = [
    (RACING_BULLS_ENTRANT, "racing-bulls", "lawson", "1;3"),
    (RACING_BULLS_ENTRANT, "racing-bulls", "tsunoda", "2"),
    (RACING_BULLS_ENTRANT, "racing-bulls", "reserve", ""),
    (RED_BULL_ENTRANT, "red-bull", "lawson", "2"),
    (RED_BULL_ENTRANT, "red-bull", "hadjar", "1;3"),
]


@pytest.fixture
def standings_db(monkeypatch):
    """An in-memory f1db covering a mid-season seat swap and its reversal."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO race VALUES (?, 2026, ?)", RACES)
    conn.executemany(
        "INSERT INTO driver VALUES (?, ?, ?, NULL)",
        [
            ("hadjar", "Isack Hadjar", "HAD"),
            ("lawson", "Liam Lawson", "LAW"),
            ("tsunoda", "Yuki Tsunoda", "TSU"),
            ("reserve", "Reserve Driver", "RES"),
        ],
    )
    conn.executemany(
        "INSERT INTO constructor VALUES (?, ?)",
        [("red-bull", "Red Bull"), ("racing-bulls", "Racing Bulls")],
    )
    conn.executemany(
        "INSERT INTO race_data VALUES (?, 'RACE_RESULT', NULL, ?, ?)",
        [(round_num, driver, team) for round_num, driver, team in STARTS],
    )
    conn.executemany(
        "INSERT INTO season_entrant_driver VALUES (2026, ?, ?, ?, ?)", SEASON_ENTRIES
    )
    conn.executemany(
        "INSERT INTO race_driver_standing VALUES (3, ?, ?, ?)",
        [
            ("hadjar", 1, 30.0),
            ("lawson", 2, 20.0),
            ("tsunoda", 3, 1.0),
            ("reserve", 4, 0.0),
        ],
    )
    conn.commit()

    # ``connect()`` is used as a context manager, which on a sqlite3 connection
    # commits or rolls back but does not close, so one connection serves the test.
    monkeypatch.setattr(f1db_standings, "connect", lambda: conn)
    yield conn
    conn.close()


def teams(rows):
    return {row["code"]: row["team"] for row in rows}


def test_driver_back_in_their_own_seat_is_shown_at_their_own_team(standings_db):
    assert teams(driver_standings_detailed(2026))["LAW"] == "Racing Bulls"


def test_stand_in_is_shown_at_the_team_they_stood_in_for(standings_db):
    assert teams(driver_standings_detailed(2026))["TSU"] == "Racing Bulls"


def test_driver_who_missed_races_keeps_their_team(standings_db):
    assert teams(driver_standings_detailed(2026))["HAD"] == "Red Bull"


def test_driver_with_no_race_start_falls_back_to_their_season_entry(standings_db):
    assert teams(driver_standings_detailed(2026))["RES"] == "Racing Bulls"


def test_each_driver_appears_once(standings_db):
    codes = [row["code"] for row in driver_standings_detailed(2026)]

    assert codes == ["HAD", "LAW", "TSU", "RES"]
