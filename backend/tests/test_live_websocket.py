"""Tests for app.api.live.websocket — the live-timing endpoint's poll loop.

``live_timing`` is an unbounded ``while True`` holding a socket, a heartbeat
task and an entry in a process-wide registry. The risks are all lifecycle ones:

* **Every exit path must release everything.** A normal disconnect, a stale
  connection, a bug in the poll loop and a bad OpenF1 response all have to end
  with the heartbeat task cancelled and the socket out of the registry —
  otherwise the process accumulates tasks pinging dead sockets.
* **A degraded feed must not end the connection.** OpenF1 returning nothing is
  the common case between sessions; the loop keeps its last known lap and
  carries on rather than dropping the client.
* **Commentary is rate-limited and never speculative.** The first poll of a room
  has no baseline to compare against, and inside the cooldown window no model
  call may happen at all.

Timers are neutralised by patching ``WS_POLL_INTERVAL`` to zero and the receive
timeout to milliseconds, and every fake client disconnects after a bounded
number of reads, so no test here can hang.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime

from fastapi import WebSocketDisconnect
import pytest

from app.api.live import websocket as ws_mod
from app.api.live.commentary import _commentary_state
from app.api.live.connections import ConnectionManager
from app.api.live.events import Snapshot

ROOM = "2026-4"
POSITIONS = [
    {"position": 1, "driver": "VER", "gap": "LEADER"},
    {"position": 2, "driver": "NOR", "gap": "+1.200"},
]
SWAPPED = [
    {"position": 1, "driver": "NOR", "gap": "LEADER"},
    {"position": 2, "driver": "VER", "gap": "+0.800"},
]

_FEED_DEFAULTS = {
    "_find_openf1_session": ("9999", 57),
    "_poll_openf1_positions": POSITIONS,
    "_fetch_current_lap": 12,
    "_fetch_session_status": "",
    "_fetch_stint_counts": {},
}


class _FakeWebSocket:
    """A client that answers a bounded number of reads, then disconnects.

    ``incoming`` may hold exceptions, which are raised instead of returned —
    that is how a mid-session disconnect or a transport error arrives. Once the
    queue empties every further read raises ``WebSocketDisconnect``, which is
    what bounds the endpoint's ``while True``.
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


def _returning(value):
    """An async stand-in that ignores its arguments and answers ``value``."""

    async def _call(*_args):
        return value

    return _call


def _raising(error):
    async def _call(*_args):
        raise error

    return _call


def _patch_feeds(monkeypatch, **fields):
    """Replace the OpenF1 calls ``websocket.py`` imported with fixed answers.

    A value that is an exception instance is raised by the stand-in instead.
    """
    for name, value in {**_FEED_DEFAULTS, **fields}.items():
        stub = _raising(value) if isinstance(value, BaseException) else _returning(value)
        monkeypatch.setattr(ws_mod, name, stub)


@pytest.fixture(autouse=True)
def _clear_commentary_state():
    """Per-room commentary state is a process global keyed by year-round."""
    _commentary_state.clear()
    yield
    _commentary_state.clear()


@pytest.fixture
def manager(monkeypatch):
    """A registry per test — production uses a module-level singleton."""
    fresh = ConnectionManager()
    monkeypatch.setattr(ws_mod, "manager", fresh)
    return fresh


@pytest.fixture
def no_waiting(monkeypatch):
    """Collapse the poll interval so the loop costs no wall time."""
    monkeypatch.setattr(ws_mod, "WS_POLL_INTERVAL", 0)


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


def _session(**fields):
    defaults = {"key": "9999", "total_laps": 57, "room": ROOM, "race_name": "Round 4 2026"}
    return ws_mod.LiveSession(**{**defaults, **fields})


async def _drain(task):
    """Let a cancelled task finish so ``cancelled()`` is meaningful."""
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# _resolve_session
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_known_round_resolves_to_its_openf1_session(monkeypatch):
    _patch_feeds(monkeypatch)

    session = await ws_mod._resolve_session(2026, 4, ROOM)

    assert session == ws_mod.LiveSession(key="9999", total_laps=57, room=ROOM, race_name="Round 4 2026")


