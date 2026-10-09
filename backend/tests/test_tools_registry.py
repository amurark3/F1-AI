"""Tests for app.api.tools.__init__ — the registry the agent loop dispatches on.

``TOOL_LIST`` is what the model is bound to and ``TOOL_MAP`` is what the loop
looks a returned call up in. If the two ever disagree the model is offered a
tool that cannot be executed, and the turn silently drops the call instead of
failing — so their agreement is asserted rather than assumed.

A tool's name and description are its public schema: the model chooses a tool by
reading them. A tool that loses its description becomes invisible to the model
while every test of its body still passes, which is why the descriptions are
pinned here too.
"""

from __future__ import annotations

import pytest

from app.api import tools as tools_pkg

# The contract the chat router and the system prompt are written against.
EXPECTED_TOOLS = frozenset(
    {
        "get_race_predictions",
        "query_f1_database",
        "get_race_anomalies",
        "get_pit_strategy",
        "get_weather_conditions",
        "perform_web_search",
        "get_sprint_results",
        "get_sprint_qualifying_results",
        "get_qualifying_results",
        "compare_drivers",
        "get_race_results",
        "consult_rulebook",
        "get_driver_standings",
        "get_constructor_standings",
        "get_season_schedule",
    }
)


@pytest.mark.unit
def test_the_package_exposes_exactly_the_expected_tool_set():
    assert {tool.name for tool in tools_pkg.TOOL_LIST} == EXPECTED_TOOLS


@pytest.mark.unit
def test_the_registry_has_no_duplicate_entries():
    """A duplicate would be invisible in TOOL_MAP but doubles the bound schema."""
    assert len(tools_pkg.TOOL_LIST) == len(EXPECTED_TOOLS)


@pytest.mark.unit
def test_the_map_and_the_list_describe_the_same_tools():
    assert {tool.name: tool for tool in tools_pkg.TOOL_LIST} == tools_pkg.TOOL_MAP


@pytest.mark.unit
def test_only_the_registry_is_exported():
    assert tools_pkg.__all__ == ["TOOL_LIST", "TOOL_MAP"]


@pytest.mark.unit
@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
def test_every_tool_advertises_a_description_to_the_model(tool_name):
    """An empty description leaves the model guessing from the name alone."""
    assert len(tools_pkg.TOOL_MAP[tool_name].description.strip()) > 40


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool_name", "expected_args"),
    [
        ("get_race_predictions", {"year", "round_num"}),
        ("get_pit_strategy", {"year", "round_num", "driver_code"}),
        ("query_f1_database", {"sql"}),
        ("consult_rulebook", {"query", "year"}),
        ("compare_drivers", {"year", "grand_prix", "driver1", "driver2"}),
        ("get_race_results", {"year", "grand_prix"}),
        ("get_sprint_results", {"year", "grand_prix"}),
        ("get_sprint_qualifying_results", {"year", "grand_prix"}),
        ("get_qualifying_results", {"year", "grand_prix"}),
        ("get_race_anomalies", {"year", "round_num"}),
        ("get_weather_conditions", {"location"}),
        ("perform_web_search", {"query"}),
        ("get_driver_standings", {"year"}),
        ("get_constructor_standings", {"year"}),
        ("get_season_schedule", {"year"}),
    ],
)
def test_each_tool_advertises_its_parameter_names(tool_name, expected_args):
    """Renaming a parameter changes the schema the model fills in."""
    assert set(tools_pkg.TOOL_MAP[tool_name].args) == expected_args


@pytest.mark.unit
def test_the_sql_tool_ships_the_database_schema_in_its_description():
    """Without the table reference the model writes SQL against invented tables."""
    description = tools_pkg.TOOL_MAP["query_f1_database"].description

    assert "SCHEMA:" in description
    assert "race_data" in description
