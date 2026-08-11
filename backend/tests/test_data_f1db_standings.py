"""Tests for app.data.f1db_standings — championship tables read from local f1db.

These functions replaced the live Ergast standings calls that were returning
hundreds of HTTP 429s, so they are now the *only* source of championship
position: both the "standings before round N" feature used to build the training
set and the latest-round tables the UI renders. Two risks are specific to this
module and are asserted directly:

* the per-``(year, round)`` memo caches are module-level and process-wide — a
  stale entry silently freezes the championship for the rest of the process;
* ``race_driver_standing`` joins ``season_entrant_driver``, which carries one row
  per team a driver raced for, so a mid-season switch duplicates the driver.

Everything runs against a real seeded SQLite f1db so the SQL is exercised.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from app.data import f1db_standings
from app.data.f1db_standings import (
    constructor_standings_after_round,
    constructor_standings_detailed,
    current_constructor_standings,
    current_driver_standings,
    driver_standings_after_round,
    driver_standings_detailed,
)
from tests.f1db_fixture import build_f1db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_standings_caches():
    """The memo dicts are module globals — reset so tests cannot leak."""
    f1db_standings._driver_cache.clear()
    f1db_standings._constructor_cache.clear()
    yield
    f1db_standings._driver_cache.clear()
    f1db_standings._constructor_cache.clear()


@pytest.fixture
def sql_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a bespoke f1db from a SQL script and point the source at it.

    The seeded fixture has no NULL team/points/nationality rows, which are the
    real-world shape for a driver whose entrant row is missing.
    """
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

    monkeypatch.setattr(f1db_standings, "connect", _fail)


# ---------------------------------------------------------------------------
# driver_standings_after_round
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_driver_standings_after_round_returns_positions_keyed_by_code(fake_f1db):
    # 2026 round 1 (race id 3): VER leads on countback despite fewer points.
    assert driver_standings_after_round(2026, 1) == {"VER": 1, "LEC": 2}


@pytest.mark.integration
def test_driver_standings_after_round_reflects_the_requested_round_not_the_latest(fake_f1db):
    """Training features need standings *before* a race — asking for round 1 must
    not silently return the end-of-season table."""
    assert driver_standings_after_round(2026, 2) == {"VER": 1, "LEC": 2}
    assert driver_standings_after_round(2025, 1) == {}


@pytest.mark.unit
@pytest.mark.parametrize("round_num", [0, -1])
def test_driver_standings_after_round_is_empty_before_the_season_starts(round_num):
    # Guarded before any connection, so no database fixture is needed.
    assert driver_standings_after_round(2026, round_num) == {}


@pytest.mark.integration
def test_driver_standings_after_round_is_empty_for_a_round_not_in_the_dataset(fake_f1db):
    assert driver_standings_after_round(2026, 3) == {}


@pytest.mark.integration
def test_driver_standings_after_round_memoises_by_year_and_round(fake_f1db, monkeypatch):
    first = driver_standings_after_round(2026, 1)
    _explode_on_connect(monkeypatch)

    assert driver_standings_after_round(2026, 1) is first


@pytest.mark.integration
def test_driver_standings_after_round_caches_the_empty_result_too(fake_f1db, monkeypatch):
    """An absent round is a legitimate answer, not a miss to be retried."""
    assert driver_standings_after_round(2026, 3) == {}
    _explode_on_connect(monkeypatch)

    assert driver_standings_after_round(2026, 3) == {}


@pytest.mark.integration
def test_driver_standings_after_round_skips_drivers_without_an_abbreviation(sql_f1db):
    """A driver with no three-letter code cannot be keyed, so the row is dropped
    rather than colliding under a NULL key."""
    sql_f1db(
        """
        INSERT INTO race (id, year, round) VALUES (1, 2026, 1);
        INSERT INTO driver (id, name, abbreviation) VALUES ('a', 'Coded', 'AAA');
        INSERT INTO driver (id, name, abbreviation) VALUES ('b', 'Uncoded', NULL);
        INSERT INTO race_driver_standing (race_id, position_number, driver_id, points)
            VALUES (1, 1, 'a', 10.0), (1, 2, 'b', 5.0);
        """
    )

    assert driver_standings_after_round(2026, 1) == {"AAA": 1}


# ---------------------------------------------------------------------------
# constructor_standings_after_round
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_standings_after_round_returns_rows_in_championship_order(fake_f1db):
    assert constructor_standings_after_round(2026, 2) == [
        {"constructor_name": "Red Bull", "position": 1},
        {"constructor_name": "Ferrari", "position": 2},
    ]


@pytest.mark.unit
@pytest.mark.parametrize("round_num", [0, -3])
def test_constructor_standings_after_round_is_empty_before_the_season_starts(round_num):
    assert constructor_standings_after_round(2026, round_num) == []


@pytest.mark.integration
def test_constructor_standings_after_round_is_empty_for_a_round_without_standings(fake_f1db):
    # Only round 2 has constructor standings seeded.
    assert constructor_standings_after_round(2026, 1) == []


@pytest.mark.integration
def test_constructor_standings_after_round_memoises_by_year_and_round(fake_f1db, monkeypatch):
    first = constructor_standings_after_round(2026, 2)
    _explode_on_connect(monkeypatch)

    assert constructor_standings_after_round(2026, 2) is first


# ---------------------------------------------------------------------------
# driver_standings_detailed
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_driver_standings_detailed_returns_the_latest_round_table(fake_f1db):
    """Round 2 is the last round with standings, so that is the live table."""
    rows = driver_standings_detailed(2026)
    leader = dict(rows[0])
    leader.pop("team")  # asserted separately: VER switched teams mid-2026

    assert leader == {
        "code": "VER",
        "name": "Verstappen",
        "position": 1,
        "points": 50.0,
        "wins": 2,
        "nationality": "Netherlands",
        "driver_id": "max-verstappen",
    }
    assert rows[1] == {
        "code": "LEC",
        "name": "Leclerc",
        "team": "Ferrari",
        "position": 2,
        "points": 44.0,
        "wins": 0,
        "nationality": "Monaco",
        "driver_id": "charles-leclerc",
    }


