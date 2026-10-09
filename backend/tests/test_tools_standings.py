"""Tests for app.api.tools.standings — championship tables and the calendar.

Two standings tools that read f1db first and fall back to Ergast, plus the
season schedule. The risks are source-shaped and date-shaped:

* **f1db is preferred and Ergast is only a fallback.** Ergast is rate limited
  and does not carry the current season; reaching for it when f1db has the data
  is the failure this ordering exists to prevent.
* **An empty f1db answer still produces a table.** ``[]`` is falsy and must
  route to Ergast rather than render a header with no rows under it.
* **A race's date decides Completed vs Upcoming.** FastF1 hands back a tz-naive
  ``EventDate``; comparing it against a tz-aware now raises, and the raise is
  swallowed by the tool's own except clause, so the whole calendar degrades to
  an error string with nothing pointing at the cause.

FastF1 and Ergast are mocked at their import sites; the frames are real pandas
so the row iteration and formatting under test are the real ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.api.tools import standings as standings_module
from app.api.tools.standings import (
    get_constructor_standings,
    get_driver_standings,
    get_season_schedule,
)


class _FakeErgastResponse:
    def __init__(self, content: list):
        self.content = content


class _FakeErgast:
    """Stands in for ``fastf1.ergast.Ergast``; records that it was consulted."""

    def __init__(self, drivers=None, constructors=None):
        self._drivers = drivers
        self._constructors = constructors
        self.calls: list[tuple[str, int]] = []

    def get_driver_standings(self, season: int):
        self.calls.append(("drivers", season))
        return _FakeErgastResponse(self._drivers or [])

    def get_constructor_standings(self, season: int):
        self.calls.append(("constructors", season))
        return _FakeErgastResponse(self._constructors or [])


def _install_ergast(monkeypatch, ergast: _FakeErgast) -> _FakeErgast:
    monkeypatch.setattr(standings_module, "Ergast", lambda: ergast)
    return ergast


# ---------------------------------------------------------------------------
# get_driver_standings
# ---------------------------------------------------------------------------


def _f1db_drivers() -> list[dict]:
    return [
        {"position": 1, "code": "VER", "team": "Red Bull", "points": 393.0, "wins": 9},
        # A driver who changed teams carries both, already joined by f1db.
        {"position": 2, "code": "NOR", "team": "McLaren", "points": 331.5, "wins": 4},
    ]


@pytest.mark.unit
def test_driver_standings_render_from_f1db(monkeypatch):
    monkeypatch.setattr(standings_module, "driver_standings_detailed", lambda year: _f1db_drivers())

    table = get_driver_standings.invoke({"year": 2026})

    assert table.splitlines() == [
        "### Driver Standings (2026)",
        "| Pos | Driver | Team | Points | Wins |",
        "| :-- | :----- | :--- | :----- | :--- |",
        # ":g" drops the trailing zero on a whole-number total but keeps a half point.
        "| 1 | VER | Red Bull | 393 | 9 |",
        "| 2 | NOR | McLaren | 331.5 | 4 |",
    ]


@pytest.mark.unit
def test_driver_standings_do_not_reach_for_ergast_when_f1db_answers(monkeypatch):
    """Ergast is rate limited; the local dataset must win when it has the season."""
    monkeypatch.setattr(standings_module, "driver_standings_detailed", lambda year: _f1db_drivers())
    ergast = _install_ergast(monkeypatch, _FakeErgast())

    get_driver_standings.invoke({"year": 2026})

    assert ergast.calls == []


@pytest.mark.unit
def test_driver_standings_fall_back_to_ergast_when_f1db_is_empty(monkeypatch):
    monkeypatch.setattr(standings_module, "driver_standings_detailed", lambda year: [])
    frame = pd.DataFrame(
        [
            {
                "position": 1,
                "driverCode": "HAM",
                "points": 413,
                "wins": 11,
                "constructorNames": ["Mercedes"],
            }
        ]
    )
    ergast = _install_ergast(monkeypatch, _FakeErgast(drivers=[frame]))

    table = get_driver_standings.invoke({"year": 2020})

    assert ergast.calls == [("drivers", 2020)]
    assert "| 1 | HAM | Mercedes | 413 | 11 |" in table


@pytest.mark.unit
def test_a_mid_season_team_switch_lists_every_constructor(monkeypatch):
    """Ergast returns a list here; str() on it would render Python syntax."""
    monkeypatch.setattr(standings_module, "driver_standings_detailed", lambda year: [])
    frame = pd.DataFrame(
        [
            {
                "position": 12,
                "driverCode": "SAI",
                "points": 38,
                "wins": 0,
                "constructorNames": ["Ferrari", "Williams"],
            }
        ]
    )
    _install_ergast(monkeypatch, _FakeErgast(drivers=[frame]))

    assert "| 12 | SAI | Ferrari, Williams | 38 | 0 |" in get_driver_standings.invoke({"year": 2024})


@pytest.mark.unit
def test_a_season_neither_source_knows_is_reported_as_missing(monkeypatch):
    monkeypatch.setattr(standings_module, "driver_standings_detailed", lambda year: [])
    _install_ergast(monkeypatch, _FakeErgast(drivers=[]))

    assert get_driver_standings.invoke({"year": 1949}) == "No driver standings found for 1949."


@pytest.mark.unit
def test_a_driver_standings_failure_is_reported_rather_than_raised(monkeypatch):
    def _boom(year):
        raise RuntimeError("f1db is locked")

    monkeypatch.setattr(standings_module, "driver_standings_detailed", _boom)

    assert get_driver_standings.invoke({"year": 2026}) == "Failed to fetch driver standings: f1db is locked"


# ---------------------------------------------------------------------------
# get_constructor_standings
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_constructor_standings_render_from_f1db(monkeypatch):
    monkeypatch.setattr(
        standings_module,
        "constructor_standings_detailed",
        lambda year: [
            {"position": 1, "team": "McLaren", "points": 666.0, "wins": 12},
            {"position": 2, "team": "Ferrari", "points": 652.5, "wins": 6},
        ],
    )

    table = get_constructor_standings.invoke({"year": 2026})

    assert table.splitlines() == [
        "### Constructor Standings (2026)",
        "| Pos | Team | Points | Wins |",
        "| :-- | :--- | :----- | :--- |",
        "| 1 | McLaren | 666 | 12 |",
        "| 2 | Ferrari | 652.5 | 6 |",
    ]


@pytest.mark.unit
def test_constructor_standings_fall_back_to_ergast_when_f1db_is_empty(monkeypatch):
    monkeypatch.setattr(standings_module, "constructor_standings_detailed", lambda year: [])
    frame = pd.DataFrame([{"position": 1, "constructorName": "Mercedes", "points": 739, "wins": 15}])
    ergast = _install_ergast(monkeypatch, _FakeErgast(constructors=[frame]))

    table = get_constructor_standings.invoke({"year": 2019})

    assert ergast.calls == [("constructors", 2019)]
    assert "| 1 | Mercedes | 739 | 15 |" in table


@pytest.mark.unit
def test_a_season_with_no_constructor_data_is_reported_as_missing(monkeypatch):
    monkeypatch.setattr(standings_module, "constructor_standings_detailed", lambda year: [])
    _install_ergast(monkeypatch, _FakeErgast(constructors=[]))

    assert get_constructor_standings.invoke({"year": 1949}) == "No constructor standings found for 1949."


@pytest.mark.unit
def test_a_constructor_standings_failure_is_reported_rather_than_raised(monkeypatch):
    def _boom(year):
        raise RuntimeError("f1db is locked")

    monkeypatch.setattr(standings_module, "constructor_standings_detailed", _boom)

    assert get_constructor_standings.invoke({"year": 2026}) == "Failed to fetch constructor standings: f1db is locked"


# ---------------------------------------------------------------------------
# get_season_schedule
# ---------------------------------------------------------------------------


def _schedule(dates: list[pd.Timestamp]) -> pd.DataFrame:
    names = ["Bahrain Grand Prix", "Saudi Arabian Grand Prix", "Australian Grand Prix"]
    return pd.DataFrame(
        [{"RoundNumber": index + 1, "EventName": names[index], "EventDate": date} for index, date in enumerate(dates)]
    )


def _install_schedule(monkeypatch, schedule) -> list[dict]:
    calls: list[dict] = []

    def _get_event_schedule(*, year, include_testing):
        calls.append({"year": year, "include_testing": include_testing})
        if isinstance(schedule, Exception):
            raise schedule
        return schedule

    monkeypatch.setattr(standings_module.fastf1, "get_event_schedule", _get_event_schedule)
    return calls


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.unit
def test_a_tz_naive_event_date_still_classifies_as_completed(monkeypatch):
    """FastF1 hands back tz-naive dates; a tz-aware comparison raises.

    The raise lands in the tool's own except clause, so the whole calendar comes
    back as "Failed to fetch schedule" with nothing naming the real cause.
    """
    past = pd.Timestamp(_now() - timedelta(days=30))
    _install_schedule(monkeypatch, _schedule([past]))

    table = get_season_schedule.invoke({"year": 2026})

    assert not table.startswith("Failed to fetch schedule")
    assert "✅ Completed" in table


@pytest.mark.unit
def test_a_tz_aware_event_date_is_also_accepted(monkeypatch):
    """A future pandas or FastF1 that localises the column must not break this."""
    past = pd.Timestamp(_now() - timedelta(days=30), tz="UTC")
    _install_schedule(monkeypatch, _schedule([past]))

    assert "✅ Completed" in get_season_schedule.invoke({"year": 2026})


@pytest.mark.unit
def test_races_are_split_into_completed_and_upcoming(monkeypatch):
    now = _now()
    _install_schedule(
        monkeypatch,
        _schedule(
            [
                pd.Timestamp(now - timedelta(days=30)),
                pd.Timestamp(now - timedelta(days=7)),
                pd.Timestamp(now + timedelta(days=14)),
            ]
        ),
    )

    lines = get_season_schedule.invoke({"year": 2026}).splitlines()
    rows = [line for line in lines if line.startswith(("| 1 |", "| 2 |", "| 3 |"))]

    assert [row.endswith("✅ Completed |") for row in rows] == [True, True, False]
    assert rows[2].endswith("🔜 Upcoming |")


@pytest.mark.unit
def test_the_last_completed_race_is_named_for_the_model(monkeypatch):
    """ "What happened in the last race?" is answered from this line, not inferred."""
    now = _now()
    _install_schedule(
        monkeypatch,
        _schedule(
            [
                pd.Timestamp(now - timedelta(days=30)),
                pd.Timestamp(now - timedelta(days=7)),
                pd.Timestamp(now + timedelta(days=14)),
            ]
        ),
    )

    table = get_season_schedule.invoke({"year": 2026})

    assert table.endswith("**Context:** The last completed race was the **Saudi Arabian Grand Prix**.")


@pytest.mark.unit
def test_a_season_that_has_not_started_reports_no_last_race(monkeypatch):
    future = pd.Timestamp(_now() + timedelta(days=40))
    _install_schedule(monkeypatch, _schedule([future]))

    table = get_season_schedule.invoke({"year": 2027})

    assert table.endswith("**Context:** The last completed race was the **None**.")


@pytest.mark.unit
def test_the_schedule_excludes_pre_season_testing(monkeypatch):
    """Test sessions are not races and would be classified alongside them."""
    calls = _install_schedule(monkeypatch, _schedule([pd.Timestamp(_now() - timedelta(days=1))]))

    get_season_schedule.invoke({"year": 2026})

    assert calls == [{"year": 2026, "include_testing": False}]


@pytest.mark.unit
def test_a_schedule_failure_is_reported_rather_than_raised(monkeypatch):
    _install_schedule(monkeypatch, ConnectionError("ergast unreachable"))

    assert get_season_schedule.invoke({"year": 2026}) == "Failed to fetch schedule: ergast unreachable"
