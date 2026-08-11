"""The live-timing WebSocket endpoint.

Polls OpenF1 and fans position/timing updates out to connected clients, adding
commentary when a notable event is detected.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.api.live.commentary import (
    COMMENTARY_COOLDOWN_SECONDS,
    _commentary_state,
    _generate_commentary,
)
from app.api.live.connections import ConnectionManager
from app.api.live.events import Snapshot, _detect_event
from app.api.live.openf1 import (
    _fetch_current_lap,
    _fetch_session_status,
    _fetch_stint_counts,
    _find_openf1_session,
    _poll_openf1_positions,
)
from app.config import WS_POLL_INTERVAL, WS_RECEIVE_TIMEOUT

logger = structlog.get_logger()

router = APIRouter()

manager = ConnectionManager()


@dataclass(frozen=True)
class LiveSession:
    """The OpenF1 session a socket is following, resolved once per connection."""

    key: str | None
    total_laps: int
    room: str
    race_name: str


async def _resolve_session(year: int, round_num: int, room: str) -> LiveSession:
    """Look the round up on OpenF1; a miss yields a session with no key."""
    result = await _find_openf1_session(year, round_num)
    key, total_laps = result or (None, 0)
    return LiveSession(
        key=key,
        total_laps=total_laps,
        room=room,
        race_name=f"Round {round_num} {year}",  # fallback; sufficient for prompts
    )


def _room_state(room: str) -> dict:
    """The per-room commentary state, created empty on first poll."""
    return _commentary_state.setdefault(
        room,
        {
            "last_time": 0.0,
            "prev_positions": [],
            "prev_session_status": "",
            "prev_stints": {},
        },
    )


def _stored_snapshot(state: dict) -> Snapshot:
    """Rebuild the previous snapshot from the room's stored state."""
    return Snapshot(
        positions=state["prev_positions"],
        session_status=state["prev_session_status"],
        stints=state["prev_stints"],
    )


def _store_snapshot(state: dict, snapshot: Snapshot) -> None:
    """Record ``snapshot`` as the baseline the next poll compares against."""
    state["prev_positions"] = snapshot.positions
    state["prev_session_status"] = snapshot.session_status
    state["prev_stints"] = snapshot.stints


async def _send_positions(websocket: WebSocket, positions: list[dict]) -> None:
    """Broadcast the running order."""
    await websocket.send_json({"type": "positions", "data": positions})
    manager.touch(websocket)


async def _send_session_status(websocket: WebSocket, session: LiveSession, last_known_lap: int) -> int:
    """Broadcast lap and status, returning the lap number to carry forward.

    The lap counter is sticky: OpenF1 briefly reports 0 between laps, and
    resetting the client's display to nothing on every gap looks like a fault.
    """
    current_lap = await _fetch_current_lap(session.key)
    lap = current_lap if current_lap > 0 else last_known_lap
    await websocket.send_json(
        {
            "type": "session_status",
            "data": {
                "status": "started",
                "lap": lap if lap > 0 else None,
                "total_laps": session.total_laps if session.total_laps > 0 else None,
            },
        }
    )
    manager.touch(websocket)
    return lap


async def _send_commentary(websocket: WebSocket, session: LiveSession, event: dict, state: dict) -> None:
    """Generate commentary for ``event`` and broadcast it if the LLM produced any."""
    text = await _generate_commentary(event, session.race_name)
    if not text:
        return
    await websocket.send_json(
        {
            "type": "commentary",
            "data": {
                "id": str(time.time()),
                "text": text,
                "event_type": event["type"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
    )
    state["last_time"] = time.time()
    logger.info("commentary.broadcast", room=session.room, event_type=event["type"])


async def _handle_commentary(websocket: WebSocket, session: LiveSession, current: Snapshot) -> None:
    """Detect an event against the stored snapshot and commentate on it."""
    state = _room_state(session.room)

    if not state["prev_positions"]:
        # First snapshot — store and skip detection to avoid false positives.
        _store_snapshot(state, current)
        return

    if time.time() - state["last_time"] >= COMMENTARY_COOLDOWN_SECONDS:
        event = _detect_event(_stored_snapshot(state), current)
        if event:
            await _send_commentary(websocket, session, event, state)

    _store_snapshot(state, current)


async def _poll_once(websocket: WebSocket, session: LiveSession, last_known_lap: int) -> int:
    """Run one poll cycle, returning the lap number to carry into the next."""
    positions = await _poll_openf1_positions(session.key)
    if not positions:
        return last_known_lap

    await _send_positions(websocket, positions)
    lap = await _send_session_status(websocket, session, last_known_lap)

    # Auxiliary feeds for the event types the positions endpoint cannot report.
    status, stints = await asyncio.gather(
        _fetch_session_status(session.key),
        _fetch_stint_counts(session.key),
    )
    await _handle_commentary(
        websocket,
        session,
        Snapshot(positions=positions, session_status=status, stints=stints),
    )
    return lap


async def _await_client_message(websocket: WebSocket) -> None:
    """Consume a client keepalive if one arrives; silence is normal.

    A real disconnect raises out of ``receive_text`` and propagates to the
    caller's handler — only the timeout is swallowed.
    """
    try:
        await asyncio.wait_for(websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT)
        manager.touch(websocket)
    except asyncio.TimeoutError:
        pass


@router.websocket("/live/{year}/{round_num}")
async def live_timing(websocket: WebSocket, year: int, round_num: int) -> None:
    """WebSocket endpoint for live race timing data.

    Uses ConnectionManager for heartbeat pings and stale connection cleanup.
    """
    room = f"{year}-{round_num}"
    await manager.connect(room, websocket)

    # Start heartbeat as a background task
    heartbeat_task = asyncio.create_task(manager.heartbeat(websocket))

    try:
        session = await _resolve_session(year, round_num, room)
        last_known_lap = 0

        while True:
            if manager.is_stale(websocket):
                logger.warning("ws.stale_connection", room=room, connection_id=id(websocket))
                break

            if session.key:
                last_known_lap = await _poll_once(websocket, session, last_known_lap)

            await asyncio.sleep(WS_POLL_INTERVAL)
            await _await_client_message(websocket)

    except WebSocketDisconnect:
        logger.info("ws.client_disconnected", year=year, round_num=round_num)
    except Exception:
        # A bug in the polling loop used to be indistinguishable from a normal
        # disconnect, because both landed in the same silent handler.
        logger.exception("ws.live_timing_failed", year=year, round_num=round_num)
    finally:
        heartbeat_task.cancel()
        manager.disconnect(room, websocket)
