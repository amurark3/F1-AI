"""Tests for the standings progression: every round's championship table and the round each title was won.

Read on the morning after Mexico 2026 (``tests/standings_support.mexico_feeds``):
f1db holds rounds 1-18 and the newest round is computed from OpenF1's points.
"""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import race_control as rc_router
from app.data import f1db_source
from app.data.f1db_calendar import CalendarUnavailableError
from app.services.race_control import progression, table_reach
from tests.roster_support import F1DB_2026, load
from tests.standings_support import (
    AFTER_ROUND_19,
    BASE_AND_ROUND_19,
    SEASON,
    Feeds,
    event,
    f1db_only,
    mexico_feeds,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.integration

SPRINT_ROUNDS = (2, 4, 5, 9, 12, 17)
EARLIER = load(F1DB_2026 / "standings_by_round.json")
ROUND_18 = load(F1DB_2026 / "standings_r18.json")


def _earlier_event(round_num: int) -> dict:
    return {
        **event(18),
        "round": round_num,
        "name": f"Round {round_num} Grand Prix",
        "location": f"Venue {round_num}, Country",
        "is_sprint": round_num in SPRINT_ROUNDS,
    }


SEASON_ALL = [_earlier_event(n) for n in range(1, 18)] + SEASON


def _install_earlier_rounds(path: Path) -> None:
    """Rounds 1-17 of f1db's published tables, and the decider columns the real schema has."""
    with closing(sqlite3.connect(path)) as conn:
        conn.executemany(
            "INSERT INTO race_driver_standing (race_id, driver_id, position_number, points) VALUES (?, ?, ?, ?)",
            EARLIER["driver_standings"],
        )
        conn.executemany(
            "INSERT INTO race_constructor_standing (race_id, constructor_id, position_number, points) "
            "VALUES (?, ?, ?, ?)",
            EARLIER["constructor_standings"],
        )
        conn.execute("ALTER TABLE race ADD COLUMN drivers_championship_decider INTEGER")
        conn.execute("ALTER TABLE race ADD COLUMN constructors_championship_decider INTEGER")
        conn.commit()


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    for module in (progression, table_reach):
        monkeypatch.setattr(module, "season_events", lambda _year: SEASON_ALL)
    for opened in mexico_feeds(tmp_path, monkeypatch):
        _install_earlier_rounds(f1db_source.DB_PATH)
        yield opened


def _no_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_year: int) -> list[dict]:
        raise CalendarUnavailableError("no calendar")

    for module in (progression, table_reach):
        monkeypatch.setattr(module, "season_events", refuse)


def _flag(*, drivers: bool, round_num: int) -> None:
    with closing(sqlite3.connect(f1db_source.DB_PATH)) as conn:
        if drivers:
            conn.execute("UPDATE race SET drivers_championship_decider = 1 WHERE round = ?", (round_num,))
        else:
            conn.execute("UPDATE race SET constructors_championship_decider = 1 WHERE round = ?", (round_num,))
        conn.commit()


def _entrant(payload: dict, table: str, key: str) -> dict:
    return next(row for row in payload[table]["entrants"] if row["key"] == key)


def test_each_round_reads_f1db_and_the_newest_is_the_computed_one(feeds):
    payload = progression.build_standings_progression(2026)

    assert [row["round"] for row in payload["rounds"]] == list(range(1, 20))
    antonelli = _entrant(payload, "drivers", "ANT")
    assert (antonelli["points"][17], antonelli["points"][18], antonelli["positions"][18]) == (365, 380, 1)
    assert _entrant(payload, "drivers", "VER")["points"][18] == 261
    assert payload["rounds"][17]["provisional"] is False
    assert payload["rounds"][18]["provisional"] is True
    assert {key: payload[key] for key in AFTER_ROUND_19} == AFTER_ROUND_19
    assert payload["sources"][:2] == BASE_AND_ROUND_19
    assert payload["rounds"][18]["name"] == "Round 19 Grand Prix"
    assert payload["rounds"][18]["location"] == "Venue 19, Country"


