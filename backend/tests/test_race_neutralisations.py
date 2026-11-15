"""Tests for app.data.race_neutralisations: race-control windows read as lap ranges."""

from __future__ import annotations

from datetime import timedelta

from app.data import race_neutralisations as module
from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.race_control import RED_FLAG, SAFETY_CAR, VIRTUAL_SAFETY_CAR, Window
from tests.openf1_support import T0, make_lap, make_session_laps


def at(seconds: float):
    return T0 + timedelta(seconds=seconds)


def race(driver: int, count: int):
    return tuple(make_lap(driver, n, start=(n - 1) * 100, time=100) for n in range(1, count + 1))


def test_a_window_becomes_the_laps_run_under_it():
    laps = race(1, 10)
    windows = (Window(kind=SAFETY_CAR, start=at(250), end=at(480)),)
    assert module.lap_ranges(laps, windows) == [{"kind": "sc", "start_lap": 3, "end_lap": 5}]


def test_the_car_with_most_laps_sets_the_lap_numbers_and_a_tie_takes_the_lowest_number():
    laps = race(5, 6) + race(2, 6) + race(9, 3)
    windows = (Window(kind=VIRTUAL_SAFETY_CAR, start=at(50), end=at(150)),)
    assert module.lap_ranges(laps, windows) == [{"kind": "vsc", "start_lap": 1, "end_lap": 2}]


def test_an_open_window_runs_to_the_last_lap_and_a_window_no_lap_ran_under_is_dropped():
    laps = race(1, 4)
    windows = (
        Window(kind=RED_FLAG, start=at(250), end=None),
        Window(kind=SAFETY_CAR, start=at(5000), end=at(6000)),
    )
    assert module.lap_ranges(laps, windows) == [{"kind": "red", "start_lap": 3, "end_lap": 4}]


def test_laps_without_a_start_are_never_under_a_window():
    laps = (make_lap(1, 1), make_lap(1, 2, start=100))
    windows = (Window(kind=SAFETY_CAR, start=at(0), end=at(1000)),)
    assert module.lap_ranges(laps, windows) == [{"kind": "sc", "start_lap": 2, "end_lap": 2}]


def test_a_lap_with_a_start_but_no_time_counts_as_an_instant():
    laps = (make_lap(1, 1, start=100),)
    windows = (Window(kind=SAFETY_CAR, start=at(50), end=at(150)),)
    assert module.lap_ranges(laps, windows) == [{"kind": "sc", "start_lap": 1, "end_lap": 1}]


def test_no_laps_means_no_ranges():
    assert module.lap_ranges((), (Window(kind=SAFETY_CAR, start=at(0), end=None),)) == []


def test_a_safety_car_ends_where_the_red_flag_it_ran_through_starts():
    laps = race(1, 10)
    windows = (
        Window(kind=SAFETY_CAR, start=at(350), end=at(650)),
        Window(kind=RED_FLAG, start=at(450), end=at(600)),
        Window(kind=VIRTUAL_SAFETY_CAR, start=at(850), end=at(900)),
    )
    assert module.lap_ranges(laps, windows) == [
        {"kind": "sc", "start_lap": 4, "end_lap": 4},
        {"kind": "red", "start_lap": 5, "end_lap": 6},
        {"kind": "vsc", "start_lap": 9, "end_lap": 9},
    ]


def test_the_race_session_is_read(monkeypatch):
    session = make_session_laps(race(1, 3), code="R", windows=(Window(kind=SAFETY_CAR, start=at(150), end=None),))
    seen = []
    monkeypatch.setattr(module, "load_session_laps", lambda y, r, code: seen.append((y, r, code)) or session)
    assert module.race_neutralisations(2026, 19) == [{"kind": "sc", "start_lap": 2, "end_lap": 3}]
    assert seen == [(2026, 19, "R")]


def test_a_race_without_a_session_or_with_openf1_down_is_unknown_not_empty(monkeypatch):
    monkeypatch.setattr(module, "load_session_laps", lambda y, r, code: None)
    assert module.race_neutralisations(2026, 19) is None

    def down(y, r, code):
        raise OpenF1UnavailableError("down")

    monkeypatch.setattr(module, "load_session_laps", down)
    assert module.race_neutralisations(2026, 19) is None
