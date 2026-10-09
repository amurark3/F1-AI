"""Tests for app.api.routers.season — schedule and championship standings.

Three things make this module worth close testing:

* **Session times are the product.** The schedule feeds a countdown, so every
  timestamp must leave as an explicit UTC instant. FastF1 hands back naive
  ``Session*DateUtc`` values, and a stamp that ships without a designator is
  read as local time by the browser.
* **The standings have a two-source fallback.** f1db is preferred (no rate
  limit, carries the live season); Ergast is the fallback and is rate-limited,
  which is exactly why the f1db path must not silently stop being taken.
* **A season with no points yet is not an empty season.** Before round one
  every driver has zero points, and Ergast returns no standings rows at all —
  the zero-point builders exist so the page lists the grid instead of nothing.

FastF1 and Ergast are mocked at the boundary; the network is blocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app.api.routers import season as season_router
from app.api.routers.season import (
    build_constructor_standing,
    build_driver_standing,
    build_schedule_event,
    build_zero_point_constructor_standings,
    build_zero_point_driver_standings,
)


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
def test_an_event_with_no_session_times_is_upcoming(monkeypatch):
    _freeze_now(monkeypatch, datetime(2030, 1, 1))

    row = _event_row(**{f"Session{i}": None for i in range(1, 6)})

    assert build_schedule_event(row)["status"] == "upcoming"


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
    monkeypatch.setattr(season_router.fastf1, "get_event_schedule", lambda year, include_testing: frame)

    body = await season_router.get_schedule(2026)

    assert [event["round"] for event in body] == [1, 2]


@pytest.mark.unit
async def test_schedule_excludes_pre_season_testing(monkeypatch):
    """Testing events have no round number and would corrupt the calendar."""
    _freeze_now(monkeypatch, datetime(2026, 1, 1))
    seen: dict = {}

    def capture(year, include_testing):
        seen.update({"year": year, "include_testing": include_testing})
        return pd.DataFrame([_event_row()])

    monkeypatch.setattr(season_router.fastf1, "get_event_schedule", capture)

    await season_router.get_schedule(2026)

    assert seen == {"year": 2026, "include_testing": False}


@pytest.mark.unit
async def test_schedule_failure_returns_a_client_safe_error(monkeypatch):
    def explode(**_kwargs):
        raise ConnectionError("https://api.jolpi.ca/ergast returned 429")

    monkeypatch.setattr(season_router.fastf1, "get_event_schedule", explode)

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
    monkeypatch.setattr(
        season_router,
        "Ergast",
        lambda: pytest.fail("Ergast is rate-limited and must not be reached on the f1db path"),
    )

    body = await season_router.get_driver_standings(2026)

    assert body == [{"position": 1, "driver": "Max Verstappen", "team": "Red Bull", "points": 50.0, "wins": 2}]


@pytest.mark.unit
async def test_driver_standings_fall_back_to_ergast(monkeypatch):
    monkeypatch.setattr(season_router, "driver_standings_detailed", lambda year: [])
    frame = pd.DataFrame(
        [
            {
                "position": 1,
                "givenName": "Ayrton",
                "familyName": "Senna",
                "constructorNames": ["McLaren"],
                "points": 90.0,
                "wins": 8,
            }
        ]
    )

    class _FakeErgast:
        def get_driver_standings(self, season):
            return type("R", (), {"content": [frame]})()

    monkeypatch.setattr(season_router, "Ergast", _FakeErgast)

    body = await season_router.get_driver_standings(1988)

    assert body[0]["driver"] == "Ayrton Senna"
    assert body[0]["team"] == "McLaren"


@pytest.mark.unit
async def test_driver_standings_return_the_grid_before_any_points_are_scored(monkeypatch):
    """Ergast returns no standings rows pre-season; the page must still list drivers."""
    monkeypatch.setattr(season_router, "driver_standings_detailed", lambda year: [])

    class _FakeErgast:
        def get_driver_standings(self, season):
            return type("R", (), {"content": []})()

        def get_constructor_info(self, season):
            return pd.DataFrame([{"constructorId": "ferrari", "constructorName": "Ferrari"}])

        def get_driver_info(self, season, constructor):
            return pd.DataFrame([{"givenName": "Charles", "familyName": "Leclerc"}])

    monkeypatch.setattr(season_router, "Ergast", _FakeErgast)

    body = await season_router.get_driver_standings(2027)

    assert body == [{"position": 1, "driver": "Charles Leclerc", "team": "Ferrari", "points": 0.0, "wins": 0}]


@pytest.mark.unit
async def test_driver_standings_return_empty_on_failure(monkeypatch):
    monkeypatch.setattr(season_router, "driver_standings_detailed", lambda year: [])

    def explode():
        raise ConnectionError("ergast unreachable")

    monkeypatch.setattr(season_router, "Ergast", explode)

    assert await season_router.get_driver_standings(1950) == []


@pytest.mark.unit
def test_driver_standing_uses_the_row_position_when_present():
    row = pd.Series(
        {
            "position": 3,
            "givenName": "Lando",
            "familyName": "Norris",
            "constructorName": "McLaren",
            "points": 30,
            "wins": 1,
        }
    )

    assert build_driver_standing(row, fallback_position=99)["position"] == 3


@pytest.mark.unit
def test_driver_standing_falls_back_to_the_enumeration_index():
    """Ergast omits `position` for some historical seasons."""
    row = pd.Series({"position": float("nan"), "givenName": "Jim", "familyName": "Clark"})

    assert build_driver_standing(row, fallback_position=4)["position"] == 4


@pytest.mark.unit
def test_driver_standing_uses_the_last_constructor_of_a_split_season():
    # A driver who switched teams mid-season is listed under the team they
    # finished with, which is the one the standings table shows.
    row = pd.Series(
        {"position": 5, "givenName": "Carlos", "familyName": "Sainz", "constructorNames": ["Ferrari", "Williams"]}
    )

    assert build_driver_standing(row, 5)["team"] == "Williams"


@pytest.mark.unit
def test_driver_standing_stringifies_a_non_list_constructor_field():
    row = pd.Series({"position": 5, "givenName": "A", "familyName": "B", "constructorNames": "Sauber"})

    assert build_driver_standing(row, 5)["team"] == "Sauber"


@pytest.mark.unit
def test_driver_standing_reports_unknown_when_no_constructor_is_given():
    row = pd.Series({"position": 5, "givenName": "A", "familyName": "B"})

    assert build_driver_standing(row, 5)["team"] == "Unknown"


@pytest.mark.unit
def test_zero_point_driver_standings_are_empty_without_constructors():
    class _FakeErgast:
        def get_constructor_info(self, season):
            return pd.DataFrame()

    assert build_zero_point_driver_standings(_FakeErgast(), 2027) == []


@pytest.mark.unit
def test_zero_point_driver_standings_number_every_driver_sequentially():
    class _FakeErgast:
        def get_constructor_info(self, season):
            return pd.DataFrame(
                [
                    {"constructorId": "ferrari", "constructorName": "Ferrari"},
                    {"constructorId": "mclaren", "constructorName": "McLaren"},
                ]
            )

        def get_driver_info(self, season, constructor):
            return pd.DataFrame([{"givenName": "A", "familyName": "One"}, {"givenName": "B", "familyName": "Two"}])

    result = build_zero_point_driver_standings(_FakeErgast(), 2027)

    assert [r["position"] for r in result] == [1, 2, 3, 4]
    assert result[2]["team"] == "McLaren"


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
    monkeypatch.setattr(season_router, "Ergast", lambda: pytest.fail("must not reach Ergast"))

    assert await season_router.get_constructor_standings(2026) == [
        {"position": 1, "team": "Red Bull", "points": 50.0, "wins": 2}
    ]


@pytest.mark.unit
async def test_constructor_standings_fall_back_to_ergast(monkeypatch):
    monkeypatch.setattr(season_router, "constructor_standings_detailed", lambda year: [])
    frame = pd.DataFrame([{"position": 1, "constructorName": "Williams", "points": 164.0, "wins": 7}])

    class _FakeErgast:
        def get_constructor_standings(self, season):
            return type("R", (), {"content": [frame]})()

    monkeypatch.setattr(season_router, "Ergast", _FakeErgast)

    assert (await season_router.get_constructor_standings(1992))[0]["team"] == "Williams"


@pytest.mark.unit
async def test_constructor_standings_list_the_grid_before_any_points(monkeypatch):
    monkeypatch.setattr(season_router, "constructor_standings_detailed", lambda year: [])

    class _FakeErgast:
        def get_constructor_standings(self, season):
            return type("R", (), {"content": []})()

        def get_constructor_info(self, season):
            return pd.DataFrame([{"constructorName": "Ferrari"}, {"constructorName": "McLaren"}])

    monkeypatch.setattr(season_router, "Ergast", _FakeErgast)

    body = await season_router.get_constructor_standings(2027)

    assert [row["team"] for row in body] == ["Ferrari", "McLaren"]
    assert all(row["points"] == 0.0 for row in body)


@pytest.mark.unit
async def test_constructor_standings_return_empty_on_failure(monkeypatch):
    monkeypatch.setattr(season_router, "constructor_standings_detailed", lambda year: [])

    def explode():
        raise ConnectionError("ergast unreachable")

    monkeypatch.setattr(season_router, "Ergast", explode)

    assert await season_router.get_constructor_standings(1950) == []


@pytest.mark.unit
def test_constructor_standing_uses_the_row_position_when_present():
    row = pd.Series({"position": 2, "constructorName": "Ferrari", "points": 40, "wins": 1})

    assert build_constructor_standing(row, 9)["position"] == 2


@pytest.mark.unit
def test_constructor_standing_falls_back_to_the_enumeration_index():
    row = pd.Series({"position": float("nan"), "constructorName": "Ferrari"})

    assert build_constructor_standing(row, 3)["position"] == 3


@pytest.mark.unit
def test_constructor_standing_reports_unknown_for_a_missing_name():
    row = pd.Series({"position": 1})

    assert build_constructor_standing(row, 1)["team"] == "Unknown"


@pytest.mark.unit
def test_zero_point_constructor_standings_are_empty_without_constructors():
    class _FakeErgast:
        def get_constructor_info(self, season):
            return pd.DataFrame()

    assert build_zero_point_constructor_standings(_FakeErgast(), 2027) == []


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
    monkeypatch.setattr(
        season_router.fastf1, "get_event_schedule", lambda year, include_testing: pd.DataFrame([_event_row()])
    )
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

    def explode(year, include_testing):
        raise RuntimeError("FastF1 is down")

    monkeypatch.setattr(season_router.fastf1, "get_event_schedule", explode)

    response = client.get("/schedule/2026")

    assert response.status_code == 200
    assert "error_id" in response.json()
