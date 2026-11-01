"""Tests for app.data.profiles — team and driver seasons read from f1db.

The dataset (tests/profiles_support.py) carries a mid-season seat swap, a
reserve, an unclassified DNF, a DNS and a classified retirement, a sprint
weekend, a team with no result yet, and a round still to run. Each property
below is one the pages rely on to tell the truth about a season.
"""

from __future__ import annotations

import pytest

from app.data.profiles import driver_season, team_season
from app.data.profiles.circuit_history import previous_edition
from app.data.profiles.results import rounds_label


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rounds", "expected"),
    [
        ([], ""),
        ([12], "R12"),
        ([12, 13, 14], "R12–14"),
        ([10, 9, 1, 2, 3, 7, 3], "R1–3, R7, R9–10"),
    ],
    ids=["none", "single", "span", "unsorted-with-duplicates"],
)
def test_rounds_label_compresses_rounds_into_spans(rounds, expected):
    assert rounds_label(rounds) == expected


# ---------------------------------------------------------------------------
# team_season
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_team_headline_takes_points_from_the_championship_table(profiles_f1db):
    team = team_season(2026, "red-bull")["team"]

    assert team == {
        "id": "red-bull",
        "name": "Red Bull",
        "full_name": "Red Bull Racing",
        "color": "#3671C6",
        "position": 1,
        "points": 128.0,
        "wins": 2,
        # R1 VER, R2 VER and LAW, R3 HAD and VER — sprints do not count.
        "podiums": 5,
        "poles": 1,
    }


@pytest.mark.integration
def test_current_line_up_is_who_started_the_latest_race(profiles_f1db):
    drivers = team_season(2026, "red-bull")["drivers"]

    assert [(item["id"], item["current"]) for item in drivers] == [
        ("max-verstappen", True),
        ("isack-hadjar", True),
        ("liam-lawson", False),
    ]


@pytest.mark.integration
def test_a_stand_in_is_listed_with_the_rounds_they_raced(profiles_f1db):
    lawson = team_season(2026, "red-bull")["drivers"][2]

    assert lawson == {
        "id": "liam-lawson",
        "name": "Liam Lawson",
        "code": "LAW",
        "number": 30,
        "current": False,
        "rounds": [2],
        "rounds_label": "R2",
        "position": 5,
        "points": 22.0,
        "wins": 0,
    }


@pytest.mark.integration
def test_a_reserve_never_appears_in_the_line_up(profiles_f1db):
    ids = {item["id"] for item in team_season(2026, "red-bull")["drivers"]}

    assert "ayumu-iwasa" not in ids


@pytest.mark.integration
def test_team_wins_name_the_round_and_winner(profiles_f1db):
    wins = team_season(2026, "red-bull")["wins"]

    assert wins == [
        {
            "round": 1,
            "name": "Australian Grand Prix",
            "short_name": "Australian GP",
            "driver_id": "max-verstappen",
            "grid": 1,
        },
        # No short name in f1db, so the full one is used.
        {
            "round": 3,
            "name": "Italian Grand Prix",
            "short_name": "Italian Grand Prix",
            "driver_id": "isack-hadjar",
            "grid": 5,
        },
    ]


@pytest.mark.integration
def test_team_rounds_sum_race_and_sprint_points_and_run_a_cumulative_total(profiles_f1db):
    rounds = team_season(2026, "red-bull")["rounds"]

    assert [(item["round"], item["status"], item["points"], item["cumulative_points"]) for item in rounds] == [
        (1, "complete", 25.0, 25.0),
        (2, "complete", 48.0, 73.0),
        (3, "complete", 40.0, 113.0),
        (4, "pending", 0, None),
    ]
    assert rounds[3]["results"] == []


@pytest.mark.integration
def test_team_round_pairs_each_drivers_race_and_sprint(profiles_f1db):
    second = team_season(2026, "red-bull")["rounds"][1]
    by_driver = {item["driver_id"]: item for item in second["results"]}

    assert set(by_driver) == {"max-verstappen", "liam-lawson"}
    assert by_driver["liam-lawson"]["race"]["position"] == 3
    assert by_driver["liam-lawson"]["sprint"] == {
        "number": 30,
        "position": 2,
        "position_text": "2",
        "grid": 3,
        "points": 7.0,
        "positions_gained": 1,
        "reason_retired": None,
        "fastest_lap": False,
        "pole": False,
    }


@pytest.mark.integration
def test_an_unclassified_retirement_keeps_its_text_and_reason(profiles_f1db):
    first = team_season(2026, "red-bull")["rounds"][0]
    hadjar = next(item for item in first["results"] if item["driver_id"] == "isack-hadjar")

    assert hadjar["race"]["position"] is None
    assert hadjar["race"]["position_text"] == "DNF"
    assert hadjar["race"]["reason_retired"] == "Engine"
    assert hadjar["race"]["points"] == 0.0
    assert hadjar["sprint"] is None


@pytest.mark.integration
def test_team_results_run_through_the_latest_published_race(profiles_f1db):
    assert team_season(2026, "red-bull")["results_through"] == {"round": 3, "name": "Italian Grand Prix"}


@pytest.mark.integration
def test_a_team_with_no_result_yet_lists_its_entrants_as_current(profiles_f1db):
    season = team_season(2026, "cadillac")

    assert season["team"]["full_name"] == "Cadillac"
    assert season["team"]["position"] is None
    assert season["team"]["points"] == 0
    assert season["drivers"] == [
        {
            "id": "sergio-perez",
            "name": "Sergio Pérez",
            "code": "PER",
            "number": 11,
            "current": True,
            "rounds": [],
            "rounds_label": "",
            "position": None,
            "points": 0.0,
            "wins": 0,
        }
    ]
    assert season["wins"] == []


