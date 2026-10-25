"""Answer-quality eval for the AI Engineer: fixed questions, scored against f1db.

The unit suite never sees a real answer, by design — every failure this exists
for (invented teams, miscounted wins, a "double" that never happened) passed it.
This runs real questions through the real agent and scores what comes back.

    cd backend
    python -m scripts.eval_answers                                  # every question, 3 samples each
    python -m scripts.eval_answers --question sprint-weekends --samples 5
    python -m scripts.eval_answers --json reports/eval.json

It calls live Groq, so it spends free-tier tokens, and it pauses between
samples (``--pause``, default 75 s) to stay under the tokens-per-minute limit.
Groq at temperature 0 is not deterministic: read the results as rates over
samples, never as a verdict from one.

Each answer is scored on:
- status: answered, or the error / rate-limit / notice text the user would see
- misattributions: driver↔team claims the rows contradict (app.api.claim_check,
  against the season's f1db roster plus the tables the tools returned)
- forbidden: claims known to be wrong, seen in production (per question)
- missing: facts the answer must contain, computed from f1db (per question)
- absolutes: "only / never / none / first" — a risk signal, not an error

Exit code 1 if any answered sample is wrong; a rate-limited sample is not.
The question set is written against the 2026 season (SEASON).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from itertools import product
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage

from app.api.claim_check import Roster, find_misattributions, roster_from_tables
from app.api.routers import chat
from app.data.f1db_query import constructor_names
from app.data.f1db_source import connect

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

SEASON = 2026
DEFAULT_SAMPLES = 3
DEFAULT_PAUSE_SECONDS = 75.0

_TOOL_MARKER = re.compile(r"\[TOOL_START\](.*?)\[/TOOL_START\]")
_ANY_MARKER = re.compile(r"\[TOOL_(?:START|END)\].*?\[/TOOL_(?:START|END)\]")
_ABSOLUTE = re.compile(r"\b(?:only|never|none|first)\b", re.IGNORECASE)
_STATUS_PREFIXES = (
    ("**System Error:**", "error"),
    ("**Box, box:**", "rate_limited"),
    ("**System Notice:**", "notice"),
)
_NUMBER_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
]

_SEASON_ROSTER_SQL = """
SELECT DISTINCT dr.name AS driver, dr.abbreviation AS code, c.name AS team
FROM race_data d JOIN race r ON r.id = d.race_id
JOIN driver dr ON dr.id = d.driver_id JOIN constructor c ON c.id = d.constructor_id
WHERE r.year = ? AND d.type IN ('RACE_RESULT', 'SPRINT_RACE_RESULT')
"""

_MOST_RACE_WINS_SQL = """
SELECT c.name AS team, COUNT(*) AS wins
FROM race_data d JOIN race r ON r.id = d.race_id JOIN constructor c ON c.id = d.constructor_id
WHERE r.year = ? AND d.type = 'RACE_RESULT' AND d.position_number = 1
GROUP BY c.id ORDER BY wins DESC LIMIT 1
"""


def season_roster(year: int) -> dict[str, frozenset[str]]:
    """Every driver who raced in ``year`` → the teams they raced for."""
    with connect() as conn:
        rows = conn.execute(_SEASON_ROSTER_SQL, (year,)).fetchall()
    table = "| Driver | Team |\n| --- | --- |\n" + "\n".join(
        f"| {row['driver']} ({row['code']}) | {row['team']} |" for row in rows
    )
    return roster_from_tables([table])


_TOP_THREE_SQL = """
SELECT dr.name AS name FROM race_data d
JOIN race r ON r.id = d.race_id JOIN driver dr ON dr.id = d.driver_id
WHERE r.year = ? AND r.grand_prix_id = ? AND d.type = ? AND d.position_number <= 3
ORDER BY d.position_number
"""


def top_three(result_type: str, grand_prix_id: str) -> Callable[[], list[str]]:
    """The family names of a session's top three this season, read when scored."""

    def expect() -> list[str]:
        with connect() as conn:
            rows = conn.execute(_TOP_THREE_SQL, (SEASON, grand_prix_id, result_type)).fetchall()
        return [row["name"].split()[-1] for row in rows]

    return expect


