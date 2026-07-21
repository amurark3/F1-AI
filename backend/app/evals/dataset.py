"""Golden F1 Q&A set for evaluating the assistant.

Each item pairs a question with (a) cheap deterministic keyword checks and
(b) a rubric the LLM judge scores against.  The questions deliberately exercise
the tool surface: the f1db query tool (records/superlatives), the rulebook RAG,
and championship facts.  Keep answers stable and unambiguous so the eval stays
deterministic enough to gate on.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenQA:
    id: str
    question: str
    must_include: list[str] = field(default_factory=list)  # any-of keyword signals
    rubric: str = ""


GOLDEN_QA: list[GoldenQA] = [
    GoldenQA(
        id="wdc-2021",
        question="Who won the 2021 Formula 1 World Drivers' Championship?",
        must_include=["Verstappen"],
        rubric="Correct answer is Max Verstappen (2021 WDC). Full credit only if it names Verstappen.",
    ),
    GoldenQA(
        id="monaco-wins",
        question="Who has the most Formula 1 race wins at the Monaco Grand Prix in history?",
        must_include=["Senna"],
        rubric="Ayrton Senna holds the record with 6 Monaco wins. Full credit if it names Senna (6 wins).",
    ),
    GoldenQA(
        id="most-poles",
        question="Which driver has the most career pole positions in Formula 1?",
        must_include=["Hamilton"],
        rubric="Lewis Hamilton has the most career poles. Full credit if it names Hamilton.",
    ),
    GoldenQA(
        id="most-wcc",
        question="Which constructor has won the most Formula 1 Constructors' Championships?",
        must_include=["Ferrari"],
        rubric="Ferrari has the most Constructors' titles. Full credit if it names Ferrari.",
    ),
    GoldenQA(
        id="pit-speed-penalty",
        question="What is the penalty for a driver exceeding the pit lane speed limit during a practice session?",
        must_include=["fine", "€", "km/h"],
        rubric=(
            "Per the FIA Sporting Regulations, exceeding the pit lane limit in practice/qualifying "
            "is a fine of €100 per km/h over the limit, up to €1000. Full credit if it states a "
            "monetary fine scaled per km/h; partial credit if it mentions a fine without the amount."
        ),
    ),
]
