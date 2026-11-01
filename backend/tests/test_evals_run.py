"""Tests for app.evals.run — the golden-set quality gate.

This is the assistant's regression harness, so the risk is a gate that cannot
fail: if a rate limit or an engine outage crashed the runner, CI would go red
for an infrastructure reason rather than a quality one — and worse, a runner
that swallowed those into full-marks answers would let a real prompt
regression ship. What is pinned here is that the runner scores the agent that
ships (the chat router's own entry point), that a rate limit is waited out a
bounded number of times, and that the exit code follows the mean score
against the gate.

The agent, the LLM judge and ``asyncio.sleep`` are all faked; no engine key is
set and no model is ever constructed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.evals import run
from app.evals.dataset import GoldenQA


async def _returning(value):
    return value


def _streamed(*texts: str):
    """A fake ``ask_anonymously`` that streams ``texts`` in turn, recording each question."""
    questions: list[str] = []
    queue = list(texts)

    async def ask(question: str):
        questions.append(question)
        return queue.pop(0), []

    return ask, questions


@pytest.mark.unit
async def test_the_agent_run_is_the_chat_routers_own_entry_point(monkeypatch):
    ask, questions = _streamed("Max Verstappen")
    monkeypatch.setattr(run, "ask_anonymously", ask)

    assert await run._run_agent("Who won 2021?") == "Max Verstappen"
    assert questions == ["Who won 2021?"]


@pytest.mark.unit
async def test_tool_markers_are_stripped_from_the_scored_answer(monkeypatch):
    """The judge grades the answer the user reads, not the progress indicators."""
    ask, _ = _streamed(
        "[TOOL_START]Query F1 Database[/TOOL_START][TOOL_END]Query F1 Database[/TOOL_END]Ayrton Senna, 6 wins."
    )
    monkeypatch.setattr(run, "ask_anonymously", ask)

    assert await run._run_agent("Most Monaco wins?") == "Ayrton Senna, 6 wins."


def _golden(qa_id: str = "wdc-2021") -> GoldenQA:
    return GoldenQA(id=qa_id, question="Who won 2021?", must_include=["Verstappen"], rubric="Names Verstappen.")


@pytest.fixture
def stub_judge(monkeypatch):
    """Deterministic keyword + judge scoring so only the runner is under test."""
    monkeypatch.setattr(run, "keyword_score", lambda answer, must_include: 0.5)
    monkeypatch.setattr(
        run,
        "judge_answer",
        lambda question, answer, rubric, must_include: {"score": 0.8125, "reason": "names it", "method": "llm"},
    )


@pytest.mark.unit
async def test_a_scored_item_carries_the_question_answer_and_both_scores(monkeypatch, stub_judge):
    monkeypatch.setattr(run, "_run_agent", lambda question: _returning("Max Verstappen"))

    result = await run._evaluate_one(_golden())

    assert result == {
        "id": "wdc-2021",
        "question": "Who won 2021?",
        "answer": "Max Verstappen",
        "keyword_score": 0.5,
        "score": 0.81,
        "reason": "names it",
        "method": "llm",
    }


@pytest.mark.unit
async def test_a_rate_limited_answer_is_retried_after_backing_off(monkeypatch, stub_judge):
    slept: list[float] = []
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _returning(slept.append(seconds)))
    ask, questions = _streamed(run.RATE_LIMITED_NOTICE, "Max Verstappen")
    monkeypatch.setattr(run, "ask_anonymously", ask)

    result = await run._evaluate_one(_golden())

    assert result["answer"] == "Max Verstappen"
    assert len(questions) == 2
    assert slept == [run.RATE_LIMIT_PAUSE_SECONDS]


@pytest.mark.unit
async def test_any_other_answer_is_scored_without_a_retry(monkeypatch, stub_judge):
    """An error the user would see is a quality failure, not something to wait out."""
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: pytest.fail("only a rate limit backs off"))
    ask, _ = _streamed("**System Error:** something broke (ref abc)")
    monkeypatch.setattr(run, "ask_anonymously", ask)

    result = await run._evaluate_one(_golden())

    assert result["answer"] == "**System Error:** something broke (ref abc)"


@pytest.mark.unit
async def test_persistent_rate_limiting_gives_up_after_the_last_retry(monkeypatch, stub_judge):
    slept: list[float] = []
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _returning(slept.append(seconds)))
    ask, questions = _streamed(*[run.RATE_LIMITED_NOTICE] * run.RATE_LIMIT_RETRIES)
    monkeypatch.setattr(run, "ask_anonymously", ask)

    result = await run._evaluate_one(_golden())

    assert result["answer"] == run.RATE_LIMITED_NOTICE, "scored as what the user would see"
    assert len(questions) == run.RATE_LIMIT_RETRIES
    assert len(slept) == run.RATE_LIMIT_RETRIES - 1, "the final attempt must not sleep before giving up"


@pytest.mark.unit
async def test_run_evals_averages_the_item_scores(monkeypatch):
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _returning(None))
    scores = iter([0.5, 1.0])
    monkeypatch.setattr(run, "_evaluate_one", lambda item: _returning({"id": item.id, "score": next(scores)}))

    report = await run.run_evals([_golden("a"), _golden("b")])

    assert report == {"mean_score": 0.75, "n": 2, "results": [{"id": "a", "score": 0.5}, {"id": "b", "score": 1.0}]}


@pytest.mark.unit
async def test_an_empty_item_list_falls_back_to_the_golden_set(monkeypatch):
    """``items or GOLDEN_QA`` treats an empty list as "unspecified", not "none".

    A consequence worth knowing: the ``if results else 0.0`` guard against a
    zero-division on the mean is unreachable through this entry point, because
    ``items`` can never be empty by the time the loop runs.
    """
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _returning(None))
    monkeypatch.setattr(run, "_evaluate_one", lambda item: _returning({"id": item.id, "score": 1.0}))

    report = await run.run_evals([])

    assert report["n"] == len(run.GOLDEN_QA)


@pytest.mark.unit
async def test_run_evals_defaults_to_the_golden_set(monkeypatch):
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _returning(None))
    seen: list[str] = []
    # The loop logs `result["id"]`, so a stubbed result must carry one.
    monkeypatch.setattr(
        run, "_evaluate_one", lambda item: _returning(seen.append(item.id) or {"id": item.id, "score": 1.0})
    )

    report = await run.run_evals()

    assert seen == [item.id for item in run.GOLDEN_QA]
    assert report["n"] == len(run.GOLDEN_QA)


def _stub_report(monkeypatch, mean: float, results=None) -> None:
    report = {
        "mean_score": mean,
        "n": len(results or []),
        "results": results
        or [{"id": "wdc-2021", "score": mean, "method": "llm", "keyword_score": 1.0, "reason": "ok"}],
    }

    async def fake_run_evals():
        return report

    monkeypatch.setattr(run, "run_evals", fake_run_evals)


@pytest.mark.unit
def test_main_exits_non_zero_when_the_mean_falls_below_the_gate(monkeypatch, capsys):
    monkeypatch.setattr(run.sys, "argv", ["run"])
    _stub_report(monkeypatch, 0.4)

    with pytest.raises(SystemExit, match="1"):
        run.main()

    out = capsys.readouterr().out
    assert "GATE FAILED" in out
    assert f"(gate {run.DEFAULT_GATE})" in out


@pytest.mark.unit
def test_main_passes_and_marks_each_item(monkeypatch, capsys):
    monkeypatch.setattr(run.sys, "argv", ["run"])
    _stub_report(
        monkeypatch,
        0.8,
        results=[
            {"id": "wdc-2021", "score": 0.9, "method": "llm", "keyword_score": 1.0, "reason": "names it"},
            {"id": "monaco-wins", "score": 0.5, "method": "keyword", "keyword_score": 0.0, "reason": "missed"},
        ],
    )

    run.main()

    out = capsys.readouterr().out
    assert "[PASS] wdc-2021" in out
    assert "[FAIL] monaco-wins" in out
    assert "GATE PASSED." in out


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argv", "expected_gate"),
    [
        (["run", "--gate", "0.9"], "0.9"),
        (["run", "--gate", "not-a-number"], str(run.DEFAULT_GATE)),
        (["run", "--gate"], str(run.DEFAULT_GATE)),
    ],
)
def test_the_gate_can_be_overridden_and_falls_back_when_malformed(monkeypatch, capsys, argv, expected_gate):
    monkeypatch.setattr(run.sys, "argv", argv)
    _stub_report(monkeypatch, 1.0)

    run.main()

    assert f"(gate {expected_gate})" in capsys.readouterr().out


@pytest.mark.unit
def test_main_drives_the_real_event_loop_entry_point(monkeypatch):
    """``main`` is a ``python -m`` entrypoint: it owns the loop, not the caller."""
    monkeypatch.setattr(run.sys, "argv", ["run"])
    _stub_report(monkeypatch, 1.0)

    assert asyncio.get_event_loop_policy() is not None
    run.main()
