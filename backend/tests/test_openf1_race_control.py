"""Tests for app.data.openf1.laps and app.data.openf1.race_control.

The risks pinned here are measured against real OpenF1 messages:

* **A deleted time is found by its time; "LAP n" breaks ties and places an
  untimed deletion.** The message's lap is OpenF1's lap in a race or sprint and
  one ahead of it elsewhere (Gasly's deleted 1:36.764 at Austin 2026 FP2 is his
  lap 2, the message says LAP 3). An untimed message can come late: Gasly's
  R19 FP3 "LAP 12" struck his valid lap 14 before D3.1.
* "WILL BE REINSTATED" cancels a deletion (Abu Dhabi 2024, PER and PIA).
* A red flag ends when the session starts again, not at the "TRACK CLEAR" sent
  seconds after the suspension (Monza 2026); a VSC ends at TRACK CLEAR.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.data.openf1.laps import Lap, lap_from_openf1, laps_from_openf1
from app.data.openf1.race_control import (
    RED_FLAG,
    SAFETY_CAR,
    VIRTUAL_SAFETY_CAR,
    Window,
    deleted_laps,
    lap_by_time,
    lap_seconds,
    neutralised_windows,
    standing_deletions,
)
from tests.openf1_support import T0, iso, make_lap

pytestmark = pytest.mark.unit


def _message(at: float, text: str, **extra) -> dict:
    return {"date": iso(at), "message": text, **extra}


# ---------------------------------------------------------------------------
# Laps
# ---------------------------------------------------------------------------


def test_an_openf1_lap_row_reads_every_measured_field():
    lap = lap_from_openf1(
        {
            "driver_number": 10,
            "lap_number": 2,
            "date_start": iso(0),
            "lap_duration": 96.764,
            "duration_sector_1": 25.1,
            "duration_sector_2": 40,
            "duration_sector_3": None,
            "i1_speed": 224,
            "i2_speed": True,
            "st_speed": 326.0,
            "is_pit_out_lap": False,
        }
    )

    assert lap == Lap(10, 2, T0, 96.764, (25.1, 40.0, None), (224, None, 326), False)
    assert lap.end == T0 + timedelta(seconds=96.764)


def test_rows_without_a_car_or_lap_number_are_skipped_and_the_rest_sorted():
    rows = [
        {"driver_number": 3, "lap_number": 2},
        {"driver_number": None, "lap_number": 1},
        {"driver_number": 1, "lap_number": 5},
        {"driver_number": 3, "lap_number": 1},
    ]

    assert [(lap.driver, lap.number) for lap in laps_from_openf1(rows)] == [(1, 5), (3, 1), (3, 2)]


def test_an_untimed_lap_has_no_end():
    assert make_lap(1, 1, start=0).end is None
    assert make_lap(1, 1, time=90).end is None


def test_a_lap_survives_the_round_trip_through_the_cache():
    lap = make_lap(1, 8, start=10, time=94.539, sectors=(25.3, 37.575, 31.664), traps=(224, 179, 326), deleted=True)

    assert Lap.from_json(lap.to_json()) == lap
    assert Lap.from_json(make_lap(1, 1).to_json()) == make_lap(1, 1)


# ---------------------------------------------------------------------------
# Deleted lap times
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "seconds"), [("1:36.764", 96.764), ("56.1", 56.1), ("1:xx", None)])
def test_lap_times_are_read_as_seconds(text, seconds):
    assert lap_seconds(text) == seconds


GAS_LAPS = (
    make_lap(10, 1, start=0, pit_out=True),
    make_lap(10, 2, start=122, time=96.764),
    make_lap(10, 3, start=219, time=130.977),
)


def test_a_deleted_time_is_matched_to_the_lap_with_that_time_not_the_lap_named():
    messages = [_message(240, "CAR 10 (GAS) TIME 1:36.764 DELETED - TRACK LIMITS AT TURN 9 LAP 3 16:07:14")]

    assert deleted_laps(standing_deletions(messages), GAS_LAPS, "FP2") == {(10, 2)}


# Gasly, R19 FP3: "LAP 12" sent 14 minutes late, after his valid lap 14.
GAS_FP3_LAPS = tuple(make_lap(10, number, start=100 * number, time=81.266 + number) for number in range(10, 15))
LATE_UNTIMED = "CAR 10 (GAS) LAP DELETED - TRACK LIMITS AT TURN 9 LAP 12 11:51:31 (PIT)"


@pytest.mark.parametrize(("code", "lap"), [("FP3", 11), ("Q", 11), ("SQ", 11), ("R", 12), ("S", 12)])
def test_an_untimed_deletion_strikes_the_lap_its_message_names_not_the_last_one_finished(code, lap):
    messages = [_message(1600, LATE_UNTIMED)]

    assert deleted_laps(standing_deletions(messages), GAS_FP3_LAPS, code) == {(10, lap)}


@pytest.mark.parametrize(
    "text",
    [
        "CAR 10 (GAS) LAP DELETED - TRACK LIMITS AT TURN 20 (NEXT LAP PIT)",
        "CAR 10 (GAS) LAP DELETED - TRACK LIMITS AT TURN 9 LAP 40 (PIT)",
    ],
)
def test_an_untimed_deletion_with_no_lap_it_can_place_falls_on_the_last_lap_finished_before_it(text):
    messages = [_message(360, text)]

    assert deleted_laps(standing_deletions(messages), GAS_LAPS, "FP1") == {(10, 3)}


def test_an_untimed_deletion_in_an_unknown_session_falls_on_the_last_lap_finished_before_it():
    messages = [_message(360, "CAR 10 (GAS) LAP DELETED - TRACK LIMITS AT TURN 11 LAP 2 (PIT)")]

    assert deleted_laps(standing_deletions(messages), GAS_LAPS, "") == {(10, 3)}


def test_a_deletion_with_no_lap_to_place_it_on_is_dropped():
    messages = [_message(1, "CAR 10 (GAS) LAP DELETED - TRACK LIMITS")]

    assert deleted_laps(standing_deletions(messages), GAS_LAPS, "FP1") == frozenset()


def test_a_deleted_time_that_matches_no_lap_marks_nothing():
    messages = [_message(240, "CAR 10 (GAS) TIME 1:20.820 DELETED - TRACK LIMITS AT TURN 12 LAP 3 11:36:50")]

    assert deleted_laps(standing_deletions(messages), GAS_LAPS, "R") == frozenset()


# Lawson, Austin 2026 FP2: 1:43.065 is both lap 23 and lap 24; the message says LAP 25.
LAW_LAPS = (make_lap(30, 23, start=0, time=103.0652), make_lap(30, 24, start=104, time=103.0648))


@pytest.mark.parametrize(
    ("code", "text", "lap"),
    [
        ("FP2", "CAR 30 (LAW) TIME 1:43.065 DELETED - TRACK LIMITS AT TURN 20 LAP 25 17:01:00", 24),
        ("R", "CAR 30 (LAW) TIME 1:43.065 DELETED - TRACK LIMITS AT TURN 20 LAP 23 17:01:00", 23),
        ("FP2", "CAR 30 (LAW) TIME 1:43.065 DELETED - TRACK LIMITS AT TURN 20 LAP 9 17:01:00", 23),
    ],
)
def test_a_time_two_laps_share_is_placed_by_the_lap_the_message_names(code, text, lap):
    messages = [_message(300, text)]

    assert deleted_laps(standing_deletions(messages), LAW_LAPS, code) == {(30, lap)}


def test_a_time_that_did_not_parse_names_no_lap():
    assert lap_by_time(list(GAS_LAPS), None) is None


def test_a_reinstated_time_is_no_longer_deleted():
    messages = [
        _message(240, "CAR 10 (GAS) TIME 1:36.764 DELETED - TRACK LIMITS AT TURN 1 LAP 3"),
        _message(500, "CAR 10 (GAS) TIME 1:36.764 WILL BE REINSTATED"),
        _message(260, "CAR 10 (GAS) TIME 2:10.977 DELETED - TRACK LIMITS"),
    ]

    (standing,) = standing_deletions(messages)

    assert (standing.car, standing.seconds) == (10, 130.977)


def test_other_messages_and_undated_ones_are_not_deletions():
    messages = [
        _message(10, "FIA STEWARDS: CAR 10 (GAS) NOTED - TRACK LIMITS"),
        {"date": None, "message": "CAR 10 (GAS) TIME 1:36.764 DELETED"},
        {"date": iso(5), "message": None},
    ]

    assert standing_deletions(messages) == ()


# ---------------------------------------------------------------------------
# Neutralised running
# ---------------------------------------------------------------------------


def test_a_vsc_ends_at_the_next_track_clear():
    messages = [
        _message(100, "VSC DEPLOYED", category="SafetyCar"),
        _message(110, "CLEAR IN TRACK SECTOR 4", flag="CLEAR", scope="Sector"),
        _message(200, "VSC ENDING", category="SafetyCar"),
        _message(212, "TRACK CLEAR", flag="CLEAR", scope="Track"),
    ]

    assert neutralised_windows(messages) == (
        Window(VIRTUAL_SAFETY_CAR, T0 + timedelta(seconds=100), T0 + timedelta(seconds=212)),
    )


def test_a_red_flag_ends_when_the_session_starts_again_not_at_the_next_track_clear():
    messages = [
        _message(100, "SAFETY CAR DEPLOYED", category="SafetyCar"),
        _message(150, "RED FLAG - RACE SUSPENDED", category="Other"),
        _message(250, "TRACK CLEAR", flag="CLEAR", scope="Track"),
        _message(1900, "SESSION STARTED", category="SessionStatus"),
    ]

    sc, red = neutralised_windows(messages)

    assert (sc.kind, sc.end) == (SAFETY_CAR, T0 + timedelta(seconds=250))
    assert (red.kind, red.end) == (RED_FLAG, T0 + timedelta(seconds=1900))


def test_a_pre_2026_red_flag_is_read_from_its_flag():
    (red,) = neutralised_windows([_message(10, "RED FLAG", flag="RED")])

    assert (red.kind, red.end) == (RED_FLAG, None)


@pytest.mark.parametrize(
    "text",
    ["CAR 1 (VER) RED FLAG INFRINGEMENT", "RED FLAG INFRINGEMENT - CAR 1", "MEDICAL CAR DEPLOYED", "VSC ENDING"],
)
def test_messages_that_only_mention_a_neutralisation_open_nothing(text):
    flag = "RED" if text.startswith("RED") else None

    assert neutralised_windows([_message(10, text, flag=flag)]) == ()


def test_a_virtual_safety_car_by_its_full_name_opens_a_vsc():
    (window,) = neutralised_windows([_message(10, "VIRTUAL SAFETY CAR DEPLOYED")])

    assert window.kind == VIRTUAL_SAFETY_CAR


def test_a_window_survives_the_round_trip_through_the_cache():
    closed = Window(SAFETY_CAR, T0, T0 + timedelta(seconds=90))
    open_ended = Window(RED_FLAG, T0, None)

    assert Window.from_json(closed.to_json()) == closed
    assert Window.from_json(open_ended.to_json()) == open_ended


def test_a_kept_window_without_a_start_is_refused():
    with pytest.raises(ValueError, match="without a start"):
        Window.from_json({"kind": SAFETY_CAR, "start": None, "end": None})
