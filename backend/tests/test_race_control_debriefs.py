"""Tests for app.services.race_control_debriefs: the debrief summary and the classification the championship reads.

The risks worth guarding:

* **Claiming a result before the race has run.** The classification is read only
  once the race's start plus three hours has passed.
* **A grid that is not official must not invent places gained.** A provisional
  grid or a qualifying-order stand-in leaves every car without a start.
* **A retirement is never a place.** A car that did not finish has no
  ``position`` and reads "DNF (Engine)", whatever the source lists it at.
* **A title is only announced at the round that decided it.**

No FastF1 request is made: the classification is f1db's (Mexico City 2026,
``fixtures/f1db_race_results``, five retirements), OpenF1's until f1db holds the
race. The calendar (``season_schedule``) is stubbed with real pandas rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.services import race_control_debriefs as module, race_results
from tests.fastf1_guard import no_fastf1  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_fastf1")

_NOW = datetime.now(UTC).replace(tzinfo=None)


def _schedule(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _event(round_number: int, race_time: datetime | None, *, name: str = "Monaco Grand Prix") -> dict:
    """One schedule row whose fifth session is the Grand Prix itself."""
    return {
        "RoundNumber": round_number,
        "EventName": name,
        "Location": "Monte Carlo",
        "Country": "Monaco",
        "Session5": "Race",
        "Session5DateUtc": pd.Timestamp(race_time) if race_time is not None else pd.NaT,
    }


def _stub_calendar(monkeypatch: pytest.MonkeyPatch, schedule: pd.DataFrame) -> list[int]:
    """Serve a fixed schedule; returns the years it was asked for."""
    requested: list[int] = []

    def _season_schedule(year: int) -> pd.DataFrame:
        requested.append(year)
        return schedule

    monkeypatch.setattr(module, "season_schedule", _season_schedule)
    return requested


# ---------------------------------------------------------------------------
# load_race_classification
# ---------------------------------------------------------------------------

MEXICO = _event(19, _NOW - timedelta(days=2), name="Mexican Grand Prix")
GRID = {"VER": 3, "HAM": 1, "ANT": 2, "LIN": None}


@pytest.fixture
def mexico(race_results_f1db, monkeypatch: pytest.MonkeyPatch):
    """f1db's Mexico City 2026 race, two days on, with a hand-set grid (a pit-lane start for Lindblad)."""
    _stub_calendar(monkeypatch, _schedule([MEXICO]))
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    monkeypatch.setattr(module, "official_grid", lambda _year, _round: GRID)


