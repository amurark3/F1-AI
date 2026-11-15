"""Tests for app.api.routers.season — schedule and championship standings.

Two things make this module worth close testing:

* **Session times are the product.** The schedule feeds a countdown, so every
  timestamp must leave as an explicit UTC instant. FastF1 hands back naive
  ``Session*DateUtc`` values, and a stamp that ships without a designator is
  read as local time by the browser.
* **The standings read f1db alone.** It has no rate limit and carries the live
  season; a season it has no table for yet answers an empty list (Jolpica is
  not asked: FastF1's Ergast client is gone).

f1db and the schedule are mocked at the boundary; the network is blocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app.api.routers import season as season_router
from app.api.routers.season import (
    build_schedule_event,
)
from app.data.f1db_calendar import CalendarUnavailableError


@pytest.fixture
def client():
    """A client that surfaces handler/validation failures as a 500 rather than raising.

    Keeps a response-model regression visible as a status code instead of an
    exception escaping the test client — see
    ``test_list_returning_handlers_answer_200_over_http``.
    """
    app = FastAPI()
    app.include_router(season_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _event_row(**overrides) -> pd.Series:
    """A FastF1 schedule row. Session times are naive UTC, as FastF1 supplies them."""
    base = datetime(2026, 3, 6, 12, 0)
    data = {
        "RoundNumber": 1,
        "EventName": "Bahrain Grand Prix",
        "Location": "Sakhir",
        "Country": "Bahrain",
        "EventDate": pd.Timestamp("2026-03-08"),
        "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp(base),
        "Session2": "Practice 2",
        "Session2DateUtc": pd.Timestamp(base + timedelta(hours=4)),
        "Session3": "Qualifying",
        "Session3DateUtc": pd.Timestamp(base + timedelta(days=1)),
        "Session4": "Race",
        "Session4DateUtc": pd.Timestamp(base + timedelta(days=2)),
        "Session5": None,
        "Session5DateUtc": pd.NaT,
    }
    data.update(overrides)
    return pd.Series(data)


def _freeze_now(monkeypatch, when: datetime) -> None:
    """Pin the module's clock so schedule status is deterministic."""

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz) if tz else when

    monkeypatch.setattr(season_router, "datetime", _FrozenDatetime)


# ---------------------------------------------------------------------------
# build_schedule_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_event_carries_the_round_name_and_combined_location(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    event = build_schedule_event(_event_row())

    assert event["round"] == 1
    assert event["name"] == "Bahrain Grand Prix"
    assert event["location"] == "Sakhir, Bahrain"


