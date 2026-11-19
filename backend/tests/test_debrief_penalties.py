"""The debrief's penalty timeline on Mexico City 2026: race control's in-race penalties and the FIA's post-race ones."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from app.services import debrief_penalties as module, race_results
from tests.debrief_r19_support import race_session, rows
from tests.fia_documents_support import MEXICO_2026, hold

pytestmark = pytest.mark.unit


def _serve(monkeypatch, messages: list[dict] | None, *, session=True):
    monkeypatch.setattr(module, "new_client", nullcontext)
    monkeypatch.setattr(module, "find_session", lambda *_args: race_session() if session else None)
    monkeypatch.setattr(module, "get_json", lambda _client, path, _params: messages if path == "race_control" else [])


@pytest.fixture
def mexico(race_results_f1db, monkeypatch):
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    _serve(monkeypatch, rows("openf1_race_control.json"))


def _brief(row: dict, *keys: str) -> tuple:
    return tuple(row[key] for key in keys)


def test_mexico_in_race_penalties_are_the_four_served_ones(mexico, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    in_race = module.build_debrief_penalties(2026, 19)["in_race"]

    assert [_brief(row, "lap", "driver_code", "seconds", "offence", "served") for row in in_race] == [
        (12, "LEC", 5, "Leaving the track and gaining an advantage", True),
        (13, "RUS", 10, "Causing a collision", True),
        (46, "PER", 5, "Speeding in the pit lane", True),
        (51, "HUL", 10, "Causing a collision", True),
    ]
    assert in_race[0]["penalty"] == "5 second time penalty"
    # The test f1db holds no drivers table, so the name falls back to the code.
    assert in_race[0]["driver_name"] == "LEC"


def test_mexico_post_race_penalties_come_from_the_fia_final_classification(mexico, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    result = module.build_debrief_penalties(2026, 19)

    post = {row["driver_code"]: row for row in result["post_race"]}
    assert _brief(post["PIA"], "document", "seconds", "road_position", "position") == (79, 10, 7, 13)
    assert _brief(post["GAS"], "document", "seconds", "road_position", "position") == (84, 30, 10, 17)
    assert _brief(post["COL"], "document", "road_position", "position") == (85, 8, 15)
    assert [row["document"] for row in result["post_race"]] == sorted(row["document"] for row in result["post_race"])
    assert result["fia_document"] == {
        "number": 86,
        "url": MEXICO_2026["Doc 86 - Final Race Classification"]["url"],
    }


def test_without_the_fia_document_post_race_rows_come_from_the_time_penalties_f1db_lists(mexico):
    result = module.build_debrief_penalties(2026, 19)

    assert result["fia_document"] is None
    assert result["post_race"]
    assert all(row["document"] is None and row["reason"] is None for row in result["post_race"])
    assert all(row["ruling"] == f"{row['seconds']} second time penalty" for row in result["post_race"])


def _message(text: str, lap: int = 10) -> dict:
    return {"lap_number": lap, "message": text}


def test_an_investigation_a_no_further_action_and_a_flag_are_not_penalties(race_results_f1db, monkeypatch):
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    _serve(
        monkeypatch,
        [
            _message("FIA STEWARDS: TURN 4 INCIDENT INVOLVING CARS 63 (RUS) AND 1 (NOR) UNDER INVESTIGATION"),
            _message("FIA STEWARDS: NO FURTHER ACTION - INCIDENT INVOLVING CARS 63 (RUS) AND 1 (NOR)"),
            _message("BLACK AND WHITE FLAG FOR CAR 1 (NOR) - TRACK LIMITS"),
            {"lap_number": 3, "message": None},
        ],
    )

    assert module.build_debrief_penalties(2026, 19)["in_race"] == []


def test_a_served_message_without_a_time_matches_by_its_text(race_results_f1db, monkeypatch):
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    _serve(
        monkeypatch,
        [
            _message("FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 1 (NOR)", 5),
            _message("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 63 (RUS)", 6),
            _message("FIA STEWARDS: PENALTY SERVED - 10 SECOND TIME PENALTY FOR CAR 1 (NOR)", 20),
            _message("FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 3 (VER) - SPEEDING", 7),
        ],
    )

    in_race = module.build_debrief_penalties(2026, 19)["in_race"]

    assert [_brief(row, "driver_code", "served", "seconds", "offence") for row in in_race] == [
        ("NOR", True, 10, None),
        ("RUS", False, 5, None),
        ("VER", False, None, "Speeding"),
    ]


def test_a_post_race_row_the_race_already_penalised_is_dropped(mexico, monkeypatch):
    monkeypatch.setattr(
        module,
        "_changes",
        lambda _race: {
            "LEC": {"driver_name": "Charles Leclerc", "time_penalty": 5, "road_position": 3, "position": 4},
            "ALO": {"driver_name": "Fernando Alonso", "time_penalty": 10, "road_position": 9, "position": 10},
        },
    )

    post_race = module.build_debrief_penalties(2026, 19)["post_race"]

    assert [row["driver_code"] for row in post_race] == ["ALO"]


def test_no_race_session_is_unavailable(monkeypatch):
    _serve(monkeypatch, [], session=False)

    assert module.build_debrief_penalties(2026, 19) == {
        "available": False,
        "in_race": [],
        "post_race": [],
        "fia_document": None,
    }


def test_a_ruling_that_is_no_time_penalty_has_no_seconds_and_no_road_change(race_results_f1db, monkeypatch, tmp_path):
    monkeypatch.setattr(race_results, "openf1_session_result", lambda *_args: ([], {}))
    _serve(monkeypatch, [])
    hold(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "_changes", lambda _race: {})

    post_race = module.build_debrief_penalties(2026, 19)["post_race"]

    assert post_race
    assert all(row["road_position"] is None and row["position"] is None for row in post_race)
    assert module._seconds("Drive through penalty") is None