@pytest.mark.unit
def test_an_unknown_round_returns_an_error_without_reading_a_classification(monkeypatch: pytest.MonkeyPatch):
    asked = _stub_calendar(monkeypatch, _schedule([_event(1, _NOW - timedelta(days=7))]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: pytest.fail("a result was read"))

    result = module.load_race_classification(2024, 99)

    assert result == {"error": "Round 99 not found for 2024", "race_results": [], "podium": []}
    assert asked == [2024]


@pytest.mark.unit
def test_a_race_still_in_the_future_returns_the_event_shell_only(monkeypatch: pytest.MonkeyPatch):
    _stub_calendar(monkeypatch, _schedule([_event(3, _NOW + timedelta(days=2))]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: pytest.fail("a result was read"))

    result = module.load_race_classification(2024, 3)

    assert result == {
        "round": 3,
        "name": "Monaco Grand Prix",
        "location": "Monte Carlo, Monaco",
        "race_results": [],
        "podium": [],
    }


@pytest.mark.unit
def test_a_race_inside_the_three_hour_window_is_not_yet_classified(monkeypatch: pytest.MonkeyPatch):
    """The result is only read three hours after lights out, not at lights out."""
    _stub_calendar(monkeypatch, _schedule([_event(3, _NOW - timedelta(hours=1))]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: pytest.fail("a result was read"))

    assert module.load_race_classification(2024, 3)["race_results"] == []


@pytest.mark.unit
def test_an_event_with_no_race_session_date_is_never_loaded(monkeypatch: pytest.MonkeyPatch):
    _stub_calendar(monkeypatch, _schedule([_event(3, None)]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: pytest.fail("a result was read"))

    assert module.load_race_classification(2024, 3)["race_results"] == []


@pytest.mark.unit
def test_a_race_no_source_holds_yet_returns_the_event_shell(monkeypatch: pytest.MonkeyPatch):
    _stub_calendar(monkeypatch, _schedule([_event(3, _NOW - timedelta(days=1))]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: None)

    result = module.load_race_classification(2024, 3)

    assert (result["race_results"], result["podium"], "final" in result) == ([], [], False)


@pytest.mark.integration
def test_mexico_is_read_from_f1db_in_finishing_order_with_a_podium_and_provenance(mexico):
    result = module.load_race_classification(2026, 19)

    rows = result["race_results"]
    assert [row["driver"] for row in rows][:4] == ["VER", "HAM", "ANT", "LEC"]
    assert [row["driver"] for row in result["podium"]] == ["VER", "HAM", "ANT"]
    assert rows[0] == {
        "position": 1,
        "driver": "VER",
        "full_name": "Max Verstappen",
        "team": "Red Bull",
        "grid": 3,
        "points": 25.0,
        "status": "Finished",
    }
    assert result["final"] is True
    assert result["sources"][0]["source"] == "f1db"


@pytest.mark.integration
def test_retirements_have_no_place_a_reason_and_stay_off_the_podium(mexico):
    rows = module.load_race_classification(2026, 19)["race_results"]

    retired = [row for row in rows if row["status"] != "Finished"]
    assert [(row["driver"], row["position"], row["status"]) for row in retired] == [
        ("LIN", None, "DNF (Collision)"),
        ("BEA", None, "DNF (Collision damage)"),
        ("BOT", None, "DNF (Accident)"),
        ("STR", None, "DNF (Engine)"),
        ("ALO", None, "DNF (Engine)"),
    ]
    assert set(rows[-1]) == {"position", "driver", "full_name", "team", "grid", "points", "status"}


@pytest.mark.integration
def test_a_pit_lane_start_and_a_car_the_grid_does_not_list_record_no_grid_slot(mexico):
    rows = {row["driver"]: row for row in module.load_race_classification(2026, 19)["race_results"]}

    assert (rows["LIN"]["grid"], rows["LEC"]["grid"]) == (None, None)


@pytest.mark.unit
def test_a_status_with_no_reason_reads_as_the_status_alone():
    assert module._status_text({"status": "DSQ", "reason": None}) == "DSQ"
    assert module._status_text({"status": "DNF", "reason": "Engine"}) == "DNF (Engine)"


# ---------------------------------------------------------------------------
# build_race_debrief
# ---------------------------------------------------------------------------

DOC = {"number": 74, "final": True, "url": "https://fia.example/doc74"}
RACE = {
    "final": True,
    "sources": [{"source": "f1db", "role": "classification"}],
    "classification": [
        {"driver_code": "VER", "position": 1},
        {"driver_code": "LIN", "position": None},
        {"driver_code": "LEC", "position": 3},
    ],
}


def _grid(*, available: bool = True, provisional: bool = False) -> dict:
    return {
        "available": available,
        "provisional": provisional,
        "fia_document": DOC,
        "grid": [
            {"driver_code": "VER", "position": 3, "pit_lane": False},
            {"driver_code": "LIN", "position": None, "pit_lane": True},
        ],
    }


def _progression(*, clinched_at: int | None = 19, constructors_at: int | None = None, runner_up: bool = True) -> dict:
    entrants = [
        {"key": "ant", "name": "Kimi Antonelli", "team": "Mercedes", "points": [None, 380]},
        {"key": "ham", "name": "Lewis Hamilton", "team": "Ferrari", "points": [None, 261]},
        {"key": "ver", "name": "Max Verstappen", "team": "Red Bull", "points": [10, None]},
    ]
    teams = [
        {"key": "mer", "name": "Mercedes", "team": "Mercedes", "points": [None, 500]},
        {"key": "fer", "name": "Ferrari", "team": "Ferrari", "points": [None, 400]},
    ]
    return {
        "rounds": [{"round": 18, "provisional": False}, {"round": 19, "provisional": True}],
        "drivers": {
            "entrants": entrants if runner_up else entrants[:1],
            "clinched": None if clinched_at is None else {"round": clinched_at, "races_left": 4},
        },
        "constructors": {
            "entrants": teams,
            "clinched": None if constructors_at is None else {"round": constructors_at, "races_left": 0},
        },
    }


@pytest.fixture
def summary(monkeypatch: pytest.MonkeyPatch):
    """Everything the summary reads, stubbed; each test overrides what it varies."""
    _stub_calendar(monkeypatch, _schedule([MEXICO]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: RACE)
    monkeypatch.setattr(module, "build_starting_grid", lambda *_args: _grid())
    monkeypatch.setattr(module, "build_standings_progression", lambda _year: _progression())


@pytest.mark.unit
def test_the_summary_merges_the_official_grid_into_each_classification_row(summary):
    result = module.build_race_debrief(2026, 19)

    assert (result["available"], result["reason"], result["final"], result["race"]) == (
        True,
        None,
        True,
        "Mexican Grand Prix",
    )
    assert result["location"] == "Monte Carlo, Monaco"
    assert result["sources"] == RACE["sources"]
    assert [(row["driver_code"], row["grid"], row["pit_lane"]) for row in result["classification"]] == [
        ("VER", 3, False),
        ("LIN", None, True),
        ("LEC", None, False),
    ]
    assert result["grid"] == {"available": True, "fia_document": DOC}


@pytest.mark.unit
@pytest.mark.parametrize("grid", [_grid(available=False), _grid(provisional=True)])
def test_a_grid_that_is_missing_or_provisional_gives_no_starts(summary, monkeypatch, grid):
    monkeypatch.setattr(module, "build_starting_grid", lambda *_args: grid)

    result = module.build_race_debrief(2026, 19)

    assert all(row["grid"] is None and row["pit_lane"] is False for row in result["classification"])
    assert result["grid"] == {"available": False, "fia_document": None}


@pytest.mark.unit
def test_the_drivers_title_clinched_here_carries_the_points_and_the_lead(summary):
    assert module.build_race_debrief(2026, 19)["titles"] == [
        {
            "table": "drivers",
            "name": "Kimi Antonelli",
            "team": "Mercedes",
            "points": 380,
            "lead": 119,
            "runner_up": "Lewis Hamilton",
            "races_left": 4,
            "provisional": True,
        }
    ]


@pytest.mark.unit
def test_the_constructors_title_is_listed_after_the_drivers(summary, monkeypatch):
    monkeypatch.setattr(module, "build_standings_progression", lambda _year: _progression(constructors_at=19))

    titles = module.build_race_debrief(2026, 19)["titles"]

    assert [(title["table"], title["name"], title["lead"], title["races_left"]) for title in titles] == [
        ("drivers", "Kimi Antonelli", 119, 4),
        ("constructors", "Mercedes", 100, 0),
    ]


@pytest.mark.unit
def test_a_title_clinched_at_another_round_or_not_yet_is_not_announced(summary, monkeypatch):
    for clinched_at in (18, None):
        monkeypatch.setattr(
            module, "build_standings_progression", lambda _year, at=clinched_at: _progression(clinched_at=at)
        )
        assert module.build_race_debrief(2026, 19)["titles"] == []


@pytest.mark.unit
def test_a_round_the_standings_do_not_cover_has_no_titles(summary, monkeypatch):
    monkeypatch.setattr(module, "build_standings_progression", lambda _year: {"rounds": []})

    assert module.build_race_debrief(2026, 19)["titles"] == []


@pytest.mark.unit
def test_a_lone_entrant_champion_has_no_runner_up(summary, monkeypatch):
    monkeypatch.setattr(module, "build_standings_progression", lambda _year: _progression(runner_up=False))

    title = module.build_race_debrief(2026, 19)["titles"][0]

    assert (title["lead"], title["runner_up"]) == (None, None)


@pytest.mark.unit
def test_a_race_nothing_has_classified_yet_says_so(summary, monkeypatch):
    monkeypatch.setattr(module, "build_session_result", lambda *_args: None)

    result = module.build_race_debrief(2026, 19)

    assert (result["available"], result["reason"], result["classification"], result["titles"]) == (
        False,
        "The race hasn't been classified yet.",
        [],
        [],
    )
    assert result["race"] == "Mexican Grand Prix"


@pytest.mark.unit
def test_a_race_still_to_run_is_not_read(monkeypatch):
    _stub_calendar(monkeypatch, _schedule([_event(3, _NOW + timedelta(days=2))]))
    monkeypatch.setattr(module, "build_session_result", lambda *_args: pytest.fail("a result was read"))

    result = module.build_race_debrief(2026, 3)

    assert (result["available"], result["reason"]) == (False, "The race hasn't been classified yet.")


@pytest.mark.unit
def test_an_unknown_round_is_unavailable_with_its_reason(monkeypatch):
    _stub_calendar(monkeypatch, _schedule([MEXICO]))

    result = module.build_race_debrief(2026, 99)

    assert (result["available"], result["reason"], result["race"], result["location"]) == (
        False,
        "Round 99 not found for 2026",
        "Round 99",
        "",
    )
