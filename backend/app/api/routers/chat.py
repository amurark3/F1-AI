"""AI chat router and agent orchestration."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
from typing import NamedTuple

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
import structlog

from app.api.errors import client_error_text
from app.api.llm import build_chat_llm
from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.schemas.chat import ChatRequest
from app.api.tool_recovery import is_tool_use_failed, recover_tool_calls, unbound_tool_name
from app.api.tool_router import select_tools
from app.api.tools import TOOL_MAP
from app.config import MAX_AGENT_TURNS, TOOL_TIMEOUT_SECONDS
from app.data.memory import build_memory_context, save_message

logger = structlog.get_logger()
router = APIRouter(tags=["chat"])


# The chat model is built lazily on first use, not at import. Constructing it
# eagerly would (a) import langchain_groq — which pulls in torch — during app
# startup, spiking memory and risking a slow/OOM boot that fails the deploy
# health check, and (b) make a missing GROQ_API_KEY crash the whole service
# instead of only the chat endpoint. Deferring keeps boot fast and isolates the
# LLM dependency to requests that actually need it.
#
# Keyed by tool subset: every distinct selection from tool_router needs its own
# bound model, and binding is pure setup, so they are cached rather than rebuilt
# per request. The number of distinct subsets is bounded by the keyword table.
_llm_cache: dict[frozenset[str], Runnable] = {}
_llm_lock = threading.Lock()


def _get_llm(tool_names: frozenset[str]) -> Runnable:
    """Return a model bound to exactly ``tool_names`` (unbound if empty)."""
    global _llm_cache
    cached = _llm_cache.get(tool_names)
    if cached is not None:
        return cached

    with _llm_lock:
        cached = _llm_cache.get(tool_names)
        if cached is None:
            base = build_chat_llm()
            cached = base.bind_tools([TOOL_MAP[name] for name in sorted(tool_names)]) if tool_names else base
            _llm_cache = {**_llm_cache, tool_names: cached}
    return cached


FINAL_TURN_DIRECTIVE = (
    "You have gathered all the data you are going to get. Answer the user's "
    "question now, in full, using only the data retrieved so far. If it does "
    "not cover everything asked, say which part is missing. Do not request "
    "any further tools."
)


def _as_plain_transcript(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The conversation with its tool exchanges folded into one block of prose.

    The structured calls and results are dropped from the history and restated,
    each result under the call that fetched it, in a closing system message.
    """
    args_by_call = {call["id"]: call["args"] for m in messages if isinstance(m, AIMessage) for call in m.tool_calls}
    results = [
        f"### {m.name} {json.dumps(args_by_call.get(m.tool_call_id, {}), ensure_ascii=False)}\n{m.content}"
        for m in messages
        if isinstance(m, ToolMessage)
    ]
    conversation = [
        m for m in messages if not isinstance(m, ToolMessage) and not (isinstance(m, AIMessage) and m.tool_calls)
    ]
    data = "\n\n".join(results)
    return [*conversation, SystemMessage(content=f"{FINAL_TURN_DIRECTIVE}\n\nDATA RETRIEVED SO FAR:\n\n{data}")]


async def _answer_or_none(messages: list[BaseMessage]) -> AIMessage | None:
    """A reply with no tools offered, or None if the model called one anyway."""
    try:
        return await _get_llm(frozenset()).ainvoke(messages)
    except Exception as exc:
        if not is_tool_use_failed(exc):
            raise
        return None


async def _ainvoke_final(messages: list[BaseMessage]) -> AIMessage:
    """Force a text answer out of the model on the last permitted turn.

    Binding no tools is the cheap path — it drops the entire schema payload from
    one of the most expensive calls in the loop. But a model that has just seen
    several tool calls in the history will sometimes attempt one more anyway,
    and Groq rejects that with a 400 ("attempted to call tool X which was not in
    request.tools") rather than ignoring it.

    Disabling tool calling is no fix: gpt-oss ignores tool_choice="none", and
    Groq 400s that too ("Tool choice is none, but model called a tool"). What
    works is taking the invitation away — the retry restates the tool history as
    plain text. If even that is refused, the reply comes back empty and the loop
    shows its notice, so the last turn never ends in an error. A refusal costs
    one extra request; nothing else is absorbed, so a rate limit still surfaces.
    """
    answer = await _answer_or_none([*messages, SystemMessage(content=FINAL_TURN_DIRECTIVE)])
    if answer is None:
        logger.info("agent.final_turn_as_transcript")
        answer = await _answer_or_none(_as_plain_transcript(messages))
    if answer is None:
        logger.warning("agent.final_turn_refused")
        return AIMessage(content="")
    return answer


class _ModelTurn(NamedTuple):
    """One model reply, and the tools bound from here on.

    The set only ever grows: a tool bound mid-loop to satisfy the model stays
    bound, or the next turn that reaches for it is refused all over again.
    """

    response: AIMessage
    tool_names: frozenset[str]


