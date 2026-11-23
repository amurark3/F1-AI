"""Race Rewind's payload on the real R19 fixtures, its kept rows and its fallbacks."""

from __future__ import annotations

import pytest

from app.data.race_classification import (
    NO_CLASSIFICATION,
    OPENF1_SOURCE,
    RaceClassification,
    classification_from_openf1,
)
from app.services import debrief_overtakes, race_rewind
from tests.debrief_r19_support import entries, rows
from tests.rewind_r19_support import FIXTURE_BY_PATH, serve_mexico

pytestmark = pytest.mark.unit

FIA_ORDER = [
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
    "LIN",
    "BEA",
    "BOT",
    "STR",
    "ALO",
]
CODES = {number: entry.code for number, entry in entries().items()}


@pytest.fixture
def served(monkeypatch, tmp_path):
    return serve_mexico(monkeypatch, tmp_path)


@pytest.fixture
def payload(served):
    return race_rewind.build_race_rewind(2026, 19)


def final_row(payload, code):
    return next(row for row in payload["final"]["rows"] if row["driver_code"] == code)


def test_the_payload_describes_the_race(payload):
    assert payload["available"] is True
    assert payload["reason"] is None
    assert payload["total_laps"] == 71 == len(payload["laps"])
    assert len(payload["drivers"]) == 22
    ver = next(d for d in payload["drivers"] if d["driver_code"] == "VER")
    assert (ver["car"], ver["status"], ver["laps"]) == (3, "finished", 71)
    assert ver["driver_name"] == "Max Verstappen"
    assert payload["neutralisations"] == [
        {"kind": "vsc", "start_lap": 7, "end_lap": 8},
        {"kind": "sc", "start_lap": 44, "end_lap": 44},
        {"kind": "red", "start_lap": 45, "end_lap": 46},
        {"kind": "sc", "start_lap": 59, "end_lap": 62},
    ]
    assert payload["stops"][0] == {"driver_code": "ALO", "lap": 3}


def test_the_tracks_of_the_laps(payload):
    tracks = {lap["lap"]: lap["track"] for lap in payload["laps"]}
    assert (tracks[7], tracks[44], tracks[45], tracks[59], tracks[10]) == ("vsc", "sc", "red", "sc", None)


def test_the_grid_is_the_fia_final_starting_grid(payload):
    grid = payload["grid"]
    assert (grid["source"], grid["document"], grid["pit_lane"]) == ("fia_starting_grid", 67, ["LAW"])
    assert grid["order"][0] == "HAM"
    assert grid["order"][-1] == "LAW"


def test_the_final_step_is_the_fia_classification_car_for_car(payload):
    final = payload["final"]
    assert [row["driver_code"] for row in final["rows"]] == FIA_ORDER
    assert (final["source"], final["provisional"], final["document"]) == ("fia-final-classification", False, 86)
    assert final["url"].startswith("https://www.fia.com/")
    retired = [(row["driver_code"], row["status"], row["laps"]) for row in final["rows"][17:]]
    assert retired == [("LIN", "dnf", 58), ("BEA", "dnf", 47), ("BOT", "dnf", 42), ("STR", "dnf", 5), ("ALO", "dnf", 5)]


def test_the_post_race_penalties_carry_their_documents(payload):
    pia, gas, col, law = (final_row(payload, code) for code in ("PIA", "GAS", "COL", "LAW"))
    assert (pia["road_position"], pia["position"]) == (7, 13)
    assert [(n["seconds"], n["document"]) for n in pia["penalties"]] == [(10, 79)]
    assert (gas["road_position"], gas["position"]) == (10, 17)
    assert [(n["seconds"], n["document"]) for n in gas["penalties"]] == [(30, 84)]
    assert gas["penalties"][0]["ruling"] == "Stop and go penalty converted to 30 second time penalty"
    assert (col["road_position"], col["position"]) == (8, 15)
    assert [(n["seconds"], n["document"]) for n in col["penalties"]] == [(10, 85)]
    assert (law["road_position"], law["position"], law["penalties"]) == (9, 7, [])


def test_positions_and_overtakes_are_kept_once_the_race_has_settled(served, monkeypatch, payload):
    assert served.get(race_rewind.POSITIONS_KIND, "2026:19", 1)["rows"] == rows(FIXTURE_BY_PATH["position"])
    kept = served.get(debrief_overtakes.OVERTAKES_KIND, "2026:19", debrief_overtakes.OVERTAKES_VERSION)
    assert kept["rows"] == rows("openf1_overtakes.json")
    requested = []

    def pit_only(_client, path, _params):
        requested.append(path)
        return rows(FIXTURE_BY_PATH["pit"])

    monkeypatch.setattr(race_rewind, "get_json", pit_only)

    again = race_rewind.build_race_rewind(2026, 19)

    assert requested == ["pit"]
    assert again["laps"] == payload["laps"]


