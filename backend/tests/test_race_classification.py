"""Tests for a race's classification (app.data.race_classification).

The classification is the only source allowed to say who finished. Inferring it
from laps or stints labelled Lindblad's Mexico 2026 retirement on lap 58 "ran to
the flag", so every status here is read from a published result: OpenF1's
``session_result`` first, Jolpica's results when OpenF1 cannot answer.

The R19 fixtures are the real responses captured on 2 Nov 2026 (session_key
11404). OpenF1 matched FIA document 86, the final classification; Jolpica still
carried the pre-penalty order.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app.data import race_classification as module
from app.data.race_classification import (
    ClassifiedDriver,
    RaceClassification,
    classification_from_jolpica,
    classification_from_openf1,
    race_classification,
)
from tests.openf1_support import make_session, serve

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
R19_FINISHERS = [
    "VER",
    "HAM",
    "ANT",
    "LEC",
    "NOR",
    "RUS",
    "LAW",
    "BOR",
    "HAD",
    "HIR",
    "ALB",
    "SAI",
    "PIA",
    "HUL",
    "COL",
    "PER",
    "GAS",
]
R19_RETIREMENTS = {"LIN": 58, "BEA": 47, "BOT": 42, "STR": 5, "ALO": 5}


def fixture(name: str) -> list | dict:
    return json.loads((FIXTURES / name).read_text())


def r19_codes() -> dict[int, str]:
    return {row["driver_number"]: row["name_acronym"] for row in fixture("openf1_drivers.json")}


def jolpica_records() -> list[dict]:
    """The Jolpica rows as FastF1's Ergast client flattens them."""
    return [
        {
            "number": int(row["number"]),
            "position": int(row["position"]),
            "positionText": row["positionText"],
            "points": float(row["points"]),
            "grid": int(row["grid"]),
            "laps": int(row["laps"]),
            "status": row["status"],
            "driverCode": row["Driver"]["code"],
        }
        for row in fixture("jolpica_results.json")["Results"]
    ]


def by_code(classification: tuple[ClassifiedDriver, ...]) -> dict[str, ClassifiedDriver]:
    return {driver.driver_code: driver for driver in classification}


# --- OpenF1 session_result ---------------------------------------------------------


def test_mexico_2026_retirements_are_dnf_with_the_laps_they_completed():
    drivers = by_code(classification_from_openf1(fixture("openf1_session_result.json"), r19_codes()))

    for code, laps in R19_RETIREMENTS.items():
        assert (drivers[code].status, drivers[code].laps_completed, drivers[code].position) == ("dnf", laps, None)
    assert [code for code, driver in drivers.items() if driver.status == "finished"] == R19_FINISHERS
    assert all(drivers[code].laps_completed == 71 for code in R19_FINISHERS)


def test_mexico_2026_is_in_the_fia_order_with_retirements_last():
    """FIA document 86 put Lawson 7th, Piastri 13th and Gasly 17th after penalties."""
    order = [
        driver.driver_code for driver in classification_from_openf1(fixture("openf1_session_result.json"), r19_codes())
    ]

    assert order == [*R19_FINISHERS, "LIN", "BEA", "BOT", "STR", "ALO"]


def openf1_row(number: int, position: int | None, laps: int, **flags: bool) -> dict:
    return {
        "driver_number": number,
        "position": position,
        "number_of_laps": laps,
        "dnf": flags.get("dnf", False),
        "dns": flags.get("dns", False),
        "dsq": flags.get("dsq", False),
    }


@pytest.mark.parametrize(
    ("row", "status"),
    [
        (openf1_row(1, None, 0, dns=True), "dns"),
        (openf1_row(1, None, 71, dsq=True), "dsq"),
        (openf1_row(1, None, 40), "not_classified"),
        (openf1_row(1, 3, 71), "finished"),
    ],
    ids=["did not start", "disqualified", "not classified", "finished"],
)
def test_each_openf1_flag_reads_as_its_status(row, status):
    assert classification_from_openf1([row], {1: "NOR"})[0].status == status


