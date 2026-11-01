"""Tests for the chat router's engine failover.

AMD Token Lab answers first, but it is a beta: a points budget and an access
window that lapses unless extended by hand. When it (or any engine) fails with
its own error, the question has to move to the next engine rather than become
a "System Error". What is pinned here:

* **The engine's own failures hand the question on** — spent points (402),
  a rate limit (429), a dropped connection — and the failed engine rests.
* **The next engine starts from the question.** It never sees the failed
  engine's half-finished tool calls, and the eval's history is the winner's.
* **Our own bugs do not fail over.** Running them on a second engine would
  only fail twice and hide the cause.
* **When the last engine fails, the user sees that failure**, through the same
  client-safe path as any other.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage, ToolMessage
import pytest

from app.api import llm as llm_module
from app.api.routers import chat as chat_router
from app.config import LLMProvider

PRIMARY = LLMProvider(name="primary", model="m-1", key_env="PRIMARY_KEY", base_url="https://primary.example/v1")
BACKUP = LLMProvider(name="backup", model="m-2", key_env="BACKUP_KEY")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(chat_router, "_llm_cache", {})
    monkeypatch.setattr(llm_module, "_resting_until", {})
    monkeypatch.setattr(chat_router, "build_memory_context", lambda *_a, **_k: "")
    monkeypatch.setattr(chat_router, "save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat_router, "available_providers", lambda: (PRIMARY, BACKUP))


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


class _Engine:
    """One engine's scripted replies, and every message list it was sent."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.seen: list[list] = []

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _install_engines(monkeypatch, primary: list, backup: list) -> tuple[_Engine, _Engine]:
    engines = {"primary": _Engine(primary), "backup": _Engine(backup)}
    monkeypatch.setattr(chat_router, "_get_llm", lambda provider, *, with_tools: engines[provider.name])
    return engines["primary"], engines["backup"]


def _status_error(status: int) -> Exception:
    exc = RuntimeError(f"Error code: {status}")
    exc.status_code = status  # type: ignore[attr-defined]
    return exc


def _network_error() -> Exception:
    try:
        raise RuntimeError("Connection error.") from httpx.ConnectError("connection reset")
    except RuntimeError as exc:
        return exc


def _tool_call(name: str = "get_race_results") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": "call-1", "type": "tool_call"}])


class _FakeTool:
    def invoke(self, _args):
        return "VER P1"


def _post(client) -> str:
    return client.post("/chat", json={"messages": [{"role": "user", "content": "who won?"}]}).text


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure",
    [_status_error(402), _status_error(429), _status_error(503), _network_error()],
    ids=["points-spent", "rate-limited", "overloaded", "unreachable"],
)
def test_an_engine_failure_hands_the_question_to_the_next_engine(client, monkeypatch, failure):
    _install_engines(monkeypatch, primary=[failure], backup=[AIMessage(content="Verstappen won.")])

    assert _post(client) == "Verstappen won."


@pytest.mark.unit
def test_the_failed_engine_rests_so_the_next_questions_skip_it(client, monkeypatch):
    _install_engines(monkeypatch, primary=[_status_error(402)], backup=[AIMessage(content="ok")])

    _post(client)

    assert "primary" in llm_module._resting_until
    assert "backup" not in llm_module._resting_until


@pytest.mark.unit
def test_the_next_engine_starts_from_the_question_not_the_failed_tool_calls(client, monkeypatch):
    """A failure mid-loop leaves the primary's tool calls in the history; the
    backup must not inherit calls it never made (Gemini rejects them)."""
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool())
    _, backup = _install_engines(
        monkeypatch,
        primary=[_tool_call(), _status_error(402)],
        backup=[AIMessage(content="Verstappen won.")],
    )

    body = _post(client)

    assert backup.seen[0][-1].content == "who won?"
    assert not any(isinstance(m, ToolMessage) for m in backup.seen[0])
    # The primary's markers were already streamed; the answer is the backup's.
    assert "[TOOL_START]Get Race Results[/TOOL_START]" in body
    assert body.endswith("Verstappen won.")


@pytest.mark.unit
def test_our_own_bug_is_not_retried_on_another_engine(client, monkeypatch):
    _, backup = _install_engines(monkeypatch, primary=[KeyError("messages")], backup=[])

    body = _post(client)

    assert "System Error" in body
    assert backup.seen == [], "the backup would only fail the same way"
    assert llm_module._resting_until == {}


@pytest.mark.unit
def test_when_every_engine_fails_the_user_sees_the_last_failure(client, monkeypatch):
    _install_engines(monkeypatch, primary=[_status_error(402)], backup=[_status_error(429)])

    body = _post(client)

    assert "rate-limited" in body
    assert set(llm_module._resting_until) == {"primary", "backup"}


@pytest.mark.unit
def test_no_engine_configured_is_a_client_safe_error(client, monkeypatch):
    def _none_configured():
        raise RuntimeError("No chat engine is configured: set at least one of TOKENLAB_API_KEY, GOOGLE_API_KEY")

    monkeypatch.setattr(chat_router, "available_providers", _none_configured)

    body = _post(client)

    assert body.startswith("**System Error:**")
    assert "TOKENLAB_API_KEY" not in body, "configuration detail stays in the server log"


@pytest.mark.unit
async def test_the_eval_gets_the_answering_engines_history(monkeypatch):
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_race_results", _FakeTool())
    _install_engines(
        monkeypatch,
        primary=[_status_error(503)],
        backup=[_tool_call(), AIMessage(content="Verstappen won.")],
    )

    streamed, messages = await chat_router.ask_anonymously("Who won Monaco?")

    assert streamed.endswith("Verstappen won.")
    assert [m.content for m in messages if isinstance(m, ToolMessage)] == ["VER P1"]


@pytest.mark.unit
def test_an_answer_repair_runs_on_the_engine_that_answered(client, monkeypatch):
    """The repair request goes to the backup that wrote the answer, not the resting primary."""
    from app.api import answer_repair

    table = "| race_winner | race_team |\n| --- | --- |\n| Lando Norris | McLaren |"
    monkeypatch.setattr(answer_repair, "constructor_names", lambda: frozenset({"Mercedes", "McLaren"}))
    monkeypatch.setitem(chat_router.TOOL_MAP, "query_f1_database", type("_T", (), {"invoke": lambda _s, _a: table})())
    _, backup = _install_engines(
        monkeypatch,
        primary=[_status_error(402)],
        backup=[
            _tool_call("query_f1_database"),
            AIMessage(content="Lando Norris (Mercedes) won."),
            AIMessage(content="Lando Norris (McLaren) won."),
        ],
    )

    body = _post(client)

    assert body.endswith("Lando Norris (McLaren) won.")
    assert len(backup.seen) == 3, "tool turn, answer, repair — all on the backup"
