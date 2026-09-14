"""Tests for the OpenF1 live-timing client.

Uses ``asyncio.run`` rather than an async plugin: requirements-dev.txt pins
pytest alone, so async-marked tests would pass locally and skip in CI.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import live_timing_client as client
from app.services.live_timing import GAP_FEED_WINDOW, LAP_FEED_WINDOW

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

RACE_START = _utc(2026, 8, 23, 13, 0)


@pytest.fixture(autouse=True)
def _clear_driver_cache():
    client._driver_cache.clear()
    yield
    client._driver_cache.clear()


def _stub_openf1(monkeypatch, *, meetings=MEETINGS, sessions=SESSIONS,
                 positions=None, intervals=None, laps=None, drivers=None):
    """Replace OpenF1 HTTP access with canned payloads, recording each call."""
    calls: list[tuple[str, dict]] = []
    payloads = {
        "meetings": meetings,
        "sessions": sessions,
        "position": positions,
        "intervals": intervals,
        "laps": laps,
        "drivers": drivers,
    }

    async def fake_get_json(_client, path, params):
        calls.append((path, params))
        return payloads.get(path)

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    return calls


def _stub_event(monkeypatch, identity=("Zandvoort", None, "Dutch Grand Prix")):
    location, date, name = identity
    resolved = (location, date or _utc(2026, 8, 23), name)
    monkeypatch.setattr(client, "_event_identity", lambda *_: resolved if location else None)


def _paths(calls) -> list[str]:
    return [path for path, _ in calls]


def _params(calls, path) -> dict:
    return next(params for called, params in calls if called == path)


def _race(session_key="11353") -> client.ActiveSession:
    return client.ActiveSession(
        session_key=session_key,
        session_name="Race",
        session_type="Race",
        meeting_name="Dutch Grand Prix",
        date_start=RACE_START,
        date_end=_utc(2026, 8, 23, 15, 0),
    )


# --------------------------------------------------------------------------
# resolve_session_window
# --------------------------------------------------------------------------


def test_resolve_returns_the_grand_prix_during_the_race(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active

    assert active.session_key == "11353"
    assert active.session_name == "Race"
    assert active.meeting_name == "Dutch Grand Prix"


def test_resolve_returns_the_sprint_during_the_sprint(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 22, 10, 20))).active

    assert active.session_key == "11348"
    assert active.session_name == "Sprint"


def test_resolve_never_returns_another_meeting(monkeypatch):
    """Regression: round 12 must resolve to Zandvoort, not Spa."""
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active

    assert active.meeting_name != "Belgian Grand Prix"


def test_resolve_is_empty_between_sessions(monkeypatch):
    """Saturday night: the weekend is under way but nothing is on track."""
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    assert asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 22, 23, 28))).active is None


def test_resolve_reports_when_the_next_session_opens(monkeypatch):
    """The socket must know to look again at lights out, not five minutes later."""
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    lookup = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 12, 58)))

    assert lookup.active is None
    assert lookup.next_start == RACE_START


def test_resolve_reports_the_next_session_while_one_is_running(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    lookup = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 22, 10, 20)))

    assert lookup.active.session_name == "Sprint"
    assert lookup.next_start == RACE_START


def test_resolve_is_empty_when_the_meeting_is_unmatched(monkeypatch):
    _stub_event(monkeypatch, identity=("Nowhere", _utc(2026, 1, 1), "Phantom Grand Prix"))
    _stub_openf1(monkeypatch)

    lookup = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30)))

    assert lookup.active is None
    assert lookup.next_start is None


def test_resolve_is_empty_for_an_unknown_round(monkeypatch):
    _stub_event(monkeypatch, identity=(None, None, None))
    _stub_openf1(monkeypatch)

    assert asyncio.run(client.resolve_session_window(2026, 99, now=_utc(2026, 8, 23, 13, 30))).active is None


def test_resolve_is_empty_when_openf1_returns_nothing(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch, meetings=None)

    assert asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active is None


def test_resolve_is_empty_when_the_session_list_is_empty(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch, sessions=[])

    assert asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active is None


def test_resolve_is_empty_when_the_session_has_unusable_timestamps(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch, sessions=[
        {"session_key": 1, "session_name": "Race",
         "date_start": "2026-08-23T13:00:00+00:00", "date_end": "2026-08-23T15:00:00+00:00"},
    ])
    monkeypatch.setattr(client, "select_active_session", lambda *_a, **_k: {"session_key": 1})

    assert asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active is None


def test_active_session_exposes_its_window_for_state_derivation(monkeypatch):
    _stub_event(monkeypatch)
    _stub_openf1(monkeypatch)

    active = asyncio.run(client.resolve_session_window(2026, 12, now=_utc(2026, 8, 23, 13, 30))).active

    assert active.raw["date_start"].startswith("2026-08-23T13:00")
    assert active.raw["date_end"].startswith("2026-08-23T15:00")


# --------------------------------------------------------------------------
# poll_timing
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


def test_poll_timing_rejects_a_finished_session_replayed_as_live(monkeypatch):
    """The original bug: July's classification must not render in August."""
    _stub_openf1(monkeypatch, positions=BELGIAN_FINAL, intervals=[], laps=[], drivers=DRIVERS)

    assert asyncio.run(client.poll_timing(_race(), now=_utc(2026, 8, 22, 23, 28))) is None