def test_a_classified_retirement_keeps_both_facts():
    # Stopped after 90% distance: classified 15th, and still a retirement.
    driver = classification_from_openf1([openf1_row(1, 15, 65, dnf=True)], {1: "NOR"})[0]

    assert (driver.position, driver.status, driver.laps_completed) == (15, "dnf", 65)


def test_unclassified_cars_sort_by_laps_with_disqualifications_last():
    rows = [
        openf1_row(3, None, 71, dsq=True),
        openf1_row(2, None, 5, dnf=True),
        openf1_row(1, None, 40, dnf=True),
        openf1_row(4, 1, 71),
    ]

    order = [d.driver_code for d in classification_from_openf1(rows, {1: "A", 2: "B", 3: "C", 4: "D"})]

    assert order == ["D", "A", "B", "C"]


def test_a_car_missing_from_the_entry_list_keeps_its_number():
    assert classification_from_openf1([openf1_row(99, 1, 71)], {})[0].driver_code == "99"


def test_rows_without_a_driver_number_are_skipped():
    assert classification_from_openf1([{"position": 1, "number_of_laps": 71}], {}) == ()


def test_unrecorded_laps_are_unknown_not_zero():
    row = {"driver_number": 1, "position": 1, "number_of_laps": None}

    assert classification_from_openf1([row], {1: "NOR"})[0].laps_completed is None


# --- Jolpica results ---------------------------------------------------------------


def test_mexico_2026_from_jolpica_reads_the_same_statuses():
    drivers = by_code(classification_from_jolpica(jolpica_records()))

    for code, laps in R19_RETIREMENTS.items():
        assert (drivers[code].status, drivers[code].laps_completed, drivers[code].position) == ("dnf", laps, None)
    assert sorted(code for code, d in drivers.items() if d.status == "finished") == sorted(R19_FINISHERS)


def test_jolpica_keeps_its_published_order_even_when_it_lags_the_fia():
    # Jolpica had not applied the post-race penalties: Piastri still 7th.
    order = [d.driver_code for d in classification_from_jolpica(jolpica_records())]

    assert order[6] == "PIA"
    assert order[-5:] == ["LIN", "BEA", "BOT", "STR", "ALO"]


def jolpica_row(position_text: str, status: str = "Finished", laps: object = 71, position: int = 1) -> dict:
    return {"driverCode": "NOR", "position": position, "positionText": position_text, "laps": laps, "status": status}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (jolpica_row("D", "Disqualified"), ("dsq", None)),
        (jolpica_row("E", "Excluded"), ("dsq", None)),
        (jolpica_row("W", "Did not start", 0), ("dns", None)),
        (jolpica_row("F", "Did not qualify", 0), ("dns", None)),
        (jolpica_row("N", "Not classified", 40), ("not_classified", None)),
        (jolpica_row("R", "Accident", 12), ("dnf", None)),
        (jolpica_row("15", "Engine", 65, 15), ("dnf", 15)),
        (jolpica_row("12", "+1 Lap", 70, 12), ("finished", 12)),
        (jolpica_row("12", "Lapped", 70, 12), ("finished", 12)),
        (jolpica_row("1", "Finished"), ("finished", 1)),
        (jolpica_row("?", "Unknown"), ("not_classified", None)),
    ],
    ids=[
        "disqualified",
        "excluded",
        "withdrawn",
        "failed to qualify",
        "not classified",
        "retired",
        "classified retirement",
        "one lap down",
        "lapped",
        "finished",
        "unknown position text",
    ],
)
def test_each_jolpica_position_text_reads_as_its_status(row, expected):
    driver = classification_from_jolpica([row])[0]

    assert (driver.status, driver.position) == expected


def test_jolpica_missing_laps_are_unknown():
    assert classification_from_jolpica([jolpica_row("1", laps=float("nan"))])[0].laps_completed is None


def test_jolpica_rows_without_a_code_are_skipped():
    assert classification_from_jolpica([{**jolpica_row("1"), "driverCode": float("nan")}]) == ()


# --- where the classification comes from -------------------------------------------


class FakeErgast:
    def __init__(self, state: dict) -> None:
        self.state = state

    def get_race_results(self, season: int, round: int) -> SimpleNamespace:  # noqa: A002 - FastF1's keyword
        self.state["jolpica_calls"] += 1
        if self.state["jolpica_error"] is not None:
            raise self.state["jolpica_error"]
        records = self.state["jolpica"]
        return SimpleNamespace(content=[pd.DataFrame(records)] if records else [])


