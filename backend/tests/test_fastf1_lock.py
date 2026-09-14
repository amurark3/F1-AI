"""Tests for the shared FastF1 lock (app.utils.fastf1_lock).

The failure this guards against: FastF1 reads through a requests-cache SQLite
file that is not safe against concurrent writers. With a private lock per
module, a request-path session load could run alongside the boot prefetch loop
and reach ``OperationalError: database is locked`` — observed taking the worker
down with it. The lock therefore has to belong to the resource, and every
module that touches FastF1 has to be holding the same one.
"""

import threading

import pytest

from app.api import routes
from app.data import predictions, race_stints, session_entries, strategy
from app.utils.fastf1_lock import FASTF1_LOCK

pytestmark = pytest.mark.unit

FASTF1_MODULES = [routes, predictions, race_stints, session_entries, strategy]


@pytest.mark.parametrize("module", FASTF1_MODULES, ids=lambda m: m.__name__)
def test_every_fastf1_module_shares_one_lock(module):
    """A second lock object would serialise nothing between modules."""
    assert module._fastf1_lock is FASTF1_LOCK


def test_the_lock_is_reentrant():
    """Callers hold it across get_session + load, and the wrappers retake it.

    A plain Lock would deadlock on the second acquisition from the same thread,
    which would hang the worker rather than crash it — strictly worse.
    """
    with FASTF1_LOCK:
        acquired = FASTF1_LOCK.acquire(blocking=False)
        if acquired:
            FASTF1_LOCK.release()

    assert acquired is True


def test_the_lock_actually_excludes_another_thread():
    """Reentrancy must not weaken the guarantee for a *different* thread."""
    blocked = threading.Event()
    got_it = []

    def contender():
        got_it.append(FASTF1_LOCK.acquire(blocking=False))
        blocked.set()

    with FASTF1_LOCK:
        thread = threading.Thread(target=contender)
        thread.start()
        blocked.wait(timeout=5)
        thread.join(timeout=5)

    assert got_it == [False]
