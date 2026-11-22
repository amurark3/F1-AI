"""Tests for app.api.answer_data: what an answer read, gathered from its tool results."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
import pytest

from app.api.answer_data import answer_data
from app.api.tools.provenance import Provenance, ReachChart, ReachRow

pytestmark = pytest.mark.unit

CHART = ReachChart(
    title="2 drivers can still finish second",
    championship="drivers",
    year=2026,
    rows=(
        ReachRow("VER", "Max Verstappen", "Red Bull", 261, 361),
        ReachRow("HAM", "Lewis Hamilton", "Ferrari", 259, 359),
    ),
)


def _result(provenance, call_id="c1") -> ToolMessage:
    return ToolMessage(tool_call_id=call_id, content="text", name="tool", artifact=provenance)


def test_no_provenance_means_no_data():
    assert answer_data([AIMessage(content="hi"), _result(None), ToolMessage(tool_call_id="c", content="x")]) is None


def test_the_subject_is_the_first_one_given():
    messages = [
        _result(Provenance(sources=("a",))),
        _result(Provenance(sources=("b",), subject="2026 calendar"), "c2"),
        _result(Provenance(sources=("c",), subject="later"), "c3"),
    ]

    assert answer_data(messages)["subject"] == "2026 calendar"


def test_no_subject_anywhere_is_none():
    assert answer_data([_result(Provenance(sources=("a",)))])["subject"] is None


def test_chips_are_kept_once_in_order():
    messages = [
        _result(Provenance(sources=("a", "b"))),
        _result(Provenance(sources=("b", "c")), "c2"),
    ]

    assert answer_data(messages)["sources"] == ["a", "b", "c"]


def test_a_chart_read_twice_is_sent_once():
    messages = [_result(Provenance(sources=(), chart=CHART)), _result(Provenance(sources=(), chart=CHART), "c2")]

    charts = answer_data(messages)["charts"]

    assert len(charts) == 1
    assert charts[0]["kind"] == "reach"
    assert charts[0]["rows"][0] == {
        "key": "VER",
        "name": "Max Verstappen",
        "team": "Red Bull",
        "points": 261,
        "max": 361,
    }
