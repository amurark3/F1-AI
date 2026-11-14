"""Tests for the graded call (app.data.predictions.graded).

A race can hold several stored calls of both phases, and every number that
grades the model (rolling accuracy, the adaptive corrections, the post-mortem, a
review that names no phase) has to score the same one: the latest
post-qualifying call when the race has one, else its latest pre-qualifying call.

The failure this file pins is R20 São Paulo's. A manual pre-qualifying
recompute 16 s after the post-qualifying call (2026-11-08 00:45:59) became the
"latest" call, so the race was graded on VER P2 instead of the VER P8 the site
showed. The fixture is that entry, copied from production's history backup.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.data.predictions.graded import CALL_FIELDS, graded_call, legacy_call, with_graded_fields

FIXTURES = Path(__file__).parent / "fixtures"
R20_POST_QUALIFYING_AT = "2026-11-08T00:45:43.688379+00:00"


def _history_entry(edition: str) -> dict:
    return json.loads((FIXTURES / edition / "prediction_history_entry.json").read_text(encoding="utf-8"))["entry"]


@pytest.fixture
def r20() -> dict:
    return _history_entry("sao_paulo_2026_r20")


@pytest.fixture
def r19() -> dict:
    return _history_entry("mexico_2026_r19")


def _call(phase: str | None, at: str, ver: int) -> dict:
    return {
        "generated_at": at,
        "prediction_phase": phase,
        "data_sources": [phase or "legacy"],
        "predicted_positions": {"VER": ver},
        "risk_predictions": {"VER": {"dnf_risk_pct": ver}},
    }


# ---------------------------------------------------------------------------
# graded_call
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_r20_grades_the_post_qualifying_call_not_the_pre_qualifying_one_16_s_later(r20):
    phases = [(item["prediction_phase"], item["generated_at"]) for item in r20["snapshots"]]
    # The shape that broke it: post-qualifying, then pre-qualifying 16 s later.
    assert phases[4:6] == [
        ("post_qualifying", R20_POST_QUALIFYING_AT),
        ("pre_qualifying", "2026-11-08T00:45:59.289535+00:00"),
    ]
    assert r20["prediction_phase"] == "pre_qualifying"

    call = graded_call(r20)

    assert call["prediction_phase"] == "post_qualifying"
    assert call["generated_at"] == R20_POST_QUALIFYING_AT
    assert call["predicted_positions"]["VER"] == 8
    assert len(call["predicted_positions"]) == 22


@pytest.mark.unit
def test_the_latest_post_qualifying_call_wins_over_an_earlier_one():
    entry = {
        "snapshots": [
            _call("post_qualifying", "t1", 3),
            _call("pre_qualifying", "t2", 5),
            _call("post_qualifying", "t3", 4),
        ]
    }

    assert graded_call(entry)["generated_at"] == "t3"


@pytest.mark.unit
def test_a_race_without_a_post_qualifying_call_grades_its_latest_pre_qualifying_one():
    entry = {"snapshots": [_call("pre_qualifying", "t1", 3), _call("pre_qualifying", "t2", 5)]}

    assert graded_call(entry)["predicted_positions"] == {"VER": 5}


@pytest.mark.unit
def test_a_pre_qualifying_call_wins_over_a_later_one_with_no_phase():
    entry = {"snapshots": [_call("pre_qualifying", "t1", 3), _call(None, "t2", 9)]}

    assert graded_call(entry)["generated_at"] == "t1"


@pytest.mark.unit
def test_calls_stored_before_phases_existed_grade_the_latest_one():
    entry = {"snapshots": [{"predicted_positions": {"VER": 10}}, {"predicted_positions": {"VER": 2}}]}

    assert graded_call(entry) == {"predicted_positions": {"VER": 2}}


@pytest.mark.unit
def test_an_entry_without_snapshots_grades_its_top_level_fields():
    entry = {**_call("post_qualifying", "t1", 4), "actual_positions": {"VER": 1}}

    assert graded_call(entry) == _call("post_qualifying", "t1", 4)


@pytest.mark.unit
def test_anything_that_is_not_a_call_is_ignored():
    entry = {"snapshots": ["corrupt", None, _call("pre_qualifying", "t1", 6)], "predicted_positions": {"VER": 1}}

    assert graded_call(entry)["predicted_positions"] == {"VER": 6}


@pytest.mark.unit
def test_the_legacy_call_reads_absent_fields_as_empty_collections():
    assert legacy_call({}) == {
        "generated_at": None,
        "prediction_phase": None,
        "data_sources": [],
        "predicted_positions": {},
        "risk_predictions": {},
    }


# ---------------------------------------------------------------------------
# with_graded_fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_r20s_top_level_fields_become_its_post_qualifying_call(r20):
    original = copy.deepcopy(r20)
    post = r20["snapshots"][4]

    repaired = with_graded_fields(r20)

    assert {field: repaired[field] for field in CALL_FIELDS} == {field: post[field] for field in CALL_FIELDS}
    assert repaired["predicted_positions"]["VER"] == 8
    # The calls and the recorded result are carried over untouched.
    for field in ("snapshots", "actual_positions", "actual_statuses", "actual_incidents"):
        assert repaired[field] == original[field]
    assert r20 == original, "the entry handed in is never mutated"


@pytest.mark.unit
def test_an_entry_already_holding_its_graded_call_comes_back_equal(r19):
    assert r19["prediction_phase"] == "post_qualifying"

    assert with_graded_fields(r19) == r19


@pytest.mark.unit
def test_an_entry_without_snapshots_keeps_its_top_level_fields_as_they_are():
    entry = {"predicted_positions": {"VER": 3}, "data_sources": None}

    repaired = with_graded_fields(entry)

    assert repaired == entry
    assert repaired is not entry
