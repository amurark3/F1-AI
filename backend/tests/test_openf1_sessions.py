"""Tests for app.data.openf1.sessions: which OpenF1 session a round's Q, sprint or race is.

* Sessions are picked by OpenF1's **name**, and 2023's sprint shootout is
  "Sprint Qualifying" in OpenF1, so SQ maps to both names.
* A cancelled session is not offered.
* The weekend list comes from FastF1's calendar, which loads while OpenF1 is
  closed for a live session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd
import pytest

from app.data.openf1 import sessions as module
from app.data.openf1.sessions import (
    DEFAULT_TEAM_COLOUR,
    OpenF1Session,
    entry_list,
    event_identity,
    find_session,
    session_code,
    session_ended,
    weekend_schedule,
    weekend_sessions,
)
from tests.openf1_support import FakeOpenF1

pytestmark = pytest.mark.unit

SCHEDULE = pd.DataFrame(
    [
        {
            "RoundNumber": 4,
            "Location": "Baku",
            "EventDate": pd.Timestamp("2023-04-30"),
            "Session1": "Practice 1",
            "Session1DateUtc": pd.Timestamp("2023-04-28 09:30"),
            "Session2": "Qualifying",
            "Session2DateUtc": pd.Timestamp("2023-04-28 13:00"),
            "Session3": "Sprint Shootout",
            "Session3DateUtc": pd.Timestamp("2023-04-29 08:30"),
            "Session4": "Sprint",
            "Session4DateUtc": pd.NaT,
            "Session5": "None",
            "Session5DateUtc": pd.NaT,
        }
    ]
)
MEETINGS = [
    {"meeting_key": 1206, "location": "Baku", "date_start": "2023-04-28T09:30:00+00:00"},
]
SESSIONS = [
    {"session_key": 9070, "meeting_key": 1206, "session_name": "Race", "date_start": "2023-04-30T11:00:00+00:00"},
    {"session_key": 9068, "meeting_key": 1206, "session_name": "Sprint Qualifying", "date_start": None},
    {
        "session_key": 9064,
        "meeting_key": 1206,
        "session_name": "Qualifying",
        "circuit_key": 144,
        "date_start": "2023-04-28T13:00:00+00:00",
    },
    {"session_key": 9063, "meeting_key": 1206, "session_name": "Practice 1", "is_cancelled": True},
    {"session_key": 9062, "meeting_key": 1206, "session_name": "Day 1"},
    {"meeting_key": 1206, "session_name": "Sprint"},
]


@pytest.fixture
def calendar(monkeypatch):
    monkeypatch.setattr(module.fastf1, "get_event_schedule", lambda *_args, **_kwargs: SCHEDULE)


def _client(routes: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(FakeOpenF1(routes)))


@pytest.fixture
def openf1(calendar):
    with _client({"meetings": MEETINGS, "sessions": SESSIONS}) as client:
        yield client


@pytest.mark.parametrize(
    ("name", "code"),
    [("Sprint Shootout", "SQ"), ("Sprint Qualifying", "SQ"), ("Race", "R"), ("Practice 3", "FP3"), ("Day 1", None)],
)
def test_session_names_map_to_app_codes(name, code):
    assert session_code(name) == code


def test_the_event_is_located_from_the_calendar(calendar):
    assert event_identity(2023, 4) == ("Baku", datetime(2023, 4, 30, tzinfo=UTC))
    assert event_identity(2023, 99) is None


def test_the_weekend_list_comes_from_the_calendar_without_openf1(calendar):
    schedule = weekend_schedule(2023, 4)

    assert [(session.code, session.name) for session in schedule] == [
        ("FP1", "Practice 1"),
        ("Q", "Qualifying"),
        ("SQ", "Sprint Shootout"),
        ("S", "Sprint"),
    ]
    assert schedule[0].start == datetime(2023, 4, 28, 9, 30, tzinfo=UTC)
    assert schedule[3].start is None
    assert weekend_schedule(2023, 99) == ()


def test_weekend_sessions_skip_cancelled_unknown_and_keyless_rows(openf1):
    sessions = weekend_sessions(openf1, 2023, 4)

    # Running order by start time; an undated session goes last.
    assert [session.code for session in sessions] == ["Q", "R", "SQ"]
    assert sessions[0].circuit_key == 144
    assert sessions[1].circuit_key is None


def test_sprint_qualifying_is_found_under_openf1s_name(openf1):
    session = find_session(openf1, 2023, 4, "SQ")

    assert session is not None
    assert session.session_key == 9068


def test_a_round_off_the_calendar_or_unmatched_has_no_sessions(calendar):
    with _client({"meetings": [{"meeting_key": 1, "location": "Imola", "date_start": "2023-05-19"}]}) as client:
        assert weekend_sessions(client, 2023, 99) == ()
        assert find_session(client, 2023, 4, "R") is None


def _session(end: datetime | None) -> OpenF1Session:
    return OpenF1Session(1, 1, None, "Q", "Qualifying", None, end)


def test_a_session_is_kept_only_once_it_has_ended_and_settled():
    end = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    settle = timedelta(minutes=module.ANALYSIS_SESSION_SETTLE_MINUTES)

    assert not session_ended(_session(None))
    assert not session_ended(_session(end), now=end + settle - timedelta(seconds=1))
    assert session_ended(_session(end), now=end + settle)
    assert session_ended(_session(datetime(2020, 1, 1, tzinfo=UTC)))


def test_the_entry_list_reads_codes_teams_and_colours():
    routes = {
        "drivers": [
            {"driver_number": 1, "name_acronym": "nor", "full_name": "Lando NORRIS", "team_colour": "f47600"},
            {"driver_number": 3, "broadcast_name": "M VERSTAPPEN", "team_name": "Red Bull", "team_colour": "#zz"},
            {"name_acronym": "XXX"},
        ]
    }

    with _client(routes) as client:
        drivers = entry_list(client, 11392)

    assert drivers[1].code == "NOR"
    assert drivers[1].colour == "#F47600"
    assert drivers[3].code == "3"
    assert drivers[3].name == "M VERSTAPPEN"
    assert drivers[3].colour == DEFAULT_TEAM_COLOUR
    assert set(drivers) == {1, 3}
