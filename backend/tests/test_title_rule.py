"""Tests for the title rule (app.data.title_rule): can a rival still beat the leader?

Every title read on the site comes from this one rule, so an error here is a
false headline everywhere at once: a champion still "under pressure", or a
rival shown as out who can still win. The edge is the tie: a deficit exactly
equal to the points left is only bridged by the rival scoring the maximum
everywhere while the leader scores nothing, and the count-back then decides.
"""

from __future__ import annotations

import pytest

from app.data.standings_table import Standing
from app.data.title_rule import CONSTRUCTORS, DRIVERS, Remaining, can_still_beat, max_points

pytestmark = pytest.mark.unit

AFTER_MEXICO = Remaining(races=4, sprints=0)


def entrant(key: str, points: float, finishes: tuple[int, ...] = ()) -> Standing:
    return Standing(key=key, name=key, team=key, points=points, finishes=finishes)


# -- the most a driver or a team can still score -----------------------------------


def test_a_driver_can_score_a_win_in_every_race_and_sprint_left():
    assert max_points(AFTER_MEXICO, DRIVERS) == 100
    assert max_points(Remaining(races=3, sprints=2), DRIVERS) == 3 * 25 + 2 * 8


def test_a_team_can_score_a_one_two_in_every_race_and_sprint_left():
    """25 + 18 a Grand Prix and 8 + 7 a sprint: both cars on the top two steps."""
    assert max_points(AFTER_MEXICO, CONSTRUCTORS) == 172
    assert max_points(Remaining(races=3, sprints=2), CONSTRUCTORS) == 3 * 43 + 2 * 15


# -- after Mexico 2026 ----------------------------------------------------------------


def test_after_mexico_no_driver_can_catch_antonelli():
    antonelli = entrant("ANT", 380)

    assert not can_still_beat(antonelli, entrant("VER", 261), AFTER_MEXICO, DRIVERS)
    assert not can_still_beat(antonelli, entrant("HAM", 259), AFTER_MEXICO, DRIVERS)


def test_after_mexico_ferrari_can_still_catch_mercedes():
    assert can_still_beat(entrant("Mercedes", 630), entrant("Ferrari", 504), AFTER_MEXICO, CONSTRUCTORS)
    assert not can_still_beat(entrant("Mercedes", 630), entrant("Red Bull", 382), AFTER_MEXICO, CONSTRUCTORS)


def test_a_deficit_one_point_inside_what_is_left_is_still_alive():
    assert can_still_beat(entrant("A", 200), entrant("B", 101), AFTER_MEXICO, DRIVERS)
    assert not can_still_beat(entrant("A", 200), entrant("B", 99), AFTER_MEXICO, DRIVERS)


# -- a deficit equal to what is left: the count-back decides --------------------------

TWO_RACES = Remaining(races=2, sprints=0)  # 50 points for a driver


def test_level_on_points_the_rival_needs_more_wins_than_two_more_can_give():
    """Winning both races gives the rival 3 wins; the leader has 3 and a second place."""
    leader = entrant("A", 100, (1, 1, 1, 2))
    rival = entrant("B", 50, (1,))

    assert not can_still_beat(leader, rival, TWO_RACES, DRIVERS)


def test_level_on_points_the_rival_with_more_wins_takes_the_title():
    leader = entrant("A", 100, (1, 1, 2, 2))
    rival = entrant("B", 50, (1,))

    assert can_still_beat(leader, rival, TWO_RACES, DRIVERS)


def test_a_count_back_level_all_the_way_down_is_the_fia_s_call_so_the_rival_stays_in():
    leader = entrant("A", 100, (1, 1, 1, 4))
    rival = entrant("B", 50, (1, 4))

    assert can_still_beat(leader, rival, TWO_RACES, DRIVERS)


def test_sprint_places_take_no_part_in_the_count_back():
    """A rival who ties by winning the last sprint gains no Grand Prix place from it."""
    one_sprint = Remaining(races=0, sprints=1)

    assert not can_still_beat(entrant("A", 100, (1,)), entrant("B", 92, ()), one_sprint, DRIVERS)
    assert can_still_beat(entrant("A", 100, ()), entrant("B", 92, (1,)), one_sprint, DRIVERS)


def test_a_team_level_on_points_has_taken_a_win_and_a_second_in_every_race():
    """Counted as a win only, the rival would lose on seconds (1 to 2); the one-two makes it level."""
    leader = entrant("Mercedes", 143, (1, 2, 2))
    rival = entrant("Ferrari", 100, (2,))

    assert can_still_beat(leader, rival, Remaining(races=1, sprints=0), CONSTRUCTORS)


def test_with_nothing_left_a_tie_on_points_is_settled_by_the_count_back_already_held():
    season_over = Remaining(races=0, sprints=0)

    assert not can_still_beat(entrant("A", 300, (1, 1)), entrant("B", 300, (1,)), season_over, DRIVERS)
    assert can_still_beat(entrant("A", 300, (1,)), entrant("B", 300, (1,)), season_over, DRIVERS)
