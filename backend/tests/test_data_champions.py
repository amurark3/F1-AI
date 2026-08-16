"""Tests for app.data.champions — the /api/champions read model over f1db.

Three things here are easy to get wrong and expensive when wrong:

* **Memoisation.** ``_cache`` is a module-level dict with no expiry, so a value
  stored once is served for the life of the process. Both the cold and the
  memoised path are covered, and the "season does not exist" answer is checked
  *not* to be cached.
* **Title decided vs in progress.** ``championship_won`` is what separates a
  crowned champion from the current points leader. Rendering the live leader as
  champion is the headline bug this module can produce, so 2025 (decided) and
  2026 (in progress) are asserted against each other.
* **The title team.** A driver can have several ``season_entrant_driver`` rows —
  one per team after a mid-season switch, plus reserve/test entries. The title
  team is the one they raced most rounds for, and a ``test_driver`` row must
  never win that contest.

Everything runs against a real seeded SQLite f1db so the SQL is exercised.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from app.data import champions
from app.data.champions import get_champion_stats, get_season_detail, list_champions
from app.data.f1db_source import connect
from tests.f1db_fixture import build_f1db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_champions_cache():
    """``_cache`` is process-wide — reset so results cannot leak between tests."""
    champions._cache.clear()
    yield
    champions._cache.clear()


@pytest.fixture
def sql_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a bespoke f1db from a SQL script and point the source at it."""
    from app.data import f1db_source

    def _build(script: str) -> Path:
        path = build_f1db(tmp_path / "custom.db", seed=False)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()
        monkeypatch.setattr(f1db_source, "DB_PATH", path)
        return path

    return _build


