"""Tests for app.api.routers.chat — the agentic tool-use loop.

This is the module where a failure is most visible to a user and least visible
to a log, so the behaviours pinned here are the ones that keep a broken turn
from becoming a hung or lying answer:

* **The loop terminates — with an answer.** ``MAX_AGENT_TURNS`` is the only
  thing standing between a model that keeps requesting tools and an endless
  stream. The last permitted turn offers no tools, so the model answers from
  what it already fetched; the notice is only for a model that says nothing.
* **A failing tool does not kill the turn.** A timeout or an exception becomes a
  ``ToolMessage`` the model can read and route around — the alternative is a
  dead stream with no explanation.
* **Malformed tool calls are recovered.** The model sometimes emits calls as
  inline ``<function=...>`` text and Groq rejects them; `tool_recovery` parses
  the intent back out. If recovery silently stopped working the chat would
  still "work", just never call a tool.
* **The model is built lazily, once per tool subset.** Constructing it at
  import would pull torch into startup and turn a missing ``GROQ_API_KEY`` into
  a dead service instead of a dead endpoint. Only the tools the question needs
  are bound, because every schema costs prompt tokens on every turn.
* **Nothing leaks.** A crash renders through the client-safe error path, and a
  rate limit gets its own message rather than an error id.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import pytest

from app.api.routers import chat as chat_router
from app.api.schemas.chat import ChatRequest


@pytest.fixture(autouse=True)
def _reset_llm_cache(monkeypatch):
    """Bound models are a module-global memo and would leak between tests."""
    monkeypatch.setattr(chat_router, "_llm_cache", {})


@pytest.fixture(autouse=True)
def _no_memory(monkeypatch):
    """Memory is off unless a test opts in; it is a separate subsystem."""
    monkeypatch.setattr(chat_router, "build_memory_context", lambda *_a, **_k: "")
    monkeypatch.setattr(chat_router, "save_message", lambda *_a, **_k: None)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


class _ScriptedLLM:
    """Returns a queued response per `ainvoke`, recording what it was sent.

    One script serves every tool subset, so ``bound_to`` records which subset
    each call asked for, and ``bindings`` any ``.bind(...)`` applied on top.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.seen: list[list] = []
        self.bound_to: list[frozenset[str]] = []
        self.bindings: list[dict] = []

    def bind(self, **kwargs):
        self.bindings.append(kwargs)
        return self

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _install_llm(monkeypatch, responses):
    llm = _ScriptedLLM(responses)

    def _get_llm(tool_names):
        llm.bound_to.append(tool_names)
        return llm

    monkeypatch.setattr(chat_router, "_get_llm", _get_llm)
    return llm


TOOLS = frozenset({"get_race_results"})


def _tool_call(name, args=None, call_id="call-1"):
    return {"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}


def _post(client, **payload):
    body = {"messages": [{"role": "user", "content": "who won?"}], **payload}
    return client.post("/chat", json=body).text


# ---------------------------------------------------------------------------
# Message construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_system_prompt_carries_the_persona_and_today():
    prompt = chat_router.build_system_prompt("March 08, 2026")

    assert "Race Engineer" in prompt
    assert "March 08, 2026" in prompt


@pytest.mark.unit
def test_system_prompt_tells_the_model_which_season_to_ask_for():
    """The schedule tool needs a year; it is parsed out of today's date."""
    prompt = chat_router.build_system_prompt("March 08, 2026")

    assert "get_season_schedule(2026)" in prompt


@pytest.mark.unit
def test_system_prompt_omits_the_memory_block_when_there_is_none():
    assert "PERSONALISATION & MEMORY" not in chat_router.build_system_prompt("March 08, 2026")


@pytest.mark.unit
def test_system_prompt_includes_supplied_memory_context():
    prompt = chat_router.build_system_prompt("March 08, 2026", "Supports Ferrari.")

    assert "PERSONALISATION & MEMORY" in prompt
    assert "Supports Ferrari." in prompt


@pytest.mark.unit
def test_history_is_translated_into_langchain_roles():
    request = ChatRequest(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "who won Monaco?"},
        ]
    )

    messages = chat_router.build_langchain_messages(request, "March 08, 2026")

    # A client-supplied "system" turn must not be able to inject a second
    # system prompt alongside the persona.
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage, AIMessage, HumanMessage]


@pytest.mark.unit
def test_latest_user_text_reads_the_most_recent_user_turn():
    request = ChatRequest(
        messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )

    assert chat_router._latest_user_text(request) == "second"


@pytest.mark.unit
def test_latest_user_text_is_empty_without_a_user_turn():
    assert chat_router._latest_user_text(ChatRequest(messages=[{"role": "assistant", "content": "hi"}])) == ""


