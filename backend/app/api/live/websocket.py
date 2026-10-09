"""The live-timing WebSocket endpoint.

Streams whichever session is running at a race weekend. Session resolution and
OpenF1 polling live in :mod:`app.services.live_timing_client`; this module owns
only the socket: when to re-resolve, how fast to poll, and what to send.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.api.live.connections import ConnectionManager
from app.config import (
    SESSION_LOOKUP_INTERVAL,
    WS_IDLE_POLL_INTERVAL,
    WS_POLL_INTERVAL,
    WS_RECEIVE_TIMEOUT,
)
from app.services.live_timing import SESSION_END_GRACE, derive_session_state
from app.services.live_timing_client import (
    ActiveSession,
    TimingSnapshot,
    poll_timing,
    resolve_session_window,
)

logger = structlog.get_logger()

router = APIRouter()

manager = ConnectionManager()


@router.websocket("/live/{year}/{round_num}")
async def live_timing(websocket: WebSocket, year: int, round_num: int) -> None:
    """Stream live timing for whichever session is running at a race weekend.

    The socket stays open across the weekend and re-resolves the active session
    as practice gives way to qualifying and the race. It reports ``standby``
    honestly between sessions rather than replaying finished classifications.
    """
    room = f"{year}-{round_num}"
    await manager.connect(room, websocket)
    heartbeat_task = asyncio.create_task(manager.heartbeat(websocket))

    try:
        await _run_live_loop(websocket, room, year, round_num)
    except WebSocketDisconnect:
        logger.info("ws.client_disconnected", year=year, round_num=round_num)
    except Exception:
        # A bug in the polling loop used to be indistinguishable from a normal
        # disconnect, because both landed in the same silent handler.
        logger.exception("ws.live_timing_failed", year=year, round_num=round_num)
    finally:
        heartbeat_task.cancel()
        manager.disconnect(room, websocket)


async def _run_live_loop(websocket: WebSocket, room: str, year: int, round_num: int) -> None:
    """Poll the active session until the client goes away.

    Idles cheaply between sessions: a socket left open across a race weekend
    must not re-resolve the calendar every few seconds.
    """
    active: ActiveSession | None = None
    next_start: datetime | None = None
    last_lap: int | None = None
    resolved_at = 0.0

    while not manager.is_stale(websocket):
        now = datetime.now(timezone.utc)

        if _needs_resolution(active, now, resolved_at, next_start):
            previous_key = active.session_key if active else None
            lookup = await resolve_session_window(year, round_num, now=now)
            active, next_start = lookup.active, lookup.next_start
            resolved_at = time.time()
            if active is None or active.session_key != previous_key:
                last_lap = None
                logger.info(
                    "live.session_resolved",
                    room=room,
                    session=active.session_name if active else None,
                    next_start=str(next_start),
                )

        snapshot = await poll_timing(active, now=now, last_lap=last_lap) if active else None
        if snapshot:
            last_lap = snapshot.lap
        state = derive_session_state(active.raw if active else None, now, snapshot is not None)

        await _broadcast_state(websocket, _session_status(active, snapshot, state, now), snapshot)

        await asyncio.sleep(WS_POLL_INTERVAL if active else WS_IDLE_POLL_INTERVAL)
        await _drain_client(websocket)

    logger.warning("ws.stale_connection", room=room, connection_id=id(websocket))


def _needs_resolution(
    active: ActiveSession | None,
    now: datetime,
    resolved_at: float,
    next_start: datetime | None = None,
) -> bool:
    """Whether the active session must be looked up again.

    While nothing is on track the lookup is rate-limited: it costs a FastF1
    schedule read plus two OpenF1 calls, and the answer changes at most once
    per session. The calendar is the exception to that thrift — once it says a
    session is due, waiting out the interval means reporting an empty track
    into a running session for up to five minutes.
    """
    if active is not None:
        return now > active.date_end + SESSION_END_GRACE
    if next_start is not None and now >= next_start:
        return True
    return (time.time() - resolved_at) >= SESSION_LOOKUP_INTERVAL


def _feed_age(snapshot: TimingSnapshot | None, now: datetime) -> int | None:
    """Seconds since the newest sample, never negative.

    OpenF1 stamps samples with its own clock, so a few seconds of skew against
    ours can put the newest sample marginally in the future. "-3s ago" is not
    a thing the desk should ever print.
    """
    if snapshot is None:
        return None
    return max(0, int((now - snapshot.sampled_at).total_seconds()))


def _session_status(
    active: ActiveSession | None,
    snapshot: TimingSnapshot | None,
    state: str,
    now: datetime,
) -> dict:
    """The status frame for one poll.

    ``feed_age_seconds`` lets the desk say how long the feed has been quiet.
    A quiet feed is normal — the order simply held — so the tower keeps the
    rows on screen and reports the age rather than blanking.
    """
    return {
        "status": state,
        "session_name": active.session_name if active else None,
        "meeting_name": active.meeting_name if active else None,
        "starts_at": active.date_start.isoformat() if active else None,
        "lap": snapshot.lap if snapshot else None,
        "feed_age_seconds": _feed_age(snapshot, now),
    }


async def _broadcast_state(websocket: WebSocket, status: dict, snapshot: TimingSnapshot | None) -> None:
    """Send session status, and positions only when there is a live feed."""
    await websocket.send_json({"type": "session_status", "data": status})
    manager.touch(websocket)

    if snapshot:
        await websocket.send_json({"type": "positions", "data": snapshot.rows})
        manager.touch(websocket)


async def _drain_client(websocket: WebSocket) -> None:
    """Consume any client message so liveness is tracked; silence is fine."""
    try:
        await asyncio.wait_for(websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT)
        manager.touch(websocket)
    except asyncio.TimeoutError:
        pass
