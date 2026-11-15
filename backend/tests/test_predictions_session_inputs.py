"""Tests for the prediction compute's session inputs (app.data.predictions.sessions).

Qualifying, practice pace and the sprint result are the strongest inputs a race
prediction has. None reads FastF1 any more: qualifying and the sprint come from
f1db once it holds the round, else from OpenF1's ``session_result``; practice
pace is each car's best lap in OpenF1's ``laps``.

The data is real:

* São Paulo 2026 (R20), ``fixtures/sao_paulo_2026_r20``: qualifying's
  ``session_result`` (Câmara P13) and Practice 3's laps, drivers and race
  control (two deleted laps, car 51 and car 3), captured 2026-11-14.
* São Paulo 2025 (R21), ``fixtures/sao_paulo_2025_r21/f1db_qualifying_sprint.json``:
  f1db v2026.20.0's qualifying (19 classified cars) and sprint (two retirements
  with no position) rows.
"""

from __future__ import annotations

from contextlib import closing
import json
import sqlite3

import fastf1
import httpx
import pytest
import structlog

from app.data import f1db_sessions
from app.data.canonical_names import CODE_UNRESOLVED
from app.data.f1db_calendar import CalendarUnavailableError
from app.data.openf1 import session_laps
from app.data.openf1.client import OpenF1LiveLockoutError
from app.data.openf1.sessions import ScheduledSession
from app.data.predictions import openf1_qualifying, sessions as sessions_module
from app.data.predictions.compute import _load_session_data
from app.data.predictions.sessions import _load_practice, _load_qualifying, _load_sprint_result
from tests.openf1_support import fresh_cache, serve
from tests.roster_support import SAO_PAULO, load, weekend
from tests.sao_paulo_2026_support import add_camara_to_f1db

SAO_PAULO_2025 = SAO_PAULO.parent / "sao_paulo_2025_r21"
YEAR = 2026
ROUND = 20
PRACTICE_3 = 11407

# Practice 3's best laps by car, struck by hand from fixtures/openf1_laps_practice3.json:
# the smallest lap_duration per driver_number (seconds). Car 51's 1:34.799 and car 3's
# 1:52.648 were deleted for track limits (race control) and are not their best anyway.
R20_FP3_TOP = [("VER", 71.622), ("ANT", 71.647), ("NOR", 71.753), ("RUS", 71.806), ("LEC", 71.896)]
R20_FP3_LAST = ("STR", 74.766)


@pytest.fixture(autouse=True)
def _clear_caches():
    for cache in (sessions_module._qualifying_cache, sessions_module._practice_cache, sessions_module._sprint_cache):
        cache.clear()
    yield
    for cache in (sessions_module._qualifying_cache, sessions_module._practice_cache, sessions_module._sprint_cache):
        cache.clear()


@pytest.fixture(autouse=True)
def no_fastf1(monkeypatch):
    """Any FastF1 request from a loader fails the test."""

    def refuse(*args, **kwargs):
        raise AssertionError("FastF1 was asked for a session")

    monkeypatch.setattr(fastf1, "get_session", refuse)
    monkeypatch.setattr(fastf1.core.Session, "load", refuse)


# --- f1db ------------------------------------------------------------------


