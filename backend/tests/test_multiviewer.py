"""Tests for app.data.multiviewer: optional corner labels and map rotation.

MultiViewer is unofficial, so every failure ends in ``None`` and the map draws
without corner numbers rather than failing.
"""

from __future__ import annotations

import httpx
import pytest

from app.data import multiviewer as module
from app.data.multiviewer import (
    CircuitInfo,
    CircuitLayout,
    Corner,
    load_circuit_info,
    load_circuit_layout,
    parse_circuit_info,
    parse_circuit_layout,
)
from tests.openf1_support import fresh_cache

pytestmark = pytest.mark.unit

AUSTIN = {
    "rotation": 0,
    "corners": [
        {"number": 2, "angle": -200.3, "trackPosition": {"x": 3414.0, "y": -1696.5}},
        {"number": 1, "letter": "a", "angle": -44.65, "trackPosition": {"x": 3743.5, "y": -4013.4}},
        {"number": 3, "trackPosition": "missing"},
        {"number": "x", "trackPosition": {"x": 1, "y": 1}},
        "not a corner",
    ],
}


def test_corners_are_read_and_ordered_and_bad_ones_skipped():
    info = parse_circuit_info(AUSTIN)

    assert info == CircuitInfo(
        rotation=0.0,
        corners=(Corner(1, "a", 3743.5, -4013.4, -44.65), Corner(2, "", 3414.0, -1696.5, -200.3)),
    )
    assert CircuitInfo.from_json(info.to_json()) == info


@pytest.mark.parametrize(
    "payload",
    [None, [], {"corners": "none"}, {"corners": []}, {"corners": ["x"]}],
    ids=["null", "list", "corners-not-list", "no-corners", "no-usable-corner"],
)
def test_an_answer_without_usable_corners_is_none(payload):
    assert parse_circuit_info(payload) is None


def test_an_unreadable_rotation_is_none_rather_than_a_crash():
    info = parse_circuit_info({**AUSTIN, "rotation": "north"})

    assert info is not None
    assert info.rotation == 0.0


@pytest.fixture
def multiviewer(monkeypatch):
    cache = fresh_cache(monkeypatch, module)
    calls: list[str] = []

    def install(handler):
        def recorded(request):
            calls.append(str(request.url))
            return handler(request)

        monkeypatch.setattr(module, "new_client", lambda: httpx.Client(transport=httpx.MockTransport(recorded)))
        return calls

    install.cache = cache
    return install


def test_the_circuit_is_fetched_once_and_then_kept(multiviewer):
    calls = multiviewer(lambda request: httpx.Response(200, json=AUSTIN))

    first = load_circuit_info(9, 2026)

    assert first is not None
    assert load_circuit_info(9, 2026) == first
    assert calls == [f"{module.MULTIVIEWER_BASE}/9/2026"]


@pytest.mark.parametrize(
    "answer",
    [
        lambda request: httpx.Response(404),
        lambda request: httpx.Response(200, content=b"<html>"),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)),
    ],
    ids=["not-found", "not-json", "unreachable"],
)
def test_a_failing_multiviewer_is_no_corners_and_nothing_kept(multiviewer, answer):
    calls = multiviewer(answer)

    assert load_circuit_info(9, 2026) is None
    assert load_circuit_info(9, 2026) is None
    assert len(calls) == 2


def test_the_default_client_carries_the_configured_timeout():
    with module.new_client() as client:
        assert client.timeout.read == module.OPENF1_HTTP_TIMEOUT_SECONDS


def test_a_session_without_a_circuit_key_asks_nothing(multiviewer):
    calls = multiviewer(lambda request: httpx.Response(200, json=AUSTIN))

    assert load_circuit_info(None, 2026) is None
    assert calls == []


# -- circuit outline ------------------------------------------------------------

OUTLINE = {
    **AUSTIN,
    "rotation": 90,
    "x": [float(index) for index in range(module.MIN_OUTLINE_POINTS)],
    "y": [float(index * 2) for index in range(module.MIN_OUTLINE_POINTS)],
}


def test_an_outline_is_read_with_its_rotation_and_corners():
    layout = parse_circuit_layout(OUTLINE, 2026)

    assert layout is not None
    assert (layout.season, layout.rotation) == (2026, 90.0)
    assert layout.x[:3] == (0.0, 1.0, 2.0)
    assert layout.y[:3] == (0.0, 2.0, 4.0)
    assert [corner.number for corner in layout.corners] == [1, 2]
    assert CircuitLayout.from_json(layout.to_json()) == layout


def test_an_outline_without_corners_still_draws():
    layout = parse_circuit_layout({"x": OUTLINE["x"], "y": OUTLINE["y"], "rotation": "north"}, 2025)

    assert layout is not None
    assert (layout.rotation, layout.corners) == (0.0, ())


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"x": "none", "y": []},
        {"x": OUTLINE["x"], "y": OUTLINE["y"][:-1]},
        {"x": OUTLINE["x"][:5], "y": OUTLINE["y"][:5]},
        {"x": [*OUTLINE["x"][:-1], "far"], "y": OUTLINE["y"]},
        {"x": [*OUTLINE["x"][:-1], True], "y": OUTLINE["y"]},
    ],
    ids=["null", "not-lists", "uneven", "too-short", "not-numbers", "boolean"],
)
def test_an_unusable_outline_is_none(payload):
    assert parse_circuit_layout(payload, 2026) is None


def test_the_seasons_outline_is_fetched_once_and_then_kept(multiviewer):
    calls = multiviewer(lambda request: httpx.Response(200, json=OUTLINE))

    first = load_circuit_layout(14, 2026)

    assert first is not None
    assert first.season == 2026
    assert load_circuit_layout(14, 2026) == first
    assert calls == [f"{module.MULTIVIEWER_BASE}/14/2026"]


def test_a_season_multiviewer_has_not_mapped_falls_back_to_the_last(multiviewer):
    calls = multiviewer(
        lambda request: httpx.Response(404) if request.url.path.endswith("/2026") else httpx.Response(200, json=OUTLINE)
    )

    layout = load_circuit_layout(14, 2026)

    assert layout is not None
    assert layout.season == 2025
    # The fallback is kept under the season it came from, so the new season is
    # asked for again until MultiViewer maps it.
    assert load_circuit_layout(14, 2026) == layout
    assert calls == [f"{module.MULTIVIEWER_BASE}/14/{year}" for year in (2026, 2025, 2026)]


def test_no_outline_in_either_season_is_none(multiviewer):
    multiviewer(lambda request: httpx.Response(404))

    assert load_circuit_layout(14, 2026) is None


def test_no_circuit_key_asks_for_no_outline(multiviewer):
    calls = multiviewer(lambda request: httpx.Response(200, json=OUTLINE))

    assert load_circuit_layout(None, 2026) is None
    assert calls == []