@pytest.fixture
def sources(monkeypatch):
    """OpenF1 serving the R19 race, Jolpica serving its results, and an empty cache."""
    monkeypatch.setattr(module, "_cache", {})
    state = {
        "session": make_session("R"),
        "routes": {
            "session_result": fixture("openf1_session_result.json"),
            "drivers": fixture("openf1_drivers.json"),
        },
        "jolpica": jolpica_records(),
        "jolpica_error": None,
        "jolpica_calls": 0,
        "now": 1000.0,
    }
    monkeypatch.setattr(module, "find_session", lambda client, year, rnd, code: state["session"])
    monkeypatch.setattr(module, "Ergast", lambda: FakeErgast(state))
    monkeypatch.setattr(module.time, "monotonic", lambda: state["now"])
    state["openf1"] = serve(monkeypatch, module, state["routes"])
    return state


def test_openf1_answers_first(sources):
    result = race_classification(2026, 19)

    assert result.source == module.OPENF1_SOURCE
    assert result.drivers[6].driver_code == "LAW"
    assert sources["jolpica_calls"] == 0


def test_jolpica_answers_when_openf1_has_no_result(sources):
    sources["routes"].pop("session_result")

    result = race_classification(2026, 19)

    assert result.source == module.JOLPICA_SOURCE
    assert by_code(result.drivers)["LIN"].status == "dnf"


def test_jolpica_answers_while_openf1_is_locked_out(sources):
    sources["routes"]["session_result"] = httpx.Response(401, json={"detail": "live"})

    assert race_classification(2026, 19).source == module.JOLPICA_SOURCE


def test_a_race_openf1_cannot_find_falls_back(sources):
    sources["session"] = None

    assert race_classification(2026, 19).source == module.JOLPICA_SOURCE


def test_a_race_still_running_is_not_read_from_openf1(sources):
    # A classification read mid-race would be a running order, not a result.
    sources["session"] = make_session("R", ended=False)
    sources["jolpica"] = []

    assert race_classification(2026, 19) == module.NO_CLASSIFICATION
    assert "session_result" not in sources["openf1"].paths()


def test_a_result_without_an_entry_list_is_not_trusted(sources):
    # Numbers alone would never match the stints' driver codes.
    sources["routes"].pop("drivers")

    assert race_classification(2026, 19).source == module.JOLPICA_SOURCE


def test_neither_source_answering_is_no_classification(sources):
    sources["routes"].pop("session_result")
    sources["jolpica_error"] = OSError("jolpica unreachable")

    result = race_classification(2026, 19)

    assert result == RaceClassification(source=None, drivers=())


def test_an_ergast_error_is_no_classification(sources):
    sources["routes"].pop("session_result")
    sources["jolpica_error"] = module.ErgastError("bad response")

    assert race_classification(2026, 19) == module.NO_CLASSIFICATION


def test_an_answer_is_served_from_cache_within_its_lifetime(sources):
    race_classification(2026, 19)
    sources["routes"].pop("session_result")
    sources["now"] += module.CLASSIFICATION_TTL_SECONDS - 1

    assert race_classification(2026, 19).source == module.OPENF1_SOURCE


def test_an_answer_is_read_again_once_it_expires(sources):
    """Post-race penalties change a result after it is first published."""
    race_classification(2026, 19)
    sources["routes"].pop("session_result")
    sources["now"] += module.CLASSIFICATION_TTL_SECONDS + 1

    assert race_classification(2026, 19).source == module.JOLPICA_SOURCE


def test_no_answer_is_retried_after_a_short_window(sources):
    sources["session"] = None
    sources["jolpica"] = []
    assert race_classification(2026, 19) == module.NO_CLASSIFICATION
    calls = sources["jolpica_calls"]

    race_classification(2026, 19)
    assert sources["jolpica_calls"] == calls

    sources["now"] += module.EMPTY_RETRY_SECONDS + 1
    sources["session"] = make_session("R")
    assert race_classification(2026, 19).source == module.OPENF1_SOURCE
