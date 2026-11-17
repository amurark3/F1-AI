"""Tests for the clinch builder: what each championship hangs on, race by race.

The integration tests read the morning after Mexico 2026 (``tests/standings_support.mexico_feeds``
plus rounds 1-17 from ``tests/progression_support``); the synthetic ones hand the builder small tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import race_control as rc_router
from app.services.race_control import clinch, progression, table_reach
from tests.progression_support import earlier_rounds_feeds
from tests.standings_support import AFTER_ROUND_19, BASE_AND_ROUND_19, event, standings_from_rows

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.standings_support import Feeds

pytestmark = pytest.mark.integration


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    yield from earlier_rounds_feeds(tmp_path, monkeypatch, (clinch, progression, table_reach))


def test_after_round_19_antonelli_clinched_at_round_19_provisionally(feeds):
    drivers = clinch.build_clinch(2026)["drivers"]

    assert drivers["decided"] is True
    assert drivers["leader"] == {"name": "Kimi Antonelli", "code": "ANT", "team": "Mercedes", "points": 380.0}
    assert (drivers["max_available"], drivers["next"], drivers["earliest"]) == (100, None, None)
    assert drivers["decided_at"] == {
        "round": 19,
        "name": "Round 19 Grand Prix",
        "venue": "Venue 19",
        "lead": 119.0,
        "left": 100,
        "races_to_spare": 4,
        "sprints_to_spare": 0,
        "provisional": True,
    }


def test_after_round_19_mercedes_can_clinch_at_round_20_by_outscoring_ferrari_by_3(feeds):
    constructors = clinch.build_clinch(2026)["constructors"]

    assert constructors == {
        "decided": False,
        "leader": {"name": "Mercedes", "code": None, "team": "Mercedes", "points": 630.0},
        "max_available": 172,
        "next": {
            "round": 20,
            "name": "Round 20 Grand Prix",
            "venue": "Venue 20",
            "races": 1,
            "sprints": 0,
            "max_points": 43,
            "possible": True,
            "needs": [{"name": "Ferrari", "code": None, "team": "Ferrari", "margin": 3.0, "countback": False}],
        },
        "earliest": {"round": 20, "name": "Round 20 Grand Prix", "venue": "Venue 20"},
        "decided_at": None,
    }


def test_the_payload_carries_the_tables_round_and_sources(feeds):
    payload = clinch.build_clinch(2026)

    assert payload["year"] == 2026
    assert {"as_of_round": payload["as_of_round"], "provisional": payload["provisional"]} == AFTER_ROUND_19
    assert payload["sources"][:2] == BASE_AND_ROUND_19


# --- synthetic tables ---------------------------------------------------------------


def _round(n: int, *, provisional: bool = False) -> dict:
    return {"round": n, "name": f"GP {n}", "location": f"City {n}, Land", "provisional": provisional}


def _prog(table: str, clinched: dict | None, points: list, *, rounds: tuple[dict, ...]) -> dict:
    entrants = [{"key": f"E{i}", "points": p} for i, p in enumerate(points)]
    return {"rounds": list(rounds), table: {"entrants": entrants, "clinched": clinched}}


def _drivers(*points: float) -> list[dict]:
    return [
        {"code": f"D{i}", "driver": f"Driver {i}", "team": "T", "points": p, "position": i}
        for i, p in enumerate(points, start=1)
    ]


def _teams(*points: float) -> list[dict]:
    return [{"team": f"Team {i}", "points": p, "position": i} for i, p in enumerate(points, start=1)]


def _events(*sprint_rounds: int, rounds: int = 3) -> list[dict]:
    out = []
    for n in range(1, rounds + 1):
        sessions = {"Race": f"2026-05-{n:02d}T14:00:00Z"}
        if n in sprint_rounds:
            sessions["Sprint"] = f"2026-05-{n:02d}T10:00:00Z"
        out.append(
            {
                **event(19),
                "round": n,
                "name": f"GP {n}",
                "location": f"City {n}, Land",
                "sessions": sessions,
                "is_sprint": n in sprint_rounds,
            }
        )
    return out


def _season(
    monkeypatch: pytest.MonkeyPatch,
    *,
    as_of: int,
    drivers: list[dict],
    teams: list[dict] | None = None,
    events: list[dict] | None = None,
    prog: dict | None = None,
    provisional: bool = False,
) -> None:
    standings = standings_from_rows(
        drivers, teams or [], as_of_round=as_of, provisional=provisional, sources=({"source": "f1db"},)
    )
    monkeypatch.setattr(clinch, "current_standings", lambda _year: standings)
    monkeypatch.setattr(clinch, "season_events", lambda _year: events if events is not None else _events())
    monkeypatch.setattr(clinch, "build_standings_progression", lambda _year: prog)


ROUNDS = (_round(1), _round(2), _round(3))
PROVISIONAL_THIRD = (_round(1), _round(2), _round(3, provisional=True))


def test_a_title_decided_at_the_final_round_has_nothing_to_spare(monkeypatch):
    # Round 1 has no points for the third entrant (a late arrival): a missing cell is skipped.
    points = [[1, 5, 100], [1, 4, 98], [None, None, 3]]
    prog = _prog("drivers", {"round": 3, "races_left": 0, "sprints_left": 0}, points, rounds=ROUNDS)
    _season(monkeypatch, as_of=3, drivers=_drivers(100, 98), prog=prog)

    drivers = clinch.build_clinch(2026)["drivers"]

    assert drivers["decided"] is True
    assert drivers["decided_at"] == {
        "round": 3,
        "name": "GP 3",
        "venue": "City 3",
        "lead": 2,
        "left": 0,
        "races_to_spare": 0,
        "sprints_to_spare": 0,
        "provisional": False,
    }


def test_a_clinch_at_a_round_f1db_holds_is_confirmed_under_a_provisional_table(monkeypatch):
    points = [[0, 90, 120], [0, 40, 60]]
    prog = _prog("drivers", {"round": 2, "races_left": 1, "sprints_left": 0}, points, rounds=PROVISIONAL_THIRD)
    _season(monkeypatch, as_of=3, drivers=_drivers(120, 60), provisional=True, prog=prog)

    decided_at = clinch.build_clinch(2026)["drivers"]["decided_at"]

    assert (decided_at["round"], decided_at["lead"], decided_at["left"]) == (2, 50, 25)
    assert (decided_at["races_to_spare"], decided_at["provisional"]) == (1, False)


def test_a_clinch_at_the_provisional_round_is_provisional(monkeypatch):
    points = [[0, 0, 120], [0, 0, 60]]
    prog = _prog("drivers", {"round": 3, "races_left": 0, "sprints_left": 0}, points, rounds=PROVISIONAL_THIRD)
    _season(monkeypatch, as_of=3, drivers=_drivers(120, 60), provisional=True, prog=prog)

    assert clinch.build_clinch(2026)["drivers"]["decided_at"]["provisional"] is True


@pytest.mark.parametrize("clinched", [None, {"round": 3, "races_left": None, "sprints_left": None}])
def test_an_unknown_clinch_round_leaves_decided_at_none(monkeypatch, clinched):
    prog = _prog("drivers", clinched, [[0, 0, 120], [0, 0, 60]], rounds=ROUNDS)
    _season(monkeypatch, as_of=3, drivers=_drivers(120, 60), prog=prog)

    drivers = clinch.build_clinch(2026)["drivers"]

    assert (drivers["decided"], drivers["decided_at"]) == (True, None)


def test_a_decided_constructors_title_reads_the_constructors_progression(monkeypatch):
    points = [[0, 0, 100], [0, 0, 40]]
    prog = _prog("constructors", {"round": 3, "races_left": 0, "sprints_left": 0}, points, rounds=ROUNDS)
    _season(monkeypatch, as_of=3, drivers=_drivers(100), teams=_teams(100, 40), prog=prog)

    constructors = clinch.build_clinch(2026)["constructors"]

    assert (constructors["decided"], constructors["decided_at"]["lead"]) == (True, 60)


def test_the_next_event_counts_its_sprint(monkeypatch):
    _season(monkeypatch, as_of=1, drivers=_drivers(100, 90), teams=_teams(200, 150), events=_events(2))

    payload = clinch.build_clinch(2026)

    assert (payload["drivers"]["next"]["races"], payload["drivers"]["next"]["sprints"]) == (1, 1)
    assert payload["drivers"]["next"]["max_points"] == 33
    assert payload["constructors"]["next"]["max_points"] == 58
    assert payload["drivers"]["max_available"] == 58
    assert payload["drivers"]["next"]["name"] == "GP 2"


def test_an_open_title_with_no_event_left_has_no_next_event(monkeypatch):
    _season(monkeypatch, as_of=3, drivers=_drivers(100, 100))

    drivers = clinch.build_clinch(2026)["drivers"]

    assert (drivers["decided"], drivers["next"], drivers["earliest"], drivers["decided_at"]) == (
        False,
        None,
        None,
        None,
    )


def test_a_title_that_cannot_be_settled_at_the_next_event_names_the_earliest(monkeypatch):
    _season(monkeypatch, as_of=0, drivers=_drivers(100, 99), events=_events(rounds=5))

    drivers = clinch.build_clinch(2026)["drivers"]

    assert drivers["next"]["possible"] is False
    assert drivers["earliest"] == {"round": 3, "name": "GP 3", "venue": "City 3"}


def test_seasons_before_2025_are_not_calculated(monkeypatch):
    def refuse(_year: int) -> None:
        raise AssertionError("an old season is not looked up")

    monkeypatch.setattr(clinch, "current_standings", refuse)

    assert clinch.build_clinch(2024) == {
        "year": 2024,
        "as_of_round": None,
        "provisional": False,
        "sources": [],
        "drivers": None,
        "constructors": None,
    }


@pytest.mark.parametrize("rows", [[], _drivers(50)])
def test_no_table_or_a_lone_entrant_has_no_title_state(monkeypatch, rows):
    _season(monkeypatch, as_of=1, drivers=rows, teams=[])

    payload = clinch.build_clinch(2026)

    assert (payload["drivers"], payload["constructors"]) == (None, None)


def test_a_table_where_nobody_has_scored_has_no_title_state(monkeypatch):
    _season(monkeypatch, as_of=1, drivers=_drivers(0, 0), teams=[])

    assert clinch.build_clinch(2026)["drivers"] is None


# --- the route ----------------------------------------------------------------------


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rc_router.router)
    return TestClient(app, raise_server_exceptions=False)


def test_the_clinch_route_serves_the_builder(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_clinch", lambda year: {"year": year, "drivers": None})

    assert client.get("/race-control/standings/2026/clinch").json() == {"year": 2026, "drivers": None}


def test_a_failed_clinch_is_an_error_envelope(client, monkeypatch):
    def fail(_year: int) -> dict:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(rc_router, "build_clinch", fail)
    body = client.get("/race-control/standings/2026/clinch").json()

    assert (body["year"], body["drivers"], body["constructors"]) == (2026, None, None)
    assert body["error"]
    assert "secret detail" not in str(body)
