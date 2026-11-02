"""Tests for app.services.race_control.table_reach: what each row of a table can still reach.

Every answer is ``title_rule.can_still_beat`` over the sessions
``stakes.points_left`` counts from the table's round, so a page that asks "can
Red Bull still catch Mercedes?" gets the same answer as the stakes panel.
Without a calendar nothing is known about what is left: the answer is ``None``,
never a guess in either direction.
"""

from __future__ import annotations

import pytest

from app.data.current_standings import CurrentStandings
from app.data.standings_table import Standing
from app.data.title_rule import CONSTRUCTORS, Remaining
from app.services.race_control import table_reach
from app.services.race_control.table_reach import TableReach, constructors_reach, remaining_after

pytestmark = pytest.mark.unit


def event(round_num: int, *, sprint: bool = False) -> dict:
    sessions = {"Practice 1": "2026-12-04T10:00:00Z"}
    if sprint:
        sessions["Sprint"] = "2026-12-05T10:00:00Z"
    sessions["Race"] = "2026-12-06T13:00:00Z"
    return {"round": round_num, "sessions": sessions, "is_sprint": sprint}


# Rounds 18 to 23, with a sprint at round 21.
SEASON = [event(round_num, sprint=round_num == 21) for round_num in range(18, 24)]


def team(name: str, points: float, *, wins: int = 0) -> Standing:
    return Standing(key=name, name=name, team=name, points=points, finishes=(1,) * wins)


# The top of the constructors' table after round 19 (Mexico 2026).
AFTER_MEXICO = (team("Mercedes", 630), team("Ferrari", 504), team("Red Bull", 382), team("McLaren", 365))
FOUR_RACES = Remaining(races=4, sprints=0)


def reach(rows: tuple[Standing, ...], remaining: Remaining | None = FOUR_RACES) -> TableReach:
    return TableReach(rows=rows, scoring=CONSTRUCTORS, remaining=remaining)


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Serve ``SEASON`` as the calendar; returns the years asked for."""
    years: list[int] = []

    def season_events(year: int) -> list[dict]:
        years.append(year)
        return SEASON

    monkeypatch.setattr(table_reach, "season_events", season_events)
    return years


# -- what is left ------------------------------------------------------------------------


def test_what_is_left_counts_from_the_tables_round_not_the_clock(calendar):
    assert remaining_after(2026, 19) == Remaining(races=4, sprints=1)
    assert calendar == [2026]


def test_an_unreadable_calendar_leaves_what_is_left_unknown(monkeypatch: pytest.MonkeyPatch):
    def season_events(_year: int) -> list[dict]:
        raise RuntimeError("schedule unavailable")

    monkeypatch.setattr(table_reach, "season_events", season_events)

    assert remaining_after(2026, 19) is None


def test_an_empty_calendar_is_unknown_not_a_finished_season(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(table_reach, "season_events", lambda _year: [])

    assert remaining_after(2026, 19) is None


def test_the_constructors_reach_reads_the_tables_teams_and_round(calendar):
    standings = CurrentStandings(year=2026, drivers=(), teams=AFTER_MEXICO, as_of_round=19, provisional=True)

    result = constructors_reach(standings)

    assert result == TableReach(rows=AFTER_MEXICO, scoring=CONSTRUCTORS, remaining=Remaining(races=4, sprints=1))
    assert calendar == [2026]


# -- who can still pass whom --------------------------------------------------------------


def test_after_mexico_red_bull_cannot_catch_mercedes_but_ferrari_can():
    """248 and 126 behind with four one-twos (172) left."""
    table = reach(AFTER_MEXICO)

    assert table.points_on_offer == 172
    assert table.leader_points == 630
    assert table.can_pass("Red Bull", "Mercedes") is False
    assert table.can_pass("Ferrari", "Mercedes") is True
    assert table.can_pass("Red Bull", "Ferrari") is True
    assert table.can_pass("McLaren", "Red Bull") is True


def test_the_highest_place_in_reach_skips_the_ones_out_of_reach():
    table = reach(AFTER_MEXICO)

    assert table.highest_in_reach("Red Bull") == (2, AFTER_MEXICO[1])
    assert table.highest_in_reach("Ferrari") == (1, AFTER_MEXICO[0])


def test_no_place_is_in_reach_when_every_team_ahead_is_out_of_reach():
    table = reach(AFTER_MEXICO, Remaining(races=1, sprints=0))

    assert table.highest_in_reach("Red Bull") is None


def test_the_title_is_open_while_one_rival_can_still_finish_ahead():
    assert reach(AFTER_MEXICO).decided() is False


def test_the_title_is_decided_once_no_rival_can_finish_ahead():
    """Mercedes 180 clear of Ferrari with three one-twos (129) left."""
    table = reach((team("Mercedes", 700), team("Ferrari", 520)), Remaining(races=3, sprints=0))

    assert table.decided() is True


def test_a_tie_on_the_last_points_goes_to_the_count_back():
    """Level after a perfect run is decided only when the leader wins the count-back."""
    leader, rival = team("Mercedes", 543, wins=10), team("Ferrari", 500, wins=1)

    assert reach((leader, rival), Remaining(races=1, sprints=0)).decided() is True
    assert reach((team("Mercedes", 543), rival), Remaining(races=1, sprints=0)).decided() is False


def test_a_one_row_table_has_no_title_to_decide():
    assert reach((team("Mercedes", 0),)).decided() is False


def test_without_a_calendar_every_reach_answer_is_unknown():
    table = reach(AFTER_MEXICO, None)

    assert table.points_on_offer is None
    assert table.can_pass("Red Bull", "Mercedes") is None
    assert table.decided() is None
    assert table.highest_in_reach("Red Bull") is None


def test_an_empty_table_has_no_leader_points():
    assert reach(()).leader_points == 0