@pytest.mark.unit
async def test_an_unknown_round_resolves_to_a_keyless_session(monkeypatch):
    """No key means the loop idles instead of polling a session that is not live."""
    _patch_feeds(monkeypatch, _find_openf1_session=None)

    session = await ws_mod._resolve_session(2030, 99, "2030-99")

    assert session.key is None
    assert session.total_laps == 0


# ---------------------------------------------------------------------------
# Per-room state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_new_room_starts_with_no_commentary_history():
    state = ws_mod._room_state(ROOM)

    assert state == {"last_time": 0.0, "prev_positions": [], "prev_session_status": "", "prev_stints": {}}


@pytest.mark.unit
def test_a_room_keeps_the_same_state_object_across_polls():
    """A fresh dict each poll would reset the cooldown and spam commentary."""
    first = ws_mod._room_state(ROOM)
    first["last_time"] = 123.0

    assert ws_mod._room_state(ROOM) is first
    assert ws_mod._room_state("2026-5") is not first


@pytest.mark.unit
def test_a_stored_snapshot_reads_back_unchanged():
    state = ws_mod._room_state(ROOM)
    snapshot = Snapshot(positions=POSITIONS, session_status="safety car", stints={"1": 2})

    ws_mod._store_snapshot(state, snapshot)

    assert ws_mod._stored_snapshot(state) == snapshot


# ---------------------------------------------------------------------------
# Outbound frames
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_the_running_order_is_broadcast_and_counts_as_activity(manager):
    ws = _FakeWebSocket()
    await manager.connect(ROOM, ws)
    manager.last_activity[id(ws)] = 0.0

    await ws_mod._send_positions(ws, POSITIONS)

    assert ws.sent == [{"type": "positions", "data": POSITIONS}]
    assert manager.is_stale(ws) is False, "a successful send must refresh the connection"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("current_lap", "last_known_lap", "total_laps", "expected_lap", "expected_total"),
    [
        (12, 5, 57, 12, 57),
        (0, 5, 57, 5, 57),
        (0, 0, 57, None, 57),
        (12, 0, 0, 12, None),
    ],
    ids=["fresh-lap", "sticky-across-a-gap", "race-not-started", "distance-unknown"],
)
async def test_the_lap_counter_holds_its_value_through_feed_gaps(
    monkeypatch, manager, current_lap, last_known_lap, total_laps, expected_lap, expected_total
):
    """OpenF1 reports lap 0 between laps; blanking the display would look broken."""
    _patch_feeds(monkeypatch, _fetch_current_lap=current_lap)
    ws = _FakeWebSocket()

    carried = await ws_mod._send_session_status(ws, _session(total_laps=total_laps), last_known_lap)

    assert ws.payloads_of("session_status") == [
        {"status": "started", "lap": expected_lap, "total_laps": expected_total}
    ]
    assert carried == (expected_lap or 0)


@pytest.mark.unit
async def test_commentary_is_broadcast_with_a_utc_timestamp(monkeypatch, manager):
    monkeypatch.setattr(ws_mod, "_generate_commentary", _returning("Norris takes the lead!"))
    monkeypatch.setattr(ws_mod.time, "time", lambda: 1_800_000.5)
    ws = _FakeWebSocket()
    state = ws_mod._room_state(ROOM)

    await ws_mod._send_commentary(ws, _session(), {"type": "position_change"}, state)

    (payload,) = ws.payloads_of("commentary")
    assert payload["text"] == "Norris takes the lead!"
    assert payload["event_type"] == "position_change"
    assert payload["id"] == "1800000.5"
    assert datetime.fromisoformat(payload["timestamp"]).utcoffset().total_seconds() == 0
    assert state["last_time"] == 1_800_000.5, "the cooldown window starts when the line is sent"


