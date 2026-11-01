"""Tests for the Telemetry Lab's OpenF1 loaders: session laps, lap traces and race context.

The rules pinned here:

* A load is kept only once its session has ended and settled, and never empty:
  a partial live session kept for good would outlive the gap that caused it.
* Deleted laps are marked on the lap list as it loads.
* A lap's car data and position are fetched for a padded window, because the
  feeds start ~0.2 s late and stop ~0.8 s early.
* The leader's 0.0 interval is no reading: it read as "in traffic" every lap
  the leader led.

HTTP is served by ``httpx.MockTransport``; the network is blocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data.openf1 import race_context as context_module, session_laps as laps_module, telemetry as trace_module
from app.data.openf1.race_context import (
    RaceContext,
    finishing_order,
    lap_gaps,
    load_race_context,
    rain_windows,
)
from app.data.openf1.session_laps import SessionLaps, load_session_laps
from app.data.openf1.telemetry import PADDING_SECONDS, LapTrace, load_lap_trace, merge_samples
from tests.openf1_support import NOR, T0, VER, fresh_cache, iso, make_lap, make_session, make_session_laps, serve

pytestmark = pytest.mark.unit

LAP_ROWS = [
    {"driver_number": 1, "lap_number": 1, "date_start": iso(0), "is_pit_out_lap": True},
    {"driver_number": 1, "lap_number": 2, "date_start": iso(120), "lap_duration": 94.379},
    {"driver_number": 1, "lap_number": 3, "date_start": iso(215), "lap_duration": 94.539},
]
DRIVER_ROWS = [{"driver_number": 1, "name_acronym": "NOR", "team_name": "McLaren", "team_colour": "F47600"}]
DELETION = {"date": iso(300), "message": "CAR 1 (NOR) TIME 1:34.379 DELETED - TRACK LIMITS AT TURN 19 LAP 3"}


# ---------------------------------------------------------------------------
# Session laps
# ---------------------------------------------------------------------------


@pytest.fixture
def session_openf1(monkeypatch):
    cache = fresh_cache(monkeypatch, laps_module)

    def install(session, routes: dict | None = None):
        monkeypatch.setattr(laps_module, "find_session", lambda *_args: session)
        defaults = {"drivers": DRIVER_ROWS, "laps": LAP_ROWS, "race_control": [DELETION]}
        return serve(monkeypatch, laps_module, {**defaults, **(routes or {})}), cache

    return install


def test_a_session_loads_with_its_deleted_laps_marked(session_openf1):
    session_openf1(make_session())

    loaded = load_session_laps(2026, 18, "Q")

    assert loaded is not None
    assert [(lap.number, lap.deleted) for lap in loaded.laps] == [(1, False), (2, True), (3, False)]
    assert loaded.driver_by_code(" nor ") == loaded.drivers[1]
    assert loaded.driver_by_code("VER") is None
    assert [lap.number for lap in loaded.laps_of(1)] == [1, 2, 3]


def test_an_ended_session_is_kept_and_then_served_without_openf1(session_openf1):
    fake, _cache = session_openf1(make_session(ended=True))
    first = load_session_laps(2026, 18, "Q")
    calls = len(fake.requests)

    again = load_session_laps(2026, 18, "Q")

    assert len(fake.requests) == calls
    assert again == first


def test_a_session_still_running_is_not_kept(session_openf1):
    fake, cache = session_openf1(make_session(ended=False))
    load_session_laps(2026, 18, "Q")

    assert cache.get(laps_module.SESSION_LAPS_KIND, "2026:18:Q", laps_module.SESSION_LAPS_VERSION) is None
    load_session_laps(2026, 18, "Q")
    assert fake.paths().count("laps") == 2


def test_an_empty_lap_list_is_not_kept(session_openf1):
    _fake, cache = session_openf1(make_session(ended=True), {"laps": []})

    assert load_session_laps(2026, 18, "Q").laps == ()
    assert cache.get(laps_module.SESSION_LAPS_KIND, "2026:18:Q", laps_module.SESSION_LAPS_VERSION) is None


def test_a_round_without_the_session_loads_nothing(session_openf1):
    fake, _cache = session_openf1(None)

    assert load_session_laps(2026, 18, "SQ") is None
    assert fake.requests == []


def test_session_laps_survive_the_round_trip_through_the_cache():
    from app.data.openf1.race_control import Window

    original = make_session_laps(
        (make_lap(1, 2, start=0, time=94.0),), windows=(Window("vsc", T0, None),), drivers=(NOR, VER)
    )
    undated = SessionLaps(
        session=make_session().__class__(1, 2, None, "R", "Race", None, None),
        year=2023,
        round=1,
        drivers={},
        laps=(),
        windows=(),
    )

    assert SessionLaps.from_json(original.to_json()) == original
    assert SessionLaps.from_json(undated.to_json()) == undated


# ---------------------------------------------------------------------------
# Lap traces
# ---------------------------------------------------------------------------


def _car(at: float, speed: float, brake: float = 0) -> dict:
    return {"date": iso(at), "speed": speed, "throttle": 100, "brake": brake, "n_gear": 7, "rpm": 11000}


def _where(at: float, x: float, y: float) -> dict:
    return {"date": iso(at), "x": x, "y": y}


TIMED = make_lap(1, 3, start=100, time=10.0)
CAR_ROWS = [_car(99.0, 200), _car(105.0, 250, brake=100), _car(111.0, 300), {"date": None, "speed": 1}, _car(104, None)]
WHERE_ROWS = [_where(98.0, 0, 0), _where(112.0, 1400, -700), {"date": iso(100), "x": None, "y": 1}]


def test_position_is_interpolated_onto_the_car_data_clock():
    trace = merge_samples(TIMED, CAR_ROWS, WHERE_ROWS)

    assert trace is not None
    assert trace.t == (-1.0, 5.0, 11.0)
    assert trace.speed == (200.0, 250.0, 300.0)
    assert trace.brake == (0.0, 100.0, 0.0)
    assert trace.x == (100.0, 700.0, 1300.0)
    assert trace.y == (-50.0, -350.0, -650.0)
    assert LapTrace.from_json(trace.to_json()) == trace


@pytest.mark.parametrize(
    ("lap", "car", "where"),
    [
        (make_lap(1, 1, start=100), CAR_ROWS, WHERE_ROWS),
        (TIMED, CAR_ROWS[:1], WHERE_ROWS),
        (TIMED, CAR_ROWS, WHERE_ROWS[:1]),
    ],
    ids=["untimed-lap", "one-car-sample", "one-position"],
)
def test_too_little_to_draw_is_no_trace(lap, car, where):
    assert merge_samples(lap, car, where) is None


@pytest.fixture
def trace_openf1(monkeypatch):
    cache = fresh_cache(monkeypatch, trace_module)
    fake = serve(monkeypatch, trace_module, {"car_data": CAR_ROWS, "location": WHERE_ROWS})
    return fake, cache


def test_the_lap_is_fetched_for_a_padded_window(trace_openf1):
    fake, _cache = trace_openf1

    trace = load_lap_trace(make_session_laps((TIMED,)), TIMED)

    assert trace is not None
    params = fake.requests[0].url.params
    assert params["driver_number"] == "1"
    start = datetime.fromisoformat(params["date>"])
    end = datetime.fromisoformat(params["date<"])
    assert start == T0 + timedelta(seconds=100 - PADDING_SECONDS)
    assert end == T0 + timedelta(seconds=110 + PADDING_SECONDS)


def test_a_trace_from_an_ended_session_is_kept(trace_openf1):
    fake, _cache = trace_openf1
    session = make_session_laps((TIMED,))
    first = load_lap_trace(session, TIMED)

    assert load_lap_trace(session, TIMED) == first
    assert len(fake.requests) == 2


def test_an_untimed_lap_fetches_nothing(trace_openf1):
    fake, _cache = trace_openf1

    assert load_lap_trace(make_session_laps(()), make_lap(1, 1, start=0)) is None
    assert fake.requests == []


def test_a_trace_from_a_running_session_is_not_kept(trace_openf1, monkeypatch):
    fake, _cache = trace_openf1
    session = make_session_laps((TIMED,))
    monkeypatch.setattr(trace_module, "session_ended", lambda _session: False)

    load_lap_trace(session, TIMED)
    load_lap_trace(session, TIMED)

    assert len(fake.requests) == 4


# ---------------------------------------------------------------------------
# Race context
# ---------------------------------------------------------------------------

RACE_LAPS = (
    make_lap(12, 2, start=100, time=90),
    make_lap(1, 2, start=101, time=90),
    make_lap(1, 3, start=191, time=90),
    make_lap(1, 4, start=None, time=90),
    make_lap(44, 2, start=110, time=90),
)


def _interval(driver: int, at: float, interval) -> dict:
    return {"driver_number": driver, "date": iso(at), "interval": interval}


def test_each_lap_gets_the_median_gap_to_the_car_ahead():
    rows = [
        _interval(1, 120, 0.9),
        _interval(1, 150, 1.1),
        _interval(1, 160, 3.0),
        _interval(1, 170, "+1 LAP"),
        _interval(1, 175, None),
        {"driver_number": None, "date": iso(130), "interval": 0.1},
        _interval(12, 150, 0.0),
    ]

    gaps = lap_gaps(rows, RACE_LAPS)

    # Lap 3 had no reading, lap 4 is undated, the leader's 0.0 is no reading.
    assert gaps == {(1, 2): 1.1}


def test_rain_readings_become_merged_windows():
    rows = [
        {"date": iso(0), "rainfall": 1},
        {"date": iso(50), "rainfall": 1},
        {"date": iso(300), "rainfall": 1},
        {"date": iso(120), "rainfall": 0},
        {"date": iso(400), "rainfall": None},
        {"date": None, "rainfall": 1},
    ]

    windows = rain_windows(rows)

    assert windows == (
        (T0, T0 + timedelta(seconds=110)),
        (T0 + timedelta(seconds=300), T0 + timedelta(seconds=360)),
    )


def test_the_finishing_order_puts_classified_cars_first_then_by_laps_done():
    rows = [
        {"driver_number": 43, "position": None, "number_of_laps": 35},
        {"driver_number": 16, "position": 2, "number_of_laps": 56},
        {"driver_number": 77, "position": None, "number_of_laps": 48},
        {"driver_number": 12, "position": 1, "number_of_laps": 56},
        {"driver_number": 5, "position": None, "number_of_laps": None},
        {"position": 3},
    ]

    assert finishing_order(rows) == (12, 16, 77, 43, 5)


def test_race_context_survives_the_round_trip_and_drops_unreadable_rain():
    from app.data.stint_model import Stint

    context = RaceContext(
        stints=(Stint("NOR", "McLaren", 1, "MEDIUM", 1, 16, 16, 0, True, False),),
        gaps={(1, 2): 1.1},
        rain=((T0, T0 + timedelta(seconds=60)),),
        classification=(1, 3),
    )
    payload = context.to_json()

    assert RaceContext.from_json(payload) == context
    payload["rain"].append(["not a date", iso(0)])
    assert RaceContext.from_json(payload) == context


@pytest.fixture
def race_openf1(monkeypatch):
    cache = fresh_cache(monkeypatch, context_module)

    def install(stints: list[dict]):
        return serve(
            monkeypatch,
            context_module,
            {
                "stints": stints,
                "intervals": [_interval(1, 120, 0.9)],
                "weather": [{"date": iso(0), "rainfall": 0}],
                "session_result": [{"driver_number": 1, "position": 1}],
            },
        ), cache

    return install


STINT_ROWS = [
    {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 16, "compound": "MEDIUM", "tyre_age_at_start": 0}
]


def test_a_race_context_loads_and_is_kept_once_the_race_has_ended(race_openf1):
    fake, _cache = race_openf1(STINT_ROWS)
    session = make_session_laps(RACE_LAPS, code="R")

    context = load_race_context(session)

    assert [(stint.driver_code, stint.compound) for stint in context.stints] == [("NOR", "MEDIUM")]
    assert context.gaps == {(1, 2): 0.9}
    assert context.classification == (1,)
    assert load_race_context(session) == context
    assert fake.paths() == ["stints", "intervals", "weather", "session_result"]


def test_a_race_without_stints_is_not_kept(race_openf1):
    fake, _cache = race_openf1([])
    session = make_session_laps(RACE_LAPS, code="R")

    assert load_race_context(session).stints == ()
    load_race_context(session)
    assert fake.paths().count("stints") == 2


def test_rain_windows_are_utc():
    ((start, _end),) = rain_windows([{"date": "2026-10-25T19:07:33", "rainfall": 1}])

    assert start.tzinfo == UTC
