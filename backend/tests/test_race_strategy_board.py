"""Tests for stints and pit stops (app.data.f1db_pitstops, app.data.race_stints,
app.services.race_strategy_board).

Two behaviours under test. First, a duplicated pit-stop row must not read as a
second stop: the in-progress 2026 f1db release writes nine stops twice under
different display orders, and rendered straight a driver appears to have boxed
twice on the same lap. Second, the two sources are joined on (driver, lap)
without either being able to fabricate the other — a race can have stops
published before its timing data is cached, and vice versa.
"""

import sqlite3

import pandas as pd
import pytest

from app.data import f1db_pitstops
from app.data import race_stints as stints_module
from app.data.f1db_pitstops import race_pit_stops
from app.data.race_stints import Stint, race_stints
from app.services import race_strategy_board
from app.services.race_strategy_board import build_race_strategy

pytestmark = pytest.mark.unit

SCHEMA = """
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
CREATE TABLE driver (id TEXT PRIMARY KEY, abbreviation TEXT);
CREATE TABLE race_data (
    race_id INTEGER, type TEXT, position_display_order INTEGER, driver_id TEXT,
    pit_stop_stop INTEGER, pit_stop_lap INTEGER, pit_stop_time TEXT, pit_stop_time_millis INTEGER
);
"""


@pytest.fixture
def pit_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO race VALUES (1, 2026, 13)")
    for did, code in (("leclerc", "LEC"), ("lawson", "LAW")):
        conn.execute("INSERT INTO driver VALUES (?, ?)", (did, code))

    order = {"n": 0}

    def add(driver, stop, lap, time, millis):
        order["n"] += 1
        conn.execute(
            "INSERT INTO race_data VALUES (1,'PIT_STOP',?,?,?,?,?,?)",
            (order["n"], driver, stop, lap, time, millis),
        )

    monkeypatch.setattr(f1db_pitstops, "connect", lambda: conn)
    yield add
    conn.close()


# --- pit stops -------------------------------------------------------------

def test_reads_stops_in_lap_order(pit_db):
    pit_db("leclerc", 1, 19, "21.825", 21825)
    pit_db("lawson", 1, 12, "31.197", 31197)

    assert [(s.driver_code, s.lap) for s in race_pit_stops(2026, 13)] == [("LAW", 12), ("LEC", 19)]


def test_a_duplicated_row_is_not_a_second_stop(pit_db):
    # The exact 2026 artifact: same driver, stop and lap, two display orders.
    pit_db("lawson", 2, 12, "31.197", 31197)
    pit_db("lawson", 2, 12, "31.197", 31197)

    stops = race_pit_stops(2026, 13)

    assert len(stops) == 1
    assert (stops[0].stop, stops[0].lap) == (2, 12)


def test_two_real_stops_on_the_same_lap_are_both_kept(pit_db):
    # Different drivers boxing on the same lap is an ordinary double-stack,
    # not a duplicate — de-duplication must key on the driver too.
    pit_db("leclerc", 1, 19, "21.8", 21800)
    pit_db("lawson", 1, 19, "22.4", 22400)

    assert len(race_pit_stops(2026, 13)) == 2


def test_rows_without_a_lap_or_stop_number_are_skipped(pit_db):
    pit_db("leclerc", None, 19, "21.8", 21800)
    pit_db("lawson", 1, None, "22.4", 22400)

    assert race_pit_stops(2026, 13) == ()


def test_blank_time_becomes_null(pit_db):
    pit_db("leclerc", 1, 19, "   ", None)

    stop = race_pit_stops(2026, 13)[0]
    assert (stop.time, stop.millis) == (None, None)


def test_race_with_no_stops_returns_nothing(pit_db):
    assert race_pit_stops(2026, 99) == ()


# --- stints ----------------------------------------------------------------

class FakeSession:
    def __init__(self, laps, results=None):
        self.laps = laps
        self.results = results if results is not None else pd.DataFrame()

    def load(self, **_kwargs):
        return None


def lap_frame(rows):
    return pd.DataFrame(rows, columns=["Driver", "LapNumber", "Stint", "Compound", "TyreLife", "FreshTyre", "Team", "TrackStatus"])


@pytest.fixture
def fake_fastf1(monkeypatch):
    # Stints are cached for the life of the process, so each test starts from
    # an empty cache or it would read the previous test's race.
    monkeypatch.setattr(stints_module, "_cache", {})
    monkeypatch.setattr(stints_module, "_empty_until", {})
    state = {"session": None, "raise": None}

    def get_session(year, rnd, kind):
        if state["raise"] is not None:
            raise state["raise"]
        return state["session"]

    monkeypatch.setattr(stints_module.fastf1, "get_session", get_session)
    return state


