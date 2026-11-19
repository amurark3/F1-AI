"""The debrief's lap leaders and race trace, on Mexico City 2026's real laps (the top five's), plus edge cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.laps import Lap
from app.data.openf1.session_laps import SessionLaps
from app.data.openf1.sessions import EntryDriver
from app.services import debrief_laps as module, race_results
from tests.debrief_r19_support import race_session, race_session_laps

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)


@pytest.fixture
def mexico(race_results_f1db, monkeypatch):
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    monkeypatch.setattr(module, "load_session_laps", lambda *_args: race_session_laps())
    return module.build_debrief_laps(2026, 19)


def test_mexico_leaders_are_leclerc_antonelli_then_verstappen(mexico):
    leaders = mexico["leaders"]

    assert mexico["available"] is True
    assert mexico["total_laps"] == len(leaders) == 71
    assert [(code, leaders.count(code)) for code in ("LEC", "ANT", "VER")] == [("LEC", 27), ("ANT", 16), ("VER", 28)]
    assert leaders[:27] == ["LEC"] * 27
    assert leaders[27:43] == ["ANT"] * 16
    assert leaders[43:] == ["VER"] * 28
    assert [row["driver_code"] for row in mexico["drivers"]][:3] == ["LEC", "ANT", "VER"]


def test_mexico_trace_follows_the_classification_and_ends_on_the_fia_margins(mexico):
    trace = mexico["trace"]

    assert [row["driver_code"] for row in trace] == ["VER", "HAM", "ANT", "LEC", "NOR"]
    assert [row["position"] for row in trace] == [1, 2, 3, 4, 5]
    assert all(len(row["gaps"]) == 71 for row in trace)
    assert trace[0]["gaps"][-1] == 0.0
    assert trace[1]["gaps"][-1] == pytest.approx(0.799, abs=0.05)
    assert trace[2]["gaps"][-1] == pytest.approx(4.006, abs=0.05)


def test_mexico_neutralisations_are_the_vsc_safety_cars_and_red_flag(mexico):
    assert mexico["neutralisations"] == [
        {"kind": "vsc", "start_lap": 7, "end_lap": 8},
        {"kind": "sc", "start_lap": 44, "end_lap": 44},
        {"kind": "red", "start_lap": 45, "end_lap": 46},
        {"kind": "sc", "start_lap": 59, "end_lap": 62},
    ]


def _lap(driver: int, number: int, start: int, time: float | None) -> Lap:
    return Lap(
        driver=driver,
        number=number,
        start=T0 + timedelta(seconds=start),
        time=time,
        sectors=(None, None, None),
        traps=(None, None, None),
        pit_out=False,
    )


def _session(laps: list[Lap], *, drivers: tuple[int, ...] = (1, 2)) -> SessionLaps:
    entries = {
        n: EntryDriver(number=n, code=f"D{n}", name=f"Driver {n}", team="Team", colour="#FFFFFF") for n in drivers
    }
    return SessionLaps(session=race_session(), year=2026, round=19, drivers=entries, laps=tuple(laps), windows=())


def _serve(monkeypatch, session, classification):
    monkeypatch.setattr(module, "load_session_laps", lambda *_args: session)
    monkeypatch.setattr(
        module,
        "build_session_result",
        lambda *_args: {"classification": classification} if classification is not None else None,
    )


def _row(code: str, position: int | None) -> dict:
    return {"driver_code": code, "position": position}


def test_a_lap_without_a_time_crosses_where_the_next_lap_starts(monkeypatch):
    laps = [_lap(1, 1, 0, None), _lap(1, 2, 100, 90.0), _lap(2, 1, 0, 95.0), _lap(2, 2, 95, 96.0)]
    _serve(monkeypatch, _session(laps), [_row("D1", 1), _row("D2", 2)])

    result = module.build_debrief_laps(2026, 19)

    assert result["leaders"] == ["D2", "D1"]
    assert result["trace"][0]["gaps"] == [5.0, 0.0]


def test_a_lap_nobody_crossed_has_no_leader_and_no_gap(monkeypatch):
    laps = [_lap(1, 1, 0, 90.0), _lap(1, 3, 200, 90.0), _lap(2, 1, 0, 91.0)]
    _serve(monkeypatch, _session(laps), [_row("D1", 1), _row("D2", 2)])

    result = module.build_debrief_laps(2026, 19)

    assert result["total_laps"] == 3
    assert result["leaders"] == ["D1", None, "D1"]
    assert result["trace"][1]["gaps"] == [1.0, None, None]


def test_a_top_five_car_openf1_does_not_list_is_skipped(monkeypatch):
    _serve(
        monkeypatch, _session([_lap(1, 1, 0, 90.0)], drivers=(1,)), [_row("ZZZ", 1), _row("D1", 2), _row("DNF", None)]
    )

    result = module.build_debrief_laps(2026, 19)

    assert [row["driver_code"] for row in result["trace"]] == ["D1"]


def test_a_race_with_no_classification_still_gives_leaders(monkeypatch):
    _serve(monkeypatch, _session([_lap(1, 1, 0, 90.0), _lap(9, 1, 0, 80.0)]), None)

    result = module.build_debrief_laps(2026, 19)

    assert (result["leaders"], result["trace"]) == (["D1"], [])


@pytest.mark.parametrize("held", [None, "no laps"])
def test_no_session_or_no_laps_is_unavailable(monkeypatch, held):
    session = None if held is None else replace(_session([]))
    monkeypatch.setattr(module, "load_session_laps", lambda *_args: session)

    assert module.build_debrief_laps(2026, 19) == {
        "available": False,
        "reason": "OpenF1 hasn't published this race's laps yet.",
        "total_laps": 0,
        "drivers": [],
        "leaders": [],
        "trace": [],
        "neutralisations": [],
    }


def test_openf1_being_down_propagates(monkeypatch):
    def down(*_args):
        raise OpenF1UnavailableError("laps: HTTP 503")

    monkeypatch.setattr(module, "load_session_laps", down)

    with pytest.raises(OpenF1UnavailableError):
        module.build_debrief_laps(2026, 19)