@pytest.mark.unit
def test_circuit_metadata_is_attached_from_the_location(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    event = build_schedule_event(_event_row())

    assert event["circuit"]["circuit_name"] == "Bahrain International Circuit"


@pytest.mark.unit
def test_an_unknown_location_yields_a_null_circuit(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    event = build_schedule_event(_event_row(Location="Nürburgring", Country="Germany"))

    assert event["circuit"] is None


@pytest.mark.unit
def test_every_session_time_leaves_as_an_explicit_utc_instant(monkeypatch):
    """A naive stamp would be parsed as local time by the browser countdown."""
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    sessions = build_schedule_event(_event_row())["sessions"]

    assert sessions["Practice 1"] == "2026-03-06T12:00:00Z"
    assert all(value.endswith("Z") for value in sessions.values())


@pytest.mark.unit
def test_sessions_without_a_name_or_a_date_are_skipped(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    row = _event_row(Session2=None, Session3DateUtc=pd.NaT)

    sessions = build_schedule_event(row)["sessions"]

    assert set(sessions) == {"Practice 1", "Race"}


@pytest.mark.unit
def test_a_row_missing_a_session_column_entirely_is_tolerated(monkeypatch):
    """Older FastF1 schedules carry fewer than five session columns."""
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    row = _event_row().drop(labels=["Session4", "Session4DateUtc", "Session5", "Session5DateUtc"])

    event = build_schedule_event(row)

    assert set(event["sessions"]) == {"Practice 1", "Practice 2", "Qualifying"}


@pytest.mark.unit
def test_a_sprint_weekend_is_flagged(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    assert build_schedule_event(_event_row(Session3="Sprint"))["is_sprint"] is True


@pytest.mark.unit
def test_a_normal_weekend_is_not_flagged_as_a_sprint(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    assert build_schedule_event(_event_row())["is_sprint"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 1, 1), "upcoming"),
        (datetime(2026, 3, 6, 13, 0), "in_progress"),
        (datetime(2026, 3, 8, 12, 30), "in_progress"),
        (datetime(2026, 3, 8, 15, 30), "completed"),
    ],
    ids=["before-fp1", "during-fp1", "just-after-race", "three-hours-after-race"],
)
def test_status_tracks_the_weekend_timeline(monkeypatch, now, expected):
    # The race is 2026-03-08 12:00 UTC; "completed" only lands three hours
    # later, so a red-flagged race is not marked finished while still running.
    _freeze_now(monkeypatch, now)

    assert build_schedule_event(_event_row())["status"] == expected


@pytest.mark.unit
@pytest.mark.parametrize(("now", "expected"), [(datetime(2026, 3, 7), "upcoming"), (datetime(2030, 1, 1), "completed")])
def test_an_event_with_no_session_times_is_dated_by_race_day(monkeypatch, now, expected):
    _freeze_now(monkeypatch, now)

    row = _event_row(**{f"Session{i}": None for i in range(1, 6)})

    assert build_schedule_event(row)["status"] == expected


@pytest.mark.unit
def test_an_event_date_without_a_designator_gains_one(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    assert build_schedule_event(_event_row())["date"] == "2026-03-08T00:00:00Z"


@pytest.mark.unit
def test_an_already_offset_event_date_is_left_alone(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))

    row = _event_row(EventDate=pd.Timestamp("2026-03-08T00:00:00+02:00"))

    assert build_schedule_event(row)["date"] == "2026-03-08T00:00:00+02:00"


# ---------------------------------------------------------------------------
# GET /schedule/{year}
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_schedule_returns_one_entry_per_round(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 1, 1))
    frame = pd.DataFrame([_event_row(), _event_row(RoundNumber=2, EventName="Monaco Grand Prix")])
    monkeypatch.setattr(season_router, "season_schedule", lambda _year: frame)

    body = await season_router.get_schedule(2026)

    assert [event["round"] for event in body] == [1, 2]


@pytest.mark.unit
async def test_schedule_reads_f1dbs_sprint_and_conventional_weekends(calendar_f1db, monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 11, 14))

    body = {event["round"]: event for event in await season_router.get_schedule(2026)}

    singapore, mexico = body[17], body[19]
    assert (singapore["is_sprint"], list(singapore["sessions"])) == (
        True,
        ["Practice 1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"],
    )
    assert (mexico["name"], mexico["location"], mexico["date"]) == (
        "Mexican Grand Prix",
        "Mexico City, Mexico",
        "2026-11-01T00:00:00Z",
    )
    assert (mexico["is_sprint"], mexico["sessions"]["Race"], mexico["status"]) == (
        False,
        "2026-11-01T20:00:00Z",
        "completed",
    )
    assert mexico["circuit"]["circuit_name"] == "Autódromo Hermanos Rodríguez"
    assert (body[21]["status"], len(body)) == ("upcoming", 23)


@pytest.mark.unit
async def test_a_season_f1db_has_no_session_times_for_is_dated_by_race_day(calendar_f1db, monkeypatch):
    """f1db sets no session times before 2024: a 2023 round has run once its race day has."""
    _freeze_now(monkeypatch, datetime(2026, 11, 14))

    body = await season_router.get_schedule(2023)

    assert len(body) == 22
    assert {event["status"] for event in body} == {"completed"}
    assert {len(event["sessions"]) for event in body} == {0}


