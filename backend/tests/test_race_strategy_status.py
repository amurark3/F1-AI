"""Tests for how each driver's race ended on the strategy board (app.services.race_strategy_board).

The board used to read the end of every last stint as the chequered flag. At
Mexico 2026 that labelled five retirements, Lindblad's on lap 58 among them, as
finishes. Each driver now carries the status and laps completed that the
classification publishes (:mod:`app.data.race_classification`), and nothing is
inferred when it publishes none.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
import json
from pathlib import Path

import pytest

from app.data.f1db_pitstops import PitStop
from app.data.openf1_stints import stints_from_openf1
from app.data.pit_sheet import PitSheet, stops_from_jolpica
from app.data.race_classification import (
    NO_CLASSIFICATION,
    ClassifiedDriver,
    RaceClassification,
    classification_from_openf1,
)
from app.data.race_stints import Stint
from app.services import race_strategy_board
from app.services.race_strategy_board import build_race_strategy

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
R19_RED_FLAG_LAP = 45
# Lapped at the red flag, so still on lap 44 when it came out: ALB, PER, LAW, HIR, SAI.
R19_LAPPED_AT_RED_FLAG = frozenset({23, 11, 30, 50, 55})


def stint(code: str, number: int, start: int, end: int, *, red_flag: bool = False) -> Stint:
    return Stint(
        driver_code=code,
        team="Haas F1 Team",
        stint=number,
        compound="HARD",
        start_lap=start,
        end_lap=end,
        laps=end - start + 1,
        tyre_life_start=0,
        fresh=True,
        ended_under_red_flag=red_flag,
    )


def stop(code: str, number: int, lap: int, time: str | None = "22.0") -> PitStop:
    return PitStop(driver_code=code, stop=number, lap=lap, time=time, millis=None if time is None else 22000)


def classified(code: str, position: int | None, status: str, laps: int | None) -> ClassifiedDriver:
    return ClassifiedDriver(driver_code=code, position=position, status=status, laps_completed=laps)


def openf1_classification(*drivers: ClassifiedDriver) -> RaceClassification:
    return RaceClassification(source="openf1-session-result", drivers=drivers)


@pytest.fixture
def board(monkeypatch):
    state = {"stints": (), "stops": (), "results": {}, "classification": NO_CLASSIFICATION}
    monkeypatch.setattr(race_strategy_board, "race_stints", lambda y, r: state["stints"])
    monkeypatch.setattr(race_strategy_board, "race_pit_sheet", lambda y, r: PitSheet("f1db-pit-stops", state["stops"]))
    monkeypatch.setattr(race_strategy_board, "race_results", lambda y, r: state["results"])
    monkeypatch.setattr(race_strategy_board, "race_classification", lambda y, r: state["classification"])
    return state


def rows_by_code(payload: dict) -> dict[str, dict]:
    return {row["driver_code"]: row for row in payload["drivers"]}


# --- status and laps from the classification ----------------------------------------


def test_each_driver_carries_the_published_status_and_laps(board):
    board["stints"] = (stint("VER", 1, 1, 71), stint("LIN", 1, 1, 58))
    board["classification"] = openf1_classification(
        classified("VER", 1, "finished", 71), classified("LIN", None, "dnf", 58)
    )

    rows = rows_by_code(build_race_strategy(2026, 19))

    assert (rows["VER"]["status"], rows["VER"]["laps_completed"], rows["VER"]["finish_position"]) == (
        "finished",
        71,
        1,
    )
    # Not classified: no position, and never "finished last".
    assert (rows["LIN"]["status"], rows["LIN"]["laps_completed"], rows["LIN"]["finish_position"]) == ("dnf", 58, None)


def test_the_classification_order_wins_over_f1db(board):
    """f1db lags the race by hours; the classification is what the result says now."""
    board["stints"] = (stint("PIA", 1, 1, 71), stint("LAW", 1, 1, 71))
    board["results"] = {"PIA": 7, "LAW": 9}
    board["classification"] = openf1_classification(
        classified("LAW", 7, "finished", 71), classified("PIA", 13, "finished", 71)
    )

    payload = build_race_strategy(2026, 19)

    assert [row["driver_code"] for row in payload["drivers"]] == ["LAW", "PIA"]
    assert payload["classification_source"] == "openf1-session-result"


def test_retirements_follow_the_classified_cars_in_published_order(board):
    board["stints"] = (stint("ALO", 1, 1, 5), stint("LIN", 1, 1, 58), stint("VER", 1, 1, 71))
    board["classification"] = openf1_classification(
        classified("VER", 1, "finished", 71), classified("LIN", None, "dnf", 58), classified("ALO", None, "dnf", 5)
    )

    assert [row["driver_code"] for row in build_race_strategy(2026, 19)["drivers"]] == ["VER", "LIN", "ALO"]


def test_without_a_classification_the_ending_is_unknown_not_finished(board):
    board["stints"] = (stint("VER", 1, 1, 71),)
    board["results"] = {"VER": 1}

    payload = build_race_strategy(2026, 19)
    row = payload["drivers"][0]

    assert (row["status"], row["laps_completed"], row["finish_position"]) == (None, None, 1)
    assert payload["classification_source"] is None


def test_a_driver_the_classification_omits_sorts_last(board):
    board["stints"] = (stint("ZZZ", 1, 1, 71), stint("VER", 1, 1, 71))
    board["classification"] = openf1_classification(classified("VER", 1, "finished", 71))

    rows = build_race_strategy(2026, 19)["drivers"]

    assert [row["driver_code"] for row in rows] == ["VER", "ZZZ"]
    assert rows[1]["status"] is None


def test_a_classified_car_without_stints_is_still_listed(board):
    # A car that never started has no stints, and its row says so.
    board["stints"] = (stint("VER", 1, 1, 71),)
    board["classification"] = openf1_classification(
        classified("VER", 1, "finished", 71), classified("SAR", None, "dns", 0)
    )

    row = rows_by_code(build_race_strategy(2026, 19))["SAR"]

    assert (row["status"], row["stints"], row["stops"], row["total_laps"]) == ("dns", [], 0, 0)


def test_no_classified_rows_are_invented_without_stint_data(board):
    board["classification"] = openf1_classification(classified("VER", 1, "finished", 71))

    assert build_race_strategy(2026, 19)["drivers"] == []


# --- retiring into the pits ---------------------------------------------------------


def test_a_retirement_into_the_pits_is_not_a_stop(board):
    board["stints"] = (stint("BEA", 1, 1, 20), stint("BEA", 2, 21, 30))
    board["stops"] = (stop("BEA", 1, 20), stop("BEA", 2, 30, None))
    board["classification"] = openf1_classification(classified("BEA", None, "dnf", 30))

    payload = build_race_strategy(2026, 19)
    row = payload["drivers"][0]

    assert (row["stops"], row["timed_stops"], row["retired_in_pits"]) == (1, 1, True)
    assert row["stints"][-1]["ended_by_stop"] is None
    assert payload["unmatched_stops"] == []
    assert [entry["lap"] for entry in payload["stops"]] == [20]


def test_a_stop_before_retiring_on_the_out_lap_is_still_a_stop(board):
    # New tyres went on, so the car left the pits: a stop, then a retirement.
    board["stints"] = (stint("BEA", 1, 1, 30), stint("BEA", 2, 31, 31))
    board["stops"] = (stop("BEA", 1, 30),)
    board["classification"] = openf1_classification(classified("BEA", None, "dnf", 30))

    row = build_race_strategy(2026, 19)["drivers"][0]

    assert (row["stops"], row["timed_stops"], row["retired_in_pits"]) == (1, 1, False)


def test_a_finisher_never_retired_in_the_pits(board):
    board["stints"] = (stint("VER", 1, 1, 71),)
    board["stops"] = (stop("VER", 1, 71),)
    board["classification"] = openf1_classification(classified("VER", 1, "finished", 71))

    payload = build_race_strategy(2026, 19)

    assert payload["drivers"][0]["retired_in_pits"] is False
    # A stop on the last lap of a finished race matches nothing: reported, not hidden.
    assert [entry["lap"] for entry in payload["unmatched_stops"]] == [71]


def test_a_retirement_with_unknown_laps_falls_back_to_the_last_stint(board):
    board["stints"] = (stint("BEA", 1, 1, 20), stint("BEA", 2, 21, 30))
    board["stops"] = (stop("BEA", 1, 20), stop("BEA", 2, 30, None))
    board["classification"] = openf1_classification(classified("BEA", None, "dnf", None))

    assert build_race_strategy(2026, 19)["drivers"][0]["retired_in_pits"] is True


# --- the notes under the chart ------------------------------------------------------


def test_no_published_stop_times_is_one_note_not_two_contradicting_ones(board):
    """The footer read "No pit stops are published" beside "Only 0 of the 33 stops"."""
    board["stints"] = (stint("VER", 1, 1, 30), stint("VER", 2, 31, 71))

    warnings = build_race_strategy(2026, 19)["warnings"]

    assert warnings == [race_strategy_board._untimed_stops_note(1)]


def test_a_race_without_stops_or_stop_times_says_only_that(board):
    board["stints"] = (stint("VER", 1, 1, 71),)

    assert build_race_strategy(2026, 19)["warnings"] == [race_strategy_board.STOPS_UNAVAILABLE]


# --- Mexico City 2026 (R19), from the real feeds ------------------------------------


def r19_board() -> tuple[tuple[Stint, ...], RaceClassification]:
    drivers = json.loads((FIXTURES / "openf1_drivers.json").read_text())
    results = json.loads((FIXTURES / "openf1_session_result.json").read_text())
    rows = json.loads((FIXTURES / "openf1_stints.json").read_text())
    by_number = {row["driver_number"]: row for row in drivers}
    # The race was suspended on the leader's lap 45; each car changed tyres on its own lap.
    running = {row["driver_number"] for row in results if (row["number_of_laps"] or 0) >= R19_RED_FLAG_LAP}
    red_flag_laps = {
        number: frozenset({R19_RED_FLAG_LAP - 1 if number in R19_LAPPED_AT_RED_FLAG else R19_RED_FLAG_LAP})
        for number in running
    }
    stints = stints_from_openf1(rows, by_number, red_flag_laps)
    codes = {number: row["name_acronym"] for number, row in by_number.items()}
    return stints, openf1_classification(*classification_from_openf1(results, codes))


def test_mexico_2026_retirements_are_not_finishes(board):
    board["stints"], board["classification"] = r19_board()

    rows = rows_by_code(build_race_strategy(2026, 19))

    assert {code: (rows[code]["status"], rows[code]["laps_completed"]) for code in ("LIN", "STR", "ALO")} == {
        "LIN": ("dnf", 58),
        "STR": ("dnf", 5),
        "ALO": ("dnf", 5),
    }
    finishers = [code for code, row in rows.items() if row["status"] == "finished"]
    assert len(finishers) == 17
    assert all(rows[code]["laps_completed"] == 71 for code in finishers)


def test_mexico_2026_rows_follow_the_fia_classification(board):
    board["stints"], board["classification"] = r19_board()

    codes = [row["driver_code"] for row in build_race_strategy(2026, 19)["drivers"]]

    assert codes[:7] == ["VER", "HAM", "ANT", "LEC", "NOR", "RUS", "LAW"]
    assert codes[-5:] == ["LIN", "BEA", "BOT", "STR", "ALO"]


# --- the published stop sheet (Mexico City 2026) --------------------------------------


def r19_sheet() -> tuple[PitStop, ...]:
    pit = json.loads((FIXTURES / "jolpica_pitstops.json").read_text())["PitStops"]
    results = json.loads((FIXTURES / "jolpica_results.json").read_text())["Results"]
    codes = {row["Driver"]["driverId"]: row["Driver"]["code"] for row in results}
    rows = [
        {
            "driverId": row["driverId"],
            "stop": int(row["stop"]),
            "lap": int(row["lap"]),
            "duration": ergast(row["duration"]),
        }
        for row in pit
    ]
    return stops_from_jolpica(rows, codes)


def ergast(text: str) -> timedelta:
    minutes, _, seconds = text.rpartition(":")
    return timedelta(minutes=int(minutes or 0), seconds=float(seconds))


def test_mexico_2026_stop_counts_come_from_the_sheet_without_the_suspension(board):
    board["stints"], board["classification"] = r19_board()
    board["stops"] = r19_sheet()

    payload = build_race_strategy(2026, 19)
    published = Counter(stop["driver_code"] for stop in payload["stops"])
    rows = rows_by_code(payload)

    expected = {"VER": 1, "HAM": 2, "LAW": 2, "HIR": 3, "STR": 1}
    assert {code: published[code] for code in expected} == expected
    assert {code: rows[code]["stops"] for code in expected} == expected
    assert {code: rows[code]["timed_stops"] for code in expected} == expected


def test_mexico_2026_suspension_entries_are_never_stops(board):
    board["stints"], board["classification"] = r19_board()
    board["stops"] = r19_sheet()

    payload = build_race_strategy(2026, 19)

    assert all(stop["lap"] != R19_RED_FLAG_LAP for stop in payload["stops"])
    assert payload["suspension_entries"] == 24
    assert race_strategy_board._suspension_note(24) in payload["warnings"]
    assert payload["fastest_stop"]["millis"] < 120_000
    assert payload["stops_source"] == "f1db-pit-stops"


def test_a_stop_carries_its_stationary_time_when_published(board):
    board["stints"] = (stint("VER", 1, 1, 27), stint("VER", 2, 28, 71))
    board["stops"] = (PitStop(driver_code="VER", stop=1, lap=27, time="22.466", millis=22466, stationary_millis=2400),)

    stop = build_race_strategy(2026, 19)["drivers"][0]["stints"][0]["ended_by_stop"]

    assert (stop["time"], stop["stationary_millis"]) == ("22.466", 2400)


def test_one_suspension_entry_reads_in_the_singular():
    assert "1 pit-lane entry on" in race_strategy_board._suspension_note(1)
