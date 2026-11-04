"""Tests for lap selection, loading, the weekend pickers, the speed map and the head-to-head.

* The default lap is the fastest **valid** one: car 1's quickest Austin 2026
  time was deleted, and mapping it would show a lap that does not count.
* The head-to-head delta at the line is the published gap, and mini-sector and
  corner gains add up to it.
* Every driver object prints f1db's names under OpenF1's keys: car 50 at Mexico
  City is "Ryō Hirakawa" of "Haas", where OpenF1 wrote "Ryo HIRAKAWA" of "Haas
  F1 Team". Names resolve as the answer is built, so a session kept in the
  cache with OpenF1's words still prints f1db's.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import httpx
import pytest

from app.data.multiviewer import CircuitInfo, Corner
from app.data.openf1.sessions import ScheduledSession, entry_list
from app.data.openf1.telemetry import LapTrace
from app.services.analysis import (
    comparison as comparison_module,
    loading as loading_module,
    track_map as track_map_module,
    weekend as weekend_module,
)
from app.services.analysis.common import AnalysisUnavailableError, DriverLap, SessionRef, unavailable
from app.services.analysis.comparison import biggest_gains, build_comparison
from app.services.analysis.lap_selection import LapChoice, choose_lap, fastest_valid_lap, timed_laps
from app.services.analysis.loading import LoadedLap, require_lap, require_session
from app.services.analysis.track_map import DELETED_LAP_WARNING, build_track_map, corner_markers
from app.services.analysis.weekend import build_lap_list, build_weekend
from tests.openf1_support import NOR, VER, FakeOpenF1, make_lap, make_session_laps

pytestmark = pytest.mark.unit

REF = SessionRef(2026, 18, "Q")
NOR_LAPS = (
    make_lap(1, 1, start=0, time=200.0, pit_out=True),
    make_lap(1, 2, start=200, time=94.379, deleted=True),
    make_lap(1, 3, start=300, time=130.0),
    make_lap(1, 4, start=430, time=94.539),
    make_lap(1, 5, start=None, time=93.0),
    make_lap(1, 6, start=600),
)
SESSION = make_session_laps(NOR_LAPS)


# ---------------------------------------------------------------------------
# Lap selection
# ---------------------------------------------------------------------------


def test_the_default_lap_is_the_fastest_that_counts():
    assert fastest_valid_lap(NOR_LAPS).number == 4
    assert choose_lap(SESSION, 1, None) == LapChoice(lap=NOR_LAPS[3], fastest=NOR_LAPS[3])


def test_a_named_lap_may_be_a_deleted_one():
    choice = choose_lap(SESSION, 1, 2)

    assert choice.lap.deleted
    assert choice.fastest.number == 4


@pytest.mark.parametrize("lap", [1, 5, 6, 99], ids=["pit-out", "undated", "untimed", "missing"])
def test_a_named_lap_without_a_usable_time_is_none(lap):
    assert choose_lap(SESSION, 1, lap) is None


def test_a_driver_without_a_valid_lap_has_no_default():
    assert choose_lap(SESSION, 3, None) is None
    assert fastest_valid_lap(()) is None


def test_the_lap_picker_lists_timed_laps_with_the_fastest_marked():
    assert timed_laps(SESSION, 1) == [
        {"number": 2, "time": 94.379, "deleted": True, "is_fastest": False},
        {"number": 3, "time": 130.0, "deleted": False, "is_fastest": False},
        {"number": 4, "time": 94.539, "deleted": False, "is_fastest": True},
    ]
    only_deleted = make_session_laps((make_lap(1, 2, start=0, time=90.0, deleted=True),))
    assert timed_laps(only_deleted, 1)[0]["is_fastest"] is False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _trace(lap_time: float = 10.0, speed: float = 360.0, driver: int = 1) -> LapTrace:
    t = [-1.0 + 0.25 * step for step in range(int((lap_time + 2) / 0.25) + 1)]
    return LapTrace(
        driver=driver,
        lap=4,
        lap_time=lap_time,
        t=tuple(t),
        speed=tuple([speed] * len(t)),
        throttle=tuple([100.0] * len(t)),
        brake=tuple([0.0] * len(t)),
        gear=tuple([8.0] * len(t)),
        rpm=tuple([11000.0] * len(t)),
        x=tuple(value * speed / 3.6 * 10 for value in t),
        y=tuple([0.0] * len(t)),
    )


@pytest.mark.parametrize("loaded", [None, make_session_laps(())], ids=["no-session", "no-laps"])
def test_a_missing_or_empty_session_is_no_session(monkeypatch, loaded):
    monkeypatch.setattr(loading_module, "load_session_laps", lambda *_args: loaded)

    with pytest.raises(AnalysisUnavailableError, match="no_session"):
        require_session(REF)


def test_a_session_with_laps_is_returned(monkeypatch):
    monkeypatch.setattr(loading_module, "load_session_laps", lambda *_args: SESSION)

    assert require_session(REF) is SESSION


@pytest.mark.parametrize(
    ("pick", "trace", "reason"),
    [
        (DriverLap("HAM"), _trace(), "no_driver"),
        (DriverLap("VER"), _trace(), "no_lap"),
        (DriverLap("NOR"), None, "no_telemetry"),
    ],
)
def test_require_lap_says_exactly_what_is_missing(monkeypatch, pick, trace, reason):
    monkeypatch.setattr(loading_module, "load_lap_trace", lambda *_args: trace)

    with pytest.raises(AnalysisUnavailableError, match=reason):
        require_lap(SESSION, pick)


def test_require_lap_returns_the_driver_lap_and_trace(monkeypatch):
    trace = _trace()
    monkeypatch.setattr(loading_module, "load_lap_trace", lambda *_args: trace)

    loaded = require_lap(SESSION, DriverLap("NOR"))

    assert (loaded.driver, loaded.choice.lap.number, loaded.trace) == (NOR, 4, trace)


# ---------------------------------------------------------------------------
# Pickers
# ---------------------------------------------------------------------------


def test_the_weekend_lists_sessions_and_which_have_started(monkeypatch):
    schedule = (
        ScheduledSession("FP1", "Practice 1", datetime(2026, 10, 30, 18, 30, tzinfo=UTC)),
        ScheduledSession("Q", "Qualifying", datetime(2026, 10, 31, 21, 0, tzinfo=UTC)),
        ScheduledSession("R", "Race", None),
    )
    monkeypatch.setattr(weekend_module, "weekend_schedule", lambda *_args: schedule)

    weekend = build_weekend(2026, 19, now=datetime(2026, 10, 31, 20, 0, tzinfo=UTC))

    assert [(s["code"], s["started"]) for s in weekend["sessions"]] == [("FP1", True), ("Q", False), ("R", False)]
    assert weekend["sessions"][2]["date_start"] is None


def test_a_round_off_the_calendar_has_no_sessions(monkeypatch):
    monkeypatch.setattr(weekend_module, "weekend_schedule", lambda *_args: ())

    with pytest.raises(AnalysisUnavailableError):
        build_weekend(2026, 99)


def test_drivers_are_listed_quickest_first_with_lapless_ones_last(monkeypatch):
    monkeypatch.setattr(weekend_module, "require_session", lambda _ref: SESSION)

    listing = build_lap_list(REF)

    assert [(driver["code"], driver["best"]) for driver in listing["drivers"]] == [("NOR", 94.539), ("VER", None)]
    assert listing["session"]["code"] == "Q"


def test_build_weekend_defaults_to_now(monkeypatch):
    monkeypatch.setattr(weekend_module, "weekend_schedule", lambda *_args: (ScheduledSession("Q", "Qualifying", None),))

    assert build_weekend(2026, 19)["sessions"][0]["started"] is False


# ---------------------------------------------------------------------------
# Speed map
# ---------------------------------------------------------------------------

CIRCUIT = CircuitInfo(rotation=90.0, corners=(Corner(1, "", 100.0, 0.0, 0.0), Corner(2, "a", 700.0, 0.0, 90.0)))


def test_corner_labels_sit_off_the_track_and_turn_with_the_map():
    first, second = corner_markers(CIRCUIT)

    assert (first["label"], first["x"], first["y"]) == ("1", 0.0, 100.0)
    assert (first["label_x"], first["label_y"]) == (0.0, 600.0)
    assert (second["label"], second["label_x"], second["label_y"]) == ("2a", -500.0, 700.0)
    assert corner_markers(None) == []


def _loaded(lap_number: int = 4, *, deleted: bool = False, trace: LapTrace | None = None, driver=NOR) -> LoadedLap:
    lap = make_lap(driver.number, lap_number, start=0, time=(trace or _trace()).lap_time, deleted=deleted)
    return LoadedLap(
        driver=driver, choice=LapChoice(lap=lap, fastest=None if deleted else lap), trace=trace or _trace()
    )


@pytest.fixture
def map_inputs(monkeypatch):
    def install(loaded: LoadedLap, circuit: CircuitInfo | None, module=track_map_module):
        monkeypatch.setattr(module, "require_session", lambda _ref: SESSION)
        monkeypatch.setattr(module, "load_circuit_info", lambda *_args: circuit)
        return loaded

    return install


def test_the_speed_map_carries_points_zones_stats_and_what_is_modelled(map_inputs, monkeypatch):
    loaded = map_inputs(_loaded(), CIRCUIT)
    monkeypatch.setattr(track_map_module, "require_lap", lambda *_args: loaded)

    answer = build_track_map(REF, DriverLap("NOR"))

    assert answer["available"] is True
    assert answer["lap"]["is_fastest"] is True
    assert answer["stats"]["distance_m"] == 1000
    # Rotated a quarter turn: the straight along x now runs along y.
    assert answer["points"]["x"][-1] == 0.0
    assert answer["points"]["y"][-1] == pytest.approx(10000.0)
    assert len(answer["corners"]) == 2
    assert "braking_zones" in answer["modeled"]
    assert answer["warnings"] == []


def test_a_deleted_lap_says_so_and_a_map_without_corners_is_unturned(map_inputs, monkeypatch):
    loaded = map_inputs(_loaded(2, deleted=True), None)
    monkeypatch.setattr(track_map_module, "require_lap", lambda *_args: loaded)

    answer = build_track_map(REF, DriverLap("NOR", 2))

    assert answer["warnings"] == [DELETED_LAP_WARNING]
    assert answer["corners"] == []
    assert answer["points"]["y"][-1] == 0.0


# ---------------------------------------------------------------------------
# Head-to-head
# ---------------------------------------------------------------------------


def _pair(monkeypatch, a: LoadedLap, b: LoadedLap) -> None:
    picks = {"NOR": a, "VER": b}
    monkeypatch.setattr(comparison_module, "require_lap", lambda _session, pick: picks[pick.code])


def test_identical_laps_have_no_delta_anywhere(map_inputs, monkeypatch):
    map_inputs(None, CIRCUIT, comparison_module)
    _pair(monkeypatch, _loaded(), _loaded(driver=VER))

    answer = build_comparison(REF, DriverLap("NOR"), DriverLap("VER"))

    assert answer["gap"] == 0.0
    assert set(answer["trace"]["delta"]) == {0.0}
    assert {stretch["faster"] for stretch in answer["mini_sectors"]} == {"even"}
    assert [corner["label"] for corner in answer["corners"]] == ["Turn 1", "Turn 2a"]
    assert answer["biggest_gains"] == {"a": [], "b": []}


def test_the_delta_at_the_line_is_the_lap_time_gap_and_the_stretches_add_up_to_it(map_inputs, monkeypatch):
    map_inputs(None, CIRCUIT, comparison_module)
    slower = _trace(lap_time=10.1, speed=360.0 * 10 / 10.1)
    _pair(monkeypatch, _loaded(), _loaded(trace=slower, driver=VER))

    answer = build_comparison(REF, DriverLap("NOR"), DriverLap("VER"))

    assert answer["gap"] == pytest.approx(0.1, abs=1e-3)
    assert sum(stretch["gain"] for stretch in answer["mini_sectors"]) == pytest.approx(0.1, abs=2e-3)
    assert sum(corner["gain"] for corner in answer["corners"]) == pytest.approx(0.1, abs=2e-3)
    assert {stretch["faster"] for stretch in answer["mini_sectors"]} == {"a"}
    assert len(answer["biggest_gains"]["a"]) == 2
    assert len(answer["trace"]["distance"]) == len(answer["trace"]["speed_b"])


def test_without_corners_the_biggest_gains_come_from_mini_sectors(map_inputs, monkeypatch):
    map_inputs(None, None, comparison_module)
    slower = _trace(lap_time=10.1, speed=360.0 * 10 / 10.1)
    _pair(monkeypatch, _loaded(deleted=True), _loaded(trace=slower, driver=VER))

    answer = build_comparison(REF, DriverLap("NOR"), DriverLap("VER"))

    assert answer["corners"] == []
    assert len(answer["biggest_gains"]["a"]) == comparison_module.TOP_GAIN_COUNT
    assert answer["warnings"] == [f"NOR: {DELETED_LAP_WARNING}"]
    assert answer["corner_markers"] == []


def test_sector_gains_are_left_blank_where_a_sector_time_is_missing(map_inputs, monkeypatch):
    map_inputs(None, None, comparison_module)
    a, b = _loaded(), _loaded(driver=VER)
    a_lap = make_lap(1, 4, start=0, time=10.0, sectors=(3.0, 3.0, 4.0))
    b_lap = make_lap(3, 4, start=0, time=10.0, sectors=(3.1, None, 3.9))
    a = LoadedLap(a.driver, LapChoice(a_lap, a_lap), a.trace)
    b = LoadedLap(b.driver, LapChoice(b_lap, b_lap), b.trace)
    _pair(monkeypatch, a, b)

    sectors = build_comparison(REF, DriverLap("NOR"), DriverLap("VER"))["sectors"]

    assert [sector["gain"] for sector in sectors] == [0.1, None, -0.1]


def test_biggest_gains_rank_each_drivers_best_stretches():
    stretches = [
        {"label": "1", "gain": 0.05, "faster": "a"},
        {"label": "2", "gain": -0.2, "faster": "b"},
        {"label": "3", "gain": 0.1, "faster": "a"},
        {"label": "4", "gain": 0.0, "faster": "even"},
    ]

    gains = biggest_gains(stretches)

    assert [stretch["label"] for stretch in gains["a"]] == ["3", "1"]
    assert [stretch["label"] for stretch in gains["b"]] == ["2"]


def test_an_unavailable_answer_says_why_and_whether_to_wait():
    assert unavailable("loading")["pending"] is True
    assert unavailable("no_lap") == {
        "available": False,
        "pending": False,
        "reason": "no_lap",
        "message": "No timed lap to show for that driver in this session.",
        "source": "openf1",
    }


# ---------------------------------------------------------------------------
# Names: f1db's driver and team names under OpenF1's keys
# ---------------------------------------------------------------------------

MEXICO_QUALIFYING = Path(__file__).parent / "fixtures" / "mexico_2026_r19" / "openf1_drivers_qualifying.json"
DRIVER_KEYS = {"number", "code", "name", "team", "colour"}


def _mexico_cars() -> dict:
    """OpenF1's Mexico City qualifying entry list, read the way the session loader reads it."""
    routes = {"drivers": json.loads(MEXICO_QUALIFYING.read_text())}
    with httpx.Client(transport=httpx.MockTransport(FakeOpenF1(routes))) as client:
        return entry_list(client, 11400)