def test_collapses_laps_into_one_row_per_stint(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([
        ("LEC", 1, 1.0, "MEDIUM", 1, True, "Ferrari", "1"),
        ("LEC", 2, 1.0, "MEDIUM", 2, True, "Ferrari", "1"),
        ("LEC", 3, 2.0, "HARD", 1, True, "Ferrari", "1"),
    ]))

    result = race_stints(2024, 6)

    assert [(s.stint, s.compound, s.start_lap, s.end_lap, s.laps) for s in result] == [
        (1, "MEDIUM", 1, 2, 2),
        (2, "HARD", 3, 3, 1),
    ]


def test_team_travels_with_the_stint_for_livery_tinting(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([("LEC", 1, 1.0, "HARD", 0, True, "Ferrari", "1")]))

    assert race_stints(2024, 6)[0].team == "Ferrari"


def test_reports_a_scrubbed_set_as_not_fresh(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([("PIA", 1, 1.0, "MEDIUM", 2, False, "Ferrari", "1")]))

    stint = race_stints(2024, 6)[0]

    assert (stint.tyre_life_start, stint.fresh) == (2, False)


def test_missing_tyre_history_is_unknown_not_fresh(fake_fastf1):
    # NaN is truthy: coercing it straight to bool would claim an unrecorded
    # set was new.
    fake_fastf1["session"] = FakeSession(lap_frame([("PIA", 1, 1.0, "HARD", float("nan"), float("nan"), "Ferrari", "1")]))

    stint = race_stints(2024, 6)[0]

    assert (stint.tyre_life_start, stint.fresh) == (None, None)


def test_unknown_compound_is_null_rather_than_a_label(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([("PIA", 1, 1.0, "UNKNOWN", 1, True, "Ferrari", "1")]))

    assert race_stints(2024, 6)[0].compound is None


def test_driver_number_is_mapped_to_the_three_letter_code(fake_fastf1):
    fake_fastf1["session"] = FakeSession(
        lap_frame([("16", 1, 1.0, "HARD", 1, True, "Ferrari", "1")]),
        pd.DataFrame([{"Abbreviation": "LEC", "DriverNumber": "16"}]),
    )

    assert race_stints(2024, 6)[0].driver_code == "LEC"


def test_a_results_row_without_an_abbreviation_is_skipped(fake_fastf1):
    """A blank abbreviation must not become a lookup key.

    Mapping "" onto a driver number would let an unrelated lap frame keyed by
    a missing value resolve to whichever driver happened to be blank.
    """
    fake_fastf1["session"] = FakeSession(
        lap_frame([("16", 1, 1.0, "HARD", 1, True, "Ferrari", "1")]),
        pd.DataFrame([
            {"Abbreviation": "", "DriverNumber": "99"},
            {"Abbreviation": "LEC", "DriverNumber": "16"},
        ]),
    )

    assert race_stints(2024, 6)[0].driver_code == "LEC"


def test_laps_without_a_stint_number_are_ignored(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([("LEC", 1, float("nan"), "HARD", 1, True, "Ferrari", "1")]))

    assert race_stints(2024, 6) == ()


def test_empty_lap_frame_yields_no_stints(fake_fastf1):
    fake_fastf1["session"] = FakeSession(lap_frame([]))

    assert race_stints(2024, 6) == ()


def test_a_session_that_cannot_load_degrades_to_no_stints(fake_fastf1):
    fake_fastf1["raise"] = RuntimeError("session has not been loaded")

    assert race_stints(2026, 22) == ()


def test_a_loaded_race_is_served_from_cache_on_the_next_call(fake_fastf1, monkeypatch):
    """A FastF1 load costs ~28s warm, so it must happen once per race.

    The stints of a finished race never change, which is what makes caching
    them for the life of the process correct rather than merely convenient.
    """
    loads = {"n": 0}
    frame = lap_frame([("LEC", 1, 1.0, "HARD", 0, True, "Ferrari", "1")])

    def counting_get_session(year, rnd, kind):
        loads["n"] += 1
        return FakeSession(frame)

    monkeypatch.setattr(stints_module.fastf1, "get_session", counting_get_session)

    first = race_stints(2024, 6)
    second = race_stints(2024, 6)

    assert loads["n"] == 1
    assert first == second


