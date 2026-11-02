"""Tests for app.services.race_control.stakes: what the title hangs on this weekend.

The arithmetic is small but unforgiving: a contender shown as eliminated who can
still win, or a clinch promised that a tie on count-back would undo, is a false
headline. Whether a rival is still in is ``app.data.title_rule``'s call: a tie on
points is decided only when the leader would win the count-back outright.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.data.current_standings import CurrentStandings
from app.data.standings_table import Standing
from app.services.race_control.stakes import (
    CONSTRUCTORS,
    DRIVERS,
    PointsLeft,
    build_championship_stakes,
    points_left,
    table_stakes,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def event(round_num: int, day: int, *, sprint: bool = False, month: int = 11) -> dict:
    sessions = {"Practice 1": f"2026-{month:02d}-{day:02d}T10:00:00Z"}
    if sprint:
        sessions["Sprint"] = f"2026-{month:02d}-{day + 1:02d}T10:00:00Z"
    sessions["Race"] = f"2026-{month:02d}-{day + 2:02d}T14:00:00Z"
    return {"round": round_num, "sessions": sessions, "is_sprint": sprint}


SAO_PAULO = event(20, 6, sprint=True)
SEASON = [
    event(18, 16, month=10),
    event(19, 23, month=10),
    SAO_PAULO,
    event(21, 20),
    event(22, 27, sprint=True),
]


def driver(position: int, name: str, points: float, *, finishes: tuple[int, ...] = ()) -> Standing:
    return Standing(
        key=name[:3].upper(), name=name, team="McLaren", points=points, finishes=finishes, position=position
    )


def team(position: int, name: str, points: float, *, finishes: tuple[int, ...] = ()) -> Standing:
    return Standing(key=name, name=name, team=name, points=points, finishes=finishes, position=position)


# -- points left -----------------------------------------------------------------


def test_points_left_counts_every_race_and_sprint_after_the_standings_round():
    assert points_left(SEASON, SAO_PAULO, 19, NOW) == PointsLeft(races=3, sprints=2, races_here=1, sprints_here=1)


def test_a_race_already_run_still_counts_until_the_standings_include_it():
    """f1db publishes a day or two late; spending the points early would eliminate contenders too soon."""
    after_the_weekend = datetime(2026, 11, 10, tzinfo=UTC)

    assert points_left(SEASON, SAO_PAULO, 19, after_the_weekend) == PointsLeft(
        races=3, sprints=2, races_here=1, sprints_here=1
    )
    assert points_left(SEASON, SAO_PAULO, 20, after_the_weekend) == PointsLeft(
        races=2, sprints=1, races_here=0, sprints_here=0
    )


def test_without_a_standings_round_the_clock_decides_and_a_running_session_counts():
    running = datetime(2026, 11, 8, 15, tzinfo=UTC)

    assert points_left(SEASON, SAO_PAULO, None, running) == PointsLeft(races=3, sprints=1, races_here=1, sprints_here=0)


def test_no_selected_event_has_nothing_here():
    assert points_left(SEASON, None, 19, NOW) == PointsLeft(races=3, sprints=2, races_here=0, sprints_here=0)


# -- one table -------------------------------------------------------------------

LEFT = PointsLeft(races=3, sprints=2, races_here=1, sprints_here=1)  # drivers: 91 left, 33 here, 58 after


def test_contenders_carry_their_gap_and_whether_they_are_still_alive():
    rows = (
        driver(1, "Norris", 400),
        driver(2, "Piastri", 380),
        driver(3, "Verstappen", 309),
        driver(4, "Leclerc", 308),
    )

    stakes = table_stakes(rows, LEFT, DRIVERS)

    assert stakes is not None
    assert (stakes["max_available"], stakes["max_this_weekend"]) == (91, 33)
    assert [(row["name"], row["gap"], row["alive"]) for row in stakes["contenders"]] == [
        ("Norris", 0, True),
        ("Piastri", 20, True),
        ("Verstappen", 91, True),
        ("Leclerc", 92, False),
    ]
    assert stakes["contenders"][0]["code"] == "NOR"
    assert stakes["rivals_alive"] == 2
    assert stakes["decided"] is False


def test_a_lead_that_needs_more_than_a_perfect_weekend_cannot_clinch_here():
    rows = (driver(1, "Norris", 400), driver(2, "Piastri", 380))

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    # After this weekend 58 are left; the lead must exceed that: 20 + x > 58 → x ≥ 39 > 33.
    assert clinch == {"rival": "Piastri", "margin_needed": 39, "possible": False, "rivals_in_play": 1}


def test_a_lead_within_one_weekend_of_safety_can_clinch_here():
    rows = (driver(1, "Norris", 400), driver(2, "Piastri", 350), driver(3, "Russell", 345))

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    assert clinch == {"rival": "Piastri", "margin_needed": 9, "possible": True, "rivals_in_play": 2}


def test_the_margin_to_clinch_here_asks_for_a_lead_past_what_is_left_after_the_weekend():
    """Points alone: a lead that only equals what is left needs this weekend's places to win a count-back."""
    rows = (driver(1, "Norris", 400), driver(2, "Piastri", 342))

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    # Lead 58 equals the 58 left after the weekend: one more point settles it on points.
    assert clinch["margin_needed"] == 1


