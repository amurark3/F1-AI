"""Tests for app.api.routers.chat — the agentic tool-use loop.

This is the module where a failure is most visible to a user and least visible
to a log, so the behaviours pinned here are the ones that keep a broken turn
from becoming a hung or lying answer:

* **The loop terminates.** ``MAX_AGENT_TURNS`` is the only thing standing
  between a model that keeps requesting tools and an endless stream; the notice
  it emits is asserted, not assumed.
* **A failing tool does not kill the turn.** A timeout or an exception becomes a
  ``ToolMessage`` the model can read and route around — the alternative is a
  dead stream with no explanation.
* **Malformed tool calls are recovered.** Llama emits calls as inline
  ``<function=...>`` text and Groq rejects them; `tool_recovery` parses the
  intent back out. If recovery silently stopped working the chat would still
  "work", just never call a tool.
* **The model is built lazily.** Constructing it at import would pull torch into
  startup and turn a missing ``GROQ_API_KEY`` into a dead service instead of a
  dead endpoint.
* **Nothing leaks.** A crash renders through the client-safe error path, and a
  rate limit gets its own message rather than an error id.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import pytest

from app.api.routers import chat as chat_router
from app.api.schemas.chat import ChatRequest


@pytest.fixture(autouse=True)
def _reset_llm_singleton():
    """The bound model is a module-global memo and would leak between tests."""
    chat_router._llm_with_tools = None
    yield
    chat_router._llm_with_tools = None


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
    """Returns a queued response per `ainvoke`, recording what it was sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.seen: list[list] = []

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _install_llm(monkeypatch, responses):
    llm = _ScriptedLLM(responses)
    monkeypatch.setattr(chat_router, "_get_llm_with_tools", lambda: llm)
    return llm


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


@pytest.mark.unit
def test_the_model_is_built_once_and_memoised(monkeypatch):
    built: list[int] = []

    class _Bound:
        pass

    class _Raw:
        def bind_tools(self, tools):
            built.append(len(tools))
            return _Bound()

    monkeypatch.setattr(chat_router, "build_chat_llm", _Raw)

    first = chat_router._get_llm_with_tools()
    second = chat_router._get_llm_with_tools()

    assert first is second
    assert len(built) == 1, "the model must not be rebuilt per request"


@pytest.mark.unit
def test_the_model_is_bound_to_the_whole_tool_list(monkeypatch):
    seen: list = []

    class _Raw:
        def bind_tools(self, tools):
            seen.extend(tools)
            return object()

    monkeypatch.setattr(chat_router, "build_chat_llm", _Raw)
    chat_router._get_llm_with_tools()

    assert len(seen) == len(chat_router.TOOL_LIST)


# ---------------------------------------------------------------------------
# _ainvoke_with_recovery
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_normal_response_passes_straight_through(monkeypatch):
    expected = AIMessage(content="Verstappen won.")
    _install_llm(monkeypatch, [expected])

    assert await chat_router._ainvoke_with_recovery([]) is expected


@pytest.mark.unit
async def test_a_malformed_tool_call_is_recovered_into_a_tool_message(monkeypatch):
    failure = RuntimeError("tool_use_failed")
    _install_llm(monkeypatch, [failure])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: True)
    monkeypatch.setattr(chat_router, "recover_tool_calls", lambda exc: [_tool_call("get_race_results")])

    result = await chat_router._ainvoke_with_recovery([])

    assert result.tool_calls[0]["name"] == "get_race_results"
    assert result.content == ""


@pytest.mark.unit
async def test_an_unrecoverable_tool_failure_is_reraised(monkeypatch):
    """Recovery must not swallow a call it could not parse."""
    _install_llm(monkeypatch, [RuntimeError("tool_use_failed")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: True)
    monkeypatch.setattr(chat_router, "recover_tool_calls", lambda exc: [])

    with pytest.raises(RuntimeError):
        await chat_router._ainvoke_with_recovery([])


@pytest.mark.unit
async def test_an_unrelated_error_is_not_treated_as_a_tool_failure(monkeypatch):
    _install_llm(monkeypatch, [ConnectionError("groq unreachable")])
    monkeypatch.setattr(chat_router, "is_tool_use_failed", lambda exc: False)

    with pytest.raises(ConnectionError):
        await chat_router._ainvoke_with_recovery([])


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
def test_the_loop_stops_at_the_turn_limit(client, monkeypatch):
    """Without this ceiling a tool-looping model streams forever."""
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 2)
    _install_llm(
        monkeypatch,
        [AIMessage(content="", tool_calls=[_tool_call("get_race_results")]) for _ in range(3)],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool("data"))

    body = _post(client)

    assert "maximum number of reasoning steps" in body


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