@pytest.mark.unit
async def test_empty_commentary_is_not_broadcast(monkeypatch, manager):
    """An unknown event type yields no copy; sending it would be a blank card."""
    monkeypatch.setattr(ws_mod, "_generate_commentary", _returning(""))
    ws = _FakeWebSocket()
    state = ws_mod._room_state(ROOM)

    await ws_mod._send_commentary(ws, _session(), {"type": "tyre_change"}, state)

    assert ws.sent == []
    assert state["last_time"] == 0.0, "a suppressed line must not consume the cooldown"


# ---------------------------------------------------------------------------
# _handle_commentary
# ---------------------------------------------------------------------------


def _record_commentary(monkeypatch, text="Big move!"):
    """Replace the LLM layer with a recorder of the events it was asked about."""
    seen: list[dict] = []

    async def _generate(event, _race_name):
        seen.append(event)
        return text

    monkeypatch.setattr(ws_mod, "_generate_commentary", _generate)
    return seen


@pytest.mark.unit
async def test_the_first_poll_of_a_room_establishes_a_baseline_silently(monkeypatch, manager):
    """With nothing to compare against, every driver looks like an overtake."""
    seen = _record_commentary(monkeypatch)
    ws = _FakeWebSocket()

    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))

    assert seen == []
    assert ws.sent == []
    assert ws_mod._room_state(ROOM)["prev_positions"] == POSITIONS


@pytest.mark.unit
async def test_an_overtake_after_the_cooldown_is_commentated(monkeypatch, manager):
    seen = _record_commentary(monkeypatch, "Norris sweeps around the outside!")
    ws = _FakeWebSocket()
    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))

    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=SWAPPED))

    assert seen == [{"type": "position_change", "driver": "NOR", "from_pos": 2, "to_pos": 1, "positions": SWAPPED}]
    assert ws.payloads_of("commentary")[0]["text"] == "Norris sweeps around the outside!"
    assert ws_mod._room_state(ROOM)["prev_positions"] == SWAPPED


@pytest.mark.unit
async def test_a_second_event_inside_the_cooldown_is_suppressed(monkeypatch, manager):
    """The window is what stops a busy lap turning into a wall of commentary."""
    seen = _record_commentary(monkeypatch)
    ws = _FakeWebSocket()
    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))
    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=SWAPPED))

    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))

    assert len(seen) == 1
    assert len(ws.payloads_of("commentary")) == 1
    # The baseline still advances, so the next window compares against now.
    assert ws_mod._room_state(ROOM)["prev_positions"] == POSITIONS


@pytest.mark.unit
async def test_an_uneventful_poll_produces_no_commentary(monkeypatch, manager):
    seen = _record_commentary(monkeypatch)
    ws = _FakeWebSocket()
    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))

    await ws_mod._handle_commentary(ws, _session(), Snapshot(positions=POSITIONS))

    assert seen == []
    assert ws.sent == []


# ---------------------------------------------------------------------------
# _poll_once
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_one_poll_broadcasts_the_order_then_the_lap(monkeypatch, manager):
    _patch_feeds(monkeypatch)
    _record_commentary(monkeypatch)
    ws = _FakeWebSocket()

    lap = await ws_mod._poll_once(ws, _session(), 0)

    assert [payload["type"] for payload in ws.sent] == ["positions", "session_status"]
    assert lap == 12


@pytest.mark.unit
async def test_a_poll_with_no_positions_sends_nothing_and_keeps_the_lap(monkeypatch, manager):
    """Between sessions OpenF1 returns nothing; that is not a reason to disturb the client."""
    _patch_feeds(monkeypatch, _poll_openf1_positions=None)
    ws = _FakeWebSocket()

    lap = await ws_mod._poll_once(ws, _session(), 31)

    assert ws.sent == []
    assert lap == 31


