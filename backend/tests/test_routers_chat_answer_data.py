"""Tests for the ``[ANSWER_DATA]`` block the chat stream sends ahead of an answer.

A tool that returns ``Sourced`` text hands the stream its provenance; the stream sends one block, built
from the winning engine's tool results, between the tool markers and the checked answer. The model
itself reads the plain text only.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
import pytest

from app.api import llm as llm_module
from app.api.routers import chat as chat_router
from app.api.tools.provenance import Provenance, Sourced
from app.config import LLMProvider

PRIMARY = LLMProvider(name="primary", model="m-1", key_env="PRIMARY_KEY", base_url="https://primary.example/v1")
BACKUP = LLMProvider(name="backup", model="m-2", key_env="BACKUP_KEY")
DATA = r"\[ANSWER_DATA\](.*?)\[/ANSWER_DATA\]"

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(chat_router, "_llm_cache", {})
    monkeypatch.setattr(llm_module, "_resting_until", {})
    monkeypatch.setattr(chat_router, "build_memory_context", lambda *_a, **_k: "")
    monkeypatch.setattr(chat_router, "save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat_router, "available_providers", lambda: (PRIMARY,))


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app)


class _Engine:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.seen: list[list] = []

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Tool:
    def __init__(self, result) -> None:
        self._result = result

    def invoke(self, _args):
        return self._result


def _engines(monkeypatch, **by_name) -> dict[str, _Engine]:
    engines = {name: _Engine(responses) for name, responses in by_name.items()}
    monkeypatch.setattr(chat_router, "_get_llm", lambda provider, *, with_tools: engines[provider.name])
    return engines


def _call(name: str, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": call_id, "type": "tool_call"}])


def _sourced(subject: str, *chips: str) -> Sourced:
    return Sourced(f"{subject} table", Provenance(sources=chips, subject=subject))


def _post(client) -> str:
    return client.post("/chat", json={"messages": [{"role": "user", "content": "who won?"}]}).text


def _block(body: str) -> dict:
    import re

    return json.loads(re.search(DATA, body, re.DOTALL).group(1))


def test_the_block_sits_between_the_tool_markers_and_the_answer(client, monkeypatch):
    _engines(monkeypatch, primary=[_call("get_season_schedule"), AIMessage(content="It is Mexico.")])
    monkeypatch.setitem(
        chat_router.TOOL_MAP, "get_season_schedule", _Tool(_sourced("2026 calendar", "f1db · calendar"))
    )

    body = _post(client)

    assert body.startswith("[TOOL_START]Get Season Schedule[/TOOL_START][TOOL_END]Get Season Schedule[/TOOL_END]")
    assert body.endswith("[/ANSWER_DATA]It is Mexico.")
    assert _block(body) == {"subject": "2026 calendar", "sources": ["f1db · calendar"], "charts": []}


def test_the_model_reads_the_plain_text(client, monkeypatch):
    engines = _engines(monkeypatch, primary=[_call("get_season_schedule"), AIMessage(content="ok")])
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Tool(_sourced("2026 calendar", "f1db")))

    _post(client)

    seen = next(m for m in engines["primary"].seen[-1] if isinstance(m, ToolMessage))
    assert seen.content == "2026 calendar table"
    assert type(seen.content) is str
    assert isinstance(seen.artifact, Provenance)


def test_a_plain_text_tool_sends_no_block(client, monkeypatch):
    _engines(monkeypatch, primary=[_call("get_season_schedule"), AIMessage(content="ok")])
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Tool("Failed to fetch schedule: boom"))

    assert "ANSWER_DATA" not in _post(client)


def test_an_answer_with_no_tools_sends_no_block(client, monkeypatch):
    _engines(monkeypatch, primary=[AIMessage(content="Hello.")])

    assert _post(client) == "Hello."


def test_the_forced_last_turn_answer_carries_the_block_too(client, monkeypatch):
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 1)
    _engines(monkeypatch, primary=[_call("get_season_schedule"), AIMessage(content="From the data.")])
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Tool(_sourced("2026 calendar", "f1db")))

    body = _post(client)

    assert _block(body)["subject"] == "2026 calendar"
    assert body.endswith("From the data.")


def test_the_notice_path_sends_no_block(client, monkeypatch):
    monkeypatch.setattr(chat_router, "MAX_AGENT_TURNS", 1)
    _engines(monkeypatch, primary=[_call("get_season_schedule"), AIMessage(content="")])
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Tool(_sourced("2026 calendar", "f1db")))

    body = _post(client)

    assert "maximum number of reasoning steps" in body
    assert "ANSWER_DATA" not in body


def test_after_a_failover_only_the_winning_engines_results_are_sent(client, monkeypatch):
    monkeypatch.setattr(chat_router, "available_providers", lambda: (PRIMARY, BACKUP))
    failure = RuntimeError("Error code: 402")
    failure.status_code = 402  # type: ignore[attr-defined]
    _engines(
        monkeypatch,
        primary=[_call("get_season_schedule"), failure],
        backup=[_call("get_driver_standings"), AIMessage(content="Done.")],
    )
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Tool(_sourced("2026 calendar", "primary chip")))
    monkeypatch.setitem(chat_router.TOOL_MAP, "get_driver_standings", _Tool(_sourced("2026 standings", "backup chip")))

    body = _post(client)

    assert _block(body) == {"subject": "2026 standings", "sources": ["backup chip"], "charts": []}
    assert body.count("[ANSWER_DATA]") == 1


def test_a_timeout_carries_no_provenance(monkeypatch):
    import asyncio

    monkeypatch.setattr(chat_router, "TOOL_TIMEOUT_SECONDS", 0.01)

    class _Slow:
        def invoke(self, _args):
            import time

            time.sleep(0.2)

    monkeypatch.setitem(chat_router.TOOL_MAP, "get_season_schedule", _Slow())

    content, provenance = asyncio.run(chat_router._invoke_tool({"name": "get_season_schedule", "args": {}}))

    assert "timed out" in content
    assert provenance is None


def test_the_stream_marker_strips_every_kind_including_multiline_data():
    raw = '[TOOL_START]A[/TOOL_START][TOOL_END]A[/TOOL_END][ANSWER_DATA]{\n"a": 1}[/ANSWER_DATA]Answer'

    assert chat_router.STREAM_MARKER.sub("", raw) == "Answer"