@pytest.fixture
def f1db(monkeypatch):
    """An in-memory f1db holding the captured 2025 R21 qualifying and sprint rows."""
    rows = json.loads((SAO_PAULO_2025 / "f1db_qualifying_sprint.json").read_text())
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
        CREATE TABLE driver (id TEXT PRIMARY KEY, name TEXT, abbreviation TEXT);
        CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE race_data (
            race_id INTEGER, type TEXT, driver_id TEXT, constructor_id TEXT,
            position_display_order INTEGER, position_number INTEGER, position_text TEXT,
            practice_time TEXT, practice_gap TEXT, practice_laps INTEGER,
            qualifying_q1 TEXT, qualifying_q2 TEXT, qualifying_q3 TEXT, qualifying_gap TEXT,
            race_time TEXT, race_gap TEXT, race_laps INTEGER, race_points REAL,
            race_grid_position_number INTEGER, race_reason_retired TEXT);
        INSERT INTO race VALUES (2521, 2025, 21);
        """
    )
    for kind, kind_rows in rows.items():
        for row in kind_rows:
            conn.execute("INSERT OR IGNORE INTO driver VALUES (?, ?, ?)", (row["driver_id"], row["name"], row["code"]))
            conn.execute("INSERT OR IGNORE INTO constructor VALUES (?, ?)", (row["constructor_id"], row["team"]))
            conn.execute(
                "INSERT INTO race_data (race_id, type, driver_id, constructor_id, position_display_order,"
                " position_number, position_text) VALUES (2521, ?, ?, ?, ?, ?, ?)",
                (
                    kind,
                    row["driver_id"],
                    row["constructor_id"],
                    row["position_display_order"],
                    row["position_number"],
                    row["position_text"],
                ),
            )
    monkeypatch.setattr(f1db_sessions, "connect", lambda: closing(conn))
    return rows


def test_f1dbs_qualifying_is_read_in_order_without_asking_openf1(f1db, monkeypatch):
    monkeypatch.setattr(sessions_module, "load_openf1_qualifying", lambda *a: pytest.fail("OpenF1 was asked"))

    with structlog.testing.capture_logs() as logs:
        order = _load_qualifying(2025, 21)

    assert order is not None
    assert [(row["position"], row["driver_code"]) for row in order][:3] == [(1, "NOR"), (2, "ANT"), (3, "LEC")]
    assert len(order) == 19
    assert all(set(row) == {"driver_code", "driver_name", "team", "position"} for row in order)
    assert (order[0]["driver_name"], order[0]["team"]) == ("Lando Norris", "McLaren")
    assert [(log["event"], log["source"]) for log in logs if log["event"] == "predictions.qualifying_loaded"] == [
        ("predictions.qualifying_loaded", "f1db")
    ]


def test_f1dbs_sprint_leaves_out_a_retirement_with_no_position(f1db, monkeypatch):
    monkeypatch.setattr(sessions_module, "load_openf1_qualifying", lambda *a: pytest.fail("OpenF1 was asked"))
    unplaced = {row["code"] for row in f1db["SPRINT_RACE_RESULT"] if row["position_number"] is None}

    sprint = _load_sprint_result(2025, 21)

    assert unplaced == {"PIA", "COL"}
    assert len(sprint) == len(f1db["SPRINT_RACE_RESULT"]) - 2
    assert [row["position"] for row in sprint] == list(range(1, len(sprint) + 1))
    assert unplaced.isdisjoint(row["driver_code"] for row in sprint)


def test_an_unreadable_f1db_falls_back_to_openf1_and_says_why(monkeypatch):
    def broken():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(f1db_sessions, "connect", broken)
    monkeypatch.setattr(sessions_module, "load_openf1_qualifying", lambda *a: [{"driver_code": "VER", "position": 1}])

    with structlog.testing.capture_logs() as logs:
        assert _load_qualifying(YEAR, ROUND) == [{"driver_code": "VER", "position": 1}]

    assert next(log["event"] for log in logs) == "predictions.f1db_session_unavailable"


# --- OpenF1 ----------------------------------------------------------------


def _session(code: str):
    return next((session for session in weekend(SAO_PAULO) if session.code == code), None)


@pytest.fixture
def openf1(monkeypatch, identity_f1db):
    """R20's OpenF1: qualifying's result and entry list, Practice 3's laps; f1db holds no R20 rows."""
    add_camara_to_f1db(identity_f1db)
    monkeypatch.setattr(f1db_sessions, "connect", lambda: closing(_empty_f1db()))
    state = {"practice_codes": {"FP3": "FP3"}, "lockout": set(), "asked": []}

    def find(client, year, round_num, code):
        state["asked"].append(code)
        return _session(code if code == "Q" else state["practice_codes"].get(code, "-"))

    monkeypatch.setattr(openf1_qualifying, "find_session", find)
    monkeypatch.setattr(session_laps, "find_session", find)
    fresh_cache(monkeypatch, session_laps)
    serve(
        monkeypatch,
        openf1_qualifying,
        {
            "session_result": load(SAO_PAULO / "openf1_session_result_qualifying.json"),
            "drivers": load(SAO_PAULO / "openf1_drivers_qualifying.json"),
        },
    )
    state["practice"] = serve(
        monkeypatch,
        session_laps,
        {
            "laps": load(SAO_PAULO / "openf1_laps_practice3.json"),
            "drivers": load(SAO_PAULO / "openf1_drivers_practice3.json"),
            "race_control": load(SAO_PAULO / "openf1_race_control_practice3.json"),
        },
    )
    return state


