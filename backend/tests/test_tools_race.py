"""Tests for app.api.tools.race — classification, head-to-head and anomalies.

Three tools the model reaches for when asked what happened in a race. None reads FastF1:
the classification is f1db's (OpenF1's until f1db holds the race) and the head-to-head is
OpenF1's laps. The risks are resolution-shaped and status-shaped rather than arithmetic-shaped:

* **A name has to resolve to the right driver.** The lookup is substring based so "Max"
  works, which also means a short or empty query can land on whoever is first in the entry list.
* **A retirement must not read as a place or a finishing time.** A car that did not finish
  reads DNF with its reason; its row carries no position and no time.
* **A missing sector is an unknown gap, not a dead heat.** Zero would show as the driver
  being level; the tools render a dash instead.

The rows are real: Mexico City 2026 (R19) from f1db v2026.20.0 (five retirements and time
penalties, ``fixtures/f1db_race_results``) and OpenF1's qualifying laps for the head-to-head
(``fixtures/qualifying_segments``). The grid slots in the race table are set by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.api.tools import provenance as provenance_module, race as module
from app.api.tools.race import compare_drivers, get_race_anomalies, get_race_results
from app.data.openf1 import session_laps
from app.services import race_results
from tests.fastf1_guard import no_fastf1  # noqa: F401
from tests.openf1_support import fresh_cache, make_session, serve

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_fastf1")]

FIXTURES = Path(__file__).parent / "fixtures"
QUALIFYING = FIXTURES / "qualifying_segments"
HAMILTON, RUSSELL = 44, 63


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def _round(monkeypatch: pytest.MonkeyPatch, number: int) -> None:
    monkeypatch.setattr(module, "resolve_event", lambda _year, _name: (number, "Mexican Grand Prix"))


# ---------------------------------------------------------------------------
# compare_drivers
# ---------------------------------------------------------------------------


@pytest.fixture
def mexico_qualifying(monkeypatch):
    """OpenF1 serving Mexico City 2026's qualifying (session 11400): laps, entry list, race control and result."""
    _round(monkeypatch, 19)
    state = {"laps": _load(QUALIFYING / "mexico_q_laps.json"), "session": make_session("Q")}
    monkeypatch.setattr(session_laps, "find_session", lambda *_args: state["session"])
    fresh_cache(monkeypatch, session_laps)
    serve(
        monkeypatch,
        session_laps,
        {
            "laps": lambda _request: httpx.Response(200, json=state["laps"]),
            "drivers": _load(FIXTURES / "mexico_2026_r19" / "openf1_drivers_qualifying.json"),
            "race_control": _load(QUALIFYING / "mexico_q_race_control.json"),
            "session_result": _load(QUALIFYING / "mexico_q_session_result.json"),
        },
    )
    return state


def _lap(laps: list[dict], driver: int, seconds: float) -> dict:
    return next(lap for lap in laps if lap["driver_number"] == driver and lap["lap_duration"] == seconds)


def test_hamilton_against_russell_gaps_are_openf1s_fastest_laps_sector_by_sector(mexico_qualifying):
    """Hamilton's 1:16.514 and Russell's 1:16.523 (their Q3 bests): the gap is the lap and sector arithmetic."""
    laps = mexico_qualifying["laps"]
    ham, rus = _lap(laps, HAMILTON, 76.514), _lap(laps, RUSSELL, 76.523)
    expected = [
        f"{ham[key] - rus[key]:+.3f}s"
        for key in ("lap_duration", "duration_sector_1", "duration_sector_2", "duration_sector_3")
    ]

    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "Hamilton", "driver2": "RUS"})

    lines = table.splitlines()
    assert lines[0] == "### Telemetry: Mexico 2026"
    assert lines[1] == "**HAM vs RUS**"
    assert lines[5] == f"| **TOTAL** | **{expected[0]}** | 🟢 Faster |"
    assert expected[0] == "-0.009s"
    for number, gap in enumerate(expected[1:], 1):
        assert lines[5 + number].startswith(f"| Sector {number} | {gap} |")


