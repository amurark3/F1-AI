"""Tests for app.data.openf1.sessions: which OpenF1 session a round's Q, sprint or race is.

* Sessions are picked by OpenF1's **name**, and 2023's sprint shootout is
  "Sprint Qualifying" in OpenF1, so SQ maps to both names.
* A cancelled session is not offered.
* The weekend list comes from f1db's calendar, which loads while OpenF1 is
  closed for a live session.
* The OpenF1 meeting is the one starting nearest the f1db race day: on the real
  2026 rows every round finds its meeting, past the two cancelled April rounds
  and pre-season testing, and R19/R20 find the session keys production used
  (Mexico City Q 11400, São Paulo Q 11408).
* A car prints under f1db's names: OpenF1 writes "Ryo HIRAKAWA" and "Haas F1
  Team" for car 50, the payload says "Ryō Hirakawa" and "Haas". OpenF1's number,
  code and colour are kept, and its own words when f1db cannot be read.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3

import httpx
import pandas as pd
import pytest
import structlog

from app.data import f1db_source
from app.data.openf1 import sessions as module
from app.data.openf1.sessions import (
    DEFAULT_TEAM_COLOUR,
    OpenF1Session,
    canonical_entry,
    entry_list,
    event_date,
    find_meeting,
    find_session,
    session_code,
    session_ended,
    weekend_schedule,
    weekend_sessions,
)
from tests.calendar_support import meetings_2026
from tests.openf1_support import FakeOpenF1

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
# OpenF1's Mexico City qualifying list (2026 R19): Hirakawa in car 50 for Haas.
MEXICO_QUALIFYING = FIXTURES / "mexico_2026_r19" / "openf1_drivers_qualifying.json"

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
    monkeypatch.setattr(module, "season_schedule", lambda _year: SCHEDULE)


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


def test_the_race_day_comes_from_the_calendar(calendar):
    assert event_date(2023, 4) == datetime(2023, 4, 30, tzinfo=UTC)
    assert event_date(2023, 99) is None


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


SESSIONS_2026 = {
    1298: json.loads((FIXTURES / "mexico_2026_r19" / "openf1_sessions.json").read_text()),
    1299: json.loads((FIXTURES / "sao_paulo_2026_r20" / "openf1_sessions.json").read_text()),
}


def _openf1_2026() -> httpx.Client:
    def sessions(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SESSIONS_2026[int(request.url.params["meeting_key"])])

    return _client({"meetings": meetings_2026(), "sessions": sessions})


def test_every_2026_round_finds_its_own_meeting_by_date(calendar_f1db):
    raced = [
        meeting["meeting_key"]
        for meeting in meetings_2026()
        if not meeting["is_cancelled"] and meeting["meeting_name"] != "Pre-Season Testing"
    ]

    with _openf1_2026() as client:
        found = [find_meeting(client, 2026, round_num)["meeting_key"] for round_num in range(1, 24)]

    # 23 rounds, past the cancelled April Bahrain and Saudi rounds; R16 is the
    # Bahrain Grand Prix OpenF1 files under Kuala Lumpur.
    assert found == raced
    assert found[15] == 1308


@pytest.mark.parametrize(
    ("round_num", "keys"),
    [
        (19, {"FP1": 11397, "FP2": 11398, "FP3": 11399, "Q": 11400, "R": 11404}),
        (20, {"FP1": 11405, "FP2": 11406, "FP3": 11407, "Q": 11408, "R": 11412}),
    ],
    ids=["R19", "R20"],
)
def test_r19_and_r20_find_the_sessions_production_resolved(calendar_f1db, round_num, keys):
    with _openf1_2026() as client:
        found = {code: find_session(client, 2026, round_num, code).session_key for code in keys}

    assert found == keys


def test_a_round_f1db_does_not_list_has_no_meeting(calendar_f1db):
    with _openf1_2026() as client:
        assert find_meeting(client, 2026, 24) is None


@pytest.mark.parametrize(
    ("round_num", "codes"),
    [(17, ["FP1", "SQ", "S", "Q", "R"]), (19, ["FP1", "FP2", "FP3", "Q", "R"])],
    ids=["sprint", "conventional"],
)
def test_the_weekend_list_reads_f1dbs_sessions(calendar_f1db, round_num, codes):
    schedule = weekend_schedule(2026, round_num)

    assert [session.code for session in schedule] == codes
    assert all(session.start is not None and session.start.tzinfo is UTC for session in schedule)


def test_a_weekend_before_f1db_has_session_times_lists_none(calendar_f1db):
    assert weekend_schedule(2023, 4) == ()
    assert event_date(2023, 4) == datetime(2023, 4, 30, tzinfo=UTC)


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


def _mexico_qualifying_cars() -> dict:
    with _client({"drivers": json.loads(MEXICO_QUALIFYING.read_text())}) as client:
        return entry_list(client, 11400)


def test_a_car_prints_under_f1dbs_names_and_keeps_openf1s_number_code_and_colour(identity_f1db):
    cars = _mexico_qualifying_cars()

    named = {number: canonical_entry(car, 2026) for number, car in cars.items()}

    assert (cars[50].name, cars[50].team) == ("Ryo HIRAKAWA", "Haas F1 Team")
    assert named[50] == replace(cars[50], name="Ryō Hirakawa", team="Haas")
    assert [named[number].name for number in (12, 27, 55, 11)] == [
        "Kimi Antonelli",
        "Nico Hülkenberg",
        "Carlos Sainz Jr.",
        "Sergio Pérez",
    ]
    assert (named[3].team, named[30].team) == ("Red Bull", "Racing Bulls")
    assert all(
        (named[n].number, named[n].code, named[n].colour) == (n, car.code, car.colour) for n, car in cars.items()
    )


def test_an_unreadable_f1db_leaves_openf1s_words_display_cased_and_logs_why(monkeypatch):
    def connect() -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(f1db_source, "connect", connect)
    car = _mexico_qualifying_cars()[50]

    with structlog.testing.capture_logs() as logs:
        named = canonical_entry(car, 2026)

    assert (named.name, named.team) == ("Ryo Hirakawa", "Haas F1 Team")
    assert {log["event"] for log in logs} == {"canonical_names.f1db_unreadable"}
