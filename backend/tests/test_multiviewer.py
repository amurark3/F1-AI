"""Tests for app.data.multiviewer: optional corner labels and map rotation.

MultiViewer is unofficial, so every failure ends in ``None`` and the map draws
without corner numbers rather than failing.
"""

from __future__ import annotations

import httpx
import pytest

from app.data import multiviewer as module
from app.data.multiviewer import CircuitInfo, Corner, load_circuit_info, parse_circuit_info
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
