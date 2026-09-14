"""One process-wide lock for every FastF1 session load.

FastF1 reads through ``requests-cache`` backed by a single SQLite file. That
backend is not safe against concurrent writers: two threads loading sessions at
once contend on it, and the process observed ``OperationalError: database is
locked`` followed by a segfault while a request-path load ran alongside the
boot prefetch loop.

Each module that touched FastF1 used to declare its *own* ``_fastf1_lock``.
That serialises calls within a module and does nothing at all between modules,
which is the case that actually breaks — the prefetch loop, a prediction, a
strategy read and a stint read are four different modules sharing one SQLite
cache. The lock has to be a property of the resource, not of the caller.

It is applied in :mod:`app.utils.fastf1_cache`, which already wraps
``get_session``, ``get_event_schedule`` and ``session.load`` — so every caller
is covered without having to remember to lock, including the ones that never
did.

Reentrant on purpose. Several callers already hold it across a whole
``get_session`` + ``load`` pair to make that sequence atomic, and a plain
``Lock`` would deadlock the moment the wrapped functions tried to take it
again on the same thread.

The cost is that FastF1 loads are serialised process-wide. They are slow and
heavily cached anyway, and a queued load is strictly better than a corrupted
cache file or a dead worker.
"""

from __future__ import annotations

import threading

#: Guards every FastF1 read in the process. Import this rather than declaring a
#: new lock — a second lock reintroduces exactly the bug above.
FASTF1_LOCK = threading.RLock()
