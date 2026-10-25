"""Check a final answer's driver↔team claims, and repair one the rows contradict.

The model attaches teams to drivers while writing and sometimes gets them
wrong against its own rows ("Mercedes drivers (Russell three times, Norris
once)"). Every final answer is checked against the tables this conversation's
tools returned (app.api.claim_check). A clean answer — the usual case — costs
nothing. A contradicted one gets a single repair request that names the
sentence and the team the rows show, and the repair is re-checked.

Whatever goes wrong after that — the repair is refused, repeats the mistake,
or is rate-limited — the user gets the draft plus a "Data check" line stating
what the rows show. That line is true even when the flag was a false positive,
so the fallback can never add a falsehood.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
import structlog

from app.api.claim_check import Misattribution, find_misattributions, roster_from_tables
from app.data.f1db_query import constructor_names

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    # A model call with no tools bound; None when it tried to call one anyway.
    Ask = Callable[[list[BaseMessage]], Awaitable[AIMessage | None]]

logger = structlog.get_logger()

_EDITOR = SystemMessage(
    content=(
        "You correct factual slips in a Formula 1 answer. Apply exactly the corrections "
        "listed, rewording only the sentences they name, and return the whole answer — "
        "same structure, same tables, nothing added or removed."
    )
)


async def _team_names() -> frozenset[str]:
    """Every team f1db knows, so one named only from memory is still recognised."""
    try:
        return await asyncio.to_thread(constructor_names)
    except Exception as exc:
        logger.warning("answer.team_names_unavailable", error=str(exc))
        return frozenset()  # the tables' own teams are still checked


def _teams(flag: Misattribution) -> str:
    return "/".join(flag.actual_teams)


async def _repair(answer: str, flags: list[Misattribution], ask: Ask) -> str | None:
    """One request to fix exactly the flagged claims; None if it yields nothing usable."""
    corrections = "\n".join(
        f'- In "{flag.excerpt}": {flag.driver} drove for {_teams(flag)}, not {flag.claimed_team}.' for flag in flags
    )
    request = [_EDITOR, HumanMessage(content=f"CORRECTIONS:\n{corrections}\n\nANSWER:\n{answer}")]
    try:
        reply = await ask(request)
    except Exception as exc:
        logger.warning("answer.repair_failed", error=str(exc))
        return None
    text = str(reply.content).strip() if reply else ""
    if not text:
        logger.warning("answer.repair_empty", refused=reply is None)
    return text or None


def _data_check(flags: list[Misattribution]) -> str:
    facts = "; ".join(
        f"{flag.driver} drove for {_teams(flag)} in these results, not {flag.claimed_team}" for flag in flags
    )
    return f"\n\n**Data check:** {facts}."


async def checked_answer(messages: list[BaseMessage], answer: str, ask: Ask) -> str:
    """``answer``, repaired once if it puts a driver at a team its rows contradict."""
    roster = roster_from_tables(str(m.content) for m in messages if isinstance(m, ToolMessage))
    if not roster:
        return answer
    teams = await _team_names()
    flags = find_misattributions(answer, roster, teams)
    if not flags:
        return answer
    logger.warning("answer.claims_contradict_rows", claims=[f"{f.driver} -> {f.claimed_team}" for f in flags])
    repaired = await _repair(answer, flags, ask)
    if repaired and not find_misattributions(repaired, roster, teams):
        logger.info("answer.repaired", claims=len(flags))
        return repaired
    return answer + _data_check(flags)
