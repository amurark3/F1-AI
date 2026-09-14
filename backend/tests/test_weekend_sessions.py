"""Tests for weekend session discovery (app.data.f1db_sessions, app.services.weekend_sessions).

The behaviour under test: a weekend's format is discovered from the sessions
that actually produced a classification, never assumed from a calendar flag. A
sprint weekend runs one practice session, not three, and a conventional one
runs no sprint at all — so the tab set has to follow the data or it will
promise sessions that were never run.
"""

import sqlite3

import pytest

from app.data import f1db_grid, f1db_sessions
from app.data.f1db_sessions import (
    KIND_PRACTICE,
    KIND_QUALIFYING,
    KIND_RACE,
    TYPE_PRACTICE_1,
    TYPE_SPRINT_QUALIFYING,
    TYPE_SPRINT_RACE,
    session_classification,
)
from app.services import weekend_sessions
from app.services.weekend_sessions import build_weekend_sessions

pytestmark = pytest.mark.unit

SCHEMA = """
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
CREATE TABLE driver (id TEXT PRIMARY KEY, name TEXT, abbreviation TEXT);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race_data (
    race_id INTEGER, type TEXT, position_display_order INTEGER,
    position_number INTEGER, position_text TEXT, driver_id TEXT, constructor_id TEXT,
    practice_time TEXT, practice_gap TEXT, practice_laps INTEGER,
    qualifying_q1 TEXT, qualifying_q2 TEXT, qualifying_q3 TEXT, qualifying_gap TEXT,
    race_time TEXT, race_gap TEXT, race_laps INTEGER, race_points REAL,
    race_grid_position_number INTEGER, race_reason_retired TEXT,
    starting_grid_position_qualification_position_number INTEGER,
    starting_grid_position_grid_penalty TEXT,
    starting_grid_position_grid_penalty_positions INTEGER
);
"""

COLUMNS = (
    "race_id, type, position_display_order, position_number, position_text, driver_id, constructor_id,"
    "practice_time, practice_gap, practice_laps, qualifying_q1, qualifying_q2, qualifying_q3, qualifying_gap,"
    "race_time, race_gap, race_laps, race_points, race_grid_position_number, race_reason_retired,"
    "starting_grid_position_qualification_position_number, starting_grid_position_grid_penalty,"
    "starting_grid_position_grid_penalty_positions"
)


class _Seeder:
    """Test handle over the in-memory database: seed rows, run raw SQL."""

    def __init__(self, conn, add):
        self._conn = conn
        self.add = add

    def execute(self, sql, *params):
        return self._conn.execute(sql, *params)


