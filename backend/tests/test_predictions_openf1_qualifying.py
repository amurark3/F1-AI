"""Tests for the qualifying classification read from OpenF1 (app.data.predictions.openf1_qualifying).

A post-qualifying call starts from the qualifying order. On 2026-11-11 production
could not build R20's: FastF1, its only source then, refuses every request past
500 an hour per process ("any API: 500 calls/h"), and F1's live-timing login
makes each FastF1 load spend a dozen of them on requests that fail. OpenF1's
``session_result`` is the first source ``docs/DATA_SOURCES.md`` names for a
classification, and it sits outside that budget.

The data is real (provenance in ``fixtures/sao_paulo_2026_r20/provenance.json``
and the module docstring of ``tests/sao_paulo_2026_support.py``):

* São Paulo 2026 (R20) qualifying: Câmara, car 51, set the 13th time.
* Mexico City 2026 (R19) qualifying: Lawson, car 30, was disqualified (FIA
  document 57); OpenF1 sends his row with no position.
"""

from __future__ import annotations

from dataclasses import replace
import json
from typing import TYPE_CHECKING

from fastf1.exceptions import RateLimitExceededError
import httpx
import pytest
import structlog

from app.data.canonical_names import CODE_UNRESOLVED
from app.data.openf1.sessions import entry_list
from app.data.predictions import openf1_qualifying as module
from app.data.predictions.openf1_qualifying import load_openf1_qualifying, qualifying_order
from tests.openf1_support import serve
from tests.roster_support import MEXICO, SAO_PAULO, weekend
from tests.sao_paulo_2026_support import CAMARA_NUMBER, QUALIFYING_SESSION_KEY, add_camara_to_f1db

if TYPE_CHECKING:
    from pathlib import Path

MEXICO_QUALIFYING_KEY = 11400
LAWSON_NUMBER = 30


def _rows(folder: Path, name: str) -> list[dict]:
    return json.loads((folder / name).read_text())


def _entries(folder: Path, key: int, rows: list[dict] | None = None) -> dict:
    """The session's cars as ``entry_list`` reads them from OpenF1's ``drivers`` rows."""
    served = rows if rows is not None else _rows(folder, "openf1_drivers_qualifying.json")
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=served))) as client:
        return entry_list(client, key)


def _r20_order(drivers: list[dict] | None = None) -> list[dict]:
    return qualifying_order(
        _rows(SAO_PAULO, "openf1_session_result_qualifying.json"),
        _entries(SAO_PAULO, QUALIFYING_SESSION_KEY, drivers),
        2026,
    )


def _at(order: list[dict], position: int) -> dict:
    return next(row for row in order if row["position"] == position)


def _r20_drivers_without_camaras_code() -> list[dict]:
    return [
        {**row, "name_acronym": None} if row["driver_number"] == CAMARA_NUMBER else row
        for row in _rows(SAO_PAULO, "openf1_drivers_qualifying.json")
    ]


# ---------------------------------------------------------------------------
# The order
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_r20_puts_camara_at_p13_in_a_full_22_car_order(identity_f1db):
    """Production's qualifying-day f1db (v2026.19.0) has never heard of him; OpenF1 codes his car."""
    order = _r20_order()

    assert [row["position"] for row in order] == list(range(1, 23))
    assert _at(order, 13) == {"driver_code": "CAM", "driver_name": "Rafael Camara", "team": "Haas", "position": 13}
    assert [row["driver_code"] for row in order[:5]] == ["NOR", "RUS", "ANT", "LEC", "LAW"]
    assert all(row["driver_code"].isalpha() and row["driver_code"].isupper() for row in order)


@pytest.mark.integration
def test_names_and_teams_are_f1dbs(identity_f1db):
    add_camara_to_f1db(identity_f1db)

    order = _r20_order()

    assert _at(order, 13)["driver_name"] == "Rafael Câmara"
    assert _at(order, 3) == {"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 3}
    assert _at(order, 5)["team"] == "Racing Bulls"


@pytest.mark.integration
def test_r19_a_qualifier_with_no_position_is_left_out(identity_f1db):
    """Lawson's disqualification (FIA doc 57) leaves his row without a position; the grid places him."""
    rows = _rows(MEXICO, "openf1_session_result_qualifying.json")

    order = qualifying_order(rows, _entries(MEXICO, MEXICO_QUALIFYING_KEY), 2026)

    assert next(row for row in rows if row["driver_number"] == LAWSON_NUMBER)["position"] is None
    assert [row["position"] for row in order] == list(range(1, 22))
    assert "LAW" not in {row["driver_code"] for row in order}
    assert _at(order, 1)["driver_code"] == "HAM"
    assert _at(order, 18)["driver_code"] == "HIR"


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["dsq", "dns"])
def test_a_disqualified_or_non_starting_car_is_left_out_even_with_a_position(identity_f1db, flag):
    rows = _rows(SAO_PAULO, "openf1_session_result_qualifying.json")
    flagged = [{**row, flag: True} if row["driver_number"] == CAMARA_NUMBER else row for row in rows]

    order = qualifying_order(flagged, _entries(SAO_PAULO, QUALIFYING_SESSION_KEY), 2026)

    assert len(order) == 21
    assert "CAM" not in {row["driver_code"] for row in order}


@pytest.mark.unit
def test_rows_without_a_car_number_or_a_whole_position_are_skipped(identity_f1db):
    rows = _rows(SAO_PAULO, "openf1_session_result_qualifying.json")
    broken = [{**rows[0], "driver_number": None}, {**rows[1], "position": 2.5}, *rows[2:]]

    order = qualifying_order(broken, _entries(SAO_PAULO, QUALIFYING_SESSION_KEY), 2026)

    assert [row["position"] for row in order] == list(range(3, 23))


