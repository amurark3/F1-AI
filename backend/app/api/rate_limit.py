"""A per-visitor cap on requests, so one script cannot spend the engines' daily quota.

shortcut: in memory and per process; move to a shared store if the backend
ever runs more than one process.
"""

from __future__ import annotations

from collections import deque
import threading
import time
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from collections.abc import Callable

# Cloudflare (in front of Render) overwrites these, so a client cannot forge
# them. X-Forwarded-For is no use: Render's proxy only appends to it.
_CLIENT_IP_HEADERS = ("true-client-ip", "cf-connecting-ip")


def client_ip(request: Request) -> str:
    """The visitor's address as the edge saw it, or the socket peer without an edge."""
    for header in _CLIENT_IP_HEADERS:
        if value := request.headers.get(header):
            return value.strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """At most ``count`` requests per ``window`` seconds, for each of several windows."""

    def __init__(self, limits: tuple[tuple[int, float], ...], clock: Callable[[], float] = time.monotonic) -> None:
        self._limits = limits
        self._longest = max(window for _, window in limits)
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Count a request for ``key``; False when one of the windows is already full."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._longest:
                hits.popleft()
            if any(sum(1 for hit in hits if now - hit < window) >= count for count, window in self._limits):
                return False
            hits.append(now)
            return True


# A person asks a question every few seconds at most; a day's cap keeps one
# visitor from using up the free engine's 20 requests a day many times over.
chat_limiter = RateLimiter(((6, 60.0), (100, 24 * 3600.0)))


def limit_chat(request: Request) -> None:
    """FastAPI dependency: 429 once a visitor is over the chat limits."""
    if not chat_limiter.allow(client_ip(request)):
        raise HTTPException(
            status_code=429, detail="Too many questions in a short time. Wait a minute, then ask again."
        )
