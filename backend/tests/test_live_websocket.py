"""Tests for app.api.live.websocket — the live-timing endpoint's lifecycle.

``live_timing`` holds a socket, a heartbeat task and an entry in a process-wide
registry for as long as a race weekend lasts. The risks are lifecycle ones:

* **Every exit path must release everything.** A normal disconnect, a stale
  connection and a bug in the loop all have to end with the heartbeat task
  cancelled and the socket out of the registry — otherwise the process
  accumulates tasks pinging dead sockets.
* **A crash must not look like a disconnect.** Both used to land in the same
  silent handler, which hid real bugs in the loop.
* **Between sessions nothing is polled.** A round with no active session holds
  the socket open and reports standby, without asking OpenF1 for timing.

Session resolution and frame-by-frame behaviour are covered by
``test_live_replay.py`` and ``test_live_loop_pacing.py``. Timers here are
neutralised by patching both poll intervals to zero and the receive timeout to
milliseconds, and every fake client disconnects after a bounded number of
reads, so no test can hang.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

from fastapi import WebSocketDisconnect
import pytest

from app.api.live import websocket as ws_mod
from app.api.live.connections import ConnectionManager
from app.services.live_timing_client import ActiveSession, SessionLookup, TimingSnapshot

ROOM = "2026-4"
ROWS = [
    {"position": 1, "driver": "VER", "gap": "LEADER"},
    {"position": 2, "driver": "NOR", "gap": "+1.200"},
]


class _FakeWebSocket:
    """A client that answers a bounded number of reads, then disconnects.

    ``incoming`` may hold exceptions, which are raised instead of returned —
    that is how a mid-session disconnect or a transport error arrives. Once the
    queue empties every further read raises ``WebSocketDisconnect``, which is
    what bounds the endpoint's loop.
    """

    def __init__(self, *, incoming=(), send_error=None):
        self.accepted = False
        self.sent: list[dict] = []
        self.reads = 0
        self._incoming = list(incoming)
        self._send_error = send_error

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        if self._send_error is not None:
            raise self._send_error
        self.sent.append(payload)

    async def receive_text(self):
        self.reads += 1
        if not self._incoming:
            raise WebSocketDisconnect(1001)
        nxt = self._incoming.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    def payloads_of(self, kind):
        return [payload["data"] for payload in self.sent if payload["type"] == kind]


def _active(now: datetime) -> ActiveSession:
    return ActiveSession(
        session_key="9999",
        session_name="Race",
        session_type="Race",
        meeting_name="Japanese Grand Prix",
        date_start=now - timedelta(minutes=20),
        date_end=now + timedelta(hours=1),
    )


def _serve(monkeypatch, *, active=True, poll=None):
    """Answer session lookups and timing polls without touching OpenF1.

    ``poll`` replaces the timing poll outright; by default every poll returns
    the same two-car running order sampled a few seconds ago.
    """
    polls: list[str] = []

    async def _resolve(_year, _round, now=None):
        moment = now or datetime.now(timezone.utc)
        return SessionLookup(active=_active(moment) if active else None, next_start=None)

    async def _poll(session, now=None, last_lap=None):
        polls.append(session.session_key)
        return TimingSnapshot(rows=ROWS, sampled_at=now - timedelta(seconds=3), lap=12)

    monkeypatch.setattr(ws_mod, "resolve_session_window", _resolve)
    monkeypatch.setattr(ws_mod, "poll_timing", poll or _poll)
    return polls


@pytest.fixture
def manager(monkeypatch):
    """A registry per test — production uses a module-level singleton."""
    fresh = ConnectionManager()
    monkeypatch.setattr(ws_mod, "manager", fresh)
    return fresh


@pytest.fixture
def no_waiting(monkeypatch):
    """Collapse both poll intervals so the loop costs no wall time."""
    monkeypatch.setattr(ws_mod, "WS_POLL_INTERVAL", 0)
    monkeypatch.setattr(ws_mod, "WS_IDLE_POLL_INTERVAL", 0)


@pytest.fixture
def spied_tasks(monkeypatch):
    """Capture the background tasks the endpoint creates, to assert cleanup."""
    created: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def _spy(coro):
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(ws_mod.asyncio, "create_task", _spy)
    return created


async def _drain(task):
    """Let a cancelled task finish so ``cancelled()`` is meaningful."""
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# _drain_client
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_client_keepalive_refreshes_the_connection(manager):
    ws = _FakeWebSocket(incoming=["ping"])
    await manager.connect(ROOM, ws)
    manager.last_activity[id(ws)] = 0.0

    await ws_mod._drain_client(ws)

    assert manager.is_stale(ws) is False


@pytest.mark.unit
async def test_a_silent_client_is_not_treated_as_an_error(monkeypatch, manager):
    """Browsers send nothing unless prompted; the timeout is the normal case."""
    monkeypatch.setattr(ws_mod, "WS_RECEIVE_TIMEOUT", 0.01)
    idle = asyncio.Event()

    class _SilentClient(_FakeWebSocket):
        async def receive_text(self):
            await idle.wait()  # never set — the wait_for timeout is what ends this
            return ""

    ws = _SilentClient()
    await manager.connect(ROOM, ws)
    before = manager.last_activity[id(ws)]

    await ws_mod._drain_client(ws)

    assert manager.last_activity[id(ws)] == before, "silence is not activity"


@pytest.mark.unit
async def test_a_disconnect_while_reading_propagates_to_the_endpoint(manager):
    """Only the timeout is swallowed; a real disconnect must end the loop."""
    ws = _FakeWebSocket()

    with pytest.raises(WebSocketDisconnect):
        await ws_mod._drain_client(ws)


# ---------------------------------------------------------------------------
# live_timing — connection lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_session_streams_until_the_client_disconnects(monkeypatch, manager, no_waiting, spied_tasks):
    _serve(monkeypatch)
    ws = _FakeWebSocket(incoming=["keepalive", "keepalive"])

    await ws_mod.live_timing(ws, 2026, 4)

    assert ws.accepted is True
    assert len(ws.payloads_of("positions")) == 3, "one broadcast per loop iteration"
    statuses = ws.payloads_of("session_status")
    assert {status["status"] for status in statuses} == {"live"}
    assert statuses[0]["session_name"] == "Race"
    assert statuses[0]["lap"] == 12
    assert statuses[0]["feed_age_seconds"] == 3
    assert manager.rooms == {}, "the socket must be out of the registry on exit"
    assert manager.last_activity == {}
    await _drain(spied_tasks[0])
    assert spied_tasks[0].cancelled(), "the heartbeat task must not outlive the connection"


@pytest.mark.unit
async def test_a_round_with_no_session_on_track_holds_the_socket_without_polling(
    monkeypatch, manager, no_waiting, spied_tasks
):
    polls = _serve(monkeypatch, active=False)
    ws = _FakeWebSocket(incoming=["keepalive"])

    await ws_mod.live_timing(ws, 2030, 99)

    assert polls == [], "no active session means nothing to poll"
    assert ws.payloads_of("positions") == []
    assert [status["status"] for status in ws.payloads_of("session_status")] == ["standby", "standby"]
    assert ws.payloads_of("session_status")[0]["session_name"] is None
    assert manager.rooms == {}
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_quiet_feed_reports_status_without_positions(monkeypatch, manager, no_waiting, spied_tasks):
    """An open session whose feed has not answered is standby, not live."""

    async def _nothing(_session, now=None, last_lap=None):
        return None

    _serve(monkeypatch, poll=_nothing)
    ws = _FakeWebSocket()

    await ws_mod.live_timing(ws, 2026, 4)

    [status] = ws.payloads_of("session_status")
    assert status["status"] == "standby"
    assert status["session_name"] == "Race", "the desk can still say which session is due"
    assert status["lap"] is None
    assert status["feed_age_seconds"] is None
    assert ws.payloads_of("positions") == []
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_stale_connection_is_dropped_before_polling(monkeypatch, manager, no_waiting, spied_tasks, capsys):
    _serve(monkeypatch)
    monkeypatch.setattr(manager, "is_stale", lambda _ws: True)
    ws = _FakeWebSocket(incoming=["keepalive"] * 3)

    await ws_mod.live_timing(ws, 2026, 4)

    assert ws.sent == [], "a connection past the stale timeout gets no further frames"
    assert ws.reads == 0, "the loop must break out rather than complete an iteration"
    assert "ws.stale_connection" in capsys.readouterr().out
    assert manager.rooms == {}
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_bug_in_the_loop_is_logged_and_still_releases_the_socket(
    monkeypatch, manager, no_waiting, spied_tasks, capsys
):
    """A crash used to be indistinguishable from a normal disconnect."""

    async def _broken(_session, now=None, last_lap=None):
        raise TypeError("positions payload changed shape")

    _serve(monkeypatch, poll=_broken)
    ws = _FakeWebSocket()

    await ws_mod.live_timing(ws, 2026, 4)

    logged = capsys.readouterr().out
    assert "ws.live_timing_failed" in logged
    assert "positions payload changed shape" in logged
    assert manager.rooms == {}
    await _drain(spied_tasks[0])
    assert spied_tasks[0].cancelled()


@pytest.mark.unit
async def test_a_disconnect_mid_broadcast_is_not_reported_as_a_crash(
    monkeypatch, manager, no_waiting, spied_tasks, capsys
):
    _serve(monkeypatch)
    ws = _FakeWebSocket(send_error=WebSocketDisconnect(1006))

    await ws_mod.live_timing(ws, 2026, 4)

    logged = capsys.readouterr().out
    assert "ws.client_disconnected" in logged
    assert "ws.live_timing_failed" not in logged
    assert manager.rooms == {}
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_failed_handshake_leaves_nothing_behind(monkeypatch, manager, no_waiting, spied_tasks):
    """``connect`` raising means no heartbeat is ever started to leak."""

    class _RejectingClient(_FakeWebSocket):
        async def accept(self):
            raise RuntimeError("handshake rejected")

    _serve(monkeypatch)

    with pytest.raises(RuntimeError, match="handshake rejected"):
        await ws_mod.live_timing(_RejectingClient(), 2026, 4)

    assert manager.rooms == {}
    assert spied_tasks == []


# ---------------------------------------------------------------------------
# _feed_age
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_feed_age_is_never_negative_under_clock_skew():
    now = datetime(2026, 4, 5, 6, 0, tzinfo=timezone.utc)
    ahead = TimingSnapshot(rows=ROWS, sampled_at=now + timedelta(seconds=3), lap=1)

    assert ws_mod._feed_age(ahead, now) == 0
    assert ws_mod._feed_age(None, now) is None
