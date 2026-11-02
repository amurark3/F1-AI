"""Every standings consumer serves the computed table: f1db's last round plus later rounds' points.

The morning after Mexico 2026, f1db still held round 18 while OpenF1 had round
19. A page that read f1db's table there showed the previous round: the stakes
panel counted Mexico's points as still on offer and measured every rival
against Antonelli's 365 instead of his 380. Each consumer below is read on that
morning's data (``tests/standings_support.mexico_feeds``) and must serve the
table after round 19, marked provisional, with its sources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.data.profiles import driver_season, team_season
from app.services import race_control_championship as championship
from app.services.profiles import build_directory
from app.services.race_control import overview, strategy_context
from app.services.race_control_standings import build_intel
from tests.standings_support import Feeds, mexico_feeds

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

AFTER_ROUND_19 = {"as_of_round": 19, "provisional": True}
BASE_AND_ROUND_19 = [
    {"source": "f1db", "role": "base", "through_round": 18, "version": "v2026.18.0"},
    {"source": "openf1-session-result", "role": "points", "round": 19, "sessions": ["R"]},
]
RACE_DAYS = {
    18: "2026-10-25T20:00:00Z",
    19: "2026-11-01T20:00:00Z",
    20: "2026-11-08T17:00:00Z",
    21: "2026-11-22T04:00:00Z",
    22: "2026-11-29T16:00:00Z",
    23: "2026-12-06T13:00:00Z",
}


def event(round_num: int) -> dict:
    """A calendar entry as ``season_events`` builds it; rounds after Mexico are still to run."""
    upcoming = round_num > 19
    return {
        "round": round_num,
        "name": f"Round {round_num} Grand Prix",
        "location": f"Venue {round_num}, Country",
        "country": "Country",
        "status": "upcoming" if upcoming else "completed",
        "date": RACE_DAYS[round_num][:10],
        "sessions": {"Race": RACE_DAYS[round_num]},
        "is_sprint": False,
        "days_until": 6 if upcoming else None,
        "circuit": None,
        "race_session": RACE_DAYS[round_num],
    }


# Four Grands Prix and no sprint after Mexico: 100 points for a driver, 172 for a team.
SEASON = [event(round_num) for round_num in RACE_DAYS]


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    for module in (overview, strategy_context):
        monkeypatch.setattr(module, "season_events", lambda _year: SEASON)
    yield from mexico_feeds(tmp_path, monkeypatch)


def freshness(payload: dict) -> dict:
    return {"as_of_round": payload["as_of_round"], "provisional": payload["provisional"]}


def contenders(table: dict) -> list[tuple]:
    return [(row["code"] or row["name"], row["points"], row["gap"], row["alive"]) for row in table["contenders"]]


# --- the overview shell: stakes and the championship block --------------------------


def test_the_stakes_count_from_round_19_and_measure_every_rival_against_380(feeds):
    stakes = overview.build_overview_shell(2026)["stakes"]

    assert freshness(stakes) == AFTER_ROUND_19
    assert stakes["sources"][:2] == BASE_AND_ROUND_19
    assert (stakes["races_left"], stakes["sprints_left"]) == (4, 0)
    drivers = stakes["drivers"]
    assert drivers["max_available"] == 100
    # Nobody can reach 380 with 100 points left: Hamilton and Russell cannot catch him.
    assert contenders(drivers)[:4] == [
        ("ANT", 380, 0, True),
        ("VER", 261, 119, False),
        ("HAM", 259, 121, False),
        ("RUS", 250, 130, False),
    ]
    assert drivers["rivals_alive"] == 0


def test_the_constructors_stakes_read_the_computed_table_too(feeds):
    teams = overview.build_overview_shell(2026)["stakes"]["constructors"]

    assert teams["max_available"] == 172
    assert contenders(teams)[:4] == [
        ("Mercedes", 630, 0, True),
        ("Ferrari", 504, 126, True),
        ("Red Bull", 382, 248, False),
        ("McLaren", 365, 265, False),
    ]


def test_the_championship_block_is_the_top_five_after_round_19(feeds):
    championship_block = overview.build_overview_shell(2026)["championship"]

    assert [(row["code"], row["points"]) for row in championship_block["drivers"]] == [
        ("ANT", 380),
        ("VER", 261),
        ("HAM", 259),
        ("RUS", 250),
        ("LEC", 245),
    ]
    assert championship_block["constructors"][2] == {"position": 3, "team": "Red Bull", "points": 382, "wins": 3}
    assert freshness(championship_block) == AFTER_ROUND_19
    assert championship_block["sources"][:2] == BASE_AND_ROUND_19


# --- the overview's strategy segment: the competitors it ranks ----------------------


def test_the_strategy_segment_ranks_rivals_from_the_computed_table(feeds, monkeypatch):
    monkeypatch.setattr(overview, "get_cached_race_prediction", lambda _year, _round: None)
    monkeypatch.setattr(overview, "circuit_strategy_reference", lambda _location, _year: None)

    competitors = overview.build_overview_strategy(2026)["strategy_context"]["competitors"]

    assert [(row["team"], row["points"], row["gap_to_leader"]) for row in competitors] == [
        ("Mercedes", 630, 0),
        ("Ferrari", 504, 126),
        ("Red Bull", 382, 248),
        ("McLaren", 365, 265),
        ("Racing Bulls", 108, 522),
    ]


# --- build_intel ----------------------------------------------------------------------


def test_intel_reads_red_bull_382_and_its_neighbours_after_round_19(feeds):
    intel = build_intel("red-bull", 2026)

    assert intel["status"] == "ok"
    assert freshness(intel) == AFTER_ROUND_19
    assert intel["sources"][:2] == BASE_AND_ROUND_19
    assert intel["source"] == "computed-standings"
    assert intel["team"]["standing_profile"]["points"] == 382
    # Points per GP over the 19 rounds the table covers.
    assert intel["team"]["standing_profile"]["pts per GP"] == 20.1
    assert intel["upgrade_watch"][0] == "WCC P3 with 382 points."
    assert "Next target ahead: Ferrari by 122 points." in intel["upgrade_watch"]
    assert "Nearest pressure behind: McLaren by 17 points." in intel["upgrade_watch"]
    assert ("VER", 261) in [(row["code"], row["points"]) for row in intel["drivers"]]


def test_intel_for_an_unknown_team_still_says_how_fresh_its_table_is(feeds):
    intel = build_intel("brabham", 2026)

    assert intel["status"] == "team_not_found"
    assert freshness(intel) == AFTER_ROUND_19
    assert {"slug": "red-bull", "name": "Red Bull"} in intel["available_teams"]


# --- the championship forecast --------------------------------------------------------


def test_the_forecast_projects_from_the_computed_table(feeds, monkeypatch):
    monkeypatch.setattr(championship, "completed_race_rounds", lambda _year: (list(range(1, 20)), 23))
    monkeypatch.setattr(championship, "load_race_classification", lambda _year, _round: {"race_results": []})

    forecast = championship.build_championship_forecast(2026)

    assert freshness(forecast) == AFTER_ROUND_19
    assert forecast["sources"][:2] == BASE_AND_ROUND_19
    current = {row["key"]: row["current_points"] for row in forecast["drivers"]}
    assert (current["ANT"], current["VER"]) == (380, 261)
    assert {row["key"]: row["current_points"] for row in forecast["constructors"]}["Red Bull"] == 382


# --- profiles: team and driver pages, and the directory behind their links ------------


def test_the_team_page_shows_red_bull_382_after_round_19(feeds):
    profile = team_season(2026, "red-bull")

    assert (profile["team"]["position"], profile["team"]["points"]) == (3, 382)
    verstappen = next(row for row in profile["drivers"] if row["id"] == "max-verstappen")
    assert (verstappen["position"], verstappen["points"]) == (2, 261)
    assert freshness(profile) == AFTER_ROUND_19
    assert profile["sources"][:2] == BASE_AND_ROUND_19


def test_the_driver_page_shows_antonelli_380_after_round_19(feeds):
    profile = driver_season(2026, "kimi-antonelli")

    assert profile["standing"] == {"position": 1, "points": 380}
    assert freshness(profile) == AFTER_ROUND_19
    assert profile["sources"][:2] == BASE_AND_ROUND_19


def test_the_directory_orders_teams_by_the_table_after_round_19(feeds):
    directory = build_directory(2026)

    assert [(team["id"], team["position"], team["points"]) for team in directory["teams"][:4]] == [
        ("mercedes", 1, 630),
        ("ferrari", 2, 504),
        ("red-bull", 3, 382),
        ("mclaren", 4, 365),
    ]
    assert freshness(directory) == AFTER_ROUND_19
    assert directory["sources"][:2] == BASE_AND_ROUND_19


def test_once_f1db_holds_round_19_the_pages_read_it_by_id_as_confirmed(feeds):
    """With nothing past f1db the page reads f1db's own table by id, labelled confirmed."""
    feeds.weekends.clear()

    profile = driver_season(2026, "kimi-antonelli")

    assert profile["standing"] == {"position": 1, "points": 365}
    assert freshness(profile) == {"as_of_round": 18, "provisional": False}