# A deficit equal to the 91 points left: only a perfect run (3 wins, 2 sprint wins) draws level.


def test_a_rival_who_can_only_draw_level_and_loses_the_count_back_is_out():
    rows = (driver(1, "Norris", 400, finishes=(1, 1, 1, 1, 1, 2)), driver(2, "Piastri", 309, finishes=(1, 1)))

    stakes = table_stakes(rows, LEFT, DRIVERS)

    # Level on 400, Piastri would have 5 wins to Norris's 5, and no second place to his one.
    assert stakes["contenders"][1]["alive"] is False
    assert (stakes["rivals_alive"], stakes["decided"], stakes["clinch"]) == (0, True, None)


def test_a_rival_who_can_draw_level_and_win_the_count_back_is_still_in():
    rows = (driver(1, "Norris", 400, finishes=(1, 1, 1, 2)), driver(2, "Piastri", 309, finishes=(1, 1)))

    stakes = table_stakes(rows, LEFT, DRIVERS)

    assert stakes["contenders"][1]["alive"] is True
    assert (stakes["rivals_alive"], stakes["decided"]) == (1, False)
    # Norris settles it this weekend unless Piastri outscores him by the full 33 a weekend is worth.
    assert stakes["clinch"] == {"rival": "Piastri", "margin_needed": -32, "possible": True, "rivals_in_play": 0}


def test_a_lead_already_beyond_reach_is_decided_with_no_clinch_to_chase():
    rows = (driver(1, "Norris", 500), driver(2, "Piastri", 380))

    stakes = table_stakes(rows, LEFT, DRIVERS)

    assert stakes["decided"] is True
    assert stakes["clinch"] is None
    assert stakes["rivals_alive"] == 0


def test_a_weekend_with_nothing_left_to_run_has_no_clinch():
    rows = (driver(1, "Norris", 400), driver(2, "Piastri", 380))

    stakes = table_stakes(rows, PointsLeft(races=2, sprints=1, races_here=0, sprints_here=0), DRIVERS)

    assert stakes["max_this_weekend"] == 0
    assert stakes["clinch"] is None


def test_constructors_score_with_both_cars():
    rows = (team(1, "McLaren", 700), team(2, "Mercedes", 500))

    stakes = table_stakes(rows, LEFT, CONSTRUCTORS)

    assert (stakes["max_available"], stakes["max_this_weekend"]) == (3 * 43 + 2 * 15, 58)
    assert stakes["contenders"][1] == {
        "position": 2,
        "name": "Mercedes",
        "code": None,
        "team": "Mercedes",
        "points": 500,
        "gap": 200,
        "alive": False,
    }
    assert stakes["decided"] is True


def test_a_lone_entry_has_nobody_to_beat():
    stakes = table_stakes((driver(1, "Norris", 10),), LEFT, DRIVERS)

    assert stakes["decided"] is False
    assert stakes["clinch"] is None
    assert stakes["rivals_alive"] == 0


def test_no_standings_has_no_stakes():
    assert table_stakes((), LEFT, DRIVERS) is None


# -- both tables -----------------------------------------------------------------


SOURCES = ({"source": "f1db", "role": "base", "through_round": 19, "version": "v2026.19.0"},)


def standings(
    drivers: tuple[Standing, ...],
    teams: tuple[Standing, ...],
    *,
    as_of_round: int | None = None,
    provisional: bool = False,
) -> CurrentStandings:
    """The computed table as ``current_standings`` serves it, with f1db as its base once it has a round."""
    return CurrentStandings(
        year=2026,
        drivers=drivers,
        teams=teams,
        as_of_round=as_of_round,
        provisional=provisional,
        sources=SOURCES if as_of_round else (),
    )


def test_the_block_carries_both_tables_and_the_sessions_left():
    table = standings((driver(1, "Norris", 400), driver(2, "Piastri", 380)), (team(1, "McLaren", 780),), as_of_round=19)

    stakes = build_championship_stakes(SEASON, SAO_PAULO, table, now=NOW)

    assert (stakes["as_of_round"], stakes["races_left"], stakes["sprints_left"]) == (19, 3, 2)
    assert stakes["drivers"]["leader"]["name"] == "Norris"
    assert stakes["constructors"]["leader"]["name"] == "McLaren"


def test_the_block_says_which_round_the_table_is_after_and_whether_it_is_provisional():
    table = standings((driver(1, "Norris", 400),), (), as_of_round=20, provisional=True)

    stakes = build_championship_stakes(SEASON, SAO_PAULO, table, now=NOW)

    assert (stakes["as_of_round"], stakes["provisional"], stakes["sources"]) == (20, True, list(SOURCES))
    assert (stakes["races_left"], stakes["sprints_left"]) == (2, 1), "round 20's race and sprint are already counted"


def test_the_clock_defaults_to_now():
    stakes = build_championship_stakes([], None, standings((), ()))

    assert stakes == {
        "as_of_round": None,
        "provisional": False,
        "sources": [],
        "races_left": 0,
        "sprints_left": 0,
        "drivers": None,
        "constructors": None,
    }