def test_the_lap_list_names_each_car_as_f1db_does(identity_f1db, monkeypatch):
    cars = _mexico_cars()
    session = make_session_laps((make_lap(50, 1, start=0, time=78.5),), drivers=tuple(cars.values()))
    monkeypatch.setattr(weekend_module, "require_session", lambda _ref: session)

    drivers = {driver["number"]: driver for driver in build_lap_list(REF)["drivers"]}

    assert {key: drivers[50][key] for key in DRIVER_KEYS} == {
        "number": 50,
        "code": "HIR",
        "name": "Ryō Hirakawa",
        "team": "Haas",
        "colour": cars[50].colour,
    }
    assert (drivers[27]["name"], drivers[55]["name"], drivers[3]["team"]) == (
        "Nico Hülkenberg",
        "Carlos Sainz Jr.",
        "Red Bull",
    )


def test_the_speed_maps_driver_prints_f1dbs_names(identity_f1db, map_inputs, monkeypatch):
    car = _mexico_cars()[50]
    loaded = map_inputs(_loaded(driver=car), CIRCUIT)
    monkeypatch.setattr(track_map_module, "require_lap", lambda *_args: loaded)

    driver = build_track_map(REF, DriverLap("HIR"))["driver"]

    assert driver == {"number": 50, "code": "HIR", "name": "Ryō Hirakawa", "team": "Haas", "colour": car.colour}
