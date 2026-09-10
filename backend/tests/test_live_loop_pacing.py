"""Tests for live-loop pacing.

A socket stays open across a whole race weekend, so the idle path must be
cheap without letting the connection look dead.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.api.routes import _needs_resolution
from app.config import SESSION_LOOKUP_INTERVAL, WS_IDLE_POLL_INTERVAL, WS_STALE_TIMEOUT
from app.services.live_timing_client import ActiveSession

pytestmark = pytest.mark.unit


def _session(end: datetime) -> ActiveSession:
    return ActiveSession(
        session_key="11353",
        session_name="Race",
        session_type="Race",
        meeting_name="Dutch Grand Prix",
        date_start=end - timedelta(hours=2),
        date_end=end,
    )


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


def test_idle_lookup_is_rate_limited():
    """Between sessions the calendar must not be re-read every poll cycle."""
    assert _needs_resolution(None, NOW, resolved_at=time.time()) is False


def test_idle_lookup_runs_once_the_interval_elapses():
    stale = time.time() - SESSION_LOOKUP_INTERVAL - 1
    assert _needs_resolution(None, NOW, resolved_at=stale) is True


def test_first_pass_always_resolves():
    assert _needs_resolution(None, NOW, resolved_at=0.0) is True


def test_an_open_session_is_not_re_resolved():
    active = _session(NOW + timedelta(hours=1))
    assert _needs_resolution(active, NOW, resolved_at=time.time()) is False


def test_a_finished_session_is_re_resolved_immediately():
    """Qualifying ending must hand over to the next session without waiting."""
    active = _session(NOW - timedelta(hours=1))
    assert _needs_resolution(active, NOW, resolved_at=time.time()) is True


def test_idle_interval_cannot_outlast_the_stale_timeout():
    """The loop's own sends keep a connection alive; sleeping past the
    timeout would disconnect every idle viewer."""
    assert WS_IDLE_POLL_INTERVAL < WS_STALE_TIMEOUT
