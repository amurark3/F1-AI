"""The rewind's order maths on R19's real rows, and on hand-built cases for the edges."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.data.openf1.laps import laps_from_openf1
from app.services import rewind_order as order
from tests.debrief_r19_support import entries, rows
from tests.openf1_support import T0, make_lap

pytestmark = pytest.mark.unit

CODES = {number: entry.code for number, entry in entries().items()}
NUMBERS = {code: number for number, code in CODES.items()}
FINISHERS = {
    NUMBERS[code]
    for code in [
        "VER",
        "HAM",
        "ANT",
        "LEC",
        "NOR",
        "RUS",
        "LAW",
        "BOR",
        "HAD",
        "HIR",
        "ALB",
        "SAI",
        "PIA",
        "HUL",
        "COL",
        "PER",
        "GAS",
    ]
}


@pytest.fixture(scope="module")
def laps():
    return laps_from_openf1(rows("openf1_laps.json"))


@pytest.fixture(scope="module")
def orders(laps):
    return [[CODES[n] for n in lap] for lap in order.lap_orders(laps, rows("openf1_position.json"), FINISHERS)]


@pytest.fixture(scope="module")
def stops():
    found: dict[str, list[int]] = {}
    for code, lap in order.real_stops(rows("openf1_pit_settled.json"), CODES):
        found.setdefault(code, []).append(lap)
    return found


def at(orders_, lap):
    return " ".join(orders_[lap - 1])


def test_the_last_lap_and_lap_44_are_the_real_order(orders):
    assert len(orders) == 71
    assert at(orders, 71) == "VER HAM ANT LEC NOR RUS PIA COL LAW GAS BOR HAD HIR ALB SAI HUL PER"
    assert at(orders, 44) == "VER LEC HAM ANT NOR RUS PIA LIN COL GAS HUL BEA BOR HAD LAW SAI HIR ALB PER"


def test_every_lap_is_the_running_cars_with_no_gap_or_repeat(orders):
    for lap in orders:
        assert len(lap) == len(set(lap))
    last = {code: max(i for i, lap in enumerate(orders, 1) if code in lap) for code in CODES.values()}
    assert (last["LIN"], last["BEA"], last["BOT"], last["ALO"], last["STR"]) == (58, 47, 42, 5, 5)
    assert all(last[code] == 71 for code in FINISHERS_CODES)


FINISHERS_CODES = [CODES[n] for n in FINISHERS]


def test_the_lead_runs_are_leclerc_antonelli_verstappen(orders):
    leaders = [lap[0] for lap in orders]
    assert leaders[:27] == ["LEC"] * 27
    assert leaders[27:43] == ["ANT"] * 16
    assert leaders[43:] == ["VER"] * 28


def test_real_stops_use_the_lane_time_rule(stops):
    expected = {
        "ALO": [3], "STR": [3], "HAD": [7, 41], "LAW": [11, 42], "GAS": [17, 44], "ALB": [18, 41],
        "PIA": [26, 44], "VER": [27], "LEC": [27], "HAM": [28, 44], "BOT": [30], "PER": [30, 43, 59],
        "HUL": [31, 59], "RUS": [33, 44], "COL": [34], "HIR": [35, 43, 59], "LIN": [35], "SAI": [36],
        "BOR": [38], "NOR": [39], "BEA": [40], "ANT": [43],
    }  # fmt: skip
    assert {code: sorted(laps_) for code, laps_ in stops.items()} == expected


def classified(orders, stops, lap, passes=None, status=None):
    prev = orders[lap - 2]
    return {
        c["driver_code"]: c
        for c in order.lap_changes(order.LapView(lap, prev, orders[lap - 1], stops, passes or set(), status))
    }


def shape(change):
    return (change["from"], change["to"], change["kind"], change["rival"], change["stop_lap"])


def test_lap_44_changes(orders, stops):
    found = classified(orders, stops, 44, status="sc")
    assert {code: shape(c) for code, c in found.items()} == {
        "VER": (2, 1, "rival_stop", "ANT", 43),
        "LEC": (3, 2, "rival_stop", "ANT", 43),
        "HAM": (4, 3, "own_stop", None, 44),
        "ANT": (1, 4, "own_stop", None, 43),
        "ALB": (19, 18, "rival_stop", "PER", 43),
        "PER": (18, 19, "own_stop", None, 43),
    }


def test_lap_28_retirement_and_neutralised_laps(orders, stops):
    lap28 = classified(orders, stops, 28)
    assert [(c, lap28[c]["kind"]) for c in ("ANT", "RUS", "NOR", "VER", "LEC")] == [
        ("ANT", "rival_stop"), ("RUS", "rival_stop"), ("NOR", "rival_stop"), ("VER", "own_stop"), ("LEC", "own_stop"),
    ]  # fmt: skip
    assert lap28["ANT"]["rival"] == "LEC"
    lap59 = classified(orders, stops, 59, status="sc")
    assert [c["rival"] for c in lap59.values() if c["kind"] == "retirement"] == ["LIN"] * 7
    lap46 = classified(orders, stops, 46, status="red")
    assert {c["kind"] for c in lap46.values()} == {"neutralised"}


def test_whole_race_has_no_unexplained_change(orders, stops, laps):
    codes = CODES
    passes = order.overtake_laps(rows("openf1_overtakes.json"), laps, codes)
    ranges = [
        {"kind": "vsc", "start_lap": 7, "end_lap": 8},
        {"kind": "sc", "start_lap": 44, "end_lap": 44},
        {"kind": "red", "start_lap": 45, "end_lap": 46},
        {"kind": "sc", "start_lap": 59, "end_lap": 62},
    ]
    grid = orders[0]
    kinds = []
    for lap in range(1, 72):
        prev = orders[lap - 2] if lap > 1 else grid
        status = order.track_status(ranges, lap)
        found = order.lap_changes(order.LapView(lap, prev, orders[lap - 1], stops, passes.get(lap, set()), status))
        kinds += [c["kind"] for c in found]
    assert "change" not in kinds
    assert len(kinds) > 200


def car(number, starts, tail=90.0):
    """A car's laps from start offsets (seconds after T0); every lap takes ``tail`` seconds."""
    return [make_lap(number, i, start=s, time=tail) for i, s in enumerate(starts, 1)]


