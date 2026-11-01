"""Golden-set evaluation runner with a pass/fail gate.

Runs the full agent over the golden Q&A set, scores each answer with the LLM
judge, and gates on the mean score — the same discipline the ML model already
uses against the grid baseline, applied to the assistant so prompt/model
changes can't silently regress.

    cd backend
    python -m app.evals.run              # run + print report
    python -m app.evals.run --gate 0.7   # exit non-zero if mean score < 0.7
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import sys

import structlog

from app.api.routers.chat import RATE_LIMITED_NOTICE, ask_anonymously
from app.evals.dataset import GOLDEN_QA, GoldenQA
from app.evals.judge import judge_answer, keyword_score

logger = structlog.get_logger()

DEFAULT_GATE = 0.7
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_PAUSE_SECONDS = 20

_TOOL_MARKER = re.compile(r"\[TOOL_(?:START|END)\].*?\[/TOOL_(?:START|END)\]")


async def _run_agent(question: str) -> str:
    """The answer the chat would stream for ``question``, without its tool markers.

    Runs the chat router's own entry point — same engines, failover, prompt and
    final-turn handling — so the eval scores the agent that actually ships.
    """
    streamed, _history = await ask_anonymously(question)
    return _TOOL_MARKER.sub("", streamed).strip()


async def _answer(question: str) -> str:
    """The agent's answer, waiting out a rate limit a few times before scoring it."""
    answer = ""
    for attempt in range(RATE_LIMIT_RETRIES):
        answer = await _run_agent(question)
        if answer != RATE_LIMITED_NOTICE or attempt == RATE_LIMIT_RETRIES - 1:
            break
        await asyncio.sleep(RATE_LIMIT_PAUSE_SECONDS)
    return answer


async def _evaluate_one(item: GoldenQA) -> dict:
    answer = await _answer(item.question)
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
