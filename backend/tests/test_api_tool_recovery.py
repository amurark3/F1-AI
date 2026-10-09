"""Tests for app.api.tool_recovery — repairing Groq's rejected tool calls.

Llama on Groq intermittently emits a tool call as inline ``<function=NAME{...}>``
text instead of a structured call, and Groq answers with a ``tool_use_failed``
400 carrying the raw generation. This module is the only thing standing between
that rejection and a chat turn that silently never calls a tool.

The risk here is not that recovery fails — it is that recovery succeeds
*wrongly*. A brace inside a SQL string ending the object early, half an object
parsed as a whole one, or a nameless call executed as if it were real would all
send the agent loop off with arguments the model never wrote. Every malformed
shape below asserts either the exact repaired call or an empty list; there is no
best-effort guess in between.
"""

from __future__ import annotations

import pytest

from app.api.tool_recovery import is_tool_use_failed, recover_tool_calls


def _exc(message: str, body: object = None) -> Exception:
    """A Groq SDK error stand-in: the parsed response body rides on ``.body``."""
    exc = RuntimeError(message)
    exc.body = body  # type: ignore[attr-defined]
    return exc


def _generation(text: str) -> Exception:
    """The realistic shape: a 400 whose body carries ``failed_generation``."""
    return _exc(
        "Error code: 400 - tool_use_failed",
        {"error": {"code": "tool_use_failed", "failed_generation": text}},
    )


# ---------------------------------------------------------------------------
# Classifying the error
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_structured_tool_use_failed_body_is_recognised():
    assert is_tool_use_failed(_exc("Error code: 400", {"error": {"code": "tool_use_failed"}}))


@pytest.mark.unit
def test_a_different_groq_error_code_is_not_treated_as_recoverable():
    """Retrying a context-length failure as a tool call would loop forever."""
    assert not is_tool_use_failed(_exc("Error code: 400", {"error": {"code": "context_length_exceeded"}}))


@pytest.mark.unit
def test_a_null_error_object_falls_back_to_the_message():
    assert is_tool_use_failed(_exc("tool_use_failed while parsing arguments", {"error": None}))


@pytest.mark.unit
def test_an_exception_with_no_body_is_matched_on_its_message():
    assert is_tool_use_failed(RuntimeError("Error code: 400 - {'code': 'tool_use_failed'}"))


@pytest.mark.unit
def test_a_non_dict_body_falls_back_to_the_message():
    assert not is_tool_use_failed(_exc("connection reset by peer", "<html>502</html>"))


@pytest.mark.unit
def test_an_ordinary_transport_error_is_not_recoverable():
    assert not is_tool_use_failed(ConnectionError("groq unreachable"))


# ---------------------------------------------------------------------------
# Recovering the calls
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_single_inline_call_is_recovered_with_its_arguments():
    exc = _generation('<function=get_race_results{"year": 2026, "grand_prix": "Monaco"}>')

    assert recover_tool_calls(exc) == [
        {
            "name": "get_race_results",
            "args": {"year": 2026, "grand_prix": "Monaco"},
            "id": "recovered_0",
        }
    ]


@pytest.mark.unit
def test_two_inline_calls_are_recovered_in_order_with_distinct_ids():
    """Ids must differ — the agent loop keys tool results off them."""
    exc = _generation(
        'I will check both.<function=get_driver_standings{"year": 2026}> '
        'and <function=get_constructor_standings{"year": 2026}>'
    )

    assert [(c["name"], c["id"]) for c in recover_tool_calls(exc)] == [
        ("get_driver_standings", "recovered_0"),
        ("get_constructor_standings", "recovered_1"),
    ]


@pytest.mark.unit
def test_a_brace_inside_a_sql_string_does_not_end_the_object_early():
    """The failure mode this module exists for: SQL arguments full of punctuation."""
    sql = "SELECT name FROM driver WHERE name LIKE '%{VER}%' AND id > 0"
    exc = _generation(f'<function=query_f1_database{{"sql": "{sql}"}}>')

    assert recover_tool_calls(exc)[0]["args"] == {"sql": sql}


@pytest.mark.unit
def test_an_escaped_quote_inside_a_string_does_not_end_the_string_early():
    exc = _generation('<function=query_f1_database{"sql": "SELECT \\"name\\" FROM driver"}>')

    assert recover_tool_calls(exc)[0]["args"] == {"sql": 'SELECT "name" FROM driver'}


@pytest.mark.unit
def test_a_nested_object_argument_survives_intact():
    exc = _generation('<function=get_pit_strategy{"year": 2026, "opts": {"driver": {"code": "VER"}}}>')

    assert recover_tool_calls(exc)[0]["args"]["opts"] == {"driver": {"code": "VER"}}


@pytest.mark.unit
def test_whitespace_around_the_tool_name_is_stripped():
    """A stray space would make the name miss ``TOOL_MAP`` and the call vanish."""
    exc = _generation('<function= get_season_schedule {"year": 2026}>')

    assert recover_tool_calls(exc)[0]["name"] == "get_season_schedule"


@pytest.mark.unit
def test_the_raw_message_is_parsed_when_the_body_carries_no_generation():
    exc = _exc(
        'Error code: 400 - tool_use_failed: <function=get_race_anomalies{"year": 2025, "round_num": 1}>',
        {"error": {"code": "tool_use_failed"}},
    )

    assert recover_tool_calls(exc)[0]["args"] == {"year": 2025, "round_num": 1}


@pytest.mark.unit
def test_a_bare_exception_with_no_body_is_still_parsed():
    exc = RuntimeError('tool_use_failed <function=get_qualifying_results{"year": 2026, "grand_prix": "Monaco"}>')

    assert recover_tool_calls(exc)[0]["name"] == "get_qualifying_results"


@pytest.mark.unit
def test_a_good_call_after_a_broken_one_keeps_the_recovered_index_contiguous():
    """Ids count recovered calls, not attempts, so a skip must not leave a gap."""
    exc = _generation('<function=broken{"year": }> <function=get_driver_standings{"year": 2026}>')

    assert recover_tool_calls(exc) == [{"name": "get_driver_standings", "args": {"year": 2026}, "id": "recovered_0"}]


# ---------------------------------------------------------------------------
# Shapes that must recover nothing rather than something wrong
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "generation"),
    [
        ("no marker at all", "I think Verstappen won that one."),
        ("marker with no argument object", "<function=get_race_results"),
        ("marker with a truncated object", '<function=get_race_results{"year": 2026'),
        ("unbalanced braces", '<function=get_race_results{"opts": {"year": 2026}>'),
        ("arguments that are not JSON", "<function=get_race_results{year: 2026}>"),
        ("an empty tool name", '<function={"year": 2026}>'),
        ("an empty generation", ""),
    ],
)
def test_an_unrecoverable_call_yields_nothing(shape, generation):
    """Returning [] lets the caller re-raise; a guess would run the wrong tool."""
    assert recover_tool_calls(_generation(generation)) == [], shape