@pytest.fixture
def db(monkeypatch):
    """In-memory f1db with a conventional round 13 and a sprint round 12."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO race VALUES (13, 2026, 13)")
    conn.execute("INSERT INTO race VALUES (12, 2026, 12)")
    conn.execute("INSERT INTO driver VALUES ('leclerc', 'Charles Leclerc', 'LEC')")
    conn.execute("INSERT INTO driver VALUES ('russell', 'George Russell', 'RUS')")
    conn.execute("INSERT INTO constructor VALUES ('ferrari', 'Ferrari')")
    conn.execute("INSERT INTO constructor VALUES ('mercedes', 'Mercedes')")

    def add(race_id, rtype, **cols):
        row = {name.strip(): None for name in COLUMNS.split(",")}
        row.update({
            "race_id": race_id, "type": rtype, "position_display_order": cols.get("order", 1),
            "position_number": cols.get("pos", 1), "position_text": cols.get("ptext", "1"),
            "driver_id": cols.get("driver", "leclerc"), "constructor_id": cols.get("team", "ferrari"),
        })
        for key, value in cols.items():
            if key in row:
                row[key] = value
        names = [name.strip() for name in COLUMNS.split(",")]
        conn.execute(
            f"INSERT INTO race_data ({COLUMNS}) VALUES ({','.join('?' * len(names))})",
            [row[name] for name in names],
        )

    monkeypatch.setattr(f1db_sessions, "connect", lambda: conn)
    monkeypatch.setattr(f1db_grid, "connect", lambda: conn)
    yield _Seeder(conn, add)
    conn.close()


# --- session classification ------------------------------------------------

def test_practice_entry_carries_time_gap_and_laps(db):
    db.add(13, TYPE_PRACTICE_1, practice_time="1:23.008", practice_gap="+0.173", practice_laps=29)

    entry = session_classification(2026, 13, TYPE_PRACTICE_1, KIND_PRACTICE)[0]

    assert (entry.driver_code, entry.time, entry.gap, entry.laps) == ("LEC", "1:23.008", "+0.173", 29)
    # A practice session awards nothing and retires nobody.
    assert (entry.points, entry.retired, entry.grid) == (None, None, None)


def test_qualifying_headline_time_is_the_best_segment_reached(db):
    db.add(12, TYPE_SPRINT_QUALIFYING, qualifying_q1="1:13.2", qualifying_q2="1:12.2", qualifying_q3="1:11.5")

    entry = session_classification(2026, 12, TYPE_SPRINT_QUALIFYING, KIND_QUALIFYING)[0]

    assert entry.time == "1:11.5"
    assert (entry.q1, entry.q2, entry.q3) == ("1:13.2", "1:12.2", "1:11.5")


def test_driver_knocked_out_early_shows_their_last_set_time(db):
    # No Q2 or Q3: the headline must be the Q1 time, not an empty cell.
    db.add(12, TYPE_SPRINT_QUALIFYING, qualifying_q1="1:13.9", qualifying_q2=None, qualifying_q3=None)

    assert session_classification(2026, 12, TYPE_SPRINT_QUALIFYING, KIND_QUALIFYING)[0].time == "1:13.9"


def test_race_entry_carries_points_grid_and_retirement(db):
    db.add(12, TYPE_SPRINT_RACE, race_time="30:25.318", race_gap="+1.360", race_laps=24,
           race_points=8.0, race_grid_position_number=3, race_reason_retired="Collision")

    entry = session_classification(2026, 12, TYPE_SPRINT_RACE, KIND_RACE)[0]

    assert (entry.points, entry.grid, entry.retired) == (8.0, 3, "Collision")


def test_empty_strings_become_null_rather_than_blank_values(db):
    # f1db writes '' rather than NULL for some unset times; rendered into a
    # table an empty string looks like a value that exists.
    db.add(13, TYPE_PRACTICE_1, practice_time="  ", practice_gap="")

    entry = session_classification(2026, 13, TYPE_PRACTICE_1, KIND_PRACTICE)[0]

    assert (entry.time, entry.gap) == (None, None)


def test_unclassified_driver_keeps_their_position_text(db):
    db.add(12, TYPE_SPRINT_RACE, pos=None, ptext="DNF", race_reason_retired="Engine")

    entry = session_classification(2026, 12, TYPE_SPRINT_RACE, KIND_RACE)[0]

    assert (entry.position, entry.position_text, entry.retired) == (None, "DNF", "Engine")


def test_rows_without_a_driver_code_are_dropped(db):
    db.add(13, TYPE_PRACTICE_1, driver="nobody")
    db.execute("INSERT INTO driver VALUES ('nobody', 'No Body', '')")

    assert session_classification(2026, 13, TYPE_PRACTICE_1, KIND_PRACTICE) == ()


# --- weekend assembly ------------------------------------------------------

def test_conventional_weekend_offers_three_practice_sessions_and_no_sprint(db):
    for rtype in ("FREE_PRACTICE_1_RESULT", "FREE_PRACTICE_2_RESULT", "FREE_PRACTICE_3_RESULT"):
        db.add(13, rtype, practice_time="1:23.0")

    payload = build_weekend_sessions(2026, 13)

    assert [session["id"] for session in payload["sessions"]] == ["fp1", "fp2", "fp3"]
    assert payload["is_sprint"] is False


def test_sprint_weekend_offers_one_practice_plus_the_sprint_set(db):
    db.add(12, "FREE_PRACTICE_1_RESULT", practice_time="1:20.0")
    db.add(12, TYPE_SPRINT_QUALIFYING, qualifying_q3="1:11.5")
    db.add(12, "SPRINT_STARTING_GRID_POSITION",
           starting_grid_position_qualification_position_number=1)
    db.add(12, TYPE_SPRINT_RACE, race_points=8.0)

    payload = build_weekend_sessions(2026, 12)

    assert [session["id"] for session in payload["sessions"]] == [
        "fp1", "sprint_qualifying", "sprint_grid", "sprint",
    ]
    # FP2 and FP3 are not offered, because a sprint weekend does not run them.
    assert payload["is_sprint"] is True


def test_sprint_status_follows_the_sprint_result_not_the_schedule(db):
    # Sprint qualifying ran but the sprint itself did not — the weekend cannot
    # claim to be a completed sprint weekend on the strength of a plan.
    db.add(12, TYPE_SPRINT_QUALIFYING, qualifying_q3="1:11.5")

    assert build_weekend_sessions(2026, 12)["is_sprint"] is False


def test_a_cancelled_session_simply_does_not_appear(db):
    db.add(13, "FREE_PRACTICE_1_RESULT", practice_time="1:23.0")
    db.add(13, "FREE_PRACTICE_3_RESULT", practice_time="1:22.0")

    assert [s["id"] for s in build_weekend_sessions(2026, 13)["sessions"]] == ["fp1", "fp3"]


def test_sprint_grid_reports_its_own_penalties(db):
    db.add(12, "SPRINT_STARTING_GRID_POSITION", pos=6, ptext="6",
           starting_grid_position_qualification_position_number=3,
           starting_grid_position_grid_penalty="3",
           starting_grid_position_grid_penalty_positions=3)

    grid = build_weekend_sessions(2026, 12)["sessions"][0]

    assert grid["kind"] == weekend_sessions.KIND_GRID
    assert grid["penalties"][0]["places_lost"] == 3


def test_round_with_nothing_published_says_so(db):
    payload = build_weekend_sessions(2026, 20)

    assert (payload["available"], payload["sessions"]) == (False, [])
    assert payload["warnings"] == [weekend_sessions.NO_SESSIONS_WARNING]
