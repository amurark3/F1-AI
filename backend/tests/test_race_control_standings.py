"""Tests for app.services.race_control_standings — team profiles and intel.

Every string this module emits is shown to a user as a factual claim about a
constructor's season, so the tests pin *what is said* as tightly as what is
computed:

* **Nothing may be invented.** With no standings loaded the team profile has to
  say so rather than render an empty-but-confident card.
* **Rival gaps must be read off the right neighbours.** ``_intel_context``
  indexes the constructor table by position; an off-by-one there names the
  wrong rival in a threat the strategist is asked to act on.
* **Divisors are guarded.** Points-per-event and points-share both divide by
  values that are legitimately zero at the start of a season.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import race_control_standings as module

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _constructor(team: str, *, position: int, points: float, wins: int = 0) -> dict:
    return {"position": position, "team": team, "points": points, "wins": wins}


def _driver(code: str, *, team: str, position: int = 1, points: float = 0.0, wins: int = 0) -> dict:
    return {
        "position": position,
        "code": code,
        "driver": f"{code} Driver",
        "team": team,
        "points": points,
        "wins": wins,
    }


def _stub_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    *,
    drivers: list[dict] | None = None,
    constructors: list[dict] | None = None,
    completed_events: int | None = 10,
) -> list[int]:
    """Serve fixed standings; returns the list of years the module asked for."""
    seen_years: list[int] = []

    def _snapshot(year: int) -> tuple[list[dict], list[dict]]:
        seen_years.append(year)
        return list(drivers or []), list(constructors or [])

    monkeypatch.setattr(module, "get_standings_snapshot", _snapshot)
    monkeypatch.setattr(module, "completed_race_count", lambda year: completed_events)
    return seen_years


# ---------------------------------------------------------------------------
# profile_for_team
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_placeholder_profile_admits_it_has_no_standings_behind_it():
    profile = module.profile_for_team("Red Bull Racing")

    assert profile == {
        "slug": "red-bull",
        "name": "Red Bull Racing",
        "color": "#3671C6",
        "strengths": [],
        "weaknesses": [],
        "strategy_tendency": "Standing profile unavailable until constructor standings load.",
    }


@pytest.mark.unit
def test_placeholder_profile_of_an_unknown_team_falls_back_to_a_neutral_colour():
    assert module.profile_for_team("Brabham")["color"] == "#6B7280"


# ---------------------------------------------------------------------------
# build_team_profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_leader_profile_reads_defensive_and_lists_its_evidence():
    row = _constructor("McLaren", position=1, points=500.0, wins=12)
    roster = [
        _driver("NOR", team="McLaren", points=300.0),
        _driver("PIA", team="McLaren", points=200.0),
    ]

    profile = module.build_team_profile(row, roster, leader_points=500.0, completed_events=20)

    assert profile["slug"] == "mclaren"
    assert profile["strengths"] == ["WCC P1", "500 championship pts", "12 race wins", "25.0 pts/GP"]
    assert profile["weaknesses"] == [
        "Current constructor benchmark",
        "NOR Driver has 60% of team points",
        "2 classified drivers in standings",
    ]
    assert "leads the constructors' table with 500 points" in profile["strategy_tendency"]
    assert "defensive" in profile["strategy_tendency"]
    assert profile["standing_profile"] == {
        "WCC position": 1,
        "points": 500.0,
        "wins": 12,
        "pts per GP": 25.0,
    }


@pytest.mark.unit
def test_a_chasing_team_reads_opportunistic_and_states_the_gap():
    row = _constructor("Ferrari", position=2, points=380.0, wins=1)
    roster = [_driver("LEC", team="Ferrari", points=380.0)]

    profile = module.build_team_profile(row, roster, leader_points=500.0, completed_events=20)

    assert profile["strengths"][:3] == ["WCC P2", "380 championship pts", "1 race win"]
    assert profile["weaknesses"][0] == "120 pts behind P1"
    assert profile["weaknesses"][2] == "1 classified driver in standings"
    assert "P2, 120 points off the constructor lead" in profile["strategy_tendency"]
    assert "opportunistic" in profile["strategy_tendency"]


@pytest.mark.unit
def test_a_pointless_team_level_with_the_leader_says_the_read_is_limited():
    """Only reachable pre-season, when every constructor is on zero."""
    row = _constructor("Haas", position=9, points=0.0)

    profile = module.build_team_profile(row, [], leader_points=0.0, completed_events=0)

    assert profile["weaknesses"] == ["Current constructor benchmark"]
    assert profile["strategy_tendency"] == (
        "Haas has no constructor points loaded yet. The strategy read stays limited "
        "until the standings feed contains scoring data."
    )
    # completed_events of 0 must divide by one event, not raise.
    assert profile["standing_profile"]["pts per GP"] == 0.0


@pytest.mark.unit
def test_an_unranked_row_says_so_instead_of_printing_p0():
    row = _constructor("Cadillac", position=0, points=0.0)

    profile = module.build_team_profile(row, [], leader_points=100.0, completed_events=5)

    assert profile["strengths"][0] == "No WCC rank"
    assert profile["weaknesses"] == ["100 pts behind P1"]


@pytest.mark.unit
def test_points_share_is_omitted_when_the_team_has_not_scored():
    row = _constructor("Sauber", position=10, points=0.0)
    roster = [_driver("BOT", team="Sauber", points=0.0)]

    profile = module.build_team_profile(row, roster, leader_points=0.0, completed_events=5)

    assert not any("% of team points" in entry for entry in profile["weaknesses"])
    assert profile["weaknesses"] == ["Current constructor benchmark", "1 classified driver in standings"]


@pytest.mark.unit
def test_a_gap_can_never_be_negative_when_a_team_outscores_the_named_leader():
    row = _constructor("Red Bull", position=2, points=600.0)

    profile = module.build_team_profile(row, [], leader_points=500.0, completed_events=10)

    assert profile["weaknesses"][0] == "Current constructor benchmark"


# ---------------------------------------------------------------------------
# points_trend
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_points_trend_runs_one_entry_per_event_and_lands_on_the_real_total():
    trend = module.points_trend(200.0, 4)

    assert [point["round"] for point in trend] == [1, 2, 3, 4]
    assert trend[-1]["points"] == 200.0
    assert [point["points"] for point in trend] == sorted(point["points"] for point in trend)


@pytest.mark.unit
def test_points_trend_before_any_race_still_returns_a_single_point():
    assert module.points_trend(0.0, 0) == [{"round": 1, "points": 0.0}]


# ---------------------------------------------------------------------------
# build_teams
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_teams_attaches_each_roster_to_its_own_constructor(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(
        monkeypatch,
        drivers=[
            _driver("NOR", team="McLaren", position=1, points=300.0),
            _driver("PIA", team="McLaren", position=2, points=200.0),
            _driver("LEC", team="Ferrari", position=3, points=180.0),
        ],
        constructors=[
            _constructor("McLaren", position=1, points=500.0, wins=12),
            _constructor("Ferrari", position=2, points=180.0, wins=1),
        ],
        completed_events=20,
    )

    result = module.build_teams(2024)

    assert result["error"] is None
    assert result["source"] == "jolpica-ergast-constructor-standings"
    mclaren, ferrari = result["teams"]
    assert [driver["code"] for driver in mclaren["drivers"]] == ["NOR", "PIA"]
    assert [driver["code"] for driver in ferrari["drivers"]] == ["LEC"]
    assert mclaren["pace_profile"] == mclaren["standing_profile"]
    assert ferrari["weaknesses"][0] == "320 pts behind P1"


@pytest.mark.unit
def test_recent_form_is_capped_at_five_rounds(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(
        monkeypatch,
        constructors=[_constructor("McLaren", position=1, points=500.0)],
        completed_events=22,
    )

    result = module.build_teams(2024)

    form = result["teams"][0]["recent_form"]
    assert [point["round"] for point in form] == [1, 2, 3, 4, 5]
    assert form[-1]["points"] == 500.0


@pytest.mark.unit
def test_recent_form_survives_a_season_with_no_completed_race(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(
        monkeypatch,
        constructors=[_constructor("McLaren", position=1, points=0.0)],
        completed_events=None,
    )

    result = module.build_teams(2025)

    assert result["teams"][0]["recent_form"] == [{"round": 1, "points": 0.0}]


@pytest.mark.unit
def test_build_teams_without_constructors_reports_the_gap(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(monkeypatch, drivers=[], constructors=[])

    result = module.build_teams(2024)

    assert result["teams"] == []
    assert result["drivers"] == []
    assert result["error"] == "Constructor standings are unavailable for this season."


# ---------------------------------------------------------------------------
# build_intel
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_intel_without_standings_returns_a_titled_placeholder(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(monkeypatch, constructors=[])

    result = module.build_intel("aston-martin", 2024)

    assert result["status"] == "data_unavailable"
    assert result["team"]["name"] == "Aston Martin"
    assert result["team"]["slug"] == "aston-martin"
    assert result["threats"] == []
    assert result["opportunities"] == []
    assert result["error"] == "Constructor standings are unavailable."


@pytest.mark.unit
def test_intel_for_an_unknown_slug_lists_the_teams_that_do_exist(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_snapshot(
        monkeypatch,
        constructors=[
            _constructor("McLaren", position=1, points=500.0),
            _constructor("Red Bull Racing", position=2, points=400.0),
        ],
    )

    result = module.build_intel("brabham", 2024)

    assert result["status"] == "team_not_found"
    assert result["error"] == "Team 'brabham' was not found in the constructor standings."
    assert result["available_teams"] == [
        {"slug": "mclaren", "name": "McLaren"},
        {"slug": "red-bull", "name": "Red Bull Racing"},
    ]


@pytest.mark.unit
def test_intel_defaults_to_the_current_season_when_no_year_is_given(
    monkeypatch: pytest.MonkeyPatch,
):
    seen_years = _stub_snapshot(monkeypatch, constructors=[])

    module.build_intel("mclaren")

    assert seen_years == [datetime.now(timezone.utc).year]


@pytest.mark.unit
def test_intel_for_a_midfield_team_names_the_rival_either_side(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_snapshot(
        monkeypatch,
        drivers=[
            _driver("LEC", team="Ferrari", position=3, points=100.0),
            _driver("HAM", team="Ferrari", position=4, points=80.0),
        ],
        constructors=[
            _constructor("McLaren", position=1, points=300.0, wins=9),
            _constructor("Ferrari", position=2, points=180.0, wins=2),
            _constructor("Red Bull", position=3, points=170.0, wins=1),
        ],
        completed_events=12,
    )

    result = module.build_intel("ferrari", 2024)

    assert result["status"] == "ok"
    assert result["error"] is None
    assert [driver["code"] for driver in result["drivers"]] == ["LEC", "HAM"]
    assert result["upgrade_watch"] == [
        "WCC P2 with 180 points.",
        "2 constructor wins in the standings feed.",
        "Leader gap: 120 points to McLaren.",
        "Top scorer: LEC Driver with 100 points.",
        "Next target ahead: McLaren by 120 points.",
        "Nearest pressure behind: Red Bull by 10 points.",
    ]
    assert result["threats"] == [
        "Red Bull is only 10 points behind; one race swing can change the order.",
    ]
    assert result["opportunities"] == [
        "Close the gap to McLaren by targeting points swings above 120.",
        "Protect against Red Bull by prioritising finishes that keep the gap above 10.",
        "Use both cars in scenario planning because the roster has multiple classified points sources.",
    ]


@pytest.mark.unit
def test_intel_flags_a_rival_close_ahead_as_an_immediate_threat(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_snapshot(
        monkeypatch,
        constructors=[
            _constructor("McLaren", position=1, points=200.0),
            _constructor("Ferrari", position=2, points=190.0),
        ],
    )

    result = module.build_intel("ferrari", 2024)

    assert result["threats"] == [
        "McLaren is within 10 points ahead; covering them can matter immediately.",
    ]


@pytest.mark.unit
def test_intel_flags_points_concentrated_in_a_single_car(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(
        monkeypatch,
        drivers=[
            _driver("VER", team="Red Bull", position=1, points=90.0),
            _driver("LAW", team="Red Bull", position=15, points=10.0),
        ],
        constructors=[
            _constructor("McLaren", position=1, points=400.0),
            _constructor("Red Bull", position=2, points=100.0),
        ],
    )

    result = module.build_intel("red-bull", 2024)

    assert (
        "Points are concentrated through VER Driver; losing that car has high constructor impact." in result["threats"]
    )


@pytest.mark.unit
def test_a_leader_with_no_close_rival_gets_the_explicit_no_threat_note(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_snapshot(
        monkeypatch,
        drivers=[_driver("NOR", team="McLaren", position=1, points=300.0)],
        constructors=[
            _constructor("McLaren", position=1, points=500.0, wins=1),
            _constructor("Ferrari", position=2, points=200.0),
        ],
    )

    result = module.build_intel("mclaren", 2024)

    assert result["threats"] == [
        "No close constructor-table threat is visible from current standings alone.",
    ]
    assert result["opportunities"] == [
        "Protect against Ferrari by prioritising finishes that keep the gap above 300.",
        "Leader control: minimise low-probability strategy branches when direct rivals are behind.",
    ]
    assert result["upgrade_watch"][1] == "1 constructor win in the standings feed."


@pytest.mark.unit
def test_the_last_placed_team_has_nobody_behind_it(monkeypatch: pytest.MonkeyPatch):
    _stub_snapshot(
        monkeypatch,
        constructors=[
            _constructor("McLaren", position=1, points=500.0),
            _constructor("Haas", position=2, points=20.0),
        ],
    )

    result = module.build_intel("haas", 2024)

    assert not any("pressure behind" in entry for entry in result["upgrade_watch"])
    assert result["opportunities"] == [
        "Close the gap to McLaren by targeting points swings above 480.",
    ]


@pytest.mark.unit
def test_a_solo_constructor_table_has_neither_rival(monkeypatch: pytest.MonkeyPatch):
    """Degenerate feed: the only team is simultaneously leader and last."""
    _stub_snapshot(monkeypatch, constructors=[_constructor("McLaren", position=1, points=0.0)])

    result = module.build_intel("mclaren", 2024)

    assert result["upgrade_watch"] == [
        "WCC P1 with 0 points.",
        "0 constructor wins in the standings feed.",
        "Leader gap: 0 points to McLaren.",
    ]
    assert result["opportunities"] == [
        "Leader control: minimise low-probability strategy branches when direct rivals are behind.",
    ]