@pytest.mark.integration
def test_driver_standings_detailed_lists_a_mid_season_switcher_once(fake_f1db):
    """VER has two 2026 entrant rows (McLaren then Red Bull); the join duplicates
    him and the dedupe must collapse it to a single championship row.

    Which of the two teams survives is whichever row the join emits first — this
    module keeps the first, it does not resolve the majority team the way
    ``champions._champion_team`` does.
    """
    rows = driver_standings_detailed(2026)

    assert [row["code"] for row in rows] == ["VER", "LEC"]
    assert rows[0]["team"] in {"McLaren", "Red Bull"}


@pytest.mark.integration
def test_driver_standings_detailed_counts_race_wins_only_not_sprints(fake_f1db):
    """LEC won the 2026 sprint; a sprint win is not a grand prix win."""
    by_code = {row["code"]: row for row in driver_standings_detailed(2026)}

    assert by_code["LEC"]["wins"] == 0
    assert by_code["VER"]["wins"] == 2


@pytest.mark.integration
def test_driver_standings_detailed_is_empty_when_the_season_has_no_standings(fake_f1db):
    # 2025 races exist but no per-round standings were released for them.
    assert driver_standings_detailed(2025) == []


@pytest.mark.integration
def test_driver_standings_detailed_is_empty_for_an_empty_dataset(empty_f1db):
    assert driver_standings_detailed(2026) == []


@pytest.mark.integration
def test_driver_standings_detailed_defaults_missing_team_points_and_nationality(sql_f1db):
    """A driver with no entrant row still has to render — blanks, not nulls."""
    sql_f1db(
        """
        INSERT INTO race (id, year, round) VALUES (1, 2026, 1);
        INSERT INTO driver (id, name, abbreviation, nationality_country_id)
            VALUES ('a', 'Nobody', 'NOB', NULL);
        INSERT INTO race_driver_standing (race_id, position_number, driver_id, points)
            VALUES (1, 1, 'a', NULL);
        """
    )

    assert driver_standings_detailed(2026) == [
        {
            "code": "NOB",
            "name": "Nobody",
            "team": "",
            "position": 1,
            "points": 0.0,
            "wins": 0,
            "nationality": "",
            "driver_id": "a",
        }
    ]


# ---------------------------------------------------------------------------
# constructor_standings_detailed
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_standings_detailed_returns_the_latest_round_table(fake_f1db):
    assert constructor_standings_detailed(2026) == [
        {"team": "Red Bull", "position": 1, "points": 50.0, "wins": 2},
        {"team": "Ferrari", "position": 2, "points": 44.0, "wins": 0},
    ]


@pytest.mark.integration
def test_constructor_standings_detailed_is_empty_when_the_season_has_no_standings(fake_f1db):
    assert constructor_standings_detailed(2025) == []


@pytest.mark.integration
def test_constructor_standings_detailed_defaults_missing_points_to_zero(sql_f1db):
    sql_f1db(
        """
        INSERT INTO race (id, year, round) VALUES (1, 2026, 1);
        INSERT INTO driver (id, name, abbreviation) VALUES ('a', 'Driver', 'AAA');
        INSERT INTO constructor (id, name) VALUES ('t', 'Team');
        INSERT INTO race_driver_standing (race_id, position_number, driver_id, points)
            VALUES (1, 1, 'a', 10.0);
        INSERT INTO race_constructor_standing (race_id, position_number, constructor_id, points)
            VALUES (1, 1, 't', NULL);
        """
    )

    assert constructor_standings_detailed(2026) == [{"team": "Team", "position": 1, "points": 0.0, "wins": 0}]


# ---------------------------------------------------------------------------
# current_driver_standings / current_constructor_standings
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_current_driver_standings_resolves_the_latest_round_automatically(fake_f1db):
    assert current_driver_standings(2026) == driver_standings_after_round(2026, 2)


@pytest.mark.integration
def test_current_driver_standings_is_empty_when_no_round_has_standings(fake_f1db):
    assert current_driver_standings(2025) == {}


@pytest.mark.integration
def test_current_constructor_standings_resolves_the_latest_round_automatically(fake_f1db):
    assert current_constructor_standings(2026) == [
        {"constructor_name": "Red Bull", "position": 1},
        {"constructor_name": "Ferrari", "position": 2},
    ]


@pytest.mark.integration
def test_current_constructor_standings_is_empty_when_no_round_has_standings(fake_f1db):
    assert current_constructor_standings(2025) == []


@pytest.mark.integration
def test_current_constructor_standings_uses_the_latest_driver_standing_round(sql_f1db):
    """``_latest_round`` is derived from ``race_driver_standing`` for both tables —
    a season whose constructor rows stop earlier returns nothing, not the older
    constructor round."""
    sql_f1db(
        """
        INSERT INTO race (id, year, round) VALUES (1, 2026, 1), (2, 2026, 2);
        INSERT INTO driver (id, name, abbreviation) VALUES ('a', 'Driver', 'AAA');
        INSERT INTO constructor (id, name) VALUES ('t', 'Team');
        INSERT INTO race_driver_standing (race_id, position_number, driver_id, points)
            VALUES (1, 1, 'a', 10.0), (2, 1, 'a', 20.0);
        INSERT INTO race_constructor_standing (race_id, position_number, constructor_id, points)
            VALUES (1, 1, 't', 10.0);
        """
    )

    assert current_constructor_standings(2026) == []