def _empty_f1db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE race (id INTEGER, year INTEGER, round INTEGER); CREATE TABLE driver (id TEXT, name TEXT, abbreviation TEXT);"
        "CREATE TABLE constructor (id TEXT, name TEXT);"
        "CREATE TABLE race_data (race_id INTEGER, type TEXT, driver_id TEXT, constructor_id TEXT, position_display_order INTEGER,"
        " position_number INTEGER, position_text TEXT, practice_time TEXT, practice_gap TEXT, practice_laps INTEGER,"
        " qualifying_q1 TEXT, qualifying_q2 TEXT, qualifying_q3 TEXT, qualifying_gap TEXT, race_time TEXT, race_gap TEXT,"
        " race_laps INTEGER, race_points REAL, race_grid_position_number INTEGER, race_reason_retired TEXT);"
    )
    return conn


def test_r20_qualifying_before_f1db_has_the_round_comes_from_openf1(openf1):
    order = _load_qualifying(YEAR, ROUND)

    assert order is not None
    assert [row["position"] for row in order] == list(range(1, 23))
    assert (order[12]["driver_code"], order[12]["driver_name"], order[12]["team"]) == ("CAM", "Rafael Câmara", "Haas")
    assert _load_qualifying(YEAR, ROUND) is order


def test_qualifying_neither_source_has_yet_is_not_cached(openf1, monkeypatch):
    openf1["practice_codes"] = {}
    monkeypatch.setattr(openf1_qualifying, "find_session", lambda *args: None)

    assert _load_qualifying(YEAR, ROUND) is None
    assert sessions_module._qualifying_cache == {}


def test_r20_practice_pace_is_each_cars_best_lap_in_openf1s_practice_3(openf1):
    ranked = _load_practice(YEAR, ROUND)

    assert ranked is not None
    assert len(ranked) == 22
    assert [(row["driver_code"], row["position"]) for row in ranked[:5]] == [
        (code, position) for position, (code, _) in enumerate(R20_FP3_TOP, 1)
    ]
    assert (ranked[-1]["driver_code"], ranked[-1]["position"]) == (R20_FP3_LAST[0], 22)
    assert (ranked[0]["driver_name"], ranked[0]["team"]) == ("Max Verstappen", "Red Bull")
    assert all(set(row) == {"driver_code", "driver_name", "team", "position"} for row in ranked)
    assert _load_practice(YEAR, ROUND) is ranked
    assert openf1["asked"] == ["FP3"]


def test_the_captured_best_laps_are_what_the_ranking_is_built_from():
    """The hand-check: the fixture's smallest lap per car, in seconds, is the ranking's input."""
    laps = load(SAO_PAULO / "openf1_laps_practice3.json")
    drivers = {row["driver_number"]: row["name_acronym"] for row in load(SAO_PAULO / "openf1_drivers_practice3.json")}
    best: dict[str, float] = {}
    for row in laps:
        if row["lap_duration"]:
            code = drivers[row["driver_number"]]
            best[code] = min(row["lap_duration"], best.get(code, row["lap_duration"]))

    ranked = sorted(best.items(), key=lambda item: item[1])

    assert ranked[:5] == R20_FP3_TOP
    assert ranked[-1] == R20_FP3_LAST


def test_a_deleted_lap_does_not_count_towards_the_best(openf1):
    # Car 3 (VER): strike every lap but the deleted 1:52.648 and it must not be his pace.
    rows = [row for row in load(SAO_PAULO / "openf1_laps_practice3.json") if row["driver_number"] != 3]
    rows.append(
        {"driver_number": 3, "lap_number": 10, "lap_duration": 70.0, "is_pit_out_lap": False, "date_start": None}
    )
    rc = load(SAO_PAULO / "openf1_race_control_practice3.json")
    rc.append({**rc[6], "message": "CAR 3 (VER) TIME 1:10.000 DELETED - TRACK LIMITS AT TURN 4 LAP 10 11:57:43"})
    openf1["practice"].routes["laps"], openf1["practice"].routes["race_control"] = rows, rc

    ranked = _load_practice(YEAR, ROUND)

    assert ranked is not None
    assert "VER" not in {row["driver_code"] for row in ranked}


def test_practice_falls_back_from_fp3_to_fp2_and_skips_a_session_openf1_cannot_give(openf1):
    openf1["practice_codes"] = {"FP2": "FP3"}

    ranked = _load_practice(YEAR, ROUND)

    assert ranked is not None
    assert openf1["asked"] == ["FP3", "FP2"]