@pytest.mark.integration
def test_a_car_openf1_sends_without_an_acronym_takes_f1dbs_code(identity_f1db):
    """The entry list prints a car with no acronym under its number; f1db v2026.20.0 knows car 51."""
    add_camara_to_f1db(identity_f1db)

    order = _r20_order(drivers=_r20_drivers_without_camaras_code())

    assert _at(order, 13) == {"driver_code": "CAM", "driver_name": "Rafael Câmara", "team": "Haas", "position": 13}


@pytest.mark.integration
def test_a_car_no_source_can_code_keeps_its_place_and_is_labelled(identity_f1db):
    with structlog.testing.capture_logs() as logs:
        order = _r20_order(drivers=_r20_drivers_without_camaras_code())

    assert len(order) == 22
    assert _at(order, 13) == {
        "driver_code": "",
        "driver_name": "Rafael Camara",
        "team": "Haas",
        "position": 13,
        CODE_UNRESOLVED: True,
        "driver_number": CAMARA_NUMBER,
    }
    assert [log for log in logs if log["event"] == "predictions.driver_code_unresolved"] == [
        {
            "event": "predictions.driver_code_unresolved",
            "log_level": "warning",
            "year": 2026,
            "number": CAMARA_NUMBER,
            "name": "Rafael Camara",
            "position": 13,
            "source": module.OPENF1_SOURCE,
        }
    ]


@pytest.mark.integration
def test_a_car_missing_from_the_entry_list_is_named_by_f1db(identity_f1db):
    add_camara_to_f1db(identity_f1db)
    drivers = [
        row for row in _rows(SAO_PAULO, "openf1_drivers_qualifying.json") if row["driver_number"] != CAMARA_NUMBER
    ]

    order = _r20_order(drivers=drivers)

    assert _at(order, 13) == {"driver_code": "CAM", "driver_name": "Rafael Câmara", "team": "", "position": 13}


# ---------------------------------------------------------------------------
# Reading OpenF1
# ---------------------------------------------------------------------------


@pytest.fixture
def openf1(monkeypatch, identity_f1db):
    """OpenF1 serving São Paulo 2026 qualifying, found the way the app finds it."""
    state = {
        "session": next(session for session in weekend(SAO_PAULO) if session.code == "Q"),
        "routes": {
            "session_result": _rows(SAO_PAULO, "openf1_session_result_qualifying.json"),
            "drivers": _rows(SAO_PAULO, "openf1_drivers_qualifying.json"),
        },
        "asked": [],
    }

    def _find_session(client, year, round_num, code):
        state["asked"].append((year, round_num, code))
        session = state["session"]
        if isinstance(session, Exception):
            raise session
        return session

    monkeypatch.setattr(module, "find_session", _find_session)
    state["fake"] = serve(monkeypatch, module, state["routes"])
    return state


@pytest.mark.integration
def test_the_weekends_qualifying_result_is_read_with_its_entry_list(openf1):
    order = load_openf1_qualifying(2026, 20)

    assert len(order) == 22
    assert _at(order, 13)["driver_code"] == "CAM"
    assert openf1["asked"] == [(2026, 20, "Q")]
    assert openf1["fake"].paths() == ["session_result", "drivers"]
    assert {request.url.params["session_key"] for request in openf1["fake"].requests} == {str(QUALIFYING_SESSION_KEY)}


@pytest.mark.unit
def test_a_round_openf1_does_not_list_has_no_order(openf1):
    openf1["session"] = None

    assert load_openf1_qualifying(2026, 20) == []
    assert openf1["fake"].paths() == []


@pytest.mark.unit
def test_a_session_that_has_not_finished_and_settled_is_not_read(openf1):
    # Read mid-session, the result would be a running order.
    openf1["session"] = replace(openf1["session"], date_end=None)

    assert load_openf1_qualifying(2026, 20) == []
    assert openf1["fake"].paths() == []


@pytest.mark.unit
def test_a_session_with_no_published_result_has_no_order(openf1):
    openf1["routes"].pop("session_result")

    assert load_openf1_qualifying(2026, 20) == []
    assert openf1["fake"].paths() == ["session_result"]


@pytest.mark.unit
def test_a_result_without_an_entry_list_is_not_trusted(openf1):
    # Car numbers alone would never match the entry list's codes.
    openf1["routes"].pop("drivers")

    assert load_openf1_qualifying(2026, 20) == []


@pytest.mark.unit
def test_a_live_lockout_costs_the_openf1_order_only(openf1):
    openf1["routes"]["session_result"] = httpx.Response(401, json={"detail": "live session"})

    with structlog.testing.capture_logs() as logs:
        assert load_openf1_qualifying(2026, 20) == []

    assert [log["event"] for log in logs] == ["predictions.openf1_qualifying_unavailable"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(RateLimitExceededError("any API: 500 calls/h"), id="fastf1-schedule-capped"),
        pytest.param(ValueError("no 2026 schedule"), id="no-schedule"),
        pytest.param(OSError("unreachable"), id="network"),
    ],
)
def test_a_failed_calendar_lookup_costs_the_openf1_order_only(openf1, error):
    """The meeting is found through FastF1's calendar, which FastF1's own request cap can refuse."""
    openf1["session"] = error

    assert load_openf1_qualifying(2026, 20) == []
    assert openf1["fake"].paths() == []
