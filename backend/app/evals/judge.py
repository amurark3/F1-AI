"""LLM-as-judge scoring for assistant answers.

Scores a candidate answer against a rubric on a 0.0–1.0 scale.  Uses the same
engine as the assistant (Groq) but with no tools — it only judges.  Falls back
to a deterministic keyword score when the judge LLM is unavailable, so the eval
always produces a number.
"""

from __future__ import annotations

import json
import re

import structlog

logger = structlog.get_logger()

_JUDGE_INSTRUCTIONS = (
    "You are a strict grader for a Formula 1 assistant. Given a QUESTION, the "
    "assistant's ANSWER, and a RUBRIC, score the answer from 0.0 (wrong/missing) "
    "to 1.0 (fully correct per the rubric). Judge factual correctness against the "
    "rubric only. Respond with ONLY a compact JSON object: "
    '{"score": <float 0..1>, "reason": "<one sentence>"}.'
)


def keyword_score(answer: str, must_include: list[str]) -> float:
    """Fraction of required keyword signals present (case-insensitive)."""
    if not must_include:
        return 1.0
    low = answer.lower()
    hits = sum(1 for kw in must_include if kw.lower() in low)
    return hits / len(must_include)


def _parse_score(text: str) -> tuple[float, str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            score = float(obj.get("score"))
            return max(0.0, min(1.0, score)), str(obj.get("reason", ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # Fallback: find a bare float in the text.
    num = re.search(r"(\d(?:\.\d+)?)", text)
    if num:
        return max(0.0, min(1.0, float(num.group(1)))), "parsed from freeform judge output"
    raise ValueError(f"Could not parse judge score from: {text[:120]}")


def judge_answer(question: str, answer: str, rubric: str, must_include: list[str]) -> dict:
    """Return {"score", "reason", "method"} for an answer.

    Prefers the LLM judge; falls back to keyword scoring on any failure.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.api.llm import build_chat_llm

        judge_llm = build_chat_llm()
        prompt = (
            f"QUESTION:\n{question}\n\nANSWER:\n{answer}\n\nRUBRIC:\n{rubric}"
        )
        response = judge_llm.invoke([
            SystemMessage(content=_JUDGE_INSTRUCTIONS),
            HumanMessage(content=prompt),
        ])
        score, reason = _parse_score(str(response.content))
        return {"score": score, "reason": reason, "method": "llm_judge"}
    except Exception as exc:
        logger.warning("evals.judge_llm_unavailable_using_keywords", error=str(exc))
        score = keyword_score(answer, must_include)
        return {"score": score, "reason": "keyword fallback", "method": "keyword"}
