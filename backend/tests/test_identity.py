"""Tests for app.data.identity — one season's drivers and teams by f1db id.

The properties that matter to the pages that link names:

* reserves (``test_driver = 1``) never appear, and an entrant who has not
  driven yet still does;
* a driver keeps their *latest* team and race number;
* team names resolve by exact folded match or alias, never by substring, and
  an alias cannot capture a team that is not on that season's grid;
* the directory is cached per f1db release, so a new release is re-read.
"""

from __future__ import annotations

import pytest

from app.data import f1db_source, identity
from app.data.identity import (
    NEUTRAL_TEAM_COLOR,
    TEAM_COLORS,
    as_int,
    fold,
    resolve_team,
    season_directory,
    team_color,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sergio Pérez", "sergio perez"),
        ("  Red-Bull   Racing ", "red bull racing"),
        ("SCUDERIA FERRARI", "scuderia ferrari"),
        ("", ""),
    ],
    ids=["accents", "punctuation-and-spacing", "case", "empty"],
)
def test_fold_ignores_case_accents_and_punctuation(text, expected):
    assert fold(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(6, 6), ("30", 30), (None, None), ("", None), ("N/A", None), (6.0, None)],
)
def test_as_int_reads_car_numbers_stored_as_text(value, expected):
    assert as_int(value) == expected


@pytest.mark.unit
def test_team_color_is_keyed_by_constructor_id_with_a_neutral_fallback():
    assert team_color("racing-bulls") == TEAM_COLORS["racing-bulls"]
    assert team_color("brawn") == NEUTRAL_TEAM_COLOR
    assert NEUTRAL_TEAM_COLOR not in TEAM_COLORS.values()


@pytest.mark.integration
def test_directory_lists_every_entrant_but_never_a_reserve(profiles_f1db):
    ids = {driver.id for driver in season_directory(2026).drivers}

    assert ids == {
        "max-verstappen",
        "isack-hadjar",
        "liam-lawson",
        "charles-leclerc",
        "lewis-hamilton",
        # Entered for Cadillac, no session yet.
        "sergio-perez",
    }


@pytest.mark.integration
def test_directory_keeps_each_drivers_latest_race_number(profiles_f1db):
    drivers = {driver.id: driver for driver in season_directory(2026).drivers}

    assert drivers["max-verstappen"].number == 1
    assert drivers["liam-lawson"].number == 30
    assert drivers["liam-lawson"].team_id == "red-bull"
    # No session yet, so the permanent number stands in.
    assert drivers["sergio-perez"].number == 11


@pytest.mark.integration
def test_directory_orders_teams_by_championship_with_unranked_last(profiles_f1db):
    teams = season_directory(2026).teams

    assert [team.id for team in teams] == ["red-bull", "ferrari", "cadillac"]
    assert teams[0].position == 1
    assert teams[0].points == 128.0
    assert teams[0].full_name == "Red Bull Racing"
    assert teams[2].position is None
    assert teams[2].points == 0.0
    # f1db has no full name for Cadillac; the short one is used.
    assert teams[2].full_name == "Cadillac"
    assert teams[2].color == TEAM_COLORS["cadillac"]


@pytest.mark.integration
def test_directory_before_a_season_starts_comes_from_the_entry_list(profiles_f1db):
    directory = season_directory(2027)

    assert [driver.id for driver in directory.drivers] == ["max-verstappen"]
    assert [(team.id, team.position) for team in directory.teams] == [("red-bull", None)]


@pytest.mark.integration
def test_directory_as_dict_is_the_api_shape(profiles_f1db):
    payload = season_directory(2027).as_dict()

    assert payload == {
        "year": 2027,
        "drivers": [
            {"id": "max-verstappen", "name": "Max Verstappen", "code": "VER", "number": 1, "team_id": "red-bull"}
        ],
        "teams": [
            {
                "id": "red-bull",
                "name": "Red Bull",
                "full_name": "Red Bull Racing",
                "color": TEAM_COLORS["red-bull"],
                "position": None,
                "points": 0.0,
                "aliases": ["oracle red bull racing", "red bull racing"],
            }
        ],
    }


@pytest.mark.integration
def test_directory_is_cached_until_the_f1db_release_changes(profiles_f1db, monkeypatch):
    monkeypatch.setattr(f1db_source, "installed_version", lambda: "v2026.18.0")
    first = season_directory(2026)

    assert season_directory(2026) is first

    monkeypatch.setattr(f1db_source, "installed_version", lambda: "v2026.19.0")
    assert season_directory(2026) is not first


@pytest.mark.integration
def test_clear_cache_forces_a_reread(profiles_f1db):
    first = season_directory(2026)
    identity.clear_cache()

    assert season_directory(2026) is not first


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("red-bull", "red-bull"),
        ("Ferrari", "ferrari"),
        ("Red Bull Racing", "red-bull"),
        ("SCUDERIA FERRARI", "ferrari"),
        ("Oracle Red Bull Racing", "red-bull"),
        ("Cadillac F1 Team", "cadillac"),
    ],
    ids=["id", "name", "full-name", "folded-full-name", "alias", "alias-of-new-team"],
)
def test_resolve_team_matches_exact_names_and_aliases(profiles_f1db, name, expected):
    assert resolve_team(2026, name) == expected


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    ["", "   ", "Red", "Brawn GP", "RB F1 Team"],
    ids=["empty", "blank", "substring", "unknown", "alias-off-the-grid"],
)
def test_resolve_team_never_guesses(profiles_f1db, name):
    """An empty string is a substring of every name; it must resolve to nothing."""
    assert resolve_team(2026, name) is None