@pytest.mark.unit
def test_latest_user_text_tolerates_a_turn_with_no_content():
    assert chat_router._latest_user_text(ChatRequest(messages=[{"role": "user"}])) == ""


# ---------------------------------------------------------------------------
# Lazy model construction
# ---------------------------------------------------------------------------


class _Raw:
    """Stands in for the Groq chat model; records every ``bind_tools`` call."""

    bound: ClassVar[list[list[str]]] = []

    def bind_tools(self, tools):
        type(self).bound.append([tool.name for tool in tools])
        return ("bound", tuple(tool.name for tool in tools))


@pytest.fixture
def raw_model(monkeypatch):
    _Raw.bound = []
    monkeypatch.setattr(chat_router, "build_chat_llm", _Raw)
    return _Raw


@pytest.mark.unit
def test_the_model_is_built_once_per_tool_subset_and_memoised(raw_model):
    first = chat_router._get_llm(TOOLS)
    second = chat_router._get_llm(TOOLS)

    assert first is second
    assert len(raw_model.bound) == 1, "the model must not be rebuilt per request"


@pytest.mark.unit
def test_the_model_is_bound_to_exactly_the_selected_tools(raw_model):
    chat_router._get_llm(frozenset({"get_race_results", "consult_rulebook"}))

    assert raw_model.bound == [["consult_rulebook", "get_race_results"]], "sorted, so the cache key is stable"


@pytest.mark.unit
def test_each_subset_gets_its_own_bound_model(raw_model):
    rulebook = chat_router._get_llm(frozenset({"consult_rulebook"}))
    results = chat_router._get_llm(TOOLS)

    assert rulebook != results
    assert set(chat_router._llm_cache) == {frozenset({"consult_rulebook"}), TOOLS}


@pytest.mark.unit
def test_an_empty_subset_is_the_unbound_model(raw_model):
    """No schemas at all — the cheap path for the forced final answer."""
    model = chat_router._get_llm(frozenset())

    assert isinstance(model, _Raw)
    assert raw_model.bound == []


# ---------------------------------------------------------------------------
# _ainvoke_with_recovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_normal_response_passes_straight_through(monkeypatch):
    expected = AIMessage(content="Verstappen won.")
    _install_llm(monkeypatch, [expected])

    assert await chat_router._ainvoke_with_recovery([], TOOLS) is expected


@pytest.mark.unit
async def test_a_malformed_tool_call_is_recovered_into_a_tool_message(monkeypatch):
    failure = RuntimeError("tool_use_failed")
    _install_llm(monkeypatch, [failure])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: True)
    monkeypatch.setattr(chat_router, "recover_tool_calls", lambda exc: [_tool_call("get_race_results")])

    result = await chat_router._ainvoke_with_recovery([], TOOLS)

    assert result.tool_calls[0]["name"] == "get_race_results"
    assert result.content == ""


