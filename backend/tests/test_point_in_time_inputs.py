"""Tests that a race is predicted only from what was known before it.

Recomputing a finished race — a manual recompute, or backfilling a season —
used to read the *latest* championship tables and learn adaptive corrections
from every evaluated race, the predicted race included. Round 3 recomputed
after round 15 therefore knew round 3's result and twelve rounds of standings
that did not exist when it was run.

For the upcoming race nothing changes: everything before it is everything
there is.
"""

import sqlite3

import pytest

from app.data import f1db_standings
from app.data import predictions as predictions_module
from app.data.f1db_standings import (
    constructor_standings_before_round,
    driver_standings_before_round,
)

pytestmark = pytest.mark.unit

SCHEMA = """
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
CREATE TABLE driver (id TEXT PRIMARY KEY, abbreviation TEXT);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race_driver_standing (race_id INTEGER, driver_id TEXT, position_number INTEGER);
CREATE TABLE race_constructor_standing (
    race_id INTEGER, constructor_id TEXT, position_number INTEGER
);
"""

# (race id, year, round). 2026 round 4 is on the calendar but f1db has not
# released its standings yet.
RACES = [(100, 2025, 24), (1, 2026, 1), (2, 2026, 2), (3, 2026, 3), (4, 2026, 4)]

# race id -> (driver order, constructor order), leader first. The lead swaps
# every round, so each lookup has exactly one right answer.
STANDINGS = {
    100: (["verstappen", "norris"], ["red-bull", "mclaren"]),
    1: (["norris", "verstappen"], ["mclaren", "red-bull"]),
    2: (["verstappen", "norris"], ["red-bull", "mclaren"]),
    3: (["norris", "verstappen"], ["mclaren", "red-bull"]),
}


@pytest.fixture
def standings_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO race VALUES (?, ?, ?)", RACES)
    conn.executemany(
        "INSERT INTO driver VALUES (?, ?)", [("verstappen", "VER"), ("norris", "NOR")]
    )
    conn.executemany(
        "INSERT INTO constructor VALUES (?, ?)",
        [("red-bull", "Red Bull"), ("mclaren", "McLaren")],
    )
    for race_id, (drivers, constructors) in STANDINGS.items():
        conn.executemany(
            "INSERT INTO race_driver_standing VALUES (?, ?, ?)",
            [(race_id, driver, pos) for pos, driver in enumerate(drivers, 1)],
        )
        conn.executemany(
            "INSERT INTO race_constructor_standing VALUES (?, ?, ?)",
            [(race_id, team, pos) for pos, team in enumerate(constructors, 1)],
        )
    conn.commit()

    monkeypatch.setattr(f1db_standings, "connect", lambda: conn)
    monkeypatch.setattr(f1db_standings, "_driver_cache", {})
    monkeypatch.setattr(f1db_standings, "_constructor_cache", {})
    monkeypatch.setattr(predictions_module, "_driver_standings_cache", {})
    monkeypatch.setattr(predictions_module, "_constructor_cache", {})
    yield conn
    conn.close()


def leader(standings: dict[str, int]) -> str:
    return min(standings, key=standings.get)


# ---------------------------------------------------------------------------
# Standings going into a round
# ---------------------------------------------------------------------------

def test_standings_going_into_a_round_are_those_after_the_previous_round(standings_db):
    assert leader(driver_standings_before_round(2026, 3)) == "VER"


def test_standings_never_include_the_round_being_predicted(standings_db):
    assert leader(driver_standings_before_round(2026, 2)) == "NOR"


def test_unreleased_previous_round_falls_back_to_the_latest_released(standings_db):
    # Going into round 5, round 4 has run but f1db stops at round 3.
    assert leader(driver_standings_before_round(2026, 5)) == "NOR"


def test_season_opener_uses_the_previous_season_final_table(standings_db):
    assert leader(driver_standings_before_round(2026, 1)) == "VER"


def test_season_missing_from_f1db_returns_nothing_for_live_fallback(standings_db):
    # Empty, so the caller's live Ergast fallback still runs for a season f1db
    # has not reached — rather than silently serving last season's table.
    assert driver_standings_before_round(2027, 4) == {}


def test_constructor_standings_going_into_a_round(standings_db):
    rows = constructor_standings_before_round(2026, 3)

    assert rows[0]["constructor_name"] == "Red Bull"


def test_constructor_standings_for_the_season_opener(standings_db):
    rows = constructor_standings_before_round(2026, 1)

    assert rows[0]["constructor_name"] == "Red Bull"


def test_prediction_loaders_read_standings_as_of_the_round(standings_db):
    assert leader(predictions_module._load_driver_standings(2026, 2)) == "NOR"
    assert leader(predictions_module._load_driver_standings(2026, 3)) == "VER"
    assert predictions_module._load_constructor_standings(2026, 2)[0]["constructor_name"] == "McLaren"
    assert predictions_module._load_constructor_standings(2026, 3)[0]["constructor_name"] == "Red Bull"


# ---------------------------------------------------------------------------
# Adaptive corrections learn only from earlier races
# ---------------------------------------------------------------------------

def _evaluated(predicted: int, actual: int) -> dict:
    return {
        "snapshots": [{"predicted_positions": {"VER": predicted}}],
        "actual_positions": {"VER": actual},
    }


def _corrections(monkeypatch, history: dict, year: int, round_num: int) -> dict:
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)
    return predictions_module._adaptive_position_corrections(year, round_num)


def test_adaptive_correction_ignores_the_race_being_predicted(monkeypatch):
    history = {
        "(2026,1)": _evaluated(predicted=1, actual=1),
        "(2026,2)": _evaluated(predicted=1, actual=1),
        "(2026,3)": _evaluated(predicted=1, actual=7),
    }

    correction = _corrections(monkeypatch, history, 2026, 3)["VER"]

    assert correction == {"correction": 0.0, "samples": 2}


def test_adaptive_correction_ignores_later_races(monkeypatch):
    history = {
        "(2026,1)": _evaluated(predicted=1, actual=2),
        "(2026,9)": _evaluated(predicted=1, actual=7),
        "(2027,1)": _evaluated(predicted=1, actual=7),
    }

    correction = _corrections(monkeypatch, history, 2026, 5)["VER"]

    assert correction == {"correction": 1.0, "samples": 1}


def test_adaptive_correction_window_is_the_most_recent_races_not_the_newest_keys(monkeypatch):
    # The oldest race was written last, so in storage order it looks newest.
    history = {f"(2026,{round_num})": _evaluated(predicted=1, actual=1) for round_num in range(1, 7)}
    history["(2025,24)"] = _evaluated(predicted=1, actual=7)

    correction = _corrections(monkeypatch, history, 2026, 7)["VER"]

    assert correction == {"correction": 0.0, "samples": 6}


def test_adaptive_correction_skips_unparseable_keys(monkeypatch):
    history = {
        "legacy": _evaluated(predicted=1, actual=7),
        "(2026,1)": _evaluated(predicted=1, actual=2),
    }

    correction = _corrections(monkeypatch, history, 2026, 2)["VER"]

    assert correction == {"correction": 1.0, "samples": 1}
