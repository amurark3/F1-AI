"""End-to-end replay of a real session through the live WebSocket loop.

No live race required: recorded OpenF1 frames from the 2026 Belgian Grand Prix
(`tests/fixtures/openf1_session_replay.json`) are replayed with their
timestamps rewritten to now, so the whole stack runs — freshness guard,
position builder, event detection, commentary — against real data shapes.

This is the harness to reach for whenever a live session is not available.
"""

import asyncio
import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import WebSocketDisconnect

from app.api import routes
from app.services import live_commentary as lc
from app.services import live_timing_client as client
from app.services.live_timing_client import ActiveSession

pytestmark = pytest.mark.unit

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "openf1_session_replay.json").read_text())


class FakeWebSocket:
    """Records what the loop sends and disconnects once the test has enough."""

    def __init__(self, stop_after_polls: int):
        self.sent: list[dict] = []
        self.stop_after_polls = stop_after_polls

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_text(self) -> str:
        if self.status_count >= self.stop_after_polls:
            raise WebSocketDisconnect(code=1000)
        return ""

    @property
    def status_count(self) -> int:
        return len(self.of_type("session_status"))

    def of_type(self, kind: str) -> list[dict]:
        return [m["data"] for m in self.sent if m["type"] == kind]


class Replay:
    """Serves recorded frames in order, restamped so they read as live."""

    def __init__(self, frames: list[list[dict]], now: datetime):
        self.frames = frames
        self.now = now
        self.index = 0

    def current(self) -> list[dict]:
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return [{**row, "date": self.now.isoformat()} for row in frame]


def _session(now: datetime) -> ActiveSession:
    return ActiveSession(
        session_key="11334",
        session_name="Race",
        session_type="Race",
        meeting_name="Belgian Grand Prix",
        date_start=now - timedelta(minutes=30),
        date_end=now + timedelta(hours=1),
    )


@pytest.fixture
def replay_stack(monkeypatch):
    """Wire the loop to recorded data, a stub model, and a fake socket."""
    now = datetime.now(timezone.utc)
    replay = Replay(FIXTURE["frames"], now)

    async def fake_get_json(_client, path, _params):
        # Branch rather than build a dict: only a position fetch may advance
        # the replay, or the interval and driver lookups skip frames too.
        if path == "position":
            return replay.current()
        if path == "intervals":
            return FIXTURE["intervals"]
        if path == "drivers":
            return FIXTURE["drivers"]
        if path == "laps":
            return [{"lap_number": 14}]
        return None

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    client._driver_cache.clear()

    async def fake_resolve(_year, _round, now=None):
        return _session(now or datetime.now(timezone.utc))

    monkeypatch.setattr(routes, "resolve_active_session", fake_resolve)
    monkeypatch.setattr(routes, "WS_POLL_INTERVAL", 0)

    # Commentary: no flags, no pit stops, and a model that always answers.
    async def _blank_status(_key):
        return ""

    async def _no_stints(_key):
        return {}

    class _Reply:
        content = "Verstappen sweeps into the lead at Spa!"

    class _Chat:
        def invoke(self, _prompt):
            return _Reply()

    monkeypatch.setattr(lc, "fetch_session_status", _blank_status)
    monkeypatch.setattr(lc, "fetch_stint_counts", _no_stints)
    monkeypatch.setattr(lc, "build_chat_llm", lambda: _Chat())
    monkeypatch.setattr(lc, "COMMENTARY_COOLDOWN_SECONDS", 0)
    lc._state.clear()

    return replay


def _drive(ws: FakeWebSocket) -> None:
    """Run the real loop until the fake client disconnects."""
    routes.manager.touch(ws)
    with pytest.raises(WebSocketDisconnect):
        asyncio.run(routes._run_live_loop(ws, "2026-10", 2026, 10))


def test_replay_reports_the_session_as_live(replay_stack):
    ws = FakeWebSocket(stop_after_polls=1)

    _drive(ws)

    status = ws.of_type("session_status")[0]
    assert status["status"] == "live"
    assert status["session_name"] == "Race"
    assert status["meeting_name"] == "Belgian Grand Prix"
    assert status["lap"] == 14


def test_replay_streams_the_timing_tower(replay_stack):
    ws = FakeWebSocket(stop_after_polls=1)

    _drive(ws)

    rows = ws.of_type("positions")[0]
    assert [r["position"] for r in rows] == [1, 2, 3, 4, 5, 6, 13]
    assert rows[0]["driver"] == "ANT"
    assert rows[0]["driver_number"] == 12
    assert rows[0]["gap"] == "LEADER"


def test_replay_narrates_a_real_overtake(replay_stack):
    """Frame two is a genuine swap for the lead at Spa: ANT loses P1 to VER."""
    ws = FakeWebSocket(stop_after_polls=2)

    _drive(ws)

    entries = ws.of_type("commentary")
    assert len(entries) == 1
    assert entries[0]["event_type"] == "position_change"
    assert entries[0]["text"] == "Verstappen sweeps into the lead at Spa!"


def test_replay_stays_silent_on_the_opening_snapshot(replay_stack):
    ws = FakeWebSocket(stop_after_polls=1)

    _drive(ws)

    assert ws.of_type("commentary") == []


def test_replay_goes_to_standby_when_the_feed_goes_stale(monkeypatch, replay_stack):
    """The same recorded frames at their original 19 July timestamps."""
    async def stale_get_json(_client, path, _params):
        if path == "position":
            return FIXTURE["frames"][0]
        if path == "intervals":
            return FIXTURE["intervals"]
        if path == "drivers":
            return FIXTURE["drivers"]
        return []

    monkeypatch.setattr(client, "_get_json", stale_get_json)
    client._driver_cache.clear()
    ws = FakeWebSocket(stop_after_polls=1)

    _drive(ws)

    assert ws.of_type("session_status")[0]["status"] == "standby"
    assert ws.of_type("positions") == [], "a finished session was replayed as live"


def test_replay_reports_standby_when_no_session_is_running(monkeypatch, replay_stack):
    async def no_session(_year, _round, now=None):
        return None

    monkeypatch.setattr(routes, "resolve_active_session", no_session)
    monkeypatch.setattr(routes, "WS_IDLE_POLL_INTERVAL", 0)
    ws = FakeWebSocket(stop_after_polls=1)

    _drive(ws)

    status = ws.of_type("session_status")[0]
    assert status["status"] == "standby"
    assert status["session_name"] is None
    assert ws.of_type("positions") == []