def test_nothing_is_kept_before_the_session_settles(served, monkeypatch):
    monkeypatch.setattr(race_rewind, "session_ended", lambda _session: False)

    race_rewind.build_race_rewind(2026, 19)

    assert served.get(race_rewind.POSITIONS_KIND, "2026:19", 1) is None
    assert served.get(debrief_overtakes.OVERTAKES_KIND, "2026:19", 1) is None


def test_an_empty_stream_is_never_kept(served, monkeypatch):
    monkeypatch.setattr(
        race_rewind, "get_json", lambda _c, path, _p: [] if path == "overtakes" else rows(FIXTURE_BY_PATH[path])
    )

    race_rewind.build_race_rewind(2026, 19)

    assert served.get(debrief_overtakes.OVERTAKES_KIND, "2026:19", 1) is None
    assert served.get(race_rewind.POSITIONS_KIND, "2026:19", 1) is not None


def test_no_classification_leaves_final_and_the_driver_status_empty(served, monkeypatch):
    monkeypatch.setattr(race_rewind, "race_classification", lambda *_a: NO_CLASSIFICATION)

    bare = race_rewind.build_race_rewind(2026, 19)

    assert bare["final"] is None
    assert {(d["status"], d["laps"]) for d in bare["drivers"]} == {(None, None)}


def test_an_openf1_classification_is_provisional_without_a_document_or_notes(served, monkeypatch):
    drivers = classification_from_openf1(rows("openf1_session_result.json"), CODES)
    monkeypatch.setattr(race_rewind, "race_classification", lambda *_a: RaceClassification(OPENF1_SOURCE, drivers))

    result = race_rewind.build_race_rewind(2026, 19)["final"]

    assert (result["source"], result["provisional"], result["document"], result["url"]) == (
        OPENF1_SOURCE,
        True,
        None,
        None,
    )
    assert all(row["penalties"] == [] for row in result["rows"])


def test_an_fia_source_without_its_document_carries_no_notes(payload, monkeypatch):
    monkeypatch.setattr(race_rewind, "final_classification", lambda *_a: None)

    result = race_rewind.build_race_rewind(2026, 19)["final"]

    assert (result["provisional"], result["document"], result["url"]) == (False, None, None)


def test_a_provisional_or_missing_grid_falls_back_to_openf1_positions(payload, monkeypatch):
    monkeypatch.setattr(race_rewind, "build_starting_grid", lambda *_a: {"available": False, "provisional": False})

    grid = race_rewind.build_race_rewind(2026, 19)["grid"]

    assert (grid["source"], grid["document"], grid["pit_lane"]) == ("openf1-position", None, [])
    assert grid["order"] == payload["grid"]["order"]


def test_the_official_f1db_grid_is_labelled_f1db(payload, monkeypatch):
    official = {
        "available": True,
        "provisional": False,
        "source": "official_grid",
        "fia_document": None,
        "grid": [
            {"driver_code": "VER", "position": 1, "pit_lane": False},
            {"driver_code": "LAW", "position": None, "pit_lane": True},
        ],
    }
    monkeypatch.setattr(race_rewind, "build_starting_grid", lambda *_a: official)

    grid = race_rewind.build_race_rewind(2026, 19)["grid"]

    assert grid == {"order": ["VER", "LAW"], "pit_lane": ["LAW"], "source": "f1db", "document": None}


def test_no_laps_is_unavailable_with_the_laps_reason(served, monkeypatch):
    monkeypatch.setattr(race_rewind, "load_session_laps", lambda *_a: None)

    result = race_rewind.build_race_rewind(2026, 19)

    assert (result["available"], result["reason"]) == (False, race_rewind.NO_LAPS_REASON)
    assert result["laps"] == []
    assert result["final"] is None
    assert result["grid"] is None


def test_no_position_rows_is_unavailable_with_the_positions_reason(served, monkeypatch):
    monkeypatch.setattr(race_rewind, "get_json", lambda *_a: [])

    result = race_rewind.build_race_rewind(2026, 19)

    assert (result["available"], result["reason"]) == (False, race_rewind.NO_POSITIONS_REASON)


def test_a_race_openf1_does_not_list_is_unavailable(served, monkeypatch):
    monkeypatch.setattr(race_rewind, "find_session", lambda *_a: None)

    assert race_rewind.build_race_rewind(2026, 19)["reason"] == race_rewind.NO_POSITIONS_REASON
