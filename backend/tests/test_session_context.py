"""Part gaps, DSQ promotion tags and FP1 stand-ins, on Mexico City 2026's real f1db rows.

``mexico_2026_r19/f1db_session_rows.json`` is f1db v2026.20.0's qualifying, FP1
and race classifications for round 19, as the weekend payload builds them.
"""

import json
from pathlib import Path

import pytest

from app.services.session_context import annotate_qualifying, annotate_stand_ins, time_ms

pytestmark = pytest.mark.unit

ROWS = json.loads((Path(__file__).parent / "fixtures" / "mexico_2026_r19" / "f1db_session_rows.json").read_text())


def by_code(rows):
    return {row["driver_code"]: row for row in rows}


def regulars():
    teams: dict[str, list[tuple[str, str]]] = {}
    for row in [*ROWS["qualifying"], *ROWS["race"]]:
        drivers = teams.setdefault(row["team"], [])
        if all(code != row["driver_code"] for code, _ in drivers):
            drivers.append((row["driver_code"], row["driver_name"]))
    return teams


def test_time_ms_reads_minutes_and_seconds():
    assert time_ms("1:16.514") == 76514


def test_the_gap_is_inside_the_part_each_car_was_classified_in():
    rows = by_code(annotate_qualifying(ROWS["qualifying"]))

    # Norris's Q3 lap against pole: the official +0.310, not his faster Q2 lap against it.
    assert (rows["NOR"]["part"], rows["NOR"]["part_gap"]) == ("q3", "+0.310")
    assert rows["HAM"]["part_gap"] is None
    # Hulkenberg's gap is to the fastest Q2 lap, Albon's to the fastest Q1 lap.
    assert (rows["HUL"]["part"], rows["HUL"]["part_gap"]) == ("q2", "+0.578")
    assert (rows["ALB"]["part"], rows["ALB"]["part_gap"]) == ("q1", "+1.289")


def test_the_disqualified_car_has_no_gap_and_sets_no_benchmark():
    rows = by_code(annotate_qualifying(ROWS["qualifying"]))

    assert rows["LAW"]["position"] is None
    assert (rows["LAW"]["part"], rows["LAW"]["part_gap"]) == ("q3", None)


def test_only_the_two_cars_lifted_into_a_part_they_did_not_run_in_are_tagged():
    tagged = {code: row["promoted_by"] for code, row in by_code(annotate_qualifying(ROWS["qualifying"])).items()}

    assert {code: by for code, by in tagged.items() if by} == {"HUL": ["LAW"], "ALB": ["LAW"]}


def test_a_session_without_a_time_has_no_part():
    row = {"driver_code": "XXX", "position": 1, "position_text": "1", "q1": None, "q2": None, "q3": None}

    assert annotate_qualifying([row])[0] | {} == {**row, "part": None, "part_gap": None, "promoted_by": []}


def test_a_driver_without_a_classified_position_is_never_promoted():
    row = {"driver_code": "XXX", "position": None, "position_text": "NC", "q1": "1:20.000", "q2": None, "q3": None}

    assert annotate_qualifying([row])[0]["promoted_by"] == []


def test_fp1_stand_ins_name_whose_car_they_drove():
    rows = by_code(annotate_stand_ins(ROWS["fp1"], regulars()))

    assert rows["VES"]["stand_in_for"] == {"driver_code": "RUS", "driver_name": "George Russell"}
    assert rows["HER"]["stand_in_for"]["driver_code"] == "BOT"
    assert rows["HIR"]["stand_in_for"] is None  # raced in Mexico, so a regular
    assert [code for code, row in rows.items() if row["stand_in_for"]] == [
        "VES",
        "IWA",
        "TSO",
        "MIN",
        "FOR",
        "CRA",
        "BRO",
        "SLA",
        "HER",
    ]


def test_without_an_entry_list_nobody_is_called_a_stand_in():
    assert all(row["stand_in_for"] is None for row in annotate_stand_ins(ROWS["fp1"], {}))


def test_a_stand_in_for_a_team_with_no_absent_regular_names_no_car():
    rows = annotate_stand_ins(ROWS["fp1"], {"Mercedes": [("ANT", "Kimi Antonelli")]})

    assert by_code(rows)["VES"]["stand_in_for"] is None