def _recovered_call(exc: Exception) -> AIMessage:
    """The tool call(s) Groq refused to parse, or ``exc`` again if there are none.

    When the model emits a tool call as text instead of a structured call, Groq
    returns a tool_use_failed error. We parse the intended call(s) out of it and
    return a synthesized tool-calling message so the agent loop can continue.
    """
    recovered = recover_tool_calls(exc)
    if not recovered:
        raise exc
    logger.info("agent.recovered_tool_calls", count=len(recovered))
    return AIMessage(content="", tool_calls=recovered)


async def _ainvoke_parsing_refusals(messages: list[BaseMessage], tool_names: frozenset[str]) -> AIMessage:
    """Invoke the model, recovering a tool call Groq refused to parse."""
    try:
        return await _get_llm(tool_names).ainvoke(messages)
    except Exception as exc:
        if not is_tool_use_failed(exc):
            raise
        return _recovered_call(exc)


def _with_refused_tool(exc: Exception, tool_names: frozenset[str]) -> frozenset[str] | None:
    """The tool set plus the real tool Groq refused as unoffered, if that was the refusal."""
    refused = unbound_tool_name(exc)
    if refused in TOOL_MAP and refused not in tool_names:
        return tool_names | {refused}
    return None


async def _ainvoke_with_recovery(messages: list[BaseMessage], tool_names: frozenset[str]) -> _ModelTurn:
    """Invoke the model, recovering from the tool calls Groq refuses.

    tool_router binds only the tools a question's keywords suggest, so the model
    sometimes asks for one it was not offered and Groq rejects the whole turn.
    That tool is bound and the turn retried once, so the model sees the real
    schema and writes valid arguments. Any other refusal is parsed instead.

    Widening is checked before parsing on purpose: gpt-oss's refusal carries
    the call as parseable JSON, but with arguments guessed without the schema.
    """
    try:
        return _ModelTurn(await _get_llm(tool_names).ainvoke(messages), tool_names)
    except Exception as exc:
        if not is_tool_use_failed(exc):
            raise
        widened = _with_refused_tool(exc, tool_names)
        if widened is None:
            return _ModelTurn(_recovered_call(exc), tool_names)
    logger.info("agent.unoffered_tool_bound", tools=sorted(widened - tool_names))
    return _ModelTurn(await _ainvoke_parsing_refusals(messages, widened), widened)


def build_system_prompt(today: str, memory_context: str = "") -> str:
    memory_block = f"\n\n    PERSONALISATION & MEMORY:\n    {memory_context}\n" if memory_context else ""
    return f"""
    {RACE_ENGINEER_PERSONA}

    CURRENT CONTEXT:
    - TODAY'S DATE: {today}{memory_block}

    TOOL USAGE:
    - **CRITICAL:** If the user asks for "last race", "next race", or "schedule",
      ALWAYS call `get_season_schedule({today.rsplit(",", maxsplit=1)[-1].strip()})` FIRST to
      identify the correct Grand Prix name before calling any results tool.
    - Use 'get_race_results' for final race classifications.
    - Use 'compare_drivers' for specific lap-time comparisons.
    - Use 'query_f1_database' for ANY historical or statistical question the
      other tools don't directly answer (records, career comparisons, "most/
      best/worst", results across many seasons). Write a read-only SQL SELECT.
    - When a question spans several races (a season so far, every sprint
      weekend), answer it with ONE 'query_f1_database' query — f1db holds the
      sprint and race results of every completed round, and a round had a
      sprint exactly when it has SPRINT_RACE_RESULT rows — so you do not need
      the schedule first. Do this even after checking the schedule: walking
      the season one Grand Prix at a time runs out of tool calls long before
      the season does.
    - Use 'get_power_unit_usage' for engine / power-unit element counts, allowances and the
      grid penalties they caused — it reads the FIA's own documents, so prefer it to the web.
    - Use 'perform_web_search' for recent news or information beyond your knowledge.

    GROUNDING (NON-NEGOTIABLE):
    - Your memory of drivers, teams and results is out of date: your training
      predates this season, and the grid changes every year. State a driver's
      name or team, a result, time, grid slot or points total only if it appears
      in a tool result in this conversation. Not there? Fetch it or leave it
      out — never fill it in from memory, and never guess who a driver code is.
    - Analysis means what the retrieved numbers show — patterns, comparisons,
      championship implications. It never adds facts the tools did not return.

    PRESENTING RESULTS:
    - When a tool returns a Markdown results table, keep the table intact — but
      do not stop there. Add the analysis the rows support: margins, patterns,
      who gained or lost, what the points mean. You are an analyst, not a data
      terminal — so skip any angle that needs data you were not given (tyres,
      strategy, grids, standings) rather than guessing it.
    - For 'query_f1_database' results especially, always explain the rows in
      plain language and lead with the answer to the user's actual question.
    """


def build_langchain_messages(request: ChatRequest, today: str, memory_context: str = "") -> list[BaseMessage]:
    messages = [SystemMessage(content=build_system_prompt(today, memory_context))]
    for msg in request.messages:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    return messages


