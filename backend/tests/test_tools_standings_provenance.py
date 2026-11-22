"""Tests for app.api.tools.standings_provenance: chips from a table's sources, and the reach chart.

The drivers are the 2026 championship after round 19 (Mexico) as the mockup shows it, with four
Grands Prix and no sprint left: a driver can still score 100 points. The leader (400, added here)
is out of reach, so the fight is for second; Piastri (160) cannot reach it.
"""

from __future__ import annotations

import pytest

from app.api.tools.standings_provenance import standings_provenance
from app.data.current_standings import CurrentStandings
from app.data.standings_table import Standing
from app.data.title_rule import CONSTRUCTORS, DRIVERS, Remaining
from app.services.race_control.table_reach import TableReach

pytestmark = pytest.mark.unit

RACES_LEFT = Remaining(races=4, sprints=0)
DRIVER_POINTS = (
    ("ANT", "Kimi Antonelli", "Mercedes", 400),
    ("VER", "Max Verstappen", "Red Bull", 261),
    ("HAM", "Lewis Hamilton", "Ferrari", 259),
    ("RUS", "George Russell", "Mercedes", 250),
    ("LEC", "Charles Leclerc", "Ferrari", 245),
    ("NOR", "Lando Norris", "McLaren", 221),
    ("PIA", "Oscar Piastri", "McLaren", 160),
)
BASE = {"source": "f1db", "role": "base", "through_round": 19, "version": "v2026.19.0"}


def _standings(points=DRIVER_POINTS, *, provisional=False, sources=(BASE,), as_of_round=19, teams=()):
    rows = tuple(
        Standing(key=key, name=name, team=team, points=pts, position=place)
        for place, (key, name, team, pts) in enumerate(points, start=1)
    )
    return CurrentStandings(
        year=2026, drivers=rows, teams=teams, as_of_round=as_of_round, provisional=provisional, sources=sources
    )


def _drivers(standings, remaining=RACES_LEFT):
    return standings_provenance(standings, TableReach(standings.drivers, DRIVERS, remaining), "drivers")


def test_the_mockup_fight_for_second_is_charted_with_its_basis():
    result = _drivers(_standings())

    assert result.subject == "2026 standings after round 19"
    assert result.sources == ("f1db v2026.19.0 · standings after R19", "4 races left · 100 pts max")
    chart = result.chart
    assert chart.title == "5 drivers can still finish second · points after round 19 → most possible"
    assert [(row.key, row.points, row.max) for row in chart.rows] == [
        ("VER", 261, 361),
        ("HAM", 259, 359),
        ("RUS", 250, 350),
        ("LEC", 245, 345),
        ("NOR", 221, 321),
    ]
    assert chart.rows[0].name == "Max Verstappen"
    assert chart.rows[0].team == "Red Bull"


def test_an_open_title_says_who_can_still_win_it():
    points = (("VER", "Max Verstappen", "Red Bull", 300), ("NOR", "Lando Norris", "McLaren", 250))

    chart = _drivers(_standings(points)).chart

    assert chart.title.startswith("2 drivers can still win the title · points after round 19")


def test_teams_are_counted_as_teams():
    teams = tuple(
        Standing(key=name, name=name, team=name, points=pts, position=place)
        for place, (name, pts) in enumerate((("McLaren", 500), ("Ferrari", 480)), start=1)
    )
    standings = _standings(teams=teams)

    result = standings_provenance(standings, TableReach(teams, CONSTRUCTORS, Remaining(2, 0)), "constructors")

    assert result.chart.title.startswith("2 teams can still win the title")
    assert result.chart.championship == "constructors"


def test_a_provisional_table_says_so_in_its_chart_and_chips():
    sources = (BASE, {"source": "openf1-session-result", "role": "points", "round": 20}, {"role": "cross_check"})

    result = _drivers(_standings(provisional=True, sources=sources, as_of_round=20))

    assert result.sources[:2] == (
        "f1db v2026.19.0 · standings after R19",
        "OpenF1 session results · R20 · provisional",
    )
    assert result.chart.title.endswith("most possible · provisional")


def test_a_place_past_tenth_is_named_by_its_number():
    # Ten rows 200 points apart (out of reach of each other), then two within reach at P11 and P12.
    points = tuple((f"D{n}", f"Driver {n}", "Team", 2400 - 200 * n) for n in range(10))
    points += (("D10", "Driver 10", "Team", 100), ("D11", "Driver 11", "Team", 99))

    assert _drivers(_standings(points)).chart.title.startswith("2 drivers can still finish P11")


def test_no_chart_without_a_calendar():
    result = _drivers(_standings(), remaining=None)

    assert result.chart is None
    assert result.sources == ("f1db v2026.19.0 · standings after R19",)


def test_no_chart_when_nobody_can_pass_anyone():
    points = (("VER", "Max Verstappen", "Red Bull", 900), ("NOR", "Lando Norris", "McLaren", 500))

    assert _drivers(_standings(points)).chart is None


def test_sprints_are_counted_in_the_basis_chip():
    result = _drivers(_standings(), remaining=Remaining(races=2, sprints=1))

    assert result.sources[-1] == "2 races + 1 sprint left · 58 pts max"


def test_a_table_with_no_round_names_only_its_year():
    result = _drivers(_standings(sources=(), as_of_round=None), remaining=None)

    assert result.subject == "2026 standings"
    assert result.sources == ()
