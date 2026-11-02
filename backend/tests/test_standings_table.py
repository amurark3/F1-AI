"""Tests for the championship table arithmetic (app.data.standings_table).

A round's points are added to the table as published, and the table is then
re-ordered the way the FIA orders it: points, then a count-back of Grand Prix
finishing places. Carrying the previous order over instead got most 2024–2026
rounds wrong against f1db; the count-back matched every one.
"""

from __future__ import annotations

import pytest

from app.data.standings_table import Score, Standing, Table, add_round, ranked

pytestmark = pytest.mark.unit


def driver(
    code: str, points: float, *, team: str = "Team", finishes: tuple[int, ...] = (), position: int | None = None
):
    return Standing(key=code, name=f"{code} Driver", team=team, points=points, finishes=finishes, position=position)


def team(name: str, points: float, *, finishes: tuple[int, ...] = (), position: int | None = None):
    return Standing(key=name, name=name, team=name, points=points, finishes=finishes, position=position)


def keys(rows: tuple[Standing, ...]) -> list[str]:
    return [row.key for row in rows]


# --- ranked ---------------------------------------------------------------------


def test_more_points_ranks_higher_and_positions_are_numbered_from_one():
    rows = ranked([driver("AAA", 10), driver("BBB", 30), driver("CCC", 20)])

    assert keys(rows) == ["BBB", "CCC", "AAA"]
    assert [row.position for row in rows] == [1, 2, 3]


def test_a_tie_on_points_goes_to_more_wins():
    rows = ranked([driver("AAA", 25, finishes=(2, 2)), driver("BBB", 25, finishes=(1, 9))])

    assert keys(rows) == ["BBB", "AAA"]


def test_level_wins_go_to_more_second_places_and_so_on_down():
    rows = ranked([driver("AAA", 4, finishes=(8, 11)), driver("BBB", 4, finishes=(8, 10))])

    assert keys(rows) == ["BBB", "AAA"]


def test_a_level_count_back_keeps_the_previous_order():
    rows = ranked([driver("AAA", 0, finishes=(12,), position=2), driver("BBB", 0, finishes=(12,), position=1)])

    assert keys(rows) == ["BBB", "AAA"]


def test_a_newcomer_level_on_everything_goes_after_ranked_rows_then_by_key():
    rows = ranked([driver("ZZZ", 0), driver("NEW", 0, position=None), driver("OLD", 0, position=5)])

    assert keys(rows) == ["OLD", "NEW", "ZZZ"]


def test_wins_are_the_grand_prix_firsts():
    assert driver("AAA", 50, finishes=(1, 3, 1)).wins == 2
    assert driver("BBB", 0).wins == 0


# --- add_round ------------------------------------------------------------------


def test_a_round_adds_each_cars_points_to_its_driver_and_team():
    table = Table(
        drivers=(driver("AAA", 30, team="Red", position=1), driver("BBB", 20, team="Blue", position=2)),
        teams=(team("Red", 30, position=1), team("Blue", 20, position=2)),
    )

    after = add_round(
        table,
        [
            Score(code="BBB", name="BBB Driver", team="Blue", points=25, finish=1),
            Score(code="AAA", name="AAA Driver", team="Red", points=0, finish=None),
        ],
    )

    assert [(row.key, row.points, row.position, row.wins) for row in after.drivers] == [
        ("BBB", 45, 1, 1),
        ("AAA", 30, 2, 0),
    ]
    assert [(row.key, row.points, row.position) for row in after.teams] == [("Blue", 45, 1), ("Red", 30, 2)]


def test_a_round_never_changes_the_table_it_was_given():
    table = Table(drivers=(driver("AAA", 30, position=1),), teams=(team("Team", 30, position=1),))

    add_round(table, [Score(code="AAA", name="AAA Driver", team="Team", points=25, finish=1)])

    assert table.drivers[0].points == 30
    assert table.teams[0].finishes == ()


def test_a_sprint_scores_points_but_no_finish_for_the_count_back():
    table = Table(drivers=(driver("AAA", 0, position=1),), teams=(team("Team", 0, position=1),))

    after = add_round(table, [Score(code="AAA", name="AAA Driver", team="Team", points=8, finish=None)])

    assert after.drivers[0].points == 8
    assert after.drivers[0].finishes == ()


def test_a_stand_in_joins_the_table_and_scores_for_the_team_whose_car_they_drove():
    """Hirakawa raced Ocon's Haas in Mexico 2026 and scored a point for 10th."""
    table = Table(
        drivers=(driver("OCO", 7, team="Haas", position=1),),
        teams=(team("Haas", 30, position=1),),
    )

    after = add_round(table, [Score(code="HIR", name="Ryo Hirakawa", team="Haas", points=1, finish=10)])

    by_key = {row.key: row for row in after.drivers}
    assert (by_key["HIR"].name, by_key["HIR"].team, by_key["HIR"].points) == ("Ryo Hirakawa", "Haas", 1)
    assert by_key["OCO"].points == 7
    assert after.teams[0].points == 31
    assert after.teams[0].finishes == (10,)


def test_a_driver_who_changed_teams_is_listed_under_the_team_of_their_latest_round():
    table = Table(drivers=(driver("LAW", 10, team="Racing Bulls", position=1),), teams=())

    after = add_round(table, [Score(code="LAW", name="LAW Driver", team="Red Bull", points=2, finish=9)])

    assert after.drivers[0].team == "Red Bull"
    assert [(row.key, row.points) for row in after.teams] == [("Red Bull", 2)]
