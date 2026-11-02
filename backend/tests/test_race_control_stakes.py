"""Tests for app.services.race_control.stakes: what the title hangs on this weekend.

The arithmetic is small but unforgiving: a contender shown as eliminated who can
still win, or a clinch promised that a tie on countback would undo, is a false
headline. Ties are therefore never treated as decided.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.race_control.stakes import (
    CONSTRUCTORS,
    DRIVERS,
    PointsLeft,
    Standings,
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


def driver(position: int, name: str, points: float, team: str = "McLaren") -> dict:
    return {"position": position, "code": name[:3].upper(), "driver": name, "team": team, "points": points}


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
    rows = [
        driver(1, "Norris", 400),
        driver(2, "Piastri", 380),
        driver(3, "Verstappen", 309),
        driver(4, "Leclerc", 308),
    ]

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
    rows = [driver(1, "Norris", 400), driver(2, "Piastri", 380)]

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    # After this weekend 58 are left; the lead must exceed that: 20 + x > 58 → x ≥ 39 > 33.
    assert clinch == {"rival": "Piastri", "margin_needed": 39, "possible": False, "rivals_in_play": 1}


def test_a_lead_within_one_weekend_of_safety_can_clinch_here():
    rows = [driver(1, "Norris", 400), driver(2, "Piastri", 350), driver(3, "Russell", 345)]

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    assert clinch == {"rival": "Piastri", "margin_needed": 9, "possible": True, "rivals_in_play": 2}


def test_a_tie_on_points_is_never_counted_as_a_clinch():
    rows = [driver(1, "Norris", 400), driver(2, "Piastri", 342)]

    clinch = table_stakes(rows, LEFT, DRIVERS)["clinch"]

    # Lead 58 equals the 58 left after the weekend — a tie is not a title.
    assert clinch["margin_needed"] == 1


def test_a_lead_already_beyond_reach_is_decided_with_no_clinch_to_chase():
    rows = [driver(1, "Norris", 500), driver(2, "Piastri", 380)]

    stakes = table_stakes(rows, LEFT, DRIVERS)

    assert stakes["decided"] is True
    assert stakes["clinch"] is None
    assert stakes["rivals_alive"] == 0


def test_a_weekend_with_nothing_left_to_run_has_no_clinch():
    rows = [driver(1, "Norris", 400), driver(2, "Piastri", 380)]

    stakes = table_stakes(rows, PointsLeft(races=2, sprints=1, races_here=0, sprints_here=0), DRIVERS)

    assert stakes["max_this_weekend"] == 0
    assert stakes["clinch"] is None


def test_constructors_score_with_both_cars():
    rows = [
        {"position": 1, "team": "McLaren", "points": 700},
        {"position": 2, "team": "Mercedes", "points": 500},
    ]

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
    stakes = table_stakes([driver(1, "Norris", 10)], LEFT, DRIVERS)

    assert stakes["decided"] is False
    assert stakes["clinch"] is None
    assert stakes["rivals_alive"] == 0


def test_no_standings_has_no_stakes():
    assert table_stakes([], LEFT, DRIVERS) is None


def test_rows_without_a_points_total_are_left_out_rather_than_read_as_zero():
    rows = [{"position": 1, "driver": "Norris"}, {**driver(2, "Piastri", 380), "points": True}]

    assert table_stakes(rows, LEFT, DRIVERS) is None


# -- both tables -----------------------------------------------------------------


def test_the_block_carries_both_tables_and_the_sessions_left():
    drivers = [driver(1, "Norris", 400), driver(2, "Piastri", 380)]
    constructors = [{"position": 1, "team": "McLaren", "points": 780}]

    stakes = build_championship_stakes(SEASON, SAO_PAULO, Standings(drivers, constructors, 19), now=NOW)

    assert (stakes["through_round"], stakes["races_left"], stakes["sprints_left"]) == (19, 3, 2)
    assert stakes["drivers"]["leader"]["name"] == "Norris"
    assert stakes["constructors"]["leader"]["name"] == "McLaren"


def test_the_clock_defaults_to_now():
    stakes = build_championship_stakes([], None, Standings([], [], None))

    assert stakes == {"through_round": None, "races_left": 0, "sprints_left": 0, "drivers": None, "constructors": None}