def test_poll_timing_returns_rows_for_a_live_feed(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    sampled = (now - timedelta(seconds=5)).isoformat()
    _stub_openf1(
        monkeypatch,
        positions=[
            {"driver_number": 16, "position": 2, "date": sampled},
            {"driver_number": 12, "position": 1, "date": sampled},
        ],
        intervals=[{"driver_number": 16, "gap_to_leader": 1.952}],
        laps=[{"lap_number": 34}, {"lap_number": 12}],
        drivers=DRIVERS,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now))

    assert [r["driver"] for r in snapshot.rows] == ["ANT", "LEC"]
    assert snapshot.rows[0]["driver_number"] == 12
    assert snapshot.rows[1]["gap"] == "+1.952"
    assert snapshot.lap == 34


def test_poll_timing_stays_live_through_a_quiet_hour(monkeypatch):
    """Spain 2026: 58 minutes without a position change, still a live race.

    The position feed only emits on a change, so an untouched feed means the
    order is holding — not that the session has stopped. Judged on age the
    tower went dark for 39% of that Grand Prix.
    """
    now = _utc(2026, 8, 23, 14, 2)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": (RACE_START + timedelta(minutes=4)).isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now))

    assert snapshot.rows[0]["driver"] == "ANT"
    assert snapshot.sampled_at == RACE_START + timedelta(minutes=4)


def test_poll_timing_takes_liveness_from_laps_when_gaps_are_absent(monkeypatch):
    """Practice and qualifying publish no interval feed at all."""
    now = _utc(2026, 8, 23, 13, 40)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": (RACE_START - timedelta(minutes=54)).isoformat()}],
        intervals=None,
        laps=[{"lap_number": 8, "date_start": (now - timedelta(seconds=30)).isoformat()}],
        drivers=DRIVERS,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now))

    assert snapshot.lap == 8
    assert snapshot.sampled_at == now - timedelta(seconds=30)


def test_poll_timing_is_none_before_the_feed_opens(monkeypatch):
    """13:02 on Spain's race day: lights out, but OpenF1 published nothing yet."""
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": (RACE_START - timedelta(minutes=54)).isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    assert asyncio.run(client.poll_timing(_race(), now=RACE_START + timedelta(minutes=2))) is None


def test_poll_timing_is_none_when_the_feed_is_empty(monkeypatch):
    _stub_openf1(monkeypatch, positions=[], drivers=DRIVERS)

    assert asyncio.run(client.poll_timing(_race(), now=_utc(2026, 8, 23, 13, 30))) is None


def test_poll_timing_is_none_when_openf1_fails(monkeypatch):
    _stub_openf1(monkeypatch, positions=None, drivers=DRIVERS)

    assert asyncio.run(client.poll_timing(_race(), now=_utc(2026, 8, 23, 13, 30))) is None


def test_poll_timing_is_none_when_only_laps_report_in(monkeypatch):
    """A lap time with no order to hang it on cannot build a tower."""
    now = _utc(2026, 8, 23, 13, 30)
    _stub_openf1(
        monkeypatch,
        positions=[],
        intervals=[],
        laps=[{"lap_number": 4, "date_start": now.isoformat()}],
        drivers=DRIVERS,
    )

    assert asyncio.run(client.poll_timing(_race(), now=now)) is None


def test_poll_timing_still_renders_when_driver_metadata_is_missing(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        laps=[],
        drivers=None,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now))

    assert snapshot.rows[0]["driver"] == "12"
    assert snapshot.lap is None


def test_poll_timing_fetches_driver_metadata_once_per_session(monkeypatch):
    now = _utc(2026, 8, 23, 13, 30)
    calls = _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    asyncio.run(client.poll_timing(_race(), now=now))
    asyncio.run(client.poll_timing(_race(), now=now))

    assert _paths(calls).count("drivers") == 1


def test_poll_timing_carries_the_lap_count_through_a_red_flag(monkeypatch):
    """The lap feed is windowed, so a long stoppage empties it.

    The race has not un-run those laps: blanking the counter because nothing
    was published in the last quarter of an hour would be a lie about the
    session, so the last known lap stands until a newer one arrives.
    """
    now = _utc(2026, 8, 23, 14, 30)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": (RACE_START + timedelta(minutes=5)).isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now, last_lap=41))

    assert snapshot.lap == 41


def test_poll_timing_prefers_a_freshly_published_lap(monkeypatch):
    now = _utc(2026, 8, 23, 14, 30)
    _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        laps=[{"lap_number": 42}],
        drivers=DRIVERS,
    )

    snapshot = asyncio.run(client.poll_timing(_race(), now=now, last_lap=41))

    assert snapshot.lap == 42


# --------------------------------------------------------------------------
# request windowing
# --------------------------------------------------------------------------


def test_poll_timing_windows_the_gap_and_lap_feeds(monkeypatch):
    """Unfiltered, these return the whole session: 3.8 MB of gaps by race end."""
    now = _utc(2026, 8, 23, 14, 30)
    calls = _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    asyncio.run(client.poll_timing(_race(), now=now))

    assert _params(calls, "intervals")["date>"] == (now - GAP_FEED_WINDOW).isoformat()
    assert _params(calls, "laps")["date_start>"] == (now - LAP_FEED_WINDOW).isoformat()


def test_poll_timing_reads_the_whole_position_feed(monkeypatch):
    """A driver whose place has not changed all race still belongs on the tower,
    so the order cannot be windowed the way the gap feed is."""
    now = _utc(2026, 8, 23, 14, 30)
    calls = _stub_openf1(
        monkeypatch,
        positions=[{"driver_number": 12, "position": 1, "date": now.isoformat()}],
        intervals=[],
        laps=[],
        drivers=DRIVERS,
    )

    asyncio.run(client.poll_timing(_race(), now=now))

    assert _params(calls, "position") == {"session_key": "11353"}
