"""WebSocket connection tracking for the live-timing feed."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from app.config import WS_HEARTBEAT_INTERVAL, WS_STALE_TIMEOUT

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    """Manages WebSocket connections with heartbeat pings and stale cleanup.

    Tracks active connections per room and last activity time per connection.
    Heartbeat pings are application-level JSON (not WebSocket protocol pings)
    since the client may not handle protocol pings.
    """

    def __init__(self) -> None:
        self.rooms: dict[str, list[WebSocket]] = {}
        self.last_activity: dict[int, float] = {}  # id(ws) -> timestamp

    async def connect(self, room: str, ws: WebSocket) -> None:
        """Accept a WebSocket and register it in the room."""
        await ws.accept()
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(ws)
        self.last_activity[id(ws)] = time.time()
        logger.info("ws.connected", room=room, connection_id=id(ws))

    def disconnect(self, room: str, ws: WebSocket) -> None:
        """Remove a WebSocket from tracking."""
        if room in self.rooms:
            self.rooms[room] = [c for c in self.rooms[room] if c != ws]
            if not self.rooms[room]:
                del self.rooms[room]
        self.last_activity.pop(id(ws), None)
        logger.info("ws.disconnected", room=room, connection_id=id(ws))

    def touch(self, ws: WebSocket) -> None:
        """Update last activity timestamp for a connection."""
        self.last_activity[id(ws)] = time.time()

    def is_stale(self, ws: WebSocket) -> bool:
        """Check if a connection has been inactive beyond the stale timeout."""
        last = self.last_activity.get(id(ws), 0)
        return (time.time() - last) > WS_STALE_TIMEOUT

    async def heartbeat(self, ws: WebSocket) -> None:
        """Send periodic JSON pings to keep the connection alive.

        Runs until the WebSocket is closed or a send failure occurs.
        """
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                await ws.send_json({"type": "ping"})
                logger.debug("ws.heartbeat_sent", connection_id=id(ws))
        except Exception as exc:
            # Connection closed or send failed -- caller handles cleanup.
            logger.debug("ws.heartbeat_stopped", connection_id=id(ws), error=str(exc))
