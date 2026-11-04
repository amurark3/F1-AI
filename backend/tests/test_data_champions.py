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
* **The name.** Every driver is printed by f1db's ``name`` ("Juan Manuel
  Fangio", "Kimi Räikkönen", "Carlos Sainz Jr."), with ``last_name`` beside it
  on driver records — never ``full_name``, the legal name ("Juan Manuel Fangio
  Déramo", "Carlos Sainz Vázquez de Castro"), which the page then cut down to
  "Juan Déramo" and "Carlos Castro". Pinned on real champions in
  ``fixtures/f1db_champions/``.

Everything runs against a real seeded SQLite f1db so the SQL is exercised.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from app.data import champions, f1db_source
from app.data.champions import get_champion_stats, get_season_detail, list_champions
from app.data.f1db_source import connect
from tests.f1db_fixture import build_f1db

CHAMPIONS = Path(__file__).parent / "fixtures" / "f1db_champions" / "seasons.json"
CHAMPION_SEASONS = json.loads(CHAMPIONS.read_text())

# f1db's own names for the shared seed's drivers. The seed stores a surname in
# ``name``, which f1db never does; this module prints names, so it corrects them.
SEED_NAMES = [
    ("Max Verstappen", "Max", "Verstappen", "Max Emilian Verstappen", "max-verstappen"),
    ("Charles Leclerc", "Charles", "Leclerc", "Charles Marc Hervé Perceval Leclerc", "charles-leclerc"),
    ("Lando Norris", "Lando", "Norris", "Lando Norris", "lando-norris"),
]


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


@pytest.fixture
def named_f1db(fake_f1db: Path) -> Path:
    """The shared two-season dataset, with its drivers named the way f1db names them."""
    with closing(sqlite3.connect(fake_f1db)) as conn:
        conn.executemany(
            "UPDATE driver SET name = ?, first_name = ?, last_name = ?, full_name = ? WHERE id = ?", SEED_NAMES
        )
        conn.commit()
    return fake_f1db


@pytest.fixture
def champions_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Real f1db rows for Fangio's five title seasons, 2007 and 2024 (see the fixture's ``source``)."""
    data = CHAMPION_SEASONS
    path = build_f1db(tmp_path / "champions.db", seed=False)
    with closing(sqlite3.connect(path)) as conn:
        conn.executemany("INSERT INTO season (year) VALUES (?)", [(year,) for year in data["seasons"]])
        conn.executemany("INSERT INTO country (id, name, alpha2_code) VALUES (?, ?, ?)", data["countries"])
        conn.executemany(
            """INSERT INTO driver (id, name, first_name, last_name, full_name, abbreviation, nationality_country_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            data["drivers"],
        )
        conn.executemany("INSERT INTO constructor (id, name) VALUES (?, ?)", data["constructors"])
        conn.executemany(
            "INSERT INTO race (id, year, round, date, official_name) VALUES (?, ?, ?, ?, ?)", data["races"]
        )
        conn.executemany(
            """INSERT INTO race_data (race_id, type, position_number, position_display_order, driver_id, constructor_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            data["winners"],
        )
        conn.executemany(
            """INSERT INTO season_driver_standing (year, position_number, driver_id, points, championship_won)
               VALUES (?, ?, ?, ?, ?)""",
            data["driver_standings"],
        )
        conn.executemany(
            """INSERT INTO season_constructor_standing (year, position_number, constructor_id, points, championship_won)
               VALUES (?, ?, ?, ?, ?)""",
            data["constructor_standings"],
        )
        conn.executemany(
            """INSERT INTO season_entrant_driver (year, driver_id, constructor_id, rounds_text, test_driver)
               VALUES (?, ?, ?, ?, ?)""",
            data["entrants"],
        )
        conn.commit()
    monkeypatch.setattr(f1db_source, "DB_PATH", path)
    return path


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
def test_list_champions_builds_the_full_driver_champion_record(named_f1db):
    by_season = {row["season"]: row for row in list_champions()}

    assert by_season[2025]["driver_champion"] == {
        "name": "Max Verstappen",
        "last_name": "Verstappen",
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
        INSERT INTO driver (id, name, full_name, abbreviation) VALUES ('f', 'Nino Farina', 'Emilio Giuseppe Farina', 'FAR');
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
def test_get_season_detail_lists_every_race_winner_in_round_order(named_f1db):
    detail = get_season_detail(2026)

    assert detail["race_winners"] == [
        {
            "round": 1,
            "race_name": "Bahrain Grand Prix",
            "date": "2026-03-08",
            "winner": "Max Verstappen",
            "driver_id": "max-verstappen",
            "team": "Red Bull",
            "team_id": "red-bull",
        },
        {
            "round": 2,
            "race_name": "Monaco Grand Prix",
            "date": "2026-05-24",
            "winner": "Max Verstappen",
            "driver_id": "max-verstappen",
            "team": "Red Bull",
            "team_id": "red-bull",
        },
    ]


@pytest.mark.integration
def test_get_season_detail_excludes_sprint_winners_from_race_winners(named_f1db):
    """LEC won the 2026 round 1 sprint — a sprint is not a grand prix win."""
    winners = {w["winner"] for w in get_season_detail(2026)["race_winners"]}

    assert winners == {"Max Verstappen"}


@pytest.mark.integration
def test_get_season_detail_reports_the_runner_up(named_f1db):
    assert get_season_detail(2025)["runner_up"] == {"name": "Charles Leclerc", "last_name": "Leclerc", "points": 36.0}


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
def test_get_champion_stats_counts_only_decided_titles(named_f1db):
    """VER leads 2026 too, but an undecided season adds nothing to a title count."""
    assert get_champion_stats() == {
        "most_driver_titles": [{"name": "Max Verstappen", "last_name": "Verstappen", "titles": 1}],
        "most_constructor_titles": [{"name": "Red Bull", "titles": 1}],
    }


@pytest.mark.integration
def test_get_champion_stats_ranks_by_title_count_then_name(sql_f1db):
    sql_f1db(
        """
        INSERT INTO season VALUES (1950), (1951), (1952);
        INSERT INTO driver (id, name, last_name, full_name) VALUES
            ('a', 'Alberto Ascari', 'Ascari', 'Alberto Ascari'),
            ('b', 'Nino Farina', 'Farina', 'Emilio Giuseppe Farina');
        INSERT INTO season_driver_standing (year, position_number, driver_id, points, championship_won)
            VALUES (1950, 1, 'b', 30.0, 1), (1951, 1, 'a', 31.0, 1), (1952, 1, 'a', 36.0, 1);
        """
    )

    assert get_champion_stats()["most_driver_titles"] == [
        {"name": "Alberto Ascari", "last_name": "Ascari", "titles": 2},
        {"name": "Nino Farina", "last_name": "Farina", "titles": 1},
    ]


@pytest.mark.integration
def test_get_champion_stats_is_memoised(fake_f1db, monkeypatch):
    first = get_champion_stats()
    _explode_on_connect(monkeypatch)

    assert get_champion_stats() is first


@pytest.mark.integration
def test_get_champion_stats_is_empty_for_a_dataset_with_no_titles(empty_f1db):
    assert get_champion_stats() == {"most_driver_titles": [], "most_constructor_titles": []}


# ---------------------------------------------------------------------------
# Names: f1db's ``name``, never the legal ``full_name`` (real champions)
# ---------------------------------------------------------------------------


def _every_payload() -> str:
    """Everything the three endpoints serve for the captured seasons, as one JSON text."""
    details = [get_season_detail(year) for year in CHAMPION_SEASONS["seasons"]]
    return json.dumps([list_champions(), details, get_champion_stats()], ensure_ascii=False)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("season", "name", "last_name"),
    [
        (1951, "Juan Manuel Fangio", "Fangio"),
        (2007, "Kimi Räikkönen", "Räikkönen"),
        (2024, "Max Verstappen", "Verstappen"),
    ],
)
def test_a_champion_is_printed_by_f1dbs_name_and_surname(champions_f1db, season, name, last_name):
    driver = {row["season"]: row for row in list_champions()}[season]["driver_champion"]

    assert (driver["name"], driver["last_name"]) == (name, last_name)


@pytest.mark.integration
def test_the_runner_up_is_printed_by_f1dbs_name(champions_f1db):
    assert get_season_detail(2007)["runner_up"] == {"name": "Lewis Hamilton", "last_name": "Hamilton", "points": 109.0}


@pytest.mark.integration
def test_a_race_winner_is_printed_by_f1dbs_name(champions_f1db):
    """Sainz Jr. won the 2024 Australian and Mexico City GPs; f1db's legal name ends "de Castro"."""
    winners = get_season_detail(2024)["race_winners"]

    assert [(row["round"], row["winner"]) for row in winners if row["driver_id"] == "carlos-sainz-jr"] == [
        (3, "Carlos Sainz Jr."),
        (20, "Carlos Sainz Jr."),
    ]


@pytest.mark.integration
def test_the_title_leaderboard_counts_fangios_five_under_his_f1db_name(champions_f1db):
    assert get_champion_stats()["most_driver_titles"][0] == {
        "name": "Juan Manuel Fangio",
        "last_name": "Fangio",
        "titles": 5,
    }


@pytest.mark.integration
def test_no_legal_name_reaches_any_champions_payload(champions_f1db):
    """The regression: f1db's ``full_name`` is the legal name, which the page cut to "Carlos Castro"."""
    served = _every_payload()
    legal_only = [full for _id, name, _first, _last, full, *_ in CHAMPION_SEASONS["drivers"] if full != name]

    assert "Juan Manuel Fangio Déramo" in legal_only
    assert "Carlos Sainz Vázquez de Castro" in legal_only
    assert [full for full in legal_only if full in served] == []
    assert "Carlos Sainz Jr." in served
    assert "Kimi Räikkönen" in served