def test_every_f1db_round_matches_its_published_table(feeds):
    payload = progression.build_standings_progression(2026)
    codes = {row[0]: row[2] for row in ROUND_18["drivers"]}
    teams = {row[0]: row[1] for row in ROUND_18["constructors"]}
    drivers = [*EARLIER["driver_standings"], *([18, *row] for row in ROUND_18["driver_standings"])]
    constructors = [*EARLIER["constructor_standings"], *([18, *row] for row in ROUND_18["constructor_standings"])]
    for table, names, rows in (("drivers", codes, drivers), ("constructors", teams, constructors)):
        for round_num, entrant_id, position, points in rows:
            entrant = _entrant(payload, table, names[entrant_id])
            assert (entrant["points"][round_num - 1], entrant["positions"][round_num - 1]) == (points, position)


def test_a_driver_new_to_the_table_has_no_points_before_his_first_round(feeds):
    hirakawa = _entrant(progression.build_standings_progression(2026), "drivers", "HIR")

    assert hirakawa["points"][:18] == [None] * 18
    assert hirakawa["positions"][:18] == [None] * 18
    assert hirakawa["points"][18] == 1


def test_sprint_points_count_with_their_round(feeds):
    payload = progression.build_standings_progression(2026)

    assert payload["rounds"][16]["sprint"] is True
    assert payload["rounds"][17]["sprint"] is False
    assert _entrant(payload, "drivers", "ANT")["points"][16] == 340


def test_the_drivers_title_was_clinched_in_the_computed_round_19(feeds):
    drivers = progression.build_standings_progression(2026)["drivers"]

    assert drivers["clinched"] == {"round": 19, "races_left": 4, "sprints_left": 0}


def test_the_constructors_title_is_still_open_after_round_19(feeds):
    constructors = progression.build_standings_progression(2026)["constructors"]

    assert constructors["clinched"] is None
    assert [row["points"][-1] for row in constructors["entrants"][:4]] == [630, 504, 382, 365]


def test_a_round_f1db_marks_as_the_decider_is_the_clinch_round(feeds, monkeypatch):
    f1db_only(monkeypatch)
    # A synthetic flag: the real f1db flags 2026's drivers' decider at round 19.
    _flag(drivers=True, round_num=18)

    def refuse(*_args) -> None:
        raise AssertionError("f1db's own flag is the answer; the rule is not asked")

    monkeypatch.setattr(table_reach, "remaining_after", refuse)
    drivers = progression.build_standings_progression(2026)["drivers"]

    assert drivers["clinched"] == {"round": 18, "races_left": 5, "sprints_left": 0}


def test_without_a_calendar_the_series_stand_and_no_clinch_is_claimed(feeds, monkeypatch):
    _no_calendar(monkeypatch)
    payload = progression.build_standings_progression(2026)

    assert _entrant(payload, "drivers", "ANT")["points"][18] == 380
    assert [(row["name"], row["location"], row["sprint"]) for row in payload["rounds"]] == [(None, None, None)] * 19
    assert (payload["drivers"]["clinched"], payload["constructors"]["clinched"]) == (None, None)


def test_a_flagged_decider_without_a_calendar_has_no_counts(feeds, monkeypatch):
    _no_calendar(monkeypatch)
    _flag(drivers=False, round_num=18)
    clinched = progression.build_standings_progression(2026)["constructors"]["clinched"]

    assert clinched == {"round": 18, "races_left": None, "sprints_left": None}


def test_a_season_with_no_rounds_is_empty_not_an_error(feeds, monkeypatch):
    _no_calendar(monkeypatch)
    payload = progression.build_standings_progression(2027)

    assert payload["as_of_round"] is None
    assert payload["rounds"] == []
    assert (payload["drivers"]["entrants"], payload["constructors"]["entrants"]) == ([], [])
    assert payload["drivers"]["clinched"] is None
    assert "error" not in payload


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rc_router.router)
    return TestClient(app, raise_server_exceptions=False)


def test_the_progression_route_serves_the_builder(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_standings_progression", lambda year: {"year": year, "rounds": []})

    response = client.get("/race-control/standings/2026/progression")

    assert response.json() == {"year": 2026, "rounds": []}


def test_a_progression_failure_hides_the_exception_text(client, monkeypatch):
    def fail(_year: int) -> dict:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(rc_router, "build_standings_progression", fail)
    body = client.get("/race-control/standings/2026/progression").json()

    assert (body["year"], body["rounds"]) == (2026, [])
    assert body["error"]
    assert "error_id" in body
    assert "secret detail" not in str(body)
