"""Tests for app.evals.run — the golden-set quality gate.

This is the assistant's regression harness, so the risk is a gate that cannot
fail: if a tool error, a rate limit or a runaway tool loop crashed the runner,
CI would go red for an infrastructure reason rather than a quality one — and
worse, a runner that swallowed those into full-marks answers would let a real
prompt regression ship. What is pinned here is that every failure becomes a
*scored* answer, that the tool loop is bounded, and that the exit code follows
the mean score against the gate.

The agent, the LLM judge and ``asyncio.sleep`` are all faked; ``GROQ_API_KEY``
is unset and no model is ever constructed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.evals import run
from app.evals.dataset import GoldenQA


class _Response:
    def __init__(self, content: str = "", tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _Tool:
    def __init__(self, result="tool result", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    def invoke(self, args: dict):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.result


def _scripted_agent(monkeypatch, responses: list[_Response]) -> list[list]:
    """Replay ``responses`` turn by turn, recording the message list each time."""
    seen: list[list] = []
    queue = list(responses)

    async def fake_invoke(messages):
        seen.append(list(messages))
        return queue.pop(0)

    monkeypatch.setattr(run, "_ainvoke_with_recovery", fake_invoke)
    monkeypatch.setattr(run, "build_system_prompt", lambda today: f"SYSTEM {today}")
    return seen


def _tool_call(name: str, args: dict | None = None, call_id: str = "call-1") -> dict:
    return {"name": name, "args": args or {}, "id": call_id}


@pytest.mark.unit
async def test_a_direct_answer_short_circuits_the_tool_loop(monkeypatch):
    seen = _scripted_agent(monkeypatch, [_Response("Max Verstappen")])

    answer = await run._run_agent("Who won 2021?", today="July 20, 2026")

    assert answer == "Max Verstappen"
    assert [m.content for m in seen[0]] == ["SYSTEM July 20, 2026", "Who won 2021?"]


@pytest.mark.unit
async def test_tool_results_are_fed_back_before_the_next_turn(monkeypatch):
    tool = _Tool("Senna, 6 wins")
    monkeypatch.setattr(run, "TOOL_MAP", {"f1db_query": tool})
    seen = _scripted_agent(
        monkeypatch,
        [_Response(tool_calls=[_tool_call("f1db_query", {"sql": "SELECT 1"})]), _Response("Ayrton Senna")],
    )

    answer = await run._run_agent("Most Monaco wins?")

    assert answer == "Ayrton Senna"
    assert tool.calls == [{"sql": "SELECT 1"}]
    assert seen[1][-1].content == "Senna, 6 wins"


@pytest.mark.unit
async def test_an_unknown_tool_is_skipped_rather_than_crashing_the_run(monkeypatch):
    monkeypatch.setattr(run, "TOOL_MAP", {})
    seen = _scripted_agent(monkeypatch, [_Response(tool_calls=[_tool_call("hallucinated_tool")]), _Response("final")])

    assert await run._run_agent("q") == "final"
    # No ToolMessage was appended for a tool that does not exist.
    assert len(seen[1]) == 3


@pytest.mark.unit
async def test_a_failing_tool_is_reported_back_to_the_model_as_text(monkeypatch):
    monkeypatch.setattr(run, "TOOL_MAP", {"broken": _Tool(error=RuntimeError("sqlite is locked"))})
    seen = _scripted_agent(monkeypatch, [_Response(tool_calls=[_tool_call("broken")]), _Response("recovered")])

    assert await run._run_agent("q") == "recovered"
    assert seen[1][-1].content == "Tool error: sqlite is locked"


@pytest.mark.unit
async def test_the_tool_loop_is_bounded_by_max_agent_turns(monkeypatch):
    monkeypatch.setattr(run, "MAX_AGENT_TURNS", 2)
    monkeypatch.setattr(run, "TOOL_MAP", {"looping": _Tool()})
    looping = _Response("still looping", tool_calls=[_tool_call("looping")])
    _scripted_agent(monkeypatch, [looping, looping, looping])

    # A model that never stops calling tools must terminate, not hang the gate.
    assert await run._run_agent("q") == "still looping"


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
    monkeypatch.setattr(run, "_run_agent", lambda question: _answer("Max Verstappen"))

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


async def _answer(text: str) -> str:
    return text


@pytest.mark.unit
async def test_a_rate_limited_attempt_is_retried_after_backing_off(monkeypatch, stub_judge):
    slept: list[float] = []
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _answer(slept.append(seconds)))
    attempts: list[int] = []

    async def flaky(question):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("429 Rate limit exceeded")
        return "Max Verstappen"

    monkeypatch.setattr(run, "_run_agent", flaky)

    result = await run._evaluate_one(_golden())

    assert result["answer"] == "Max Verstappen"
    assert slept == [20]


@pytest.mark.unit
async def test_a_non_retryable_failure_is_scored_rather_than_raised(monkeypatch, stub_judge):
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: pytest.fail("a hard error must not back off"))

    async def explode(question):
        raise ValueError("model not found")

    monkeypatch.setattr(run, "_run_agent", explode)

    result = await run._evaluate_one(_golden())

    assert result["answer"] == "(agent error: model not found)"


@pytest.mark.unit
async def test_persistent_rate_limiting_gives_up_after_the_last_retry(monkeypatch, stub_judge):
    slept: list[float] = []
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _answer(slept.append(seconds)))

    async def always_limited(question):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(run, "_run_agent", always_limited)

    result = await run._evaluate_one(_golden(), retries=2)

    assert result["answer"] == "(agent error: rate limited)"
    assert slept == [20], "the final attempt must not sleep before giving up"


@pytest.mark.unit
async def test_run_evals_averages_the_item_scores(monkeypatch):
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _answer(None))
    scores = iter([0.5, 1.0])
    monkeypatch.setattr(run, "_evaluate_one", lambda item: _answer({"id": item.id, "score": next(scores)}))

    report = await run.run_evals([_golden("a"), _golden("b")])

    assert report == {"mean_score": 0.75, "n": 2, "results": [{"id": "a", "score": 0.5}, {"id": "b", "score": 1.0}]}


@pytest.mark.unit
async def test_an_empty_item_list_falls_back_to_the_golden_set(monkeypatch):
    """``items or GOLDEN_QA`` treats an empty list as "unspecified", not "none".

    A consequence worth knowing: the ``if results else 0.0`` guard against a
    zero-division on the mean is unreachable through this entry point, because
    ``items`` can never be empty by the time the loop runs.
    """
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _answer(None))
    monkeypatch.setattr(run, "_evaluate_one", lambda item: _answer({"id": item.id, "score": 1.0}))

    report = await run.run_evals([])

    assert report["n"] == len(run.GOLDEN_QA)


@pytest.mark.unit
async def test_run_evals_defaults_to_the_golden_set(monkeypatch):
    monkeypatch.setattr(run.asyncio, "sleep", lambda seconds: _answer(None))
    seen: list[str] = []
    # The loop logs `result["id"]`, so a stubbed result must carry one.
    monkeypatch.setattr(
        run, "_evaluate_one", lambda item: _answer(seen.append(item.id) or {"id": item.id, "score": 1.0})
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