def _explode_on_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any further database access fail the test, proving a cache hit."""

    def _fail():
        pytest.fail("the memoised value must be returned without re-querying f1db")

    monkeypatch.setattr(champions, "connect", _fail)


# ---------------------------------------------------------------------------
# _rounds_count
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rounds_text", "expected"),
    [
        ("1;2;3", 3),
        ("1", 1),
        ("", 0),
        (None, 0),
        (";;", 0),  # separators with nothing between them are not rounds
        (" 1 ; 2 ", 2),
        (24, 1),  # f1db can hand back a bare integer for a single round
    ],
    ids=["multi", "single", "empty", "null", "separators-only", "padded", "non-string"],
)
def test_rounds_count_counts_the_semicolon_separated_rounds(rounds_text, expected):
    assert champions._rounds_count(rounds_text) == expected


# ---------------------------------------------------------------------------
# _champion_team
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_champion_team_picks_the_team_with_the_most_rounds_after_a_switch(fake_f1db):
    """VER ran round 1 of 2026 for McLaren and rounds 2-3 for Red Bull — the title
    team is the one he actually raced most of the season for."""
    with connect() as conn:
        assert champions._champion_team(conn, 2026, "max-verstappen") == "Red Bull"


@pytest.mark.integration
def test_champion_team_ignores_test_driver_entries(fake_f1db):
    """NOR's only 2026 entrant row is a ``test_driver`` seat at Ferrari. A reserve
    seat is not a title team, so there is no team at all to report."""
    with connect() as conn:
        assert champions._champion_team(conn, 2026, "lando-norris") is None


@pytest.mark.integration
def test_champion_team_is_none_for_a_driver_with_no_entrant_row(fake_f1db):
    with connect() as conn:
        assert champions._champion_team(conn, 2025, "unknown-driver") is None


# ---------------------------------------------------------------------------
# list_champions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_champions_returns_newest_season_first(fake_f1db):
    assert [row["season"] for row in list_champions()] == [2026, 2025]


@pytest.mark.integration
def test_list_champions_crowns_the_leader_only_once_the_title_is_decided(fake_f1db):
    """2025 has ``championship_won = 1`` for VER, 2026 does not. Same driver, same
    points, opposite meaning — the live leader must not be shown as champion."""
    by_season = {row["season"]: row for row in list_champions()}

    assert by_season[2025]["driver_champion"]["title_decided"] is True
    assert by_season[2025]["is_in_progress"] is False
    assert by_season[2026]["driver_champion"]["title_decided"] is False
    assert by_season[2026]["is_in_progress"] is True


@pytest.mark.integration
def test_list_champions_builds_the_full_driver_champion_record(fake_f1db):
    by_season = {row["season"]: row for row in list_champions()}

    assert by_season[2025]["driver_champion"] == {
        "name": "Max Verstappen",
        "code": "VER",
        "team": "Red Bull",
        "points": 50.0,
        "wins": 2,
        "nationality": "Netherlands",
        "title_decided": True,
    }


@pytest.mark.integration
def test_list_champions_reports_the_constructor_champion_and_round_count(fake_f1db):
    by_season = {row["season"]: row for row in list_champions()}

    assert by_season[2025]["constructor_champion"] == {
        "name": "Red Bull",
        "points": 50.0,
        "title_decided": True,
    }
    # 2026 has three rounds on the calendar even though only two have been run.
    assert by_season[2026]["round_count"] == 3
    assert by_season[2025]["round_count"] == 2


@pytest.mark.integration
def test_list_champions_is_memoised_after_the_first_build(fake_f1db, monkeypatch):
    first = list_champions()
    _explode_on_connect(monkeypatch)

    assert list_champions() is first


@pytest.mark.integration
def test_list_champions_is_empty_for_a_dataset_with_no_seasons(empty_f1db):
    assert list_champions() == []


@pytest.mark.integration
def test_list_champions_reports_no_champion_for_a_season_without_standings(sql_f1db):
    """A season row can exist before any standings are published; that is not an
    in-progress championship, it is a season with no leader at all."""
    sql_f1db("INSERT INTO season VALUES (1950);")

    assert list_champions() == [
        {
            "season": 1950,
            "is_in_progress": False,
            "driver_champion": None,
            "constructor_champion": None,
            "round_count": 0,
        }
    ]


@pytest.mark.integration
def test_list_champions_defaults_missing_points_to_zero(sql_f1db):
    sql_f1db(
        """
        INSERT INTO season VALUES (1950);
        INSERT INTO driver (id, full_name, abbreviation) VALUES ('f', 'Nino Farina', 'FAR');
        INSERT INTO constructor (id, name) VALUES ('alfa', 'Alfa Romeo');
        INSERT INTO season_driver_standing (year, position_number, driver_id, points, championship_won)
            VALUES (1950, 1, 'f', NULL, 1);
        INSERT INTO season_constructor_standing (year, position_number, constructor_id, points, championship_won)
            VALUES (1950, 1, 'alfa', NULL, 1);
        """
    )
    season = list_champions()[0]

    assert season["driver_champion"]["points"] == 0.0
    assert season["constructor_champion"]["points"] == 0.0
    # No entrant rows and no country row: team and nationality stay unset.
    assert season["driver_champion"]["team"] is None
    assert season["driver_champion"]["nationality"] is None


# ---------------------------------------------------------------------------
# get_season_detail
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_season_detail_lists_every_race_winner_in_round_order(fake_f1db):
    detail = get_season_detail(2026)

    assert detail["race_winners"] == [
        {
            "round": 1,
            "race_name": "Bahrain Grand Prix",
            "date": "2026-03-08",
            "winner": "Max Verstappen",
            "team": "Red Bull",
        },
        {
            "round": 2,
            "race_name": "Monaco Grand Prix",
            "date": "2026-05-24",
            "winner": "Max Verstappen",
            "team": "Red Bull",
        },
    ]


@pytest.mark.integration
def test_get_season_detail_excludes_sprint_winners_from_race_winners(fake_f1db):
    """LEC won the 2026 round 1 sprint — a sprint is not a grand prix win."""
    winners = {w["winner"] for w in get_season_detail(2026)["race_winners"]}

    assert winners == {"Max Verstappen"}


@pytest.mark.integration
def test_get_season_detail_reports_the_runner_up(fake_f1db):
    assert get_season_detail(2025)["runner_up"] == {"name": "Charles Leclerc", "points": 36.0}


@pytest.mark.integration
def test_get_season_detail_marks_an_undecided_season_in_progress(fake_f1db):
    assert get_season_detail(2026)["is_in_progress"] is True
    assert get_season_detail(2025)["is_in_progress"] is False


@pytest.mark.integration
def test_get_season_detail_returns_an_error_for_a_season_not_in_the_dataset(fake_f1db):
    assert get_season_detail(1997) == {"error": "No F1 season found for 1997"}


@pytest.mark.integration
def test_get_season_detail_does_not_cache_the_missing_season_answer(fake_f1db):
    """f1db gains seasons on every refresh, so "not found" must stay retryable."""
    get_season_detail(1997)

    assert "detail:1997" not in champions._cache


@pytest.mark.integration
def test_get_season_detail_is_memoised_per_season(fake_f1db, monkeypatch):
    first = get_season_detail(2025)
    _explode_on_connect(monkeypatch)

    assert get_season_detail(2025) is first


@pytest.mark.integration
def test_get_season_detail_handles_a_season_with_no_standings_at_all(sql_f1db):
    sql_f1db("INSERT INTO season VALUES (1950);")

    assert get_season_detail(1950) == {
        "season": 1950,
        "is_in_progress": False,
        "driver_champion": None,
        "constructor_champion": None,
        "runner_up": None,
        "race_winners": [],
    }


# ---------------------------------------------------------------------------
# get_champion_stats
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_champion_stats_counts_only_decided_titles(fake_f1db):
    """VER leads 2026 too, but an undecided season adds nothing to a title count."""
    assert get_champion_stats() == {
        "most_driver_titles": [{"name": "Max Verstappen", "titles": 1}],
        "most_constructor_titles": [{"name": "Red Bull", "titles": 1}],
    }


@pytest.mark.integration
def test_get_champion_stats_ranks_by_title_count_then_name(sql_f1db):
    sql_f1db(
        """
        INSERT INTO season VALUES (1950), (1951), (1952);
        INSERT INTO driver (id, full_name) VALUES ('a', 'Alberto Ascari'), ('b', 'Nino Farina');
        INSERT INTO season_driver_standing (year, position_number, driver_id, points, championship_won)
            VALUES (1950, 1, 'b', 30.0, 1), (1951, 1, 'a', 31.0, 1), (1952, 1, 'a', 36.0, 1);
        """
    )

    assert get_champion_stats()["most_driver_titles"] == [
        {"name": "Alberto Ascari", "titles": 2},
        {"name": "Nino Farina", "titles": 1},
    ]


@pytest.mark.integration
def test_get_champion_stats_is_memoised(fake_f1db, monkeypatch):
    first = get_champion_stats()
    _explode_on_connect(monkeypatch)

    assert get_champion_stats() is first


@pytest.mark.integration
def test_get_champion_stats_is_empty_for_a_dataset_with_no_titles(empty_f1db):
    assert get_champion_stats() == {"most_driver_titles": [], "most_constructor_titles": []}
