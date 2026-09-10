"""Tests for the OpenF1 live-timing client.

Uses ``asyncio.run`` rather than an async plugin: requirements-dev.txt pins
pytest alone, so async-marked tests would pass locally and skip in CI.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import live_timing_client as client

pytestmark = pytest.mark.unit


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


MEETINGS = [
    {"meeting_key": 1290, "meeting_name": "Belgian Grand Prix", "location": "Spa-Francorchamps",
     "date_start": "2026-07-17T10:30:00+00:00"},
    {"meeting_key": 1292, "meeting_name": "Dutch Grand Prix", "location": "Zandvoort",
     "date_start": "2026-08-21T10:30:00+00:00"},
]

SESSIONS = [
    {"session_key": 11348, "session_type": "Race", "session_name": "Sprint",
     "date_start": "2026-08-22T10:00:00+00:00", "date_end": "2026-08-22T10:44:00+00:00"},
    {"session_key": 11353, "session_type": "Race", "session_name": "Race",
     "date_start": "2026-08-23T13:00:00+00:00", "date_end": "2026-08-23T15:00:00+00:00"},
]


@pytest.fixture(autouse=True)
def _clear_driver_cache():
    client._driver_cache.clear()
    yield
    client._driver_cache.clear()


def _stub_openf1(monkeypatch, *, meetings=MEETINGS, sessions=SESSIONS, positions=None, intervals=None, drivers=None):
    """Replace OpenF1 HTTP access with canned payloads, recording each call."""
    calls: list[str] = []
    payloads = {
        "meetings": meetings,
        "sessions": sessions,
        "position": positions,
        "intervals": intervals,
        "drivers": drivers,
    }

    async def fake_get_json(_client, path, _params):
        calls.append(path)
        return payloads.get(path)

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    return calls


def _stub_event(monkeypatch, identity=("Zandvoort", None, "Dutch Grand Prix")):
    location, date, name = identity
    resolved = (location, date or _utc(2026, 8, 23), name)
    monkeypatch.setattr(client, "_event_identity", lambda *_: resolved if location else None)


# --------------------------------------------------------------------------
# resolve_active_session
# --------------------------------------------------------------------------


def test_resolve_active_session_returns_the_grand_prix_during_the_race(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30)))

    assert active.session_key == "11353"
    assert active.session_name == "Race"
    assert active.meeting_name == "Dutch Grand Prix"


def test_resolve_active_session_returns_the_sprint_during_the_sprint(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 22, 10, 20)))

    assert active.session_key == "11348"
    assert active.session_name == "Sprint"


def test_resolve_active_session_never_returns_another_meeting(monkeypatch):
    """Regression: round 12 must resolve to Zandvoort, not Spa."""
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30)))

    assert active.meeting_name != "Belgian Grand Prix"


def test_resolve_active_session_is_none_between_sessions(monkeypatch):
    """Saturday night: the weekend is under way but nothing is on track."""
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    assert asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 22, 23, 28))) is None


def test_resolve_active_session_is_none_when_the_meeting_is_unmatched(monkeypatch):
    _stub_event(monkeypatch, identity=("Nowhere", _utc(2026, 1, 1), "Phantom Grand Prix"))
    _stub_openf1(monkeypatch)

    assert asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30))) is None


def test_resolve_active_session_is_none_for_an_unknown_round(monkeypatch):
    _stub_event(monkeypatch, identity=(None, None, None))
    _stub_openf1(monkeypatch)

    assert asyncio.run(client.resolve_active_session(2026, 99, now=_utc(2026, 8, 23, 13, 30))) is None


def test_resolve_active_session_is_none_when_openf1_returns_nothing(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch, meetings=None)

    assert asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30))) is None


def test_resolve_active_session_is_none_when_the_session_list_is_empty(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch, sessions=[])

    assert asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30))) is None


def test_active_session_exposes_its_window_for_state_derivation(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_active_session(2026, 12, now=_utc(2026, 8, 23, 13, 30)))

    assert active.raw["date_start"].startswith("2026-08-23T13:00")
    assert active.raw["date_end"].startswith("2026-08-23T15:00")


# --------------------------------------------------------------------------
# poll_positions
# --------------------------------------------------------------------------

DRIVERS = [
    {"driver_number": 12, "name_acronym": "ANT", "team_name": "Mercedes"},
    {"driver_number": 16, "name_acronym": "LEC", "team_name": "Ferrari"},
]

# The rows OpenF1 still serves for the Belgian GP, months after it finished.
BELGIAN_FINAL = [
    {"driver_number": 12, "position": 1, "date": "2026-07-19T14:38:00+00:00"},
    {"driver_number": 16, "position": 2, "date": "2026-07-19T14:38:00+00:00"},
]


def test_poll_positions_rejects_a_finished_session_replayed_as_live(monkeypatch):
    """The reported bug: July's classification must not render in August."""
    _stub_openf1(monkeypatch, positions=BELGIAN_FINAL, intervals=[], drivers=DRIVERS)

    assert asyncio.run(client.poll_positions("11334", now=_utc(2026, 8, 22, 23, 28))) is None


def test_poll_positions_returns_rows_for_a_live_feed(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    sampled = (now - timedelta(seconds=5)).isoformat()
    _stub_openf1(
        monkeypatch,
        positions=[
            {"driver_number": 16, "position": 2, "date": sampled},
            {"driver_number": 12, "position": 1, "date": sampled},
        ],
        intervals=[{"driver_number": 16, "gap_to_leader": 1.952}],
        drivers=DRIVERS,
    )

    rows = asyncio.run(client.poll_positions("11353", now=now))

    assert [r["driver"] for r in rows] == ["ANT", "LEC"]
    assert rows[0]["driver_number"] == 12
    assert rows[1]["gap"] == "+1.952"


def test_poll_positions_is_none_when_the_feed_is_empty(monkeypatch):
    _stub_openf1(monkeypatch, positions=[], drivers=DRIVERS)

    assert asyncio.run(client.poll_positions("11353", now=_utc(2026, 8, 23, 13, 30))) is None


def test_poll_positions_is_none_when_openf1_fails(monkeypatch):
    _stub_openf1(monkeypatch, positions=None, drivers=DRIVERS)

    assert asyncio.run(client.poll_positions("11353", now=_utc(2026, 8, 23, 13, 30))) is None


def test_poll_positions_still_renders_when_driver_metadata_is_missing(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        drivers=None,
    )

    rows = asyncio.run(client.poll_positions("11353", now=now))

    assert rows[0]["driver"] == "12"


def test_poll_positions_fetches_driver_metadata_once_per_session(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    calls = _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        drivers=DRIVERS,
    )

    asyncio.run(client.poll_positions("11353", now=now))
    asyncio.run(client.poll_positions("11353", now=now))

    assert calls.count("drivers") == 1


# --------------------------------------------------------------------------
# fetch_current_lap
# --------------------------------------------------------------------------


def test_fetch_current_lap_takes_the_highest_lap_number(monkeypatch):
    async def fake_get_json(_client, _path, _params):
        return [{"lap_number": 12}, {"lap_number": 34}, {"lap_number": 33}]

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    assert asyncio.run(client.fetch_current_lap("11353")) == 34


@pytest.mark.parametrize("rows", [None, [], [{"driver_number": 1}]])
def test_fetch_current_lap_is_none_without_lap_data(monkeypatch, rows):
    async def fake_get_json(_client, _path, _params):
        return rows

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    assert asyncio.run(client.fetch_current_lap("11353")) is None
