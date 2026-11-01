"""One run of a slow job per key, however many requests ask for it.

The pattern of ``race_detail_builds`` in :mod:`app.api.race_detail`, made
reusable. A job runs on a worker thread as a task of its own, not as part of
the request that started it. A request waits for it only so long; the job then
carries on, and the next request for the same key joins it instead of starting
a second one beside it. A worker thread cannot be stopped, so a bare
``wait_for(to_thread(...))`` would leave the first run going and start another
on every retry.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

logger = structlog.get_logger()


class SingleFlight[V]:
    def __init__(self, name: str) -> None:
        self._name = name
        self._runs: dict[Hashable, asyncio.Task[V]] = {}

    def start(self, key: Hashable, work: Callable[[], V]) -> asyncio.Task[V]:
        """The run in flight for ``key``, or a newly started one."""
        run = self._runs.get(key)
        if run is None:
            run = asyncio.create_task(asyncio.to_thread(work))
            self._runs[key] = run
            run.add_done_callback(partial(self._forget, key))
        return run

    def _forget(self, key: Hashable, run: asyncio.Task[V]) -> None:
        """Drop a finished run, logging a failure no request may have stayed to see."""
        self._runs.pop(key, None)
        if not run.cancelled() and (error := run.exception()) is not None:
            logger.warning("single_flight.failed", flight=self._name, key=str(key), error=str(error))

    async def run(self, key: Hashable, work: Callable[[], V], wait_seconds: float) -> V | None:
        """The job's result, or None when it is still running after ``wait_seconds``."""
        run = self.start(key, work)
        try:
            # shield: a request that stops waiting must not cancel the shared run.
            return await asyncio.wait_for(asyncio.shield(run), timeout=wait_seconds)
        except TimeoutError:
            # Done means the job itself timed out (a socket, say); not done
            # means it is merely slow and the next request will join it.
            if run.done():
                raise
            return None
