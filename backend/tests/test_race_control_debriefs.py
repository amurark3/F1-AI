"""Tests for app.services.race_control_debriefs — post-race notes.

The debrief is the one Race Control screen that makes narrative claims ("won
from P5, the clearest execution gain"), so the tests pin the sentences, not
just the shapes. The risks worth guarding:

* **Claiming a result before the race has run.** ``load_race_classification``
  gates on the session time plus three hours; loading early would publish a
  half-populated classification as final.
* **Grid deltas read the wrong way round.** Gains and losses are the same
  subtraction with opposite signs — a flipped sign praises the driver who lost
  the most places.
* **A missing grid slot must disable the comparison, not default to zero.**
  Pit-lane starts arrive as grid 0/NaN.
* **A retirement is never a place.** A car that did not finish has no
  ``position`` and reads "DNF (Engine)", whatever the source lists it at.
* **Names are f1db's.** The classification, and every sentence built from it,
  prints "Kimi Antonelli" and "Racing Bulls".

No FastF1 request is made: the classification is f1db's (Mexico City 2026,
``fixtures/f1db_race_results``, five retirements), OpenF1's until f1db holds the
race. The calendar (``season_schedule``) is stubbed with real pandas rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.services import race_control_debriefs as module, race_results
from app.services.race_control_debriefs import DebriefSections
from tests.fastf1_guard import no_fastf1  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_fastf1")

_NOW = datetime.now(UTC).replace(tzinfo=None)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _result_row(
    driver: str,
    *,
    position: int | None,
    grid: int | None,
    team: str = "Red Bull",
    points: float = 0.0,
    status: str = "Finished",
    full_name: str | None = None,
) -> dict:
    return {
        "position": position,
        "driver": driver,
        "full_name": full_name if full_name is not None else f"{driver} Driver",
        "team": team,
        "grid": grid,
        "points": points,
        "status": status,
    }


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


def _label(notes: list[dict], label: str) -> str | None:
    return next((note["detail"] for note in notes if note["label"] == label), None)


# ---------------------------------------------------------------------------
# build_debrief_headline
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_headline_without_a_winner_says_the_classification_is_missing():
    assert module.build_debrief_headline({}, None, []) == "Race classification is not available yet."


@pytest.mark.unit
def test_a_winner_who_started_first_is_described_as_converting_track_position():
    winner = _result_row("VER", position=1, grid=1, full_name="Max Verstappen")

    headline = module.build_debrief_headline({"name": "Monaco Grand Prix"}, winner, [])

    assert headline == ("Max Verstappen converted pole or track position into the race win at Monaco Grand Prix.")


@pytest.mark.unit
def test_an_unnamed_event_still_produces_a_readable_headline():
    winner = _result_row("VER", position=1, grid=1, full_name="Max Verstappen")

    headline = module.build_debrief_headline({}, winner, [])

    assert headline.endswith("into the race win at the Grand Prix.")


@pytest.mark.unit
@pytest.mark.parametrize(("grid", "expected"), [(2, "gaining 1 place"), (9, "gaining 8 places")])
def test_a_winner_from_further_back_reports_the_places_gained(grid: int, expected: str):
    winner = _result_row("VER", position=1, grid=grid, full_name="Max Verstappen")

    headline = module.build_debrief_headline({"name": "Monaco Grand Prix"}, winner, [])

    assert headline == f"Max Verstappen won from P{grid}, {expected} against the starting grid."


@pytest.mark.unit
def test_a_winner_with_no_grid_slot_falls_back_to_the_points_scored():
    winner = _result_row("VER", position=1, grid=None, points=25.0, full_name="Max Verstappen")

    headline = module.build_debrief_headline({}, winner, [])

    assert headline == "Max Verstappen led the final classification and banked 25 points for Red Bull."


@pytest.mark.unit
def test_a_winner_with_neither_grid_nor_points_only_claims_the_classification():
    winner = {"full_name": "Max Verstappen", "position": 1, "grid": None, "points": 0}

    assert module.build_debrief_headline({}, winner, []) == "Max Verstappen topped the final classification."


# ---------------------------------------------------------------------------
# build_debrief_takeaways
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_results_produce_no_takeaways():
    assert module.build_debrief_takeaways([], []) == []


@pytest.mark.unit
def test_takeaways_cover_podium_gains_losses_and_the_points_haul():
    results = [
        _result_row("NOR", position=1, grid=3, team="McLaren", points=25.0),
        _result_row("PIA", position=2, grid=1, team="McLaren", points=18.0),
        _result_row("VER", position=3, grid=2, points=15.0),
        _result_row("HAM", position=18, grid=6, team="Ferrari", status="Accident"),
    ]
    podium = results[:3]

    takeaways = module.build_debrief_takeaways(results, podium)

    assert takeaways == [
        "McLaren placed 2 cars on the podium, shaping the main points swing.",
        "NOR Driver gained 2 positions from the grid, the clearest strategy or execution gain.",
        "HAM Driver lost 12 positions versus the grid, flagging a compromised race branch.",
        "McLaren scored the strongest constructor haul with 43 points.",
    ]


@pytest.mark.unit
def test_takeaways_are_capped_at_four_entries():
    """A fifth reliability line exists but must not push the list past four."""
    results = [
        _result_row("NOR", position=1, grid=3, team="McLaren", points=25.0),
        _result_row("HAM", position=18, grid=6, team="Ferrari", status="Accident"),
    ]

    takeaways = module.build_debrief_takeaways(results, results[:1])

    assert len(takeaways) == 4
    assert not any("non-standard finish statuses" in line for line in takeaways)


@pytest.mark.unit
def test_a_single_car_podium_uses_singular_wording():
    results = [_result_row("VER", position=1, grid=1, points=25.0)]

    takeaways = module.build_debrief_takeaways(results, results)

    assert takeaways[0] == "Red Bull placed 1 car on the podium, shaping the main points swing."


@pytest.mark.unit
def test_reliability_is_reported_when_there_is_room_for_it():
    results = [
        _result_row("VER", position=None, grid=1, status="Engine"),
        _result_row("HAM", position=None, grid=2, team="Ferrari", status="Accident"),
    ]

    takeaways = module.build_debrief_takeaways(results, [])

    assert takeaways == [
        "2 cars had non-standard finish statuses, so reliability and incident exposure mattered.",
    ]


@pytest.mark.unit
def test_a_lone_retirement_uses_singular_wording():
    results = [_result_row("VER", position=None, grid=1, status="Engine")]

    assert module.build_debrief_takeaways(results, [])[0].startswith("1 car had non-standard")


@pytest.mark.unit
def test_lapped_finishers_are_not_treated_as_reliability_problems():
    """A lapped car is classified "Finished" (its laps down are a gap, not a status): not an incident."""
    results = [_result_row("VER", position=15, grid=15, status="Finished")]

    assert not any("non-standard" in line for line in module.build_debrief_takeaways(results, []))


@pytest.mark.unit
def test_a_pointless_race_does_not_claim_a_constructor_haul():
    results = [_result_row("VER", position=1, grid=1, points=0.0)]

    assert not any("constructor haul" in line for line in module.build_debrief_takeaways(results, []))


@pytest.mark.unit
def test_rows_without_a_grid_slot_are_excluded_from_the_movement_comparison():
    results = [_result_row("VER", position=1, grid=None, points=25.0)]

    takeaways = module.build_debrief_takeaways(results, [])

    assert not any("gained" in line or "lost" in line for line in takeaways)


@pytest.mark.unit
def test_a_grid_faithful_field_reports_neither_a_gain_nor_a_loss():
    results = [
        _result_row("VER", position=1, grid=1, points=25.0),
        _result_row("NOR", position=2, grid=2, team="McLaren", points=18.0),
    ]

    takeaways = module.build_debrief_takeaways(results, [])

    assert takeaways == ["Red Bull scored the strongest constructor haul with 25 points."]


@pytest.mark.unit
def test_a_driver_without_a_full_name_is_reported_by_code():
    results = [
        _result_row("VER", position=1, grid=5, points=25.0, full_name=""),
        _result_row("NOR", position=10, grid=2, team="McLaren", full_name=""),
    ]

    takeaways = module.build_debrief_takeaways(results, [])

    assert takeaways[0].startswith("VER gained 4 positions")
    assert takeaways[1].startswith("NOR lost 8 positions")


@pytest.mark.unit
def test_results_without_a_team_key_bucket_into_unknown():
    takeaways = module.build_debrief_takeaways([{"points": 25.0}], [{"points": 25.0}])

    assert takeaways[0].startswith("Unknown placed 1 car on the podium")
    assert takeaways[1] == "Unknown scored the strongest constructor haul with 25 points."


# ---------------------------------------------------------------------------
# build_podium_cause
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_podium_cause_labels_each_step_of_the_grid_delta():
    podium = [
        _result_row("VER", position=1, grid=1, points=25.0),
        _result_row("NOR", position=2, grid=5, team="McLaren", points=18.0),
        _result_row("LEC", position=3, grid=2, team="Ferrari", points=15.0),
    ]

    rows = module.build_podium_cause(podium)

    assert [row["call"] for row in rows] == [
        "Converted starting position",
        "Made up 3 places",
        "Lost 1 place but held podium",
    ]
    assert [row["delta"] for row in rows] == [0, 3, -1]


@pytest.mark.unit
def test_podium_cause_uses_singular_wording_for_a_one_place_gain():
    podium = [_result_row("NOR", position=2, grid=3, team="McLaren", points=18.0)]

    assert module.build_podium_cause(podium)[0]["call"] == "Made up 1 place"


@pytest.mark.unit
def test_podium_cause_uses_plural_wording_for_a_multi_place_loss():
    podium = [_result_row("NOR", position=3, grid=1, team="McLaren", points=15.0)]

    assert module.build_podium_cause(podium)[0]["call"] == "Lost 2 places but held podium"


@pytest.mark.unit
def test_a_podium_finisher_with_no_grid_slot_gets_no_invented_delta():
    podium = [_result_row("NOR", position=2, grid=None, team="McLaren", points=18.0)]

    row = module.build_podium_cause(podium)[0]

    assert row["delta"] is None
    assert row["call"] == "Classification result"


@pytest.mark.unit
def test_podium_cause_falls_back_to_the_driver_code_for_a_missing_full_name():
    podium = [{"position": 1, "driver": "VER", "team": "Red Bull", "grid": 1}]

    row = module.build_podium_cause(podium)[0]

    assert row["full_name"] == "VER"
    assert row["points"] == 0


@pytest.mark.unit
def test_an_empty_podium_produces_no_cause_rows():
    assert module.build_podium_cause([]) == []


# ---------------------------------------------------------------------------
# build_constructor_impact
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_constructor_impact_ranks_by_points_and_counts_classified_cars():
    results = [
        _result_row("NOR", position=2, grid=1, team="McLaren", points=18.0),
        _result_row("PIA", position=4, grid=4, team="McLaren", points=12.0),
        _result_row("VER", position=1, grid=2, points=25.0),
        _result_row("LAW", position=None, grid=8, points=0.0, status="Engine"),
    ]

    impact = module.build_constructor_impact(results)

    assert impact == [
        {"team": "McLaren", "points": 30.0, "classified_cars": 2},
        {"team": "Red Bull", "points": 25.0, "classified_cars": 1},
    ]


@pytest.mark.unit
def test_teams_that_scored_nothing_are_left_out_of_the_impact_table():
    results = [
        _result_row("VER", position=1, grid=1, points=25.0),
        _result_row("BOT", position=12, grid=14, team="Sauber", points=0.0),
    ]

    assert [row["team"] for row in module.build_constructor_impact(results)] == ["Red Bull"]


@pytest.mark.unit
def test_constructor_impact_is_capped_at_six_teams():
    results = [
        _result_row(f"D{index}", position=index, grid=index, team=f"Team {index}", points=float(20 - index))
        for index in range(1, 11)
    ]

    impact = module.build_constructor_impact(results)

    assert len(impact) == 6
    assert [row["team"] for row in impact] == [f"Team {index}" for index in range(1, 7)]


@pytest.mark.unit
def test_no_results_produce_no_constructor_impact():
    assert module.build_constructor_impact([]) == []


# ---------------------------------------------------------------------------
# build_race_control_notes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_race_control_notes_summarise_every_populated_section():
    podium = [
        _result_row("VER", position=1, grid=2, points=25.0),
        _result_row("NOR", position=2, grid=1, team="McLaren", points=18.0),
    ]
    sections = DebriefSections(
        podium=podium,
        movers=[_result_row("HUL", position=6, grid=15, team="Haas", points=8.0)],
        constructor_impact=[{"team": "Red Bull", "points": 25.0, "classified_cars": 1}],
        reliability=[_result_row("LAW", position=None, grid=8, status="Engine")],
    )

    notes = module.build_race_control_notes(podium, sections)

    assert [note["label"] for note in notes] == [
        "Podium shape",
        "Execution swing",
        "Constructor haul",
        "Reliability / incidents",
    ]
    assert _label(notes, "Podium shape") == "P1 VER, P2 NOR"
    assert _label(notes, "Execution swing") == "HUL Driver gained 9 places from the grid."
    assert _label(notes, "Constructor haul") == "Red Bull led the points take with 25 points."
    assert _label(notes, "Reliability / incidents") == "1 non-standard finish status in classification."


@pytest.mark.unit
def test_multiple_retirements_pluralise_the_status_note():
    sections = DebriefSections(
        podium=[],
        movers=[],
        constructor_impact=[],
        reliability=[
            _result_row("LAW", position=None, grid=8, status="Engine"),
            _result_row("HAM", position=None, grid=4, team="Ferrari", status="Accident"),
        ],
    )

    notes = module.build_race_control_notes([{"position": 1}], sections)

    assert _label(notes, "Reliability / incidents") == "2 non-standard finish statuses in classification."


@pytest.mark.unit
def test_an_empty_classification_produces_only_the_awaiting_note():
    sections = DebriefSections(podium=[], movers=[], constructor_impact=[], reliability=[])

    notes = module.build_race_control_notes([], sections)

    assert notes == [
        {
            "label": "Awaiting classification",
            "detail": "Final race classification has not been published or loaded yet.",
        }
    ]


@pytest.mark.unit
def test_a_mover_without_a_full_name_is_named_by_code_in_the_notes():
    sections = DebriefSections(
        podium=[],
        movers=[_result_row("HUL", position=6, grid=15, team="Haas", full_name="")],
        constructor_impact=[],
        reliability=[],
    )

    notes = module.build_race_control_notes([{"position": 6}], sections)

    assert _label(notes, "Execution swing") == "HUL gained 9 places from the grid."


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


@pytest.mark.unit
def test_the_debrief_assembles_every_section_from_one_classification(
    monkeypatch: pytest.MonkeyPatch,
):
    results = [
        _result_row("VER", position=1, grid=3, points=25.0),
        _result_row("NOR", position=2, grid=1, team="McLaren", points=18.0),
        _result_row("LEC", position=3, grid=2, team="Ferrari", points=15.0),
        _result_row("HUL", position=6, grid=16, team="Haas", points=8.0),
        _result_row("LAW", position=None, grid=8, team="RB", status="Engine"),
    ]
    monkeypatch.setattr(
        module,
        "load_race_classification",
        lambda year, round_num: {
            "round": round_num,
            "name": "Monaco Grand Prix",
            "location": "Monte Carlo, Monaco",
            "race_results": results,
            "podium": results[:3],
        },
    )

    debrief = module.build_race_debrief(2024, 3)

    assert debrief["year"] == 2024
    assert debrief["round"] == 3
    assert debrief["race"] == "Monaco Grand Prix"
    assert debrief["location"] == "Monte Carlo, Monaco"
    assert debrief["headline"].startswith("VER Driver won from P3, gaining 2 places")
    # Ranked by grid gain (+10, +2), then the two -1 rows in classification order.
    assert [row["driver"] for row in debrief["strategy_winners"]] == ["HUL", "VER", "NOR"]
    assert [row["driver"] for row in debrief["reliability_watch"]] == ["LAW"]
    assert debrief["constructor_impact"][0]["team"] == "Red Bull"
    assert [note["label"] for note in debrief["race_control_notes"]] == [
        "Podium shape",
        "Execution swing",
        "Constructor haul",
        "Reliability / incidents",
    ]
    assert debrief["incidents"] == []
    assert debrief["insight_source"].startswith("Derived from race classification")


@pytest.mark.unit
def test_the_debrief_caps_its_classification_and_reliability_lists(
    monkeypatch: pytest.MonkeyPatch,
):
    results = [
        _result_row(f"D{index}", position=index, grid=index, team=f"Team {index}", points=1.0) for index in range(1, 13)
    ] + [
        _result_row(f"R{index}", position=None, grid=index, team=f"Team {index}", status="Engine")
        for index in range(1, 8)
    ]
    monkeypatch.setattr(
        module,
        "load_race_classification",
        lambda year, round_num: {"race_results": results, "podium": results[:3]},
    )

    debrief = module.build_race_debrief(2024, 3)

    assert len(debrief["classification"]) == 10
    assert len(debrief["reliability_watch"]) == 5


@pytest.mark.unit
def test_a_debrief_for_an_unraced_round_says_so_without_inventing_sections(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        module,
        "load_race_classification",
        lambda year, round_num: {"race_results": [], "podium": []},
    )

    debrief = module.build_race_debrief(2025, 7)

    assert debrief["race"] == "Round 7"
    assert debrief["location"] == ""
    assert debrief["headline"] == "Race classification is not available yet."
    assert debrief["podium"] == []
    assert debrief["takeaways"] == []
    assert debrief["strategy_winners"] == []
    assert debrief["constructor_impact"] == []
    assert debrief["race_control_notes"] == [
        {
            "label": "Awaiting classification",
            "detail": "Final race classification has not been published or loaded yet.",
        }
    ]


# ---------------------------------------------------------------------------
# Names and the debrief built from the real classification
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_the_debrief_sentences_name_drivers_and_teams_as_f1db_does(mexico):
    debrief = module.build_race_debrief(2026, 19)

    assert [row["full_name"] for row in debrief["podium"]] == ["Max Verstappen", "Lewis Hamilton", "Kimi Antonelli"]
    assert debrief["headline"] == "Max Verstappen won from P3, gaining 2 places against the starting grid."
    assert {row["team"] for row in debrief["constructor_impact"]} >= {"Red Bull", "Ferrari", "Mercedes"}


@pytest.mark.integration
def test_the_debrief_lists_every_retirement_with_its_reason_and_carries_its_source(mexico):
    debrief = module.build_race_debrief(2026, 19)

    assert [row["status"] for row in debrief["reliability_watch"]] == [
        "DNF (Collision)",
        "DNF (Collision damage)",
        "DNF (Accident)",
        "DNF (Engine)",
        "DNF (Engine)",
    ]
    assert debrief["final"] is True
    assert debrief["sources"][0]["source"] == "f1db"