def test_an_empty_result_is_not_reloaded_within_the_retry_window(fake_fastf1, monkeypatch):
    """An unrun race must not re-cost a FastF1 load on every request."""
    loads = {"n": 0}

    def counting_get_session(year, rnd, kind):
        loads["n"] += 1
        return FakeSession(lap_frame([]))

    monkeypatch.setattr(stints_module.fastf1, "get_session", counting_get_session)

    assert race_stints(2026, 22) == ()
    assert race_stints(2026, 22) == ()

    assert loads["n"] == 1


def test_an_empty_result_is_retried_rather_than_pinned(fake_fastf1):
    """A race that has not run yet must not be cached as "no stints" forever."""
    fake_fastf1["session"] = FakeSession(lap_frame([]))
    assert race_stints(2026, 22) == ()

    # The retry window lapses, and the race has since run.
    stints_module._empty_until.clear()
    fake_fastf1["session"] = FakeSession(lap_frame([("LEC", 1, 1.0, "HARD", 0, True, "Ferrari", "1")]))

    assert len(race_stints(2026, 22)) == 1


# --- the joined board ------------------------------------------------------

def stint(code, number, start, end, red_flag=False):
    return Stint(
        driver_code=code, team="Ferrari", stint=number, compound="HARD", start_lap=start, end_lap=end,
        laps=end - start + 1, tyre_life_start=0, fresh=True, ended_under_red_flag=red_flag,
    )


@pytest.fixture
def board(monkeypatch):
    state = {"stints": (), "stops": (), "results": {}}
    monkeypatch.setattr(race_strategy_board, "race_stints", lambda y, r: state["stints"])
    monkeypatch.setattr(race_strategy_board, "race_pit_stops", lambda y, r: state["stops"])
    monkeypatch.setattr(race_strategy_board, "race_results", lambda y, r: state["results"])
    return state


def test_drivers_are_ordered_by_finishing_position(board):
    """A strategy chart is read against the result it produced.

    Alphabetical order put ALB above the race winner, which says nothing about
    the race.
    """
    board["stints"] = (stint("ALB", 1, 1, 53), stint("VER", 1, 1, 53), stint("NOR", 1, 1, 53))
    board["results"] = {"VER": 1, "NOR": 2, "ALB": 12}

    codes = [d["driver_code"] for d in build_race_strategy(2024, 6)["drivers"]]

    assert codes == ["VER", "NOR", "ALB"]


def test_an_unplaced_driver_sorts_to_the_bottom_stably(board):
    """A driver the result does not place is not "first alphabetically"."""
    board["stints"] = (stint("ZHO", 1, 1, 53), stint("ALB", 1, 1, 53), stint("VER", 1, 1, 53))
    board["results"] = {"VER": 1}

    rows = build_race_strategy(2024, 6)["drivers"]

    assert [d["driver_code"] for d in rows] == ["VER", "ALB", "ZHO"]
    assert rows[0]["finish_position"] == 1
    # Absent, not a sentinel: "not placed" differs from "finished 999th".
    assert rows[1]["finish_position"] is None


def test_a_race_with_no_published_result_keeps_a_stable_order(board):
    board["stints"] = (stint("VER", 1, 1, 53), stint("ALB", 1, 1, 53))
    board["results"] = {}

    assert [d["driver_code"] for d in build_race_strategy(2024, 6)["drivers"]] == ["ALB", "VER"]


def test_the_stop_that_ended_a_stint_is_attached_to_it(board, pit_db):
    pit_db("leclerc", 1, 19, "21.825", 21825)
    board["stints"] = (stint("LEC", 1, 1, 19), stint("LEC", 2, 20, 57))
    board["stops"] = race_pit_stops(2026, 13)

    driver = build_race_strategy(2024, 6)["drivers"][0]

    assert driver["stints"][0]["ended_by_stop"]["time"] == "21.825"
    # The last stint ends at the flag, not in the pit lane.
    assert driver["stints"][1]["ended_by_stop"] is None
    assert driver["stops"] == 1
    assert driver["timed_stops"] == 1


def test_a_red_flag_tyre_change_is_not_a_pit_stop(board):
    """A suspended race sends the whole field to the pit lane for free.

    Monza 2026 was red-flagged on lap 3: every one of the 21 cars changed
    tyres, producing a stint boundary and a PitInTime each. Counting those as
    stops reported three stops for a driver who made one, and made the chart
    disagree with the published stop sheet by a factor of three.
    """
    board["stints"] = (
        stint("ALO", 1, 1, 3, red_flag=True),
        stint("ALO", 2, 4, 23),
    )

    driver = build_race_strategy(2026, 13)["drivers"][0]

    assert driver["stops"] == 0
    assert driver["red_flag_changes"] == 1