@pytest.mark.unit
async def test_schedule_failure_returns_a_client_safe_error(monkeypatch):
    def explode(_year):
        raise ConnectionError("https://api.jolpi.ca/ergast returned 429")

    monkeypatch.setattr(season_router, "season_schedule", explode)

    body = await season_router.get_schedule(2026)

    assert "error_id" in body
    assert "jolpi.ca" not in str(body)


# ---------------------------------------------------------------------------
# Driver standings
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_driver_standings_prefer_f1db(monkeypatch):
    monkeypatch.setattr(
        season_router,
        "driver_standings_detailed",
        lambda year: [{"position": 1, "name": "Max Verstappen", "team": "Red Bull", "points": 50.0, "wins": 2}],
    )

    body = await season_router.get_driver_standings(2026)

    assert body == [{"position": 1, "driver": "Max Verstappen", "team": "Red Bull", "points": 50.0, "wins": 2}]


@pytest.mark.unit
async def test_driver_standings_are_empty_when_f1db_has_no_table(monkeypatch):
    """A season f1db has not reached answers nothing; Jolpica is no longer asked."""
    monkeypatch.setattr(season_router, "driver_standings_detailed", lambda year: [])

    assert await season_router.get_driver_standings(2027) == []


# ---------------------------------------------------------------------------
# Constructor standings
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_constructor_standings_prefer_f1db(monkeypatch):
    monkeypatch.setattr(
        season_router,
        "constructor_standings_detailed",
        lambda year: [{"position": 1, "team": "Red Bull", "points": 50.0, "wins": 2}],
    )

    assert await season_router.get_constructor_standings(2026) == [
        {"position": 1, "team": "Red Bull", "points": 50.0, "wins": 2}
    ]


@pytest.mark.unit
async def test_constructor_standings_are_empty_when_f1db_has_no_table(monkeypatch):
    monkeypatch.setattr(season_router, "constructor_standings_detailed", lambda year: [])

    assert await season_router.get_constructor_standings(2027) == []


# ---------------------------------------------------------------------------
# Regression: the response model derived from each handler's return annotation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    ["/schedule/2026", "/standings/drivers/2026", "/standings/constructors/2026"],
)
def test_list_returning_handlers_answer_200_over_http(client, monkeypatch, path):
    """These three endpoints must survive their own response model.

    FastAPI derives ``response_model`` from a handler's return annotation. All
    three handlers return a **list**, and each was once annotated ``-> dict`` —
    so every response failed validation with ``ResponseValidationError`` and the
    client got a 500. That took out the season calendar and both standings
    tables at once.

    The bad annotations arrived with the lint pass that required every signature
    to be annotated (ruff ``ANN201``); before it these handlers were unannotated
    and so had no response model at all. Since ``ANN201`` cannot simply be
    switched off for them, the annotation has to stay *and* stay honest — which
    is what this asserts. The tests above cover the return values; this one
    covers the serialisation boundary they pass through.
    """
    _freeze_now(monkeypatch, datetime(2026, 1, 1))
    monkeypatch.setattr(season_router, "season_schedule", lambda _year: pd.DataFrame([_event_row()]))
    monkeypatch.setattr(
        season_router,
        "driver_standings_detailed",
        lambda year: [{"position": 1, "name": "M", "team": "T", "points": 1.0, "wins": 0}],
    )
    monkeypatch.setattr(
        season_router,
        "constructor_standings_detailed",
        lambda year: [{"position": 1, "team": "T", "points": 1.0, "wins": 0}],
    )

    response = client.get(path)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.unit
def test_the_schedule_error_payload_survives_its_response_model(client, monkeypatch):
    """`/schedule` answers a dict on failure, so its annotation admits both shapes.

    `get_schedule` is the one handler of the three whose error path returns
    ``client_error(...)`` — a dict — rather than an empty list. Annotating it
    ``-> list[dict]`` alone would have moved the 500 from the happy path to the
    failure path, where it would be far harder to notice.
    """

    def explode(_year):
        raise CalendarUnavailableError("f1db has no calendar for 2026 yet")

    monkeypatch.setattr(season_router, "season_schedule", explode)

    response = client.get("/schedule/2026")

    assert response.status_code == 200
    assert "error_id" in response.json()