@pytest.mark.unit
async def test_an_unrecoverable_tool_failure_is_reraised(monkeypatch):
    """Recovery must not swallow a call it could not parse."""
    _install_llm(monkeypatch, [RuntimeError("tool_use_failed")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: True)
    monkeypatch.setattr(chat_router, "recover_tool_calls", lambda exc: [])

    with pytest.raises(RuntimeError):
        await chat_router._ainvoke_with_recovery([], TOOLS)


@pytest.mark.unit
async def test_an_unrelated_error_is_not_treated_as_a_tool_failure(monkeypatch):
    _install_llm(monkeypatch, [ConnectionError("groq unreachable")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    with pytest.raises(ConnectionError):
        await chat_router._ainvoke_with_recovery([], TOOLS)


@pytest.mark.unit
async def test_recovery_asks_for_the_selected_tools(monkeypatch):
    llm = _install_llm(monkeypatch, [AIMessage(content="ok")])

    await chat_router._ainvoke_with_recovery([], TOOLS)

    assert llm.bound_to == [TOOLS]


# ---------------------------------------------------------------------------
# _ainvoke_final
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_the_final_turn_binds_no_tools_and_says_why(monkeypatch):
    llm = _install_llm(monkeypatch, [AIMessage(content="Verstappen won.")])

    result = await chat_router._ainvoke_final([HumanMessage(content="who won?")], TOOLS)

    assert result.content == "Verstappen won."
    assert llm.bound_to == [frozenset()], "the cheap path sends no schemas"
    assert llm.seen[0][-1].content == chat_router.FINAL_TURN_DIRECTIVE


@pytest.mark.unit
async def test_a_refused_final_turn_retries_with_tool_calling_disabled(monkeypatch):
    """Groq 400s a tool call the request did not offer; the retry cannot."""
    llm = _install_llm(monkeypatch, [RuntimeError("tool_use_failed"), AIMessage(content="answer")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: True)

    result = await chat_router._ainvoke_final([], TOOLS)

    assert result.content == "answer"
    assert llm.bound_to == [frozenset(), TOOLS]
    assert llm.bindings == [{"tool_choice": "none"}]


@pytest.mark.unit
async def test_an_unrelated_final_turn_failure_is_reraised(monkeypatch):
    _install_llm(monkeypatch, [ConnectionError("groq unreachable")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    with pytest.raises(ConnectionError):
        await chat_router._ainvoke_final([], TOOLS)


# ---------------------------------------------------------------------------
# The streaming endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_plain_answer_is_streamed_back(client, monkeypatch):
    _install_llm(monkeypatch, [AIMessage(content="Verstappen won in Monaco.")])

    assert _post(client) == "Verstappen won in Monaco."


@pytest.mark.unit
def test_a_tool_call_is_executed_and_bracketed_with_progress_markers(client, monkeypatch):
    _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("get_race_results", {"year": 2026})]),
            AIMessage(content="Verstappen won."),
        ],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("VER P1"))

    body = _post(client)

    # The markers drive the client's "running a tool" indicator.
    assert "[TOOL_START]Get Race Results[/TOOL_START]" in body
    assert "[TOOL_END]Get Race Results[/TOOL_END]" in body
    assert body.endswith("Verstappen won.")


@pytest.mark.unit
def test_the_tool_result_is_fed_back_to_the_model(client, monkeypatch):
    llm = _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("get_race_results")]),
            AIMessage(content="done"),
        ],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("VER P1"))

    _post(client)

    tool_messages = [m for m in llm.seen[-1] if isinstance(m, ToolMessage)]
    assert tool_messages[0].content == "VER P1"
    assert tool_messages[0].name == "get_race_results"


@pytest.mark.unit
def test_an_unknown_tool_is_skipped_rather_than_invented(client, monkeypatch):
    _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("summon_safety_car")]),
            AIMessage(content="I cannot do that."),
        ],
    )

    body = _post(client)

    assert "TOOL_START" not in body
    assert body.endswith("I cannot do that.")


@pytest.mark.unit
def test_a_tool_timeout_is_reported_to_the_model_not_the_user(client, monkeypatch):
    llm = _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("get_race_results")]),
            AIMessage(content="The data source is slow."),
        ],
    )
    monkeypatch.setattr(chat_router, "TOOL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _SlowTool())

    body = _post(client)

    tool_message = next(m for m in llm.seen[-1] if isinstance(m, ToolMessage))
    assert "timed out" in tool_message.content
    # The user sees the model's reply, not the raw tool failure.
    assert body.endswith("The data source is slow.")


@pytest.mark.unit
def test_a_tool_exception_is_reported_to_the_model(client, monkeypatch):
    llm = _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("get_race_results")]),
            AIMessage(content="I could not fetch that."),
        ],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _ExplodingTool())

    _post(client)

    tool_message = next(m for m in llm.seen[-1] if isinstance(m, ToolMessage))
    assert "Error executing tool" in tool_message.content


@pytest.mark.unit
def test_the_last_permitted_turn_forces_an_answer_from_the_data_gathered(client, monkeypatch):
    """Without this ceiling a tool-looping model streams forever."""
    saved: list[tuple] = []
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 2)
    monkeypatch.setattr(chat_router, "save_message", lambda *args: saved.append(args))
    llm = _install_llm(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[_tool_call("get_race_results")]),
            AIMessage(content="", tool_calls=[_tool_call("get_race_results")]),
            AIMessage(content="From the results: Verstappen won."),
        ],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("data"))

    body = _post(client, user_id="u-5")

    assert body.endswith("From the results: Verstappen won.")
    assert "maximum number of reasoning steps" not in body
    assert llm.bound_to[-1] == frozenset(), "the final turn offers no tools"
    assert saved[-1] == ("u-5", "default", "assistant", "From the results: Verstappen won.")


@pytest.mark.unit
def test_a_forced_answer_for_an_anonymous_user_is_not_saved(client, monkeypatch):
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 1)
    monkeypatch.setattr(chat_router, "save_message", lambda *_a: pytest.fail("anonymous chat must not be saved"))
    _install_llm(
        monkeypatch,
        [AIMessage(content="", tool_calls=[_tool_call("get_race_results")]), AIMessage(content="answer")],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("data"))

    assert _post(client).endswith("answer")


