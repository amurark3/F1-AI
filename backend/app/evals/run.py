"""Golden-set evaluation runner with a pass/fail gate.

Runs the full agent (tool loop + recovery) over the golden Q&A set, scores each
answer with the LLM judge, and gates on the mean score — the same discipline the
ML model already uses against the grid baseline, applied to the assistant so
prompt/model changes can't silently regress.

    cd backend
    python -m app.evals.run              # run + print report
    python -m app.evals.run --gate 0.7   # exit non-zero if mean score < 0.7
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
import structlog

from app.api.routers.chat import (
    MAX_AGENT_TURNS,
    TOOL_MAP,
    _ainvoke_with_recovery,
    build_system_prompt,
)
from app.evals.dataset import GOLDEN_QA, GoldenQA
from app.evals.judge import judge_answer, keyword_score

logger = structlog.get_logger()

DEFAULT_GATE = 0.7


async def _run_agent(question: str, today: str = "July 20, 2026") -> str:
    """Drive the tool-use loop to a final text answer (non-streaming)."""
    messages = [SystemMessage(content=build_system_prompt(today)), HumanMessage(content=question)]
    response = await _ainvoke_with_recovery(messages)
    for _ in range(MAX_AGENT_TURNS):
        if not response.tool_calls:
            return str(response.content)
        messages.append(response)
        for call in response.tool_calls:
            name = call["name"]
            if name not in TOOL_MAP:
                continue
            try:
                result = await asyncio.to_thread(TOOL_MAP[name].invoke, call["args"])
            except Exception as exc:  # tool failure shouldn't abort the eval
                result = f"Tool error: {exc}"
            messages.append(ToolMessage(tool_call_id=call["id"], content=str(result), name=name))
        response = await _ainvoke_with_recovery(messages)
    return str(response.content)


async def _evaluate_one(item: GoldenQA, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            answer = await _run_agent(item.question)
            break
        except Exception as exc:
            if ("rate" in str(exc).lower() or "429" in str(exc)) and attempt < retries - 1:
                await asyncio.sleep(20)
                continue
            answer = f"(agent error: {exc})"
            break

    kw = keyword_score(answer, item.must_include)
    verdict = judge_answer(item.question, answer, item.rubric, item.must_include)
    return {
        "id": item.id,
        "question": item.question,
        "answer": answer,
        "keyword_score": round(kw, 2),
        "score": round(verdict["score"], 2),
        "reason": verdict["reason"],
        "method": verdict["method"],
    }


async def run_evals(items: list[GoldenQA] | None = None) -> dict:
    items = items or GOLDEN_QA
    results = []
    for item in items:
        result = await _evaluate_one(item)
        results.append(result)
        logger.info("evals.item_scored", id=result["id"], score=result["score"])
        await asyncio.sleep(1)  # be gentle on the free-tier rate limit
    mean = round(sum(r["score"] for r in results) / len(results), 3) if results else 0.0
    return {"mean_score": mean, "n": len(results), "results": results}


def main() -> None:
    gate = DEFAULT_GATE
    if "--gate" in sys.argv:
        # A malformed or missing --gate value falls back to DEFAULT_GATE.
        with contextlib.suppress(IndexError, ValueError):
            gate = float(sys.argv[sys.argv.index("--gate") + 1])

    report = asyncio.run(run_evals())

    print("\n=== F1-AI Golden Eval ===")
    for r in report["results"]:
        mark = "PASS" if r["score"] >= 0.6 else "FAIL"
        print(f"[{mark}] {r['id']:<20} score={r['score']:.2f} ({r['method']})  kw={r['keyword_score']:.2f}")
        print(f"        {r['reason']}")
    print(f"\nmean score: {report['mean_score']:.3f} over {report['n']} questions (gate {gate})")

    if report["mean_score"] < gate:
        print("GATE FAILED — assistant quality regressed below threshold.")
        sys.exit(1)
    print("GATE PASSED.")


if __name__ == "__main__":
    main()
