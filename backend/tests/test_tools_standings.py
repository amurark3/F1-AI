"""Tests for app.api.tools.standings — championship tables and the calendar.

Two standings tools that read the computed table (``current_standings``), plus
the season schedule. The risks are freshness-, rule- and date-shaped:

* **A table without its round reads as current.** Each result says the round
  it runs to and whether f1db has confirmed it, so the assistant never quotes a
  provisional total as final, or a stale one as current.
* **The assistant doing its own title arithmetic.** Each result states the
  title state from the shared rule (decided for whom, or who can still finish
  ahead of the leader), and claims nothing when the calendar is unreadable.
* **A race's date decides Completed vs Upcoming.** FastF1 hands back a tz-naive
  ``EventDate``; comparing it against a tz-aware now raises, and the raise is
  swallowed by the tool's own except clause, so the whole calendar degrades to
  an error string with nothing pointing at the cause.

The R19 morning-after-Mexico reads are in ``test_standings_readers.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.api.tools import standings as standings_module
from app.api.tools.standings import (
    get_constructor_standings,
    get_driver_standings,
    get_season_schedule,
)
from app.data.title_rule import CONSTRUCTORS, DRIVERS, Remaining
from app.services.race_control.table_reach import TableReach
from tests.standings_support import standings_from_rows

# Two Grands Prix and a sprint: 58 points for a driver, 101 for a team.
LEFT = Remaining(races=2, sprints=1)
CONFIRMED_R22 = {"as_of_round": 22, "provisional": False}


def _serve(monkeypatch: pytest.MonkeyPatch, drivers: list[dict], teams: list[dict], **freshness) -> None:
    """Serve a fixed table, and read its reach with ``LEFT`` still to score (no calendar)."""
    standings = standings_from_rows(drivers, teams, **(freshness or CONFIRMED_R22))
    monkeypatch.setattr(standings_module, "current_standings", lambda _year: standings)
    monkeypatch.setattr(
        standings_module, "drivers_reach", lambda table: TableReach(table.drivers, DRIVERS, remaining=LEFT)
    )
    monkeypatch.setattr(
        standings_module,
        "constructors_reach",
        lambda table: TableReach(table.teams, CONSTRUCTORS, remaining=LEFT),
    )


def _boom(_year: int) -> None:
    raise RuntimeError("f1db is locked")


# ---------------------------------------------------------------------------
# get_driver_standings
# ---------------------------------------------------------------------------


def _drivers() -> list[dict]:
    return [
        {"position": 1, "code": "VER", "driver": "Max Verstappen", "team": "Red Bull", "points": 393.0, "wins": 9},
        {"position": 2, "code": "NOR", "driver": "Lando Norris", "team": "McLaren", "points": 331.5, "wins": 4},
    ]


@pytest.mark.unit
def test_driver_standings_sit_between_their_freshness_and_the_title_state(monkeypatch):
    _serve(monkeypatch, _drivers(), [])

    table = get_driver_standings.invoke({"year": 2026})

    assert table.splitlines() == [
        "### Driver Standings (2026)",
        "After round 22 · confirmed: f1db's published table.",
        "",
        "| Pos | Driver | Team | Points | Wins |",
        "| :-- | :----- | :--- | :----- | :--- |",
        # ":g" drops the trailing zero on a whole-number total but keeps a half point.
        "| 1 | VER | Red Bull | 393 | 9 |",
        "| 2 | NOR | McLaren | 331.5 | 4 |",
        "",
        # 61.5 ahead with 58 left (two wins and a sprint win): out of reach.
        "**Drivers' title:** decided for Max Verstappen (VER). Leader: 393 points, 61.5 ahead of Lando Norris "
        "(NOR), with at most 58 points left for one entrant (2 Grands Prix, 1 sprint): no rival can still "
        "finish ahead.",
    ]


@pytest.mark.unit
def test_a_season_f1db_holds_none_of_is_provisional_on_openf1_alone(monkeypatch):
    sources = tuple(
        {"source": "openf1-session-result", "role": "points", "round": rnd, "sessions": ["R"]} for rnd in (1, 2)
    )
    _serve(monkeypatch, _drivers(), [], as_of_round=2, provisional=True, sources=sources)

    assert get_driver_standings.invoke({"year": 2027}).splitlines()[1] == (
        "After round 2 · provisional: OpenF1's results for rounds 1, 2 (f1db holds none of this season yet). "
        "f1db has not confirmed round 2 yet, so post-race penalties can still change it."
    )


@pytest.mark.unit
def test_a_season_with_no_driver_table_is_reported_as_missing(monkeypatch):
    _serve(monkeypatch, [], [])

    assert get_driver_standings.invoke({"year": 1949}) == "No driver standings found for 1949."


@pytest.mark.unit
def test_a_driver_standings_failure_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(standings_module, "current_standings", _boom)

    assert get_driver_standings.invoke({"year": 2026}) == "Failed to fetch driver standings: f1db is locked"


# ---------------------------------------------------------------------------
# get_constructor_standings
# ---------------------------------------------------------------------------


def _teams() -> list[dict]:
    return [
        {"position": 1, "team": "McLaren", "points": 666.0, "wins": 12},
        {"position": 2, "team": "Ferrari", "points": 652.5, "wins": 6},
        {"position": 3, "team": "Mercedes", "points": 500.0, "wins": 2},
    ]


@pytest.mark.unit
def test_constructor_standings_name_every_team_still_able_to_finish_ahead(monkeypatch):
    _serve(monkeypatch, [], _teams())

    table = get_constructor_standings.invoke({"year": 2026})

    assert table.splitlines() == [
        "### Constructor Standings (2026)",
        "After round 22 · confirmed: f1db's published table.",
        "",
        "| Pos | Team | Points | Wins |",
        "| :-- | :--- | :----- | :--- |",
        "| 1 | McLaren | 666 | 12 |",
        "| 2 | Ferrari | 652.5 | 6 |",
        "| 3 | Mercedes | 500 | 2 |",
        "",
        # A team can score 101 (two one-twos and a sprint one-two): Ferrari 13.5 behind can, Mercedes 166 cannot.
        "**Constructors' title:** still open. Leader: McLaren, 666 points, with at most 101 points left for one "
        "entrant (2 Grands Prix, 1 sprint). Only these can still finish ahead of McLaren: Ferrari (652.5 points, "
        "13.5 behind).",
    ]


@pytest.mark.unit
def test_a_season_with_no_constructor_data_is_reported_as_missing(monkeypatch):
    _serve(monkeypatch, _drivers(), [])

    assert get_constructor_standings.invoke({"year": 1949}) == "No constructor standings found for 1949."


@pytest.mark.unit
def test_a_constructor_standings_failure_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(standings_module, "current_standings", _boom)

    assert get_constructor_standings.invoke({"year": 2026}) == "Failed to fetch constructor standings: f1db is locked"


# ---------------------------------------------------------------------------
# get_season_schedule
# ---------------------------------------------------------------------------


def _schedule(dates: list[pd.Timestamp], formats: list[str] | None = None) -> pd.DataFrame:
    names = ["Bahrain Grand Prix", "Saudi Arabian Grand Prix", "Australian Grand Prix"]
    event_formats = formats or ["conventional"] * len(dates)
    return pd.DataFrame(
        [
            {
                "RoundNumber": index + 1,
                "EventName": names[index],
                "EventDate": date,
                "EventFormat": event_formats[index],
            }
            for index, date in enumerate(dates)
        ]
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
    return datetime.now(UTC).replace(tzinfo=None)


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
def test_sprint_weekends_are_flagged_for_the_model(monkeypatch):
    """Without the flag the model cannot tell which rounds had a sprint.

    Asked "who won the sprint and the race on sprint weekends", it reached for a
    web search the request had not offered, and Groq refused the whole turn.
    FastF1 has spelled the sprint format three ways since 2021; all of them count.
    """
    now = _now()
    _install_schedule(
        monkeypatch,
        _schedule(
            [pd.Timestamp(now - timedelta(days=d)) for d in (30, 20, 10)],
            formats=["sprint_qualifying", "conventional", "sprint_shootout"],
        ),
    )

    lines = get_season_schedule.invoke({"year": 2026}).splitlines()
    rows = [line for line in lines if line.startswith(("| 1 |", "| 2 |", "| 3 |"))]

    assert "| Round | Grand Prix | Date | Format | Status |" in lines
    assert ["| Sprint |" in row for row in rows] == [True, False, True]
    assert "| Standard |" in rows[1]


@pytest.mark.unit
def test_the_2021_sprint_format_name_is_also_flagged(monkeypatch):
    _install_schedule(monkeypatch, _schedule([pd.Timestamp(_now() - timedelta(days=5))], formats=["sprint"]))

    assert "| Sprint |" in get_season_schedule.invoke({"year": 2021})


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