def _latest_user_text(request: ChatRequest) -> str:
    for msg in reversed(request.messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


@dataclass(frozen=True)
class _Conversation:
    """Whose thread a reply belongs to — anonymous chats are never saved."""

    user_id: str | None
    thread_id: str


async def _save_reply(conversation: _Conversation, content: object) -> None:
    """Persist an assistant turn; an empty turn carries nothing worth recalling."""
    if conversation.user_id and content:
        await asyncio.to_thread(save_message, conversation.user_id, conversation.thread_id, "assistant", str(content))


async def _invoke_tool(tool_call: dict) -> str:
    """Run one tool and return what the model should read back.

    A timeout or an exception becomes text the model can route around rather
    than an error that ends the stream.
    """
    name = tool_call["name"]
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(TOOL_MAP[name].invoke, tool_call["args"]),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("tool.timeout", tool=name, timeout_seconds=TOOL_TIMEOUT_SECONDS)
        return f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS} seconds. The data source may be slow — try again."
    except Exception as exc:
        logger.exception("tool.error", tool=name, error=str(exc))
        return f"Error executing tool '{name}': {exc}"
    return str(result)


async def _run_tool_calls(response: AIMessage, messages: list[BaseMessage]) -> AsyncGenerator[str, None]:
    """Execute every known tool the model asked for, bracketing each with markers.

    The markers drive the client's "running a tool" indicator. An unknown tool
    is skipped rather than invented.
    """
    for tool_call in response.tool_calls:
        name = tool_call["name"]
        if name not in TOOL_MAP:
            continue
        friendly = name.replace("_", " ").title()
        yield f"[TOOL_START]{friendly}[/TOOL_START]"
        result = await _invoke_tool(tool_call)
        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=result, name=name))
        yield f"[TOOL_END]{friendly}[/TOOL_END]"


async def _next_response(messages: list[BaseMessage], tool_names: frozenset[str], turn: int) -> _ModelTurn:
    """Ask for the next turn, offering no tools on the last one permitted.

    Without tools the model answers from what it already has, which saves the
    schema payload and turns what used to be a dead-end error into an answer.
    """
    if turn == MAX_AGENT_TURNS:
        return _ModelTurn(await _ainvoke_final(messages), tool_names)
    return await _ainvoke_with_recovery(messages, tool_names)


async def _agent_stream(
    messages: list[BaseMessage],
    tool_names: frozenset[str],
    conversation: _Conversation,
) -> AsyncGenerator[str, None]:
    """Drive the tool-use loop, streaming markers and then the final answer."""
    response, tool_names = await _ainvoke_with_recovery(messages, tool_names)

    for turn in range(1, MAX_AGENT_TURNS + 1):
        if not response.tool_calls:
            logger.info("agent.generating_response")
            await _save_reply(conversation, response.content)
            yield response.content
            return

        logger.info("agent.turn", turn=turn, tool_count=len(response.tool_calls))
        messages.append(response)
        async for marker in _run_tool_calls(response, messages):
            yield marker
        response, tool_names = await _next_response(messages, tool_names, turn)

    # Loop exhausted. The last invocation had no tools bound, so this is prose;
    # the notice remains only for a model that returns nothing.
    if response.content:
        logger.info("agent.forced_answer", turns=MAX_AGENT_TURNS)
        await _save_reply(conversation, response.content)
        yield response.content
        return

    yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."


def _failure_text(exc: Exception) -> str:
    """What the user sees when the loop dies — a quota gets its own message."""
    if "rate limit" in str(exc).lower() or "429" in str(exc):
        logger.warning("agent.rate_limited", error=str(exc))
        return "**Box, box:** The engine is rate-limited right now (free tier). Give it a few seconds and try again."
    return f"**System Error:** {client_error_text('agent.critical_error', exc)}"


async def _guarded_stream(
    messages: list[BaseMessage],
    tool_names: frozenset[str],
    conversation: _Conversation,
) -> AsyncGenerator[str, None]:
    """The agent stream, with any failure rendered through the client-safe path."""
    try:
        async for chunk in _agent_stream(messages, tool_names, conversation):
            yield chunk
    except Exception as exc:
        yield _failure_text(exc)


@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> StreamingResponse:
    """Streaming chat endpoint that drives the F1 tool-use loop."""

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    user_id = request.user_id
    thread_id = request.thread_id or "default"
    latest_user_text = _latest_user_text(request)

    # Personalisation + semantic recall (no-op without a user_id or database).
    memory_context = ""
    if user_id:
        memory_context = await asyncio.to_thread(build_memory_context, user_id, latest_user_text, thread_id)
        if latest_user_text:
            await asyncio.to_thread(save_message, user_id, thread_id, "user", latest_user_text)

    langchain_messages = build_langchain_messages(request, today, memory_context)

    # Only the tools this question plausibly needs — the full set costs ~2,100
    # prompt tokens on every turn of the loop. See app/api/tool_router.py.
    tool_names = select_tools(latest_user_text)
    conversation = _Conversation(user_id=user_id, thread_id=thread_id)

    return StreamingResponse(
        _guarded_stream(langchain_messages, tool_names, conversation),
        media_type="text/plain",
    )
