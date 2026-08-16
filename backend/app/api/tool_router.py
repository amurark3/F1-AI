"""Select which tools to bind for a given question.

Binding all 15 tools costs ~2,100 prompt tokens *per turn* of the agent loop,
re-sent on every iteration.  ``query_f1_database`` alone is ~700 of those,
because the f1db schema is appended to its description so the model can write
correct SQL — invaluable for "who has the most wet-weather wins", pure waste for
"who won Monaco 2023".

On Groq's free tier (8K tokens/minute) that overhead is the binding constraint,
so this module picks a subset from the user's question before the first call.

Deliberately keyword-based rather than LLM-based: asking a model which tools to
use would itself cost a request and tokens, defeating the purpose.  Matching is
whole-word so "sq" doesn't fire on "square" and "vs" doesn't fire on "vsomething".
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

# Always bound.  The system prompt mandates resolving "last race"/"next race"
# through the schedule before any results tool, so the loop cannot chain without
# it — and at ~429 chars it is one of the cheapest schemas we have.
CORE_TOOLS = frozenset({"get_season_schedule"})

# Used when nothing else matches: a general-purpose set that can answer or
# research almost anything, including the SQL escape hatch.
FALLBACK_TOOLS = frozenset(
    {"query_f1_database", "get_race_results", "perform_web_search"}
)

# Tools a selection reliably drags in with it. Observed against the live model:
# asked for a penalty, it searched the rulebook and then reached for the web to
# confirm the current season's wording — and a tool the model wants but was not
# given is a hard 400 from Groq, not a graceful degradation. Cheaper to bind the
# companion (~471 chars) than to lose the turn.
COMPANION_TOOLS: dict[str, frozenset[str]] = {
    "consult_rulebook": frozenset({"perform_web_search"}),
    "get_race_predictions": frozenset({"get_season_schedule"}),
    "get_race_anomalies": frozenset({"get_race_results"}),
}

# Phrases that indicate a tool is worth its schema cost for this question.
# Multi-word phrases are matched as phrases, so "sprint qualifying" pulls in the
# shootout tool without every "qualifying" question paying for it.
TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "get_race_predictions": (
        "predict",
        "prediction",
        "predictions",
        "will win",
        "who wins",
        "forecast",
        "expected",
        "odds",
        "chances",
        "likely",
    ),
    "get_pit_strategy": (
        "pit",
        "pitstop",
        "pit stop",
        "strategy",
        "tyre",
        "tire",
        "tyres",
        "tires",
        "stint",
        "undercut",
        "overcut",
        "compound",
    ),
    "get_weather_conditions": (
        "weather",
        "rain",
        "raining",
        "wet",
        "dry",
        "temperature",
        "humidity",
        "conditions",
    ),
    "perform_web_search": (
        "news",
        "latest",
        "rumour",
        "rumor",
        "announced",
        "announcement",
        "contract",
        "signing",
        "transfer",
        "recently",
    ),
    "get_sprint_results": ("sprint", "sprint race"),
    "get_sprint_qualifying_results": (
        "sprint qualifying",
        "sprint quali",
        "shootout",
        "sq",
    ),
    "get_qualifying_results": (
        "qualifying",
        "quali",
        "pole",
        "pole position",
        "grid",
        "q1",
        "q2",
        "q3",
    ),
    "compare_drivers": (
        "compare",
        "comparison",
        "versus",
        "vs",
        "head to head",
        "head-to-head",
        "faster than",
        "quicker than",
        "gap between",
        "against",
    ),
    "get_race_results": (
        "result",
        "results",
        "won",
        "win",
        "winner",
        "finished",
        "finish",
        "podium",
        "classification",
        "race",
        "grand prix",
        "gp",
    ),
    "consult_rulebook": (
        "rule",
        "rules",
        "regulation",
        "regulations",
        "penalty",
        "penalties",
        "legal",
        "illegal",
        "banned",
        "allowed",
        "fia",
        "sporting",
        "technical",
        "steward",
        "stewards",
    ),
    "get_driver_standings": (
        "standing",
        "standings",
        "championship",
        "points",
        "leader",
        "leading",
        "wdc",
        "title",
        "table",
    ),
    "get_constructor_standings": (
        "constructor",
        "constructors",
        "team standings",
        "wcc",
        "team championship",
        "teams",
    ),
    "get_season_schedule": (
        "schedule",
        "calendar",
        "next race",
        "last race",
        "upcoming",
        "when is",
        "when's",
        "round",
        "fixtures",
    ),
    "query_f1_database": (
        "most",
        "fewest",
        "best",
        "worst",
        "record",
        "records",
        "all time",
        "all-time",
        "career",
        "history",
        "historical",
        "ever",
        "how many",
        "how often",
        "statistic",
        "statistics",
        "stats",
        "average",
        "streak",
        "since",
        "total",
        "across",
    ),
    "get_race_anomalies": (
        "surprise",
        "surprising",
        "notable",
        "story",
        "stories",
        "standout",
        "retirement",
        "retirements",
        "dnf",
        "incident",
        "incidents",
        "drama",
    ),
}


def _compile(phrases: tuple[str, ...]) -> re.Pattern[str]:
    """Whole-word alternation for one tool's phrases, longest first."""
    ordered = sorted(phrases, key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b",
        re.IGNORECASE,
    )


_PATTERNS: dict[str, re.Pattern[str]] = {
    name: _compile(phrases) for name, phrases in TOOL_KEYWORDS.items()
}


def select_tools(user_text: str) -> frozenset[str]:
    """Return the tool names worth binding for ``user_text``.

    Always a superset of :data:`CORE_TOOLS`.  Falls back to a general set when
    the question matches nothing, so an unrecognised phrasing degrades to
    "slightly more expensive" rather than "no tools and a hallucinated answer".
    """
    if not user_text or not user_text.strip():
        return CORE_TOOLS | FALLBACK_TOOLS

    matched = frozenset(
        name for name, pattern in _PATTERNS.items() if pattern.search(user_text)
    )
    if matched:
        companions = frozenset(
            companion
            for name in matched
            for companion in COMPANION_TOOLS.get(name, frozenset())
        )
        selected = matched | companions | CORE_TOOLS
    else:
        selected = CORE_TOOLS | FALLBACK_TOOLS

    logger.info(
        "agent.tools_selected",
        count=len(selected),
        of_total=len(TOOL_KEYWORDS),
        tools=sorted(selected),
    )
    return selected