@pytest.mark.integration
def test_a_season_with_no_races_has_no_freshness_line(profiles_f1db):
    season = team_season(2027, "red-bull")

    assert season["rounds"] == []
    assert season["results_through"] is None
    assert [item["id"] for item in season["drivers"]] == ["max-verstappen"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "team_id"),
    [(2026, "brawn"), (2027, "ferrari")],
    ids=["unknown-team", "not-entered-that-year"],
)
def test_team_season_is_none_for_a_team_not_entered(profiles_f1db, year, team_id):
    assert team_season(year, team_id) is None


# ---------------------------------------------------------------------------
# driver_season
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_driver_header_uses_the_latest_race_number_and_team(profiles_f1db):
    season = driver_season(2026, "isack-hadjar")

    assert season["driver"] == {
        "id": "isack-hadjar",
        "name": "Isack Hadjar",
        "code": "HAD",
        "number": 6,
        "nationality": "France",
        "team_id": "red-bull",
        "team_name": "Red Bull",
        "color": "#3671C6",
    }
    assert season["standing"] == {"position": 4, "points": 25.0}


@pytest.mark.integration
def test_a_round_the_driver_sat_out_stays_in_the_list_with_no_result(profiles_f1db):
    rounds = driver_season(2026, "isack-hadjar")["rounds"]

    assert [(item["round"], item["status"], item["team_id"]) for item in rounds] == [
        (1, "complete", "red-bull"),
        (2, "complete", None),
        (3, "complete", "red-bull"),
        (4, "pending", None),
    ]
    assert rounds[1]["race"] is None
    assert rounds[1]["sprint"] is None
    assert rounds[2]["race"]["positions_gained"] == 4


@pytest.mark.integration
def test_driver_teams_list_the_rounds_raced_for_each(profiles_f1db):
    assert driver_season(2026, "isack-hadjar")["teams"] == [
        {"id": "red-bull", "name": "Red Bull", "color": "#3671C6", "rounds": [1, 3], "rounds_label": "R1, R3"}
    ]


@pytest.mark.integration
def test_driver_stats_count_wins_podiums_poles_and_retirements(profiles_f1db):
    assert driver_season(2026, "max-verstappen")["stats"] == {
        "starts": 3,
        "wins": 1,
        "podiums": 3,
        "poles": 1,
        "fastest_laps": 2,
        "retirements": 0,
        "best_finish": 1,
    }


@pytest.mark.integration
def test_not_starting_is_neither_a_start_nor_a_retirement(profiles_f1db):
    """Hamilton: DNS at R2 (with a reason), classified retirement at R3."""
    season = driver_season(2026, "lewis-hamilton")

    assert season["stats"]["starts"] == 2
    assert season["stats"]["retirements"] == 1
    assert season["stats"]["best_finish"] == 3
    assert season["driver"]["nationality"] is None


@pytest.mark.integration
def test_driver_wins_list_each_round_won(profiles_f1db):
    assert driver_season(2026, "isack-hadjar")["wins"] == [
        {"round": 3, "name": "Italian Grand Prix", "short_name": "Italian Grand Prix"}
    ]


@pytest.mark.integration
def test_a_driver_with_no_result_yet_comes_from_the_entry_list(profiles_f1db):
    season = driver_season(2026, "sergio-perez")

    assert season["driver"]["number"] == 11
    assert season["driver"]["team_id"] == "cadillac"
    assert season["teams"] == [
        {"id": "cadillac", "name": "Cadillac", "color": "#E0D4B8", "rounds": [], "rounds_label": ""}
    ]
    assert season["standing"] == {"position": None, "points": 0}
    assert season["stats"]["best_finish"] is None


@pytest.mark.integration
@pytest.mark.parametrize(
    "driver_id",
    ["ayumu-iwasa", "nobody"],
    ids=["reserve-only", "unknown"],
)
def test_driver_season_is_none_for_a_driver_who_was_not_entered(profiles_f1db, driver_id):
    assert driver_season(2026, driver_id) is None


# ---------------------------------------------------------------------------
# circuit history
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_previous_edition_is_the_latest_earlier_race_at_the_circuit(profiles_f1db):
    assert previous_edition(2026, 2) == {
        "year": 2025,
        "round": 8,
        "name": "Monaco Grand Prix",
        "winner": {
            "driver_id": "charles-leclerc",
            "driver_name": "Charles Leclerc",
            "team_id": "ferrari",
            "team_name": "Ferrari",
        },
        # Pole and the win can belong to different drivers.
        "pole": {
            "driver_id": "max-verstappen",
            "driver_name": "Max Verstappen",
            "team_id": "red-bull",
            "team_name": "Red Bull",
        },
    }


@pytest.mark.integration
def test_previous_edition_steps_back_another_year_from_an_earlier_season(profiles_f1db):
    previous = previous_edition(2025, 8)

    assert previous["year"] == 2024
    assert previous["winner"]["driver_id"] == "lewis-hamilton"
    assert previous["pole"]["driver_id"] == "charles-leclerc"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "round_num"),
    [(2026, 1), (2026, 3), (2026, 99)],
    ids=["new-circuit", "earlier-edition-has-no-result", "unknown-round"],
)
def test_previous_edition_is_none_without_published_history(profiles_f1db, year, round_num):
    assert previous_edition(year, round_num) is None