def most_race_wins_team() -> list[str]:
    """The team with the most race wins this season, and how many."""
    with connect() as conn:
        row = conn.execute(_MOST_RACE_WINS_SQL, (SEASON,)).fetchone()
    return [row["team"], str(row["wins"])] if row else []


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    forbidden: tuple[str, ...] = ()
    expect: Callable[[], list[str]] | None = None


QUESTIONS = (
    Question(
        "sprint-weekends",
        "In this season,  who has won the sprint race and the main race. Only care about sprint weekends",
        forbidden=(
            # Norris won the R4 sprint and the R12 race: two weekends, never a double.
            r"Norris[^.\n]{0,80}\bdouble\b",
            # Norris, Leclerc and Verstappen all won races on sprint weekends.
            r"only non-Mercedes",
            # Antonelli won the R9 sprint.
            r"Antonelli[^.\n]{0,160}\b(?:not|without|yet to|no)\b[^.\n]{0,25}\bsprint",
        ),
    ),
    Question(
        "singapore-sprint-podium",
        "Who won the 2026 Singapore sprint, and who else made the sprint podium?",
        # Ferrari finished second and third behind Verstappen.
        forbidden=(r"Ferrari 1[-‑–]2",),
        expect=top_three("SPRINT_RACE_RESULT", "singapore"),
    ),
    Question(
        "singapore-pole",
        "Who took pole for the 2026 Singapore Grand Prix, and who else was in the top three?",
        expect=top_three("QUALIFYING_RESULT", "singapore"),
    ),
    Question(
        "most-race-wins-team",
        "Which team has won the most races in 2026 so far, and how many?",
        expect=most_race_wins_team,
    ),
)


@dataclass(frozen=True)
class Reference:
    """What answers are checked against: the season's roster and every team name."""

    roster: Roster
    team_names: tuple[str, ...]


@dataclass(frozen=True)
class Transcript:
    answer: str
    tool_texts: tuple[str, ...]
    tools: tuple[str, ...]


@dataclass(frozen=True)
class Score:
    question_id: str
    sample: int
    status: str
    tools: tuple[str, ...]
    answer: str
    tool_texts: tuple[str, ...] = ()
    misattributions: tuple[dict, ...] = field(default=())
    forbidden_hits: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    absolutes: int = 0

    @property
    def wrong(self) -> bool:
        return self.status == "answered" and bool(self.misattributions or self.forbidden_hits or self.missing)

    @property
    def clean(self) -> bool:
        return self.status == "answered" and not self.wrong


async def ask(text: str) -> Transcript:
    """One question through the real agent, as an anonymous user (no memory writes)."""
    streamed, messages = await chat.ask_anonymously(text)
    return Transcript(
        answer=_ANY_MARKER.sub("", streamed).strip(),
        tool_texts=tuple(str(m.content) for m in messages if isinstance(m, ToolMessage)),
        tools=tuple(_TOOL_MARKER.findall(streamed)),
    )


def _status(answer: str) -> str:
    if not answer.strip():
        return "empty"
    return next((status for prefix, status in _STATUS_PREFIXES if answer.startswith(prefix)), "answered")


def _mentions(answer: str, fact: str) -> bool:
    """A team by name; a small number as digits or as a word ("2" or "two")."""
    if fact.isdigit() and int(fact) < len(_NUMBER_WORDS):
        return bool(re.search(rf"\b(?:{fact}|{_NUMBER_WORDS[int(fact)]})\b", answer, re.IGNORECASE))
    return fact.casefold() in answer.casefold()


def _merge(*rosters: Roster) -> dict[str, frozenset[str]]:
    keys = {key for roster in rosters for key in roster}
    return {key: frozenset().union(*(roster.get(key, frozenset()) for roster in rosters)) for key in keys}


