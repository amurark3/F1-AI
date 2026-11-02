"""A small thread-safe cache whose entries expire.

For answers that are right for a while and then need reading again, such as a
race result that a stewards' decision can still change. Each entry carries its
own lifetime, so a caller can keep a real answer longer than an empty one.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
import threading
import time


class TtlCache[K: Hashable, V]:
    """Values by key, each forgotten once its lifetime has passed."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[K, tuple[float, V]] = {}
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        """The value kept for ``key``, or ``None`` when there is none or it has expired."""
        with self._lock:
            hit = self._entries.get(key)
        if hit is None or self._clock() >= hit[0]:
            return None
        return hit[1]

    def put(self, key: K, value: V, lifetime: float) -> None:
        """Keep ``value`` for ``lifetime`` seconds."""
        with self._lock:
            self._entries[key] = (self._clock() + lifetime, value)