def test_a_name_matching_nobody_is_reported_rather_than_guessed(mexico_qualifying):
    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "Nobody", "driver2": "RUS"})

    assert result == "Could not find drivers 'Nobody' or 'RUS' in the entry list for Mexico 2026."


def test_a_driver_with_no_timed_lap_is_reported_rather_than_compared(mexico_qualifying):
    mexico_qualifying["laps"] = [lap for lap in mexico_qualifying["laps"] if lap["driver_number"] != HAMILTON]

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "HAM", "driver2": "RUS"})

    assert result == "No lap data found for HAM or RUS."


def test_a_missing_sector_is_shown_as_unknown_rather_than_level(mexico_qualifying):
    ham = _lap(mexico_qualifying["laps"], HAMILTON, 76.514)
    ham["duration_sector_2"] = None

    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "HAM", "driver2": "RUS"})

    assert "| Sector 2 | - | ⚪ |" in table


def test_a_round_with_no_qualifying_session_is_reported(mexico_qualifying):
    mexico_qualifying["session"] = None

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "HAM", "driver2": "RUS"})

    assert result == "No qualifying session found for Mexico 2026."


def test_a_comparison_failure_is_reported_rather_than_raised(monkeypatch):
    def refuse(_year, _name):
        raise ValueError("No 2026 Grand Prix matches 'Nowhere'")

    monkeypatch.setattr(module, "resolve_event", refuse)

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Nowhere", "driver1": "HAM", "driver2": "RUS"})

    assert result == "Comparison failed: No 2026 Grand Prix matches 'Nowhere'"


# ---------------------------------------------------------------------------
# get_race_results
# ---------------------------------------------------------------------------

GRID = {"VER": 3, "HAM": 1, "PIA": 8, "LIN": None}


@pytest.fixture
def mexico_race(race_results_f1db, monkeypatch):
    _round(monkeypatch, 19)
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    monkeypatch.setattr(module, "official_grid", lambda _year, _round: GRID)


def _row(table: str, code: str) -> str:
    return next(line for line in table.splitlines() if f"({code})" in line)


def test_the_classification_is_f1dbs_and_says_it_is_final(mexico_race):
    table = get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    lines = table.splitlines()
    assert lines[:2] == ["### Race Classification: Mexico 2026", "*(Source: the FIA final classification)*"]
    assert _row(table, "VER") == "| 🏆 1 | Max Verstappen (VER) | Red Bull | 3 | ⬆️2 | 2:20:28.772 | 25 |"
    assert _row(table, "HAM") == "| 2 | Lewis Hamilton (HAM) | Ferrari | 1 | ⬇️1 | +0.799 | 18 |"


def test_a_time_penalty_is_named_in_the_gap_and_the_place_change_is_from_the_grid(mexico_race):
    assert _row(get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"}), "PIA") == (
        "| 13 | Oscar Piastri (PIA) | McLaren | 8 | ⬇️5 | +29.475 (incl. 10s penalty) | 0 |"
    )


def test_a_car_with_no_published_slot_has_no_grid_and_no_change(mexico_race):
    assert _row(get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"}), "SAI") == (
        "| 12 | Carlos Sainz Jr. (SAI) | Williams | - | - | +28.638 | 0 |"
    )


def test_retirements_read_dnf_with_their_reason_never_a_place(mexico_race):
    table = get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    assert _row(table, "LIN") == "| DNF | Arvid Lindblad (LIN) | Racing Bulls | PL | - | ❌ DNF (Collision) | 0 |"
    assert _row(table, "STR") == "| DNF | Lance Stroll (STR) | Aston Martin | - | - | ❌ DNF (Engine) | 0 |"
    assert sum(" | DNF | " in f" {line}" for line in table.splitlines()) == 5
    assert not any(line.startswith("| 18 ") for line in table.splitlines())


def test_a_race_no_source_holds_says_so(mexico_race, monkeypatch):
    _round(monkeypatch, 21)

    assert get_race_results.invoke({"year": 2026, "grand_prix": "Brazil"}) == (
        "No race classification is published for Brazil 2026 yet."
    )


