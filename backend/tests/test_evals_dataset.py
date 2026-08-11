"""Tests for app.evals.dataset — the golden Q&A set the assistant is gated on.

``python -m app.evals.run`` fails CI when the mean judged score drops below the
gate, so this file *is* the definition of "the assistant still works". The risks
are quiet ones: a duplicate id silently overwrites a case in any id-keyed
report; an empty rubric makes the LLM judge grade against nothing and hand out
free marks; an empty ``must_include`` makes the keyword fallback return a
perfect 1.0 for any answer at all, so a Groq outage would turn into a green
build. Each assertion below pins one of those.
"""

from __future__ import annotations

import pytest

from app.evals.dataset import GOLDEN_QA, GoldenQA
from app.evals.judge import keyword_score


@pytest.mark.unit
def test_golden_set_is_not_empty():
    # run_evals divides by len(results); an empty set would gate on 0.0.
    assert len(GOLDEN_QA) >= 5


@pytest.mark.unit
def test_every_golden_id_is_unique():
    ids = [item.id for item in GOLDEN_QA]

    assert len(set(ids)) == len(ids)


@pytest.mark.unit
@pytest.mark.parametrize("item", GOLDEN_QA, ids=lambda item: item.id)
def test_every_golden_item_carries_a_question_rubric_and_keywords(item):
    assert item.question.strip()
    # An empty rubric gives the judge nothing to grade against; empty
    # must_include makes the keyword fallback score everything 1.0.
    assert item.rubric.strip()
    assert item.must_include


@pytest.mark.unit
@pytest.mark.parametrize("item", GOLDEN_QA, ids=lambda item: item.id)
def test_no_golden_question_contains_its_own_answer(item):
    """A question that leaks its keywords would score 1.0 on the fallback."""
    assert keyword_score(item.question, item.must_include) < 1.0


@pytest.mark.unit
def test_golden_qa_defaults_are_not_shared_between_instances():
    first = GoldenQA(id="a", question="?")
    second = GoldenQA(id="b", question="?")

    first.must_include.append("leaked")

    assert second.must_include == []
    assert second.rubric == ""


@pytest.mark.unit
def test_golden_qa_is_immutable():
    with pytest.raises(AttributeError):
        GOLDEN_QA[0].question = "something easier"  # type: ignore[misc]