def stamp(number, seconds, place):
    return {"driver_number": number, "position": place, "date": (T0 + timedelta(seconds=seconds)).isoformat()}


def test_crossings_use_the_next_start_and_fall_back_to_the_lap_end():
    found = order.crossings(car(1, [0, 100]))

    assert found[(1, 1)] == T0 + timedelta(seconds=100)
    assert found[(1, 2)] == T0 + timedelta(seconds=190)


def test_a_lap_with_no_end_has_no_crossing():
    assert order.crossings([make_lap(1, 1, start=0)]) == {}


def test_a_tie_in_place_is_broken_by_crossing_time():
    laps = [*car(1, [0, 100]), *car(2, [0, 101])]
    positions = [stamp(1, 0, 1), stamp(2, 0, 1)]

    assert order.lap_orders(laps, positions, set()) == [[1, 2], [1, 2]]


def test_the_first_row_is_used_when_none_is_earlier_and_a_car_without_rows_is_left_out():
    laps = [*car(1, [0, 100]), *car(2, [0, 100])]
    positions = [stamp(1, 500, 2)]

    assert order.lap_orders(laps, positions, set()) == [[1], [1]]


def test_a_lapped_finisher_is_placed_at_the_flag_by_its_last_crossing():
    laps = [*car(1, [0, 100, 200]), *car(2, [0, 100]), *car(3, [0, 100])]
    positions = [stamp(1, 0, 1), stamp(2, 0, 2), stamp(3, 0, 3)]

    assert order.lap_orders(laps, positions, {1, 2}) == [[1, 2, 3], [1, 2, 3], [1, 2]]
    assert order.lap_orders(laps, positions, {1, 2, 9}) == [[1, 2, 3], [1, 2, 3], [1, 2]]
    assert order.lap_orders(laps, positions, set())[2] == [1]


def test_no_laps_means_no_orders():
    assert order.lap_orders([], [], set()) == []


