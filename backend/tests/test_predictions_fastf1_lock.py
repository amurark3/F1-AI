"""Tests for the shared FastF1 load lock (app.data.predictions.fastf1_lock).

The risk this covers: FastF1 writes into one shared cache directory, so two
threads loading sessions at once can interleave writes and corrupt it. Every
loader in the package must serialise on *this one* lock object — a per-module
lock would look identical and protect nothing.
"""

import threading

import pytest

from app.data.predictions import form, history, sessions
from app.data.predictions.fastf1_lock import _fastf1_lock


@pytest.mark.unit
def test_lock_is_a_mutex_and_starts_unheld():
    assert isinstance(_fastf1_lock, type(threading.Lock()))
    assert _fastf1_lock.acquire(blocking=False) is True
    _fastf1_lock.release()


@pytest.mark.unit
@pytest.mark.parametrize("module", [form, history, sessions])
def test_every_fastf1_caller_serialises_on_the_same_lock_object(module):
    # Identity, not equality: two distinct locks would each pass an isinstance
    # check while allowing concurrent FastF1 loads.
    assert module._fastf1_lock is _fastf1_lock


@pytest.mark.unit
def test_lock_actually_excludes_a_second_holder():
    with _fastf1_lock:
        assert _fastf1_lock.acquire(blocking=False) is False
    assert _fastf1_lock.acquire(blocking=False) is True
    _fastf1_lock.release()
