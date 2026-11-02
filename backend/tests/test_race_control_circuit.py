"""Tests for app.services.race_control.circuit: the map and record behind the hero.

Each source fails on its own. A missing outline leaves the facts standing; a
missing f1db leaves the map standing; and OpenF1 closing for a live session must
not cost the map once its circuit key has been found.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.data.multiviewer import CircuitLayout, Corner
from app.data.openf1.client import OpenF1UnavailableError
from app.services.race_control import circuit as module
from app.services.race_control.circuit import build_circuit_segment, drawable_map, resolve_circuit_key
from tests.openf1_support import fresh_cache

pytestmark = pytest.mark.unit

PADDING = module.VIEWBOX_PADDING
SQUARE = CircuitLayout(
    season=2026,
    rotation=0.0,
    x=(0.0, 100.0, 100.0, 0.0),
    y=(0.0, 0.0, 50.0, 50.0),
    corners=(Corner(number=1, letter="", x=100.0, y=0.0, angle=0.0),),
)


# -- the drawable map ------------------------------------------------------------


def test_the_outline_fills_the_viewbox_with_north_up():
    drawn = drawable_map(SQUARE)

    scale = (module.VIEWBOX_SIZE - 2 * PADDING) / 100
    assert (drawn["source"], drawn["season"]) == ("MultiViewer", 2026)
    assert (drawn["width"], drawn["height"]) == (module.VIEWBOX_SIZE, round(50 * scale + 2 * PADDING, 1))
    # SVG's y grows downward, so the circuit's top edge (y = 50) is drawn first.
    assert drawn["points"] == [
        [PADDING, round(50 * scale + PADDING, 1)],
        [module.VIEWBOX_SIZE - PADDING, round(50 * scale + PADDING, 1)],
        [module.VIEWBOX_SIZE - PADDING, PADDING],
        [PADDING, PADDING],
    ]


def test_corners_are_placed_in_the_same_frame_with_their_labels_pushed_off_track():
    corner = drawable_map(SQUARE)["corners"][0]

    scale = (module.VIEWBOX_SIZE - 2 * PADDING) / 100
    assert corner["label"] == "1"
    assert [corner["x"], corner["y"]] == [module.VIEWBOX_SIZE - PADDING, round(50 * scale + PADDING, 1)]
    assert corner["label_x"] > corner["x"]


def test_the_map_is_turned_by_the_circuits_rotation():
    turned = drawable_map(CircuitLayout(season=2026, rotation=90.0, x=SQUARE.x, y=SQUARE.y, corners=()))

    # A quarter turn stands the 100 × 50 rectangle on its end.
    assert turned["height"] == module.VIEWBOX_SIZE
    assert turned["width"] < turned["height"]
    assert turned["corners"] == []


def test_a_degenerate_outline_does_not_divide_by_zero():
    point = CircuitLayout(season=2026, rotation=0.0, x=(5.0,) * 3, y=(5.0,) * 3, corners=())

    assert drawable_map(point)["points"] == [[PADDING, PADDING]] * 3


# -- circuit key -----------------------------------------------------------------


@pytest.fixture
def openf1(monkeypatch):
    cache = fresh_cache(monkeypatch, module)
    calls: list[tuple[int, int]] = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def install(answer):
        def find(client, year, round_num):
            calls.append((year, round_num))
            if isinstance(answer, BaseException):
                raise answer
            return answer

        monkeypatch.setattr(module, "openf1_client", _Client)
        monkeypatch.setattr(module, "find_meeting", find)
        return calls

    install.cache = cache
    return install


def test_the_circuit_key_is_found_once_and_then_kept(openf1):
    calls = openf1({"meeting_key": 1, "circuit_key": 14})

    assert resolve_circuit_key(2026, 20) == 14
    assert resolve_circuit_key(2026, 20) == 14
    assert calls == [(2026, 20)]


@pytest.mark.parametrize(
    "answer",
    [None, {"circuit_key": None}, {"circuit_key": "14"}, OpenF1UnavailableError("live")],
    ids=["no-meeting", "no-key", "not-a-number", "openf1-closed"],
)
def test_no_usable_circuit_key_is_none_and_nothing_kept(openf1, answer, capsys):
    calls = openf1(answer)

    assert resolve_circuit_key(2026, 20) is None
    assert resolve_circuit_key(2026, 20) is None
    assert len(calls) == 2
    if isinstance(answer, BaseException):
        assert "race_control.circuit_key.unavailable" in capsys.readouterr().out


# -- the segment -----------------------------------------------------------------

RACE = {"round": 20, "circuit": {"lap_record": {"time": "1:10.540", "driver": "Valtteri Bottas", "year": 2018}}}


@pytest.fixture
def sources(monkeypatch):
    seen: dict[str, tuple] = {}

    def install(*, record=None, layout=SQUARE):
        def fake_record(year, round_num):
            seen["record"] = (year, round_num)
            if isinstance(record, BaseException):
                raise record
            return record

        monkeypatch.setattr(module, "circuit_record", fake_record)
        monkeypatch.setattr(module, "resolve_circuit_key", lambda year, round_num: 14)
        monkeypatch.setattr(
            module, "load_circuit_layout", lambda key, year: seen.setdefault("layout", (key, year)) and layout
        )
        return seen

    return install


def test_the_segment_carries_the_record_the_lap_record_and_the_map(sources):
    seen = sources(record={"circuit_id": "interlagos"})

    segment = build_circuit_segment(2026, RACE)

    assert segment["record"] == {"circuit_id": "interlagos"}
    assert segment["lap_record"] == RACE["circuit"]["lap_record"]
    assert segment["map"] == drawable_map(SQUARE)
    assert seen == {"record": (2026, 20), "layout": (14, 2026)}


def test_a_missing_outline_leaves_the_facts_standing(sources):
    sources(record={"circuit_id": "interlagos"}, layout=None)

    segment = build_circuit_segment(2026, {"round": 20})

    assert segment == {"record": {"circuit_id": "interlagos"}, "lap_record": None, "map": None}


def test_a_failing_f1db_leaves_the_map_standing(sources, capsys):
    sources(record=sqlite3.OperationalError("no such table: circuit"))

    segment = build_circuit_segment(2026, RACE)

    assert segment["record"] is None
    assert segment["map"] is not None
    assert "race_control.circuit_record.failed" in capsys.readouterr().out


@pytest.mark.parametrize("race", [None, {}, {"round": None}])
def test_no_round_has_nothing_to_show(sources, race):
    seen = sources()

    assert build_circuit_segment(2026, race) == {"record": None, "lap_record": None, "map": None}
    assert seen == {}