@pytest.mark.unit
async def test_a_pit_stop_detected_from_the_stint_feed_is_commentated(monkeypatch, manager):
    seen = _record_commentary(monkeypatch, "Verstappen boxes for softs!")
    _patch_feeds(monkeypatch, _fetch_stint_counts={"VER": 1})
    ws = _FakeWebSocket()
    await ws_mod._poll_once(ws, _session(), 0)

    _patch_feeds(monkeypatch, _fetch_stint_counts={"VER": 2})
    await ws_mod._poll_once(ws, _session(), 12)

    assert seen == [{"type": "pit_stop", "driver": "VER", "pit_count": 1, "position": 1}]
    assert ws.payloads_of("commentary")[0]["text"] == "Verstappen boxes for softs!"


# ---------------------------------------------------------------------------
# _await_client_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_client_keepalive_refreshes_the_connection(manager):
    ws = _FakeWebSocket(incoming=["ping"])
    await manager.connect(ROOM, ws)
    manager.last_activity[id(ws)] = 0.0

    await ws_mod._await_client_message(ws)

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

    await ws_mod._await_client_message(ws)

    assert manager.last_activity[id(ws)] == before, "silence is not activity"


@pytest.mark.unit
async def test_a_disconnect_while_reading_propagates_to_the_endpoint(manager):
    """Only the timeout is swallowed; a real disconnect must end the loop."""
    ws = _FakeWebSocket()

    with pytest.raises(WebSocketDisconnect):
        await ws_mod._await_client_message(ws)


# ---------------------------------------------------------------------------
# live_timing — connection lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_session_streams_until_the_client_disconnects(monkeypatch, manager, no_waiting, spied_tasks):
    _patch_feeds(monkeypatch)
    _record_commentary(monkeypatch)
    ws = _FakeWebSocket(incoming=["keepalive", "keepalive"])

    await ws_mod.live_timing(ws, 2026, 4)

    assert ws.accepted is True
    assert len(ws.payloads_of("positions")) == 3, "one broadcast per loop iteration"
    assert manager.rooms == {}, "the socket must be out of the registry on exit"
    assert manager.last_activity == {}
    await _drain(spied_tasks[0])
    assert spied_tasks[0].cancelled(), "the heartbeat task must not outlive the connection"


@pytest.mark.unit
async def test_a_round_that_is_not_live_holds_the_socket_without_polling(monkeypatch, manager, no_waiting, spied_tasks):
    polls = []
    _patch_feeds(monkeypatch, _find_openf1_session=None)
    monkeypatch.setattr(ws_mod, "_poll_openf1_positions", polls.append)
    ws = _FakeWebSocket(incoming=["keepalive"])

    await ws_mod.live_timing(ws, 2030, 99)

    assert polls == [], "a session with no key must not be polled"
    assert ws.sent == []
    assert manager.rooms == {}
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_stale_connection_is_dropped_before_polling(monkeypatch, manager, no_waiting, spied_tasks, capsys):
    _patch_feeds(monkeypatch)
    monkeypatch.setattr(manager, "is_stale", lambda _ws: True)
    ws = _FakeWebSocket(incoming=["keepalive"] * 3)

    await ws_mod.live_timing(ws, 2026, 4)

    assert ws.sent == [], "a connection past the stale timeout gets no further frames"
    assert ws.reads == 0, "the loop must break out rather than complete an iteration"
    assert "ws.stale_connection" in capsys.readouterr().out
    assert manager.rooms == {}
    await _drain(spied_tasks[0])


@pytest.mark.unit
async def test_a_bug_in_the_poll_loop_is_logged_and_still_releases_the_socket(
    monkeypatch, manager, no_waiting, spied_tasks, capsys
):
    """A crash used to be indistinguishable from a normal disconnect."""
    _patch_feeds(monkeypatch, _poll_openf1_positions=TypeError("positions payload changed shape"))
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
    _patch_feeds(monkeypatch)
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

    _patch_feeds(monkeypatch)

    with pytest.raises(RuntimeError, match="handshake rejected"):
        await ws_mod.live_timing(_RejectingClient(), 2026, 4)

    assert manager.rooms == {}
    assert spied_tasks == []