def test_a_red_flag_change_and_a_real_stop_are_counted_apart(board):
    board["stints"] = (
        stint("ALB", 1, 1, 3, red_flag=True),
        stint("ALB", 2, 4, 46),
        stint("ALB", 3, 47, 52),
    )

    driver = build_race_strategy(2026, 13)["drivers"][0]

    assert (driver["stops"], driver["red_flag_changes"]) == (1, 1)


def test_the_race_reports_both_totals(board):
    board["stints"] = (
        stint("ALB", 1, 1, 3, red_flag=True),
        stint("ALB", 2, 4, 46),
        stint("ALB", 3, 47, 52),
        stint("ALO", 1, 1, 3, red_flag=True),
        stint("ALO", 2, 4, 23),
    )

    payload = build_race_strategy(2026, 13)

    # ALB stopped once for real; ALO's only change was the red flag.
    assert payload["stops_made"] == 1
    assert payload["red_flag_changes"] == 2
    assert any("red-flagged" in w for w in payload["warnings"])


def test_an_incomplete_stop_sheet_is_flagged_not_hidden(board, pit_db):
    """f1db can publish fewer stop times than the race actually had."""
    board["stints"] = (stint("ALB", 1, 1, 20), stint("ALB", 2, 21, 40), stint("ALB", 3, 41, 53))
    board["stops"] = ()

    payload = build_race_strategy(2026, 13)

    assert payload["stops_made"] == 2
    assert any("published stationary time" in w for w in payload["warnings"])


def test_a_tyre_change_counts_as_a_stop_even_with_no_published_time(board):
    """Two stints means a stop happened, whatever the stop sheet carries.

    Counting published rows instead reported "0 stops" beside a chart showing
    two compounds — a claim about the race made from a gap in the data.
    """
    board["stints"] = (stint("ALO", 1, 1, 20), stint("ALO", 2, 21, 53))

    driver = build_race_strategy(2024, 6)["drivers"][0]

    assert driver["stops"] == 1
    assert driver["timed_stops"] == 0


def test_a_one_stint_race_is_a_no_stop_race(board):
    board["stints"] = (stint("VER", 1, 1, 53),)

    assert build_race_strategy(2024, 6)["drivers"][0]["stops"] == 0


def test_driver_row_carries_the_team(board):
    board["stints"] = (stint("LEC", 1, 1, 57),)

    assert build_race_strategy(2024, 6)["drivers"][0]["team"] == "Ferrari"


def test_a_stop_matching_no_stint_is_reported_not_discarded(board, pit_db):
    pit_db("leclerc", 1, 40, "22.0", 22000)
    board["stints"] = (stint("LEC", 1, 1, 19),)
    board["stops"] = race_pit_stops(2026, 13)

    payload = build_race_strategy(2024, 6)

    assert [s["lap"] for s in payload["unmatched_stops"]] == [40]


def test_fastest_stop_is_the_shortest_stationary_time(board, pit_db):
    pit_db("leclerc", 1, 19, "21.825", 21825)
    pit_db("lawson", 1, 12, "31.197", 31197)
    board["stops"] = race_pit_stops(2026, 13)

    assert build_race_strategy(2024, 6)["fastest_stop"]["driver_code"] == "LEC"


def test_untimed_stops_cannot_win_fastest(board, pit_db):
    pit_db("leclerc", 1, 19, None, None)
    board["stops"] = race_pit_stops(2026, 13)

    assert build_race_strategy(2024, 6)["fastest_stop"] is None


def test_stops_without_stints_still_produce_a_payload(board, pit_db):
    pit_db("leclerc", 1, 19, "21.8", 21800)
    board["stops"] = race_pit_stops(2026, 13)

    payload = build_race_strategy(2024, 6)

    assert (payload["available"], payload["has_stints"], payload["has_stops"]) == (True, False, True)
    assert race_strategy_board.STINTS_UNAVAILABLE in payload["warnings"]


def test_stints_without_stops_still_produce_a_payload(board):
    board["stints"] = (stint("LEC", 1, 1, 57),)

    payload = build_race_strategy(2024, 6)

    assert (payload["has_stints"], payload["has_stops"]) == (True, False)
    assert race_strategy_board.STOPS_UNAVAILABLE in payload["warnings"]


def test_a_race_with_neither_source_is_reported_unavailable(board):
    payload = build_race_strategy(2026, 22)

    assert payload["available"] is False
    assert len(payload["warnings"]) == 2