def test_position_rows_without_a_date_car_or_place_are_ignored():
    laps = car(1, [0, 100])
    positions = [{"driver_number": 1, "position": 1, "date": None}, {"position": 1, "date": T0.isoformat()},
                 {"driver_number": 1, "date": T0.isoformat()}, stamp(1, 0, 4)]  # fmt: skip

    assert order.lap_orders(laps, positions, set()) == [[1], [1]]


def test_real_stops_edge_cases():
    assert order.real_stops([], CODES) == []
    assert (
        order.real_stops([{"driver_number": 1, "lap_number": 3, "lane_duration": None, "pit_duration": None}], CODES)
        == []
    )
    pit = [
        {"driver_number": 1, "lap_number": 5, "lane_duration": None, "pit_duration": 22.0},
        {"driver_number": 3, "lap_number": 5, "lane_duration": 24.0},
        {"driver_number": 12, "lap_number": 9, "lane_duration": 80.0, "pit_duration": 80.0},
        {"driver_number": 999, "lap_number": 9, "lane_duration": 20.0},
    ]
    assert order.real_stops(pit, CODES) == [("NOR", 5), ("VER", 5)]


def test_overtakes_land_on_the_overtaking_cars_lap_and_bad_rows_are_skipped():
    laps = car(1, [0, 100, 200])
    names = {1: "NOR", 3: "VER"}
    rows_ = [
        {
            "overtaking_driver_number": 1,
            "overtaken_driver_number": 3,
            "date": (T0 + timedelta(seconds=150)).isoformat(),
        },
        {"overtaking_driver_number": 3, "overtaken_driver_number": 1, "date": T0.isoformat()},
        {"overtaking_driver_number": 1, "overtaken_driver_number": 3, "date": None},
        {"overtaking_driver_number": 1, "overtaken_driver_number": 77, "date": T0.isoformat()},
        {"overtaking_driver_number": None, "overtaken_driver_number": 3, "date": T0.isoformat()},
        {"overtaking_driver_number": 1, "overtaken_driver_number": 3, "date": (T0 - timedelta(seconds=5)).isoformat()},
    ]

    found = order.overtake_laps(rows_, [*laps, make_lap(1, 9)], names)

    assert found == {2: {frozenset(("NOR", "VER"))}, 1: {frozenset(("NOR", "VER"))}}


def test_track_status_prefers_red_then_sc_then_vsc():
    ranges = [
        {"kind": "vsc", "start_lap": 1, "end_lap": 9},
        {"kind": "sc", "start_lap": 5, "end_lap": 9},
        {"kind": "red", "start_lap": 8, "end_lap": 9},
    ]

    assert [order.track_status(ranges, lap) for lap in (1, 5, 8, 10)] == ["vsc", "sc", "red", None]


def test_a_change_nothing_explains_is_a_plain_position_change():
    found = order.classify("A", order.LapView(3, ["A", "B"], ["B", "A"], {}, set(), None))

    assert (found["kind"], found["rival"], found["stop_lap"]) == ("change", None, None)


def test_a_pass_needs_an_overtakes_row_between_the_two_cars():
    passed = order.classify("B", order.LapView(3, ["A", "B"], ["B", "A"], {}, {frozenset(("A", "B"))}, None))
    other = order.classify("B", order.LapView(3, ["A", "B"], ["B", "A"], {}, {frozenset(("A", "C"))}, None))

    assert (passed["kind"], passed["rival"]) == ("pass", "A")
    assert other["kind"] == "change"


def test_a_gain_with_a_car_gone_is_a_retirement_and_a_loss_is_not():
    gain = order.classify("C", order.LapView(3, ["A", "B", "C"], ["C", "B"], {}, set(), None))
    loss = order.classify("B", order.LapView(3, ["A", "B", "C"], ["C", "B"], {}, set(), None))

    assert (gain["kind"], gain["rival"]) == ("retirement", "A")
    assert loss["kind"] == "change"


def test_lap_changes_skip_cars_new_to_the_order():
    assert order.lap_changes(order.LapView(1, ["A"], ["A", "B"], {}, set(), None)) == []
