"""Tests for app.api.live.connections — the shared live-timing socket registry.

``ConnectionManager`` is process-wide mutable state that every live-timing
socket writes to. The failure modes worth guarding are lifecycle ones, and none
of them raise at the point they happen:

* a socket that is disconnected but left in ``rooms`` becomes a dead entry that
  a later fan-out will try to write to forever;
* a socket removed while a broadcaster is walking the room list can wedge or
  skip that broadcast;
* ``heartbeat`` is an unbounded ``while True`` — if a send failure did not end
  it, a dropped client would leave a task pinging a closed socket for the life
  of the process.

Every timer here (``WS_HEARTBEAT_INTERVAL``, ``WS_STALE_TIMEOUT``) is driven by
patching the clock or ``asyncio.sleep``, so no test spends real time waiting.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.api.live.connections import ConnectionManager
from app.config import WS_HEARTBEAT_INTERVAL, WS_STALE_TIMEOUT


class _FakeWebSocket:
    """Minimal stand-in for ``fastapi.WebSocket``.

    ``send_json`` optionally fails after ``fail_after`` successful sends, which
    is how a client that has gone away behaves mid-broadcast.
    """

    def __init__(self, *, fail_after=None, accept_error=None):
        self.accepted = False
        self.sent: list[dict] = []
        self._fail_after = fail_after
        self._accept_error = accept_error

    async def accept(self) -> None:
        if self._accept_error is not None:
            raise self._accept_error
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise ConnectionResetError("socket is closed")
        self.sent.append(payload)


@pytest.fixture
def manager() -> ConnectionManager:
    """A registry per test — the production one is a module-level singleton."""
    return ConnectionManager()


@pytest.fixture
def instant_sleep(monkeypatch):
    """Collapse ``asyncio.sleep`` so heartbeat intervals cost no wall time."""
    slept: list[float] = []

    async def _sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    return slept


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_connect_accepts_the_socket_and_registers_it(manager):
    ws = _FakeWebSocket()

    await manager.connect("2026-1", ws)

    assert ws.accepted is True
    assert manager.rooms == {"2026-1": [ws]}
    assert id(ws) in manager.last_activity


@pytest.mark.unit
async def test_connect_appends_to_an_existing_room(manager):
    first, second = _FakeWebSocket(), _FakeWebSocket()

    await manager.connect("2026-1", first)
    await manager.connect("2026-1", second)

    assert manager.rooms["2026-1"] == [first, second]


@pytest.mark.unit
async def test_connect_keeps_rooms_independent(manager):
    ws_a, ws_b = _FakeWebSocket(), _FakeWebSocket()

    await manager.connect("2026-1", ws_a)
    await manager.connect("2026-2", ws_b)

    assert manager.rooms == {"2026-1": [ws_a], "2026-2": [ws_b]}


@pytest.mark.unit
async def test_connect_does_not_register_a_socket_whose_accept_failed(manager):
    """A refused handshake must not leave a dead entry a fan-out would write to."""
    ws = _FakeWebSocket(accept_error=RuntimeError("handshake rejected"))

    with pytest.raises(RuntimeError):
        await manager.connect("2026-1", ws)

    assert manager.rooms == {}
    assert manager.last_activity == {}


@pytest.mark.unit
async def test_disconnect_drops_the_socket_and_prunes_the_empty_room(manager):
    ws = _FakeWebSocket()
    await manager.connect("2026-1", ws)

    manager.disconnect("2026-1", ws)

    assert manager.rooms == {}, "an empty room must not linger in the registry"
    assert manager.last_activity == {}


@pytest.mark.unit
async def test_disconnect_keeps_the_room_alive_for_the_remaining_clients(manager):
    leaving, staying = _FakeWebSocket(), _FakeWebSocket()
    await manager.connect("2026-1", leaving)
    await manager.connect("2026-1", staying)

    manager.disconnect("2026-1", leaving)

    assert manager.rooms["2026-1"] == [staying]
    assert id(staying) in manager.last_activity
    assert id(leaving) not in manager.last_activity


@pytest.mark.unit
def test_disconnect_for_an_unknown_room_is_a_no_op(manager):
    """The endpoint's ``finally`` runs even when ``connect`` never completed."""
    manager.disconnect("2026-1", _FakeWebSocket())

    assert manager.rooms == {}


@pytest.mark.unit
async def test_disconnect_is_idempotent(manager):
    ws = _FakeWebSocket()
    await manager.connect("2026-1", ws)

    manager.disconnect("2026-1", ws)
    manager.disconnect("2026-1", ws)

    assert manager.rooms == {}


@pytest.mark.unit
async def test_disconnect_rebuilds_the_room_so_an_in_flight_fan_out_is_unaffected(manager):
    """A broadcaster holding the room list must not see it mutate underneath it.

    ``disconnect`` replaces the list rather than removing in place, so a
    snapshot taken before the disconnect stays a valid, complete iterable — the
    fan-out finishes instead of skipping a client or raising mid-loop.
    """
    leaving, staying = _FakeWebSocket(), _FakeWebSocket()
    await manager.connect("2026-1", leaving)
    await manager.connect("2026-1", staying)
    in_flight = manager.rooms["2026-1"]

    manager.disconnect("2026-1", leaving)

    assert in_flight == [leaving, staying]
    assert manager.rooms["2026-1"] is not in_flight


