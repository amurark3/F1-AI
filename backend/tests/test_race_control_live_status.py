"""Tests for session-level live status on the Race Control command centre.

The LIVE pill previously tracked ``status == "in_progress"``, which spans the
whole race weekend — so it stayed lit for three days regardless of whether
anything was on track.
"""

from datetime import datetime, timezone

import pytest

from app.services.race_control import build_live_status, focus_for_event

pytestmark = pytest.mark.unit

DUTCH_WEEKEND = {
    "status": "in_progress",
    "sessions": {
        "Practice 1": "2026-08-21T10:30:00+00:00",
        "Sprint": "2026-08-22T10:00:00+00:00",
        "Qualifying": "2026-08-22T14:00:00+00:00",
        "Race": "2026-08-23T13:00:00+00:00",
    },
}


@pytest.fixture
def at(monkeypatch):
    """Freeze the clock the service reads."""
    def _at(moment: datetime):
        import app.services.race_control as rc

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment

        monkeypatch.setattr(rc, "datetime", _Clock)
    return _at


def test_live_status_is_connected_during_a_session(at):
    at(datetime(2026, 8, 23, 13, 30, tzinfo=timezone.utc))

    status = build_live_status(DUTCH_WEEKEND)

    assert status["connected"] is True
    assert status["session"] == "Race"
    assert status["label"] == "Race in progress"


def test_live_status_names_the_sprint_not_the_grand_prix(at):
    at(datetime(2026, 8, 22, 10, 20, tzinfo=timezone.utc))

    assert build_live_status(DUTCH_WEEKEND)["session"] == "Sprint"


def test_live_status_is_standby_between_sessions(at):
    """Saturday night. The weekend is in progress; nothing is running."""
    at(datetime(2026, 8, 22, 23, 28, tzinfo=timezone.utc))

    status = build_live_status(DUTCH_WEEKEND)

    assert status["connected"] is False
    assert status["label"] == "Standby"
    assert status["session"] is None


def test_live_status_handles_a_missing_race(at):
    at(datetime(2026, 8, 22, 23, 28, tzinfo=timezone.utc))

    assert build_live_status(None)["connected"] is False


def test_focus_is_live_control_only_while_a_session_runs(at):
    at(datetime(2026, 8, 23, 13, 30, tzinfo=timezone.utc))
    assert focus_for_event({**DUTCH_WEEKEND, "days_until": None}) == "Live session control"


def test_focus_falls_back_between_sessions(at):
    at(datetime(2026, 8, 22, 23, 28, tzinfo=timezone.utc))
    assert focus_for_event({**DUTCH_WEEKEND, "days_until": 1}) != "Live session control"