@pytest.mark.unit
def test_a_model_that_says_nothing_on_the_last_turn_gets_the_notice(client, monkeypatch):
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 1)
    _install_llm(
        monkeypatch,
        [AIMessage(content="", tool_calls=[_tool_call("get_race_results")]), AIMessage(content="")],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("data"))

    assert "maximum number of reasoning steps" in _post(client)


@pytest.mark.unit
def test_only_the_tools_the_question_needs_are_offered(client, monkeypatch):
    questions: list[str] = []

    def _select(text):
        questions.append(text)
        return TOOLS

    monkeypatch.setattr(chat_router, "select_tools", _select)
    llm = _install_llm(monkeypatch, [AIMessage(content="ok")])

    _post(client)

    assert questions == ["who won?"]
    assert llm.bound_to == [TOOLS]


@pytest.mark.unit
def test_a_rate_limit_gets_its_own_message(client, monkeypatch):
    _install_llm(monkeypatch, [RuntimeError("Rate limit reached for model")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    body = _post(client)

    assert "rate-limited" in body
    # A quota message is not a server fault, so no correlation id is minted.
    assert "error_id" not in body


@pytest.mark.unit
def test_an_http_429_is_recognised_as_a_rate_limit(client, monkeypatch):
    _install_llm(monkeypatch, [RuntimeError("Received 429 from upstream")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    assert "rate-limited" in _post(client)


@pytest.mark.unit
def test_a_crash_renders_through_the_client_safe_error_path(client, monkeypatch):
    _install_llm(monkeypatch, [RuntimeError("connection to db.abcdefgh.supabase.co failed")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    body = _post(client)

    assert "System Error" in body
    assert "supabase.co" not in body


@pytest.mark.unit
def test_the_response_is_streamed_as_plain_text(client, monkeypatch):
    _install_llm(monkeypatch, [AIMessage(content="ok")])

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert response.headers["content-type"].startswith("text/plain")


# ---------------------------------------------------------------------------
# Memory integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_memory_is_untouched_without_a_user_id(client, monkeypatch):
    monkeypatch.setattr(
        chat_router,
        "build_memory_context",
        lambda *_a, **_k: pytest.fail("anonymous chat must not touch memory"),
    )
    _install_llm(monkeypatch, [AIMessage(content="ok")])

    assert _post(client) == "ok"


@pytest.mark.unit
def test_both_turns_are_saved_for_an_identified_user(client, monkeypatch):
    saved: list[tuple] = []
    monkeypatch.setattr(chat_router, "build_memory_context", lambda *_a, **_k: "Supports Ferrari.")
    monkeypatch.setattr(
        chat_router,
        "save_message",
        lambda user_id, thread_id, role, content: saved.append((user_id, thread_id, role, content)),
    )
    _install_llm(monkeypatch, [AIMessage(content="Verstappen won.")])

    _post(client, user_id="u-1", thread_id="t-9")

    assert saved == [
        ("u-1", "t-9", "user", "who won?"),
        ("u-1", "t-9", "assistant", "Verstappen won."),
    ]


@pytest.mark.unit
def test_an_omitted_thread_id_falls_back_to_a_default(client, monkeypatch):
    saved: list[tuple] = []
    monkeypatch.setattr(chat_router, "save_message", lambda user_id, thread_id, role, content: saved.append(thread_id))
    _install_llm(monkeypatch, [AIMessage(content="ok")])

    _post(client, user_id="u-2")

    assert saved[0] == "default"


@pytest.mark.unit
def test_the_memory_context_reaches_the_system_prompt(client, monkeypatch):
    monkeypatch.setattr(chat_router, "build_memory_context", lambda *_a, **_k: "Supports Ferrari.")
    llm = _install_llm(monkeypatch, [AIMessage(content="ok")])

    _post(client, user_id="u-3")

    assert "Supports Ferrari." in llm.seen[0][0].content


@pytest.mark.unit
def test_an_empty_assistant_reply_is_not_saved(client, monkeypatch):
    """An empty turn carries no information and would pollute recall."""
    saved: list[str] = []
    monkeypatch.setattr(chat_router, "save_message", lambda user_id, thread_id, role, content: saved.append(role))
    _install_llm(monkeypatch, [AIMessage(content="")])

    _post(client, user_id="u-4")

    assert saved == ["user"]


class _FakeTool:
    def __init__(self, result):
        self._result = result

    def invoke(self, _args):
        return self._result


class _SlowTool:
    def invoke(self, _args):
        import time

        time.sleep(0.3)
        return "too late"


class _ExplodingTool:
    def invoke(self, _args):
        raise ValueError("f1db unavailable")