def test_a_live_lockout_on_the_newest_session_falls_through_and_is_not_cached(openf1):
    openf1["practice"].routes["laps"] = httpx.Response(401, json={"detail": "live"})

    with structlog.testing.capture_logs() as logs:
        assert _load_practice(YEAR, ROUND) is None

    assert openf1["asked"] == ["FP3", "FP2", "FP1"]
    assert sessions_module._practice_cache == {}
    assert OpenF1LiveLockoutError.__name__
    assert logs[-1]["event"] == "predictions.no_practice_data"


def test_a_session_where_nobody_set_a_time_falls_through(openf1):
    openf1["practice"].routes["laps"] = [
        {"driver_number": 3, "lap_number": 1, "lap_duration": None, "is_pit_out_lap": True, "date_start": None}
    ]

    assert _load_practice(YEAR, ROUND) is None


def test_a_car_with_laps_but_no_entry_keeps_its_place_and_is_labelled(openf1):
    rows = load(SAO_PAULO / "openf1_laps_practice3.json")
    rows.append(
        {"driver_number": 99, "lap_number": 1, "lap_duration": 80.0, "is_pit_out_lap": False, "date_start": None}
    )
    openf1["practice"].routes["laps"] = rows

    ranked = _load_practice(YEAR, ROUND)

    assert ranked is not None
    assert (
        ranked[-1]["position"],
        ranked[-1]["driver_code"],
        ranked[-1][CODE_UNRESOLVED],
        ranked[-1]["driver_number"],
    ) == (
        23,
        "",
        True,
        99,
    )


# --- sprint ----------------------------------------------------------------


def _schedule(codes):
    return tuple(ScheduledSession(code=code, name=code, start=None) for code in codes)


def test_a_conventional_weekend_has_no_sprint_and_is_remembered_so(openf1, monkeypatch):
    monkeypatch.setattr(sessions_module, "weekend_schedule", lambda *a: _schedule(["FP1", "FP2", "FP3", "Q", "R"]))

    assert _load_sprint_result(YEAR, ROUND) == []
    assert sessions_module._sprint_cache == {(YEAR, ROUND): []}
    assert openf1["asked"] == []


def test_a_sprint_f1db_does_not_hold_yet_is_read_from_openf1(openf1, monkeypatch):
    monkeypatch.setattr(sessions_module, "weekend_schedule", lambda *a: _schedule(["FP1", "SQ", "S", "Q", "R"]))
    monkeypatch.setattr(openf1_qualifying, "find_session", lambda client, year, rnd, code: _session("Q"))

    sprint = _load_sprint_result(YEAR, ROUND)

    assert [row["position"] for row in sprint] == list(range(1, 23))
    assert _load_sprint_result(YEAR, ROUND) is sprint


@pytest.mark.parametrize(
    "calendar",
    [CalendarUnavailableError("f1db has no calendar for 2026"), None],
    ids=["calendar-unreadable", "sprint-not-yet-ended"],
)
def test_a_sprint_that_cannot_be_read_yet_is_retried_not_cached(openf1, monkeypatch, calendar):
    def schedule(*args):
        if calendar is not None:
            raise calendar
        return _schedule(["FP1", "SQ", "S", "Q", "R"])

    monkeypatch.setattr(sessions_module, "weekend_schedule", schedule)
    monkeypatch.setattr(openf1_qualifying, "find_session", lambda *args: None)

    assert _load_sprint_result(YEAR, ROUND) == []
    assert sessions_module._sprint_cache == {}


# --- the compute's inputs make no FastF1 request ----------------------------


def test_r20_pre_and_post_qualifying_computes_read_their_inputs_without_fastf1(openf1, monkeypatch):
    """no_fastf1 fails the test on any ``get_session`` or ``Session.load``; both phases run on OpenF1 alone."""
    monkeypatch.setattr(sessions_module, "weekend_schedule", lambda *a: _schedule(["FP1", "FP2", "FP3", "Q", "R"]))

    pre = _load_session_data(YEAR, ROUND, None, forced_pre_qualifying=True)
    post = _load_session_data(YEAR, ROUND, None, forced_pre_qualifying=False)

    assert (pre.data_sources, pre.is_pre_qualifying) == (["practice"], True)
    assert pre.quali_data[0]["driver_code"] == "VER"
    assert (post.data_sources, post.is_pre_qualifying) == (["qualifying"], False)
    assert post.quali_data[12]["driver_code"] == "CAM"
    assert _load_sprint_result(YEAR, ROUND) == []
