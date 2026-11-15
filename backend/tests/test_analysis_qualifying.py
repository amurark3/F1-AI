"""Qualifying segments in the Telemetry Lab, against captured OpenF1 data.

* Mexico City 2026 qualifying (session 11400): the windows are exactly
  21:00:00-21:25:07, 21:33:00-21:48:00 and 21:55:00-22:08:00 UTC, every driver's
  best per segment is OpenF1's ``session_result`` duration, and Lawson, who ran
  Q3 and was then disqualified (f1db says so, OpenF1 does not), does not lift
  Hülkenberg into Q3: he is out in Q2, P10 after the disqualification.
* China 2026 sprint qualifying (11236) groups SQ1-SQ3.
* Miami 2026 sprint qualifying publishes no phase 1 in race control, so nothing is grouped.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data.openf1 import session_laps as laps_module
from app.data.openf1.qualifying_result import ResultRow, result_rows
from app.data.openf1.race_control import SegmentWindow, segment_windows
from app.data.openf1.session_laps import SessionLaps, load_session_laps
from app.services.analysis import qualifying as qualifying_module, weekend as weekend_module
from app.services.analysis.common import SessionRef
from app.services.analysis.lap_selection import choose_lap, segment_of, timed_laps
from app.services.analysis.weekend import build_lap_list
from tests.openf1_support import T0, fresh_cache, make_lap, make_session, make_session_laps, serve

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
SEGMENTS = FIXTURES / "qualifying_segments"
MEXICO_DRIVERS = FIXTURES / "mexico_2026_r19" / "openf1_drivers_qualifying.json"
NOTICE = "Q1/Q2/Q3 not published for this session"


def _read(name: str) -> list[dict]:
    return json.loads((SEGMENTS / name).read_text())


def _dsq(*codes: str):
    entries = [SimpleNamespace(driver_code=code, position_text="DSQ") for code in codes]
    return lambda *_args: [SimpleNamespace(driver_code="HAM", position_text="1"), *entries]


def _load(monkeypatch, code: str, prefix: str, drivers: Path, race_control: str | None = None) -> SessionLaps:
    fresh_cache(monkeypatch, laps_module)
    monkeypatch.setattr(laps_module, "find_session", lambda *_args: make_session(code))
    routes = {
        "drivers": json.loads(drivers.read_text()),
        "laps": _read(f"{prefix}_laps.json"),
        "race_control": _read(race_control or f"{prefix}_race_control.json"),
        "session_result": _read(f"{prefix}_session_result.json"),
    }
    serve(monkeypatch, laps_module, routes)
    loaded = load_session_laps(2026, 19, code)
    assert loaded is not None
    return loaded


@pytest.fixture
def mexico(monkeypatch, identity_f1db) -> SessionLaps:
    monkeypatch.setattr(qualifying_module, "session_classification", _dsq("LAW"))
    return _load(monkeypatch, "Q", "mexico_q", MEXICO_DRIVERS)


def _answer(monkeypatch, session: SessionLaps) -> dict:
    monkeypatch.setattr(weekend_module, "require_session", lambda _ref: session)
    return build_lap_list(SessionRef(2026, 19, session.session.code))


def _by_code(answer: dict) -> dict:
    return {driver["code"]: driver for driver in answer["drivers"]}


def _groups(answer: dict) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for driver in answer["drivers"]:
        groups.setdefault(driver.get("group"), []).append(driver["code"])
    return groups


def test_the_mexico_windows_are_the_published_ones(mexico):
    def at(clock: str) -> str:
        return f"2026-10-31T{clock}+00:00"

    assert [(w.number, w.start.isoformat(), w.end.isoformat()) for w in mexico.segments] == [
        (1, at("21:00:00"), at("21:25:07")),
        (2, at("21:33:00"), at("21:48:00")),
        (3, at("21:55:00"), at("22:08:00")),
    ]


def test_every_best_per_segment_is_the_classifications_duration(monkeypatch, mexico):
    answer = _answer(monkeypatch, mexico)

    assert answer["segments"]["confirmed"] is True
    assert answer["segments"]["labels"] == ["Q1", "Q2", "Q3"]
    for row in mexico.result:
        driver = next(d for d in answer["drivers"] if d["number"] == row.driver)
        if driver["code"] == "LAW":
            # The classification drops his Q1 time (78.097 on the road) along with the disqualification.
            assert driver["segment_bests"] == [78.097, *row.durations[1:]]
        else:
            assert driver["segment_bests"] == list(row.durations)


def test_the_groups_follow_the_on_road_knock_outs_with_the_disqualified_car_put_back(monkeypatch, mexico):
    drivers = _by_code(_answer(monkeypatch, mexico))
    groups = _groups(_answer(monkeypatch, mexico))

    assert {name: len(codes) for name, codes in groups.items()} == {
        "q3": 9,
        "disqualified": 1,
        "out_q2": 6,
        "out_q1": 6,
    }
    assert groups["disqualified"] == ["LAW"]
    assert drivers["LAW"]["segment_reached"] == 3
    assert drivers["LAW"]["disqualified"] is True
    assert drivers["LAW"]["classified"] is None
    assert drivers["HUL"]["group"] == "out_q2"
    assert drivers["HUL"]["note"] == "P10 after Lawson's DSQ"
    assert drivers["ALB"]["group"] == "out_q1"
    assert drivers["ALB"]["note"] == "P16 after Lawson's DSQ"
    assert drivers["HAM"]["note"] is None


def test_a_lap_names_the_segment_it_began_in(monkeypatch, mexico):
    laps = timed_laps(mexico, 44)

    assert {1, 2, 3} <= {lap["segment"] for lap in laps}
    fastest = next(lap for lap in laps if lap["is_fastest"])
    assert (fastest["segment"], fastest["time"]) == (3, 76.514)


def test_the_fastest_lap_can_be_asked_for_within_a_segment(mexico):
    overall = choose_lap(mexico, 44, None)
    second = choose_lap(mexico, 44, None, segment=2)
    named = choose_lap(mexico, 44, second.lap.number, segment=1)

    assert (overall.lap.time, second.lap.time) == (76.514, 76.953)
    assert second.fastest == second.lap
    assert named.lap == second.lap
    assert named.fastest.time == 77.341
    assert choose_lap(mexico, 27, None, segment=3) is None


def test_a_deleted_lap_is_left_out_of_its_own_segment_only():
    windows = (
        SegmentWindow(1, T0, T0.replace(minute=10)),
        SegmentWindow(2, T0.replace(minute=20), T0.replace(minute=30)),
    )
    laps = (
        make_lap(1, 2, start=60, time=90.0, deleted=True),
        make_lap(1, 3, start=300, time=95.0),
        make_lap(1, 5, start=1300, time=91.0),
        make_lap(1, 6, start=None, time=80.0),
    )
    session = make_session_laps(laps)
    session = SessionLaps(**{**session.__dict__, "segments": windows})

    assert choose_lap(session, 1, None, segment=1).lap.number == 3
    assert choose_lap(session, 1, None, segment=2).lap.number == 5
    assert choose_lap(session, 1, None).lap.number == 5
    assert [segment_of(lap, windows) for lap in laps] == [1, 1, 2, None]


def test_the_china_sprint_qualifying_groups_sq1_to_sq3(monkeypatch, identity_f1db):
    session = _load(monkeypatch, "SQ", "shanghai_sq", SEGMENTS / "shanghai_sq_drivers.json")
    monkeypatch.setattr(qualifying_module, "session_classification", _dsq())
    answer = _answer(monkeypatch, session)

    assert answer["segments"]["labels"] == ["SQ1", "SQ2", "SQ3"]
    assert [w["label"] for w in answer["segments"]["windows"]] == ["SQ1", "SQ2", "SQ3"]
    assert answer["segments"]["confirmed"] is True
    groups = _groups(answer)
    assert {name: len(codes) for name, codes in groups.items() if name} == {"q3": 10, "out_q2": 6, "out_q1": 5}
    assert groups[None] == ["PER"]


def test_a_session_with_some_phases_missing_has_no_windows():
    assert segment_windows(_read("miami_sq_race_control.json")) == ()


def test_a_session_without_phases_stays_ungrouped_with_a_notice(monkeypatch):
    session = make_session_laps((make_lap(1, 2, start=0, time=90.0),))

    answer = _answer(monkeypatch, session)

    assert answer["segments"] == {"available": False, "labels": ["Q1", "Q2", "Q3"], "notice": NOTICE}
    assert "group" not in answer["drivers"][0]
    assert answer["drivers"][0]["laps"][0]["segment"] is None


def test_practice_sessions_carry_no_segment_block(monkeypatch):
    answer = _answer(monkeypatch, SessionLaps(**{**make_session_laps(()).__dict__, "session": make_session("R")}))

    assert "segments" not in answer


def test_a_best_outside_its_window_marks_the_grouping_unconfirmed(monkeypatch, mexico, capsys):
    wrong = tuple(
        ResultRow(
            row.driver,
            row.position,
            (row.durations[0] + 1 if row.driver == 44 else row.durations[0], *row.durations[1:]),
        )
        for row in mexico.result
    )
    skewed = SessionLaps(**{**mexico.__dict__, "result": wrong})

    answer = _answer(monkeypatch, skewed)

    assert answer["segments"]["confirmed"] is False
    assert _groups(answer)["q3"]
    assert "segment_mismatch" in capsys.readouterr().out


def test_without_a_classification_nothing_is_confirmed_or_grouped(monkeypatch, mexico):
    bare = SessionLaps(**{**mexico.__dict__, "result": ()})

    answer = _answer(monkeypatch, bare)

    assert answer["segments"]["confirmed"] is False
    assert set(_groups(answer)) == {None}
    assert answer["drivers"][0]["segment_bests"]


def test_when_f1db_cannot_say_nobody_is_disqualified_and_it_is_logged(monkeypatch, mexico):
    def broken(*_args):
        raise RuntimeError("no f1db")

    monkeypatch.setattr(qualifying_module, "session_classification", broken)

    answer = _answer(monkeypatch, mexico)

    assert _by_code(answer)["LAW"]["disqualified"] is False
    assert _by_code(answer)["LAW"]["group"] == "q3"


def test_a_field_of_twenty_lets_fifteen_through_the_first_segment():
    assert [qualifying_module._reached(i, 20) for i in (9, 10, 14, 15)] == [3, 2, 2, 1]
    assert [qualifying_module._reached(i, 22) for i in (9, 10, 15, 16)] == [3, 2, 2, 1]


def test_segment_state_survives_the_round_trip_through_the_cache(mexico):
    assert SessionLaps.from_json(mexico.to_json()) == mexico


def test_malformed_windows_and_results_are_refused_or_skipped():
    with pytest.raises(ValueError, match="both ends"):
        SegmentWindow.from_json({"number": 1, "start": None, "end": None})
    rows = result_rows(
        [
            {"driver_number": 1, "position": 1, "duration": [70.0, "x", None]},
            {"driver_number": 2, "position": None, "duration": 70.0},
            {"driver_number": None},
        ]
    )
    assert rows == (ResultRow(1, 1, (70.0, None, None)), ResultRow(2, None, (None, None, None)))
