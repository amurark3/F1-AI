"""Tests for per-question tool selection (app.api.tool_router).

The behaviour under test: a question is routed to the subset of tools it
plausibly needs, so the agent loop stops paying ~2,100 prompt tokens per turn
for all 15 schemas. Correctness here is asymmetric — binding one tool too many
costs tokens, binding one too few costs a wrong answer — so the tests pin both
the routing and the safety net.
"""

import pytest

from app.api.tool_router import (
    COMPANION_TOOLS,
    CORE_TOOLS,
    FALLBACK_TOOLS,
    TOOL_KEYWORDS,
    select_tools,
)
from app.api.tools import TOOL_MAP


def test_every_routed_name_is_a_real_tool():
    """A typo in the keyword table would silently drop a tool from binding."""
    companions = frozenset().union(*COMPANION_TOOLS.values())
    routed = set(TOOL_KEYWORDS) | CORE_TOOLS | FALLBACK_TOOLS | companions
    routed |= set(COMPANION_TOOLS)
    for name in routed:
        assert name in TOOL_MAP, f"{name} is routed but not a registered tool"


def test_rulebook_question_also_binds_web_search():
    """Regression: the live model answered a penalty question by consulting the
    rulebook and then reaching for the web. A tool it wants but wasn't given is
    a hard 400 from Groq, not a graceful fallback."""
    selected = select_tools(
        "What is the penalty for exceeding the pit lane speed limit?"
    )
    assert "consult_rulebook" in selected
    assert "perform_web_search" in selected


def test_keyword_table_covers_every_tool():
    """A tool absent from the table can only ever be bound via the fallback."""
    assert set(TOOL_KEYWORDS) == set(TOOL_MAP)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Who won the 2023 Monaco Grand Prix?", "get_race_results"),
        ("What are the current driver standings?", "get_driver_standings"),
        ("Who will win in Silverstone?", "get_race_predictions"),
        ("What's the penalty for a pit-lane speeding?", "consult_rulebook"),
        ("Compare Verstappen versus Norris in qualifying", "compare_drivers"),
        ("What tyre strategy did Ferrari run?", "get_pit_strategy"),
        ("Will it rain at Spa?", "get_weather_conditions"),
        ("Who has the most wins of all time?", "query_f1_database"),
        ("Show me the sprint shootout results", "get_sprint_qualifying_results"),
        ("What was surprising about that race?", "get_race_anomalies"),
        ("When is the next race?", "get_season_schedule"),
    ],
)
def test_question_routes_to_its_tool(question, expected):
    assert expected in select_tools(question)


def test_core_tools_always_bound():
    """The system prompt mandates resolving the schedule before results tools,
    so the loop cannot chain if the schedule tool is ever dropped."""
    for question in ["Who won Monaco?", "What are the rules on DRS?", "zzz"]:
        assert CORE_TOOLS <= select_tools(question)


def test_unmatched_question_falls_back_rather_than_binding_nothing():
    """An unrecognised phrasing must degrade to 'costs more', never to
    'no tools bound and a hallucinated answer'."""
    selected = select_tools("Tell me something interesting")
    assert FALLBACK_TOOLS <= selected
    assert "query_f1_database" in selected


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_input_falls_back(blank):
    assert FALLBACK_TOOLS <= select_tools(blank)


def test_matching_is_whole_word_not_substring():
    """'sq' inside 'square' must not pull in the sprint shootout tool."""
    assert "get_sprint_qualifying_results" not in select_tools(
        "Describe the square layout of the paddock"
    )


def test_routing_actually_shrinks_the_bound_set():
    """The whole point: a specific question binds materially fewer than 15."""
    selected = select_tools("Who won the 2023 Monaco Grand Prix?")
    assert len(selected) < len(TOOL_MAP)
    # The f1db schema is the single most expensive description; a plain
    # race-result lookup must not be paying for it.
    assert "query_f1_database" not in selected


def test_selection_is_immutable_and_deterministic():
    first = select_tools("Who won Monaco 2023?")
    second = select_tools("Who won Monaco 2023?")
    assert first == second
    assert isinstance(first, frozenset)