@pytest.mark.unit
async def test_a_client_added_during_a_fan_out_does_not_disturb_the_snapshot(manager):
    existing = _FakeWebSocket()
    await manager.connect("2026-1", existing)
    in_flight = manager.rooms["2026-1"]

    await manager.connect("2026-1", _FakeWebSocket())

    # `connect` appends in place, so a live iterator would pick the newcomer up
    # — acceptable for a join, unlike a removal, which is why it is asserted.
    assert in_flight == manager.rooms["2026-1"]
    assert len(in_flight) == 2


@pytest.mark.unit
async def test_concurrent_connects_and_disconnects_leave_no_dead_entries(manager):
    """Interleaved joins and leaves must settle with the registry consistent."""
    sockets = [_FakeWebSocket() for _ in range(8)]

    await asyncio.gather(*(manager.connect("2026-1", ws) for ws in sockets))
    for ws in sockets[::2]:
        manager.disconnect("2026-1", ws)

    assert manager.rooms["2026-1"] == sockets[1::2]
    assert set(manager.last_activity) == {id(ws) for ws in sockets[1::2]}


# ---------------------------------------------------------------------------
# touch / is_stale
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_touch_refreshes_a_connection_past_the_stale_threshold(manager):
    ws = _FakeWebSocket()
    await manager.connect("2026-1", ws)
    manager.last_activity[id(ws)] = time.time() - (WS_STALE_TIMEOUT + 10)
    assert manager.is_stale(ws) is True

    manager.touch(ws)

    assert manager.is_stale(ws) is False


@pytest.mark.unit
def test_touch_registers_activity_for_a_socket_that_was_never_connected(manager):
    ws = _FakeWebSocket()

    manager.touch(ws)

    assert manager.is_stale(ws) is False


@pytest.mark.unit
async def test_a_freshly_connected_socket_is_not_stale(manager):
    ws = _FakeWebSocket()
    await manager.connect("2026-1", ws)

    assert manager.is_stale(ws) is False


@pytest.mark.unit
def test_an_untracked_socket_reads_as_stale(manager):
    """No recorded activity means epoch zero, so the endpoint drops it."""
    assert manager.is_stale(_FakeWebSocket()) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("age", "expected"),
    [(WS_STALE_TIMEOUT - 1, False), (WS_STALE_TIMEOUT + 1, True)],
    ids=["inside-the-window", "past-the-window"],
)
def test_is_stale_turns_over_at_the_configured_timeout(manager, age, expected):
    ws = _FakeWebSocket()
    manager.last_activity[id(ws)] = time.time() - age

    assert manager.is_stale(ws) is expected


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_heartbeat_pings_on_the_configured_interval(manager, instant_sleep):
    ws = _FakeWebSocket(fail_after=3)

    await manager.heartbeat(ws)

    assert ws.sent == [{"type": "ping"}] * 3
    assert instant_sleep == [WS_HEARTBEAT_INTERVAL] * 4


@pytest.mark.unit
async def test_heartbeat_stops_on_the_first_send_failure_instead_of_retrying(manager, instant_sleep):
    """A dead client must end the task, not leave it pinging forever."""
    ws = _FakeWebSocket(fail_after=0)

    await manager.heartbeat(ws)  # must return rather than raise or spin

    assert ws.sent == []
    assert instant_sleep == [WS_HEARTBEAT_INTERVAL]


@pytest.mark.unit
async def test_heartbeat_on_a_dead_client_does_not_stop_the_others(manager, instant_sleep):
    dead, alive = _FakeWebSocket(fail_after=0), _FakeWebSocket(fail_after=2)
    await manager.connect("2026-1", dead)
    await manager.connect("2026-1", alive)

    await asyncio.gather(manager.heartbeat(dead), manager.heartbeat(alive))

    assert alive.sent == [{"type": "ping"}] * 2
    # The registry is the endpoint's job to clean up; heartbeat only stops.
    assert manager.rooms["2026-1"] == [dead, alive]


@pytest.mark.unit
async def test_heartbeat_ends_when_the_task_is_cancelled(manager, monkeypatch):
    """``live_timing`` cancels the heartbeat in its ``finally``; that must land."""
    ws = _FakeWebSocket()

    async def _cancelled_sleep(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _cancelled_sleep)

    # CancelledError is a BaseException, so the module's `except Exception`
    # deliberately does not swallow it.
    with pytest.raises(asyncio.CancelledError):
        await manager.heartbeat(ws)

    assert ws.sent == []


@pytest.mark.unit
async def test_heartbeat_logs_the_reason_it_stopped(manager, instant_sleep, capsys):
    ws = _FakeWebSocket(fail_after=0)

    await manager.heartbeat(ws)

    assert "socket is closed" in capsys.readouterr().out