def score(question: Question, sample: int, transcript: Transcript, reference: Reference) -> Score:
    answer = transcript.answer
    status = _status(answer)
    base = Score(question.id, sample, status, transcript.tools, answer, transcript.tool_texts)
    if status != "answered":
        return base
    roster = _merge(reference.roster, roster_from_tables(transcript.tool_texts))
    flags = find_misattributions(answer, roster, reference.team_names)
    return Score(
        question.id,
        sample,
        status,
        transcript.tools,
        answer,
        transcript.tool_texts,
        misattributions=tuple(asdict(flag) for flag in flags),
        forbidden_hits=tuple(p for p in question.forbidden if re.search(p, answer, re.IGNORECASE)),
        missing=tuple(fact for fact in (question.expect() if question.expect else []) if not _mentions(answer, fact)),
        absolutes=len(_ABSOLUTE.findall(answer)),
    )


async def run(questions: Sequence[Question], samples: int, pause: float) -> list[Score]:
    """Every question, ``samples`` times, pausing between asks (not before the first)."""
    reference = Reference(season_roster(SEASON), tuple(sorted(constructor_names())))
    scores = []
    for index, (question, sample) in enumerate(product(questions, range(1, samples + 1))):
        if index:
            await asyncio.sleep(pause)
        result = score(question, sample, await ask(question.text), reference)
        print(f"{question.id} #{sample}: {result.status}{'' if result.clean else ' ✗'}", flush=True)
        scores.append(result)
    return scores


def _summary(label: str, scores: Sequence[Score]) -> str:
    total = len(scores)
    return (
        f"{label}: answered {sum(s.status == 'answered' for s in scores)}/{total} · "
        f"clean {sum(s.clean for s in scores)}/{total} · "
        f"misattributions {sum(len(s.misattributions) for s in scores)} · "
        f"forbidden {sum(len(s.forbidden_hits) for s in scores)} · "
        f"missing {sum(len(s.missing) for s in scores)} · "
        f"absolutes {sum(s.absolutes for s in scores)}"
    )


def _details(result: Score) -> list[str]:
    prefix = f"  sample {result.sample} [{', '.join(result.tools)}]:"
    if result.status != "answered":
        return [f"{prefix} {result.status}"]
    return [
        *(
            f"{prefix} {m['driver']} → {m['claimed_team']} (rows: {'/'.join(m['actual_teams'])})"
            for m in result.misattributions
        ),
        *(f"{prefix} forbidden {pattern}" for pattern in result.forbidden_hits),
        *(f"{prefix} missing {fact}" for fact in result.missing),
    ]


def report(scores: Sequence[Score]) -> str:
    lines = []
    for question_id in dict.fromkeys(s.question_id for s in scores):
        own = [s for s in scores if s.question_id == question_id]
        lines.append(_summary(question_id, own))
        lines.extend(line for result in own for line in _details(result))
    lines.append(_summary("TOTAL", scores))
    return "\n".join(lines)


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", action="append", choices=[q.id for q in QUESTIONS], help="repeatable")
    parser.add_argument("--samples", type=_positive, default=DEFAULT_SAMPLES)
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS, help="seconds between samples")
    parser.add_argument("--json", type=Path, help="write every scored answer here")
    args = parser.parse_args(argv)
    # Here, not at import: only GROQ_API_KEY is needed, and it is read when the
    # model is first built. Loading at import would leak credentials into tests.
    load_dotenv()
    selected = tuple(q for q in QUESTIONS if not args.question or q.id in args.question)
    scores = asyncio.run(run(selected, args.samples, args.pause))
    print(report(scores))
    if args.json:
        args.json.write_text(json.dumps([{**asdict(s), "clean": s.clean} for s in scores], indent=2))
    return 1 if any(s.wrong for s in scores) else 0


if __name__ == "__main__":
    raise SystemExit(main())