def test_a_race_results_failure_is_reported_rather_than_raised(monkeypatch):
    def refuse(_year, _name):
        raise ValueError("f1db is locked")

    monkeypatch.setattr(module, "resolve_event", refuse)

    assert (
        get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})
        == "Failed to fetch race results: f1db is locked"
    )


# ---------------------------------------------------------------------------
# get_race_anomalies
# ---------------------------------------------------------------------------


def _install_anomalies(monkeypatch, result):
    import app.services.anomaly as anomaly_module

    def _detect(year, round_num):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(anomaly_module, "detect_race_anomalies", _detect)


@pytest.mark.unit
def test_the_notable_stories_are_listed_as_bullets(monkeypatch):
    _install_anomalies(
        monkeypatch,
        {
            "available": True,
            "anomalies": [
                {"detail": "HAM gained 12 places from P18"},
                {"detail": "VER retired from the lead on lap 40"},
            ],
        },
    )

    lines = get_race_anomalies.invoke({"year": 2026, "round_num": 4}).splitlines()

    assert lines == [
        "### Notable stories — 2026 Round 4",
        "",
        "- HAM gained 12 places from P18",
        "- VER retired from the lead on lap 40",
    ]


@pytest.mark.unit
def test_a_race_with_nothing_notable_says_so_rather_than_returning_an_empty_header(monkeypatch):
    """An empty section would invite the model to invent stories to fill it."""
    _install_anomalies(monkeypatch, {"available": True, "anomalies": []})

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 4}) == (
        "### 2026 Round 4: no major anomalies — a clean, orderly race."
    )


@pytest.mark.unit
def test_a_race_that_has_not_run_is_reported_as_having_no_data(monkeypatch):
    _install_anomalies(monkeypatch, {"available": False, "anomalies": []})

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 22}) == (
        "No completed-race data available for 2026 Round 22."
    )


@pytest.mark.unit
def test_an_anomaly_failure_is_reported_rather_than_raised(monkeypatch):
    _install_anomalies(monkeypatch, RuntimeError("f1db is locked"))

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 4}) == "Anomaly analysis failed: f1db is locked"


# ---------------------------------------------------------------------------
# Provenance: the subject and chips each success carries; a failure stays plain text
# ---------------------------------------------------------------------------


@pytest.fixture
def version(monkeypatch):
    monkeypatch.setattr(provenance_module, "installed_version", lambda: "v2026.20.0")


def test_a_comparison_carries_its_event_and_source(mexico_qualifying):
    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Mexico", "driver1": "Hamilton", "driver2": "RUS"})

    assert table.provenance.subject == "Mexican Grand Prix 2026 qualifying"
    assert table.provenance.sources == ("OpenF1 laps · qualifying",)


def test_a_race_classification_names_its_sources_and_the_grid(mexico_race, version):
    table = get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    assert table.provenance.subject == "Mexican Grand Prix 2026"
    assert table.provenance.sources == ("f1db v2026.20.0", "f1db v2026.20.0 · starting grid")


def test_a_race_without_a_published_grid_has_no_grid_chip(mexico_race, version, monkeypatch):
    monkeypatch.setattr(module, "official_grid", lambda _year, _round: {})

    table = get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    assert table.provenance.sources == ("f1db v2026.20.0",)


def test_a_missing_race_has_no_provenance(mexico_race, monkeypatch):
    monkeypatch.setattr(module, "build_session_result", lambda *_args: None)

    assert type(get_race_results.invoke({"year": 2026, "grand_prix": "Mexico"})) is str


def test_the_anomalies_name_the_round_they_read(version, monkeypatch):
    _install_anomalies(monkeypatch, {"available": True, "anomalies": [{"detail": "HAM gained 12 places"}]})
    stories = get_race_anomalies.invoke({"year": 2026, "round_num": 4})
    _install_anomalies(monkeypatch, {"available": True, "anomalies": []})
    quiet = get_race_anomalies.invoke({"year": 2026, "round_num": 4})

    for result in (stories, quiet):
        assert result.provenance.subject == "2026 round 4"
        assert result.provenance.sources == ("f1db v2026.20.0 · R4 result",)
