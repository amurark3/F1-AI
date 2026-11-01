"""AI chat router and agent orchestration."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
import json
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
import structlog

from app.api.answer_repair import checked_answer
from app.api.errors import client_error_text
from app.api.llm import (
    available_providers,
    build_chat_llm,
    is_provider_failure,
    is_rate_limited,
    mark_unavailable,
    message_text,
)
from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.schemas.chat import ChatRequest
from app.api.tools import TOOL_LIST, TOOL_MAP
from app.config import MAX_AGENT_TURNS, TOOL_TIMEOUT_SECONDS, LLMProvider
from app.data.memory import build_memory_context, save_message

logger = structlog.get_logger()
router = APIRouter(tags=["chat"])


# The chat model is built lazily on first use, not at import. Constructing it
# eagerly would (a) import the engine's client during app startup, spiking
# memory and risking a slow/OOM boot that fails the deploy health check, and
# (b) make a missing key crash the whole service instead of only the chat
# endpoint. Deferring keeps boot fast and isolates the LLM dependency to
# requests that actually need it.
#
# Per engine: one model with every tool bound, one with none for the forced
# final answer. Binding is pure setup, so both are cached rather than rebuilt
# per request.
_llm_cache: dict[tuple[LLMProvider, bool], Runnable] = {}
_llm_lock = threading.Lock()


def _get_llm(provider: LLMProvider, *, with_tools: bool) -> Runnable:
    """Return ``provider``'s model, bound to every tool or to none."""
    global _llm_cache
    key = (provider, with_tools)
    cached = _llm_cache.get(key)
    if cached is not None:
        return cached

    with _llm_lock:
        cached = _llm_cache.get(key)
        if cached is None:
            base = build_chat_llm(provider)
            cached = base.bind_tools(TOOL_LIST) if with_tools else base
            _llm_cache = {**_llm_cache, key: cached}
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


async def _answer_or_none(provider: LLMProvider, messages: list[BaseMessage]) -> AIMessage | None:
    """A reply with no tools offered, or None if the model still asked for one."""
    answer = await _get_llm(provider, with_tools=False).ainvoke(messages)
    return None if answer.tool_calls else answer


async def _ainvoke_final(provider: LLMProvider, messages: list[BaseMessage]) -> AIMessage:
    """Force a text answer out of the model on the last permitted turn.

    Binding no tools is the cheap path — it drops the entire schema payload from
    one of the most expensive calls in the loop. But a model that has just seen
    several tool calls in the history will sometimes reply with one more anyway.

    What works is taking the invitation away — the retry restates the tool
    history as plain text. If even that comes back as a tool call, the reply is
    empty and the loop shows its notice, so the last turn never ends in an
    error. Engine failures are not absorbed here: they belong to the failover.
    """
    answer = await _answer_or_none(provider, [*messages, SystemMessage(content=FINAL_TURN_DIRECTIVE)])
    if answer is None:
        logger.info("agent.final_turn_as_transcript")
        answer = await _answer_or_none(provider, _as_plain_transcript(messages))
    if answer is None:
        logger.warning("agent.final_turn_refused")
        return AIMessage(content="")
    return answer


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
    - Lead with the direct answer to the user's question, then keep any results
      table a tool returned intact.
    - Then add at most THREE observations. Each must come straight from one row
      — say which round or driver it is about — or quote a tally a tool computed.
      Do not count, sum or compare across rows yourself — quote the tool's
      tallies, or leave it out.
    - Never claim "only", "first", "never", "all" or "none" unless a tool result
      states it. No title-battle or standings talk unless standings were fetched.
    - Skip any angle that needs data you were not given (tyres, strategy, grids)
      rather than guessing it.
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
    except TimeoutError:
        logger.warning("tool.timeout", tool=name, timeout_seconds=TOOL_TIMEOUT_SECONDS)
        return f"Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS} seconds. The data source may be slow — try again."
    except Exception as exc:
        logger.exception("tool.error", tool=name, error=str(exc))
        return f"Error executing tool '{name}': {exc}"
    return str(result)


async def _run_tool_calls(response: AIMessage, messages: list[BaseMessage]) -> AsyncGenerator[str]:
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


async def _next_response(messages: list[BaseMessage], provider: LLMProvider, turn: int) -> AIMessage:
    """Ask for the next turn, offering no tools on the last one permitted.

    Without tools the model answers from what it already has, which saves the
    schema payload and turns what used to be a dead-end error into an answer.
    """
    if turn == MAX_AGENT_TURNS:
        return await _ainvoke_final(provider, messages)
    return await _get_llm(provider, with_tools=True).ainvoke(messages)


async def _finalise(
    messages: list[BaseMessage],
    provider: LLMProvider,
    conversation: _Conversation,
    answer: str,
) -> str:
    """Check the answer against the rows it was built from, save it, and return it.

    The check is free for a clean answer; one its rows contradict gets a single
    repair request (app/api/answer_repair.py) on the same engine, so the user
    and their saved history both get the corrected text.
    """
    checked = await checked_answer(messages, answer, partial(_answer_or_none, provider))
    await _save_reply(conversation, checked)
    return checked


async def _agent_stream(
    messages: list[BaseMessage],
    provider: LLMProvider,
    conversation: _Conversation,
) -> AsyncGenerator[str]:
    """Drive the tool-use loop on one engine, streaming markers and then the final answer."""
    response = await _get_llm(provider, with_tools=True).ainvoke(messages)

    for turn in range(1, MAX_AGENT_TURNS + 1):
        if not response.tool_calls:
            logger.info("agent.generating_response", provider=provider.name)
            yield await _finalise(messages, provider, conversation, message_text(response))
            return

        logger.info("agent.turn", turn=turn, tool_count=len(response.tool_calls))
        messages.append(response)
        async for marker in _run_tool_calls(response, messages):
            yield marker
        response = await _next_response(messages, provider, turn)

    # Loop exhausted. The last invocation had no tools bound, so this is prose;
    # the notice remains only for a model that returns nothing.
    answer = message_text(response)
    if answer:
        logger.info("agent.forced_answer", turns=MAX_AGENT_TURNS)
        yield await _finalise(messages, provider, conversation, answer)
        return

    yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."


RATE_LIMITED_NOTICE = (
    "**Box, box:** The engine is rate-limited right now (free tier). Give it a few seconds and try again."
)


def _failure_text(exc: Exception) -> str:
    """What the user sees when the loop dies — a quota gets its own message."""
    if is_rate_limited(exc):
        logger.warning("agent.rate_limited", error=str(exc))
        return RATE_LIMITED_NOTICE
    return f"**System Error:** {client_error_text('agent.critical_error', exc)}"


def _fails_over(provider: LLMProvider, exc: Exception, *, is_last: bool) -> bool:
    """Rest an engine that failed; True when the question should move to the next one.

    Only the engine's own failures qualify. Our own bug would fail the same way
    on every engine, and retrying it would hide it.
    """
    if not is_provider_failure(exc):
        return False
    mark_unavailable(provider, exc)
    if is_last:
        return False
    logger.warning("agent.provider_failover", provider=provider.name, error=str(exc))
    return True


async def _guarded_stream(messages: list[BaseMessage], conversation: _Conversation) -> AsyncGenerator[str]:
    """The agent stream on the first engine that answers, failures rendered client-safe.

    An engine that is out of points or credit, past its access window,
    overloaded or unreachable hands the question to the next engine (order in
    app/config.py), which starts again from the question: ``messages`` is cut
    back to it, so the next engine never sees the failed one's tool calls.
    Tool markers already streamed are repeated by the next attempt.
    """
    question_length = len(messages)
    try:
        providers = available_providers()
    except RuntimeError as exc:
        yield _failure_text(exc)
        return

    for index, provider in enumerate(providers):
        del messages[question_length:]
        try:
            async for chunk in _agent_stream(messages, provider, conversation):
                yield chunk
            return
        except Exception as exc:
            if _fails_over(provider, exc, is_last=index == len(providers) - 1):
                continue
            yield _failure_text(exc)
            return


def _today() -> str:
    return datetime.now(UTC).strftime("%B %d, %Y")


async def ask_anonymously(question: str) -> tuple[str, list[BaseMessage]]:
    """One question through the agent outside HTTP, saving nothing — for the eval.

    Returns the streamed text, tool markers included, and the whole message
    history: its ToolMessages are the tables the answer was built from.
    """
    request = ChatRequest(messages=[{"role": "user", "content": question}])
    messages = build_langchain_messages(request, _today())
    conversation = _Conversation(user_id=None, thread_id="eval")
    chunks = [chunk async for chunk in _guarded_stream(messages, conversation)]
    return "".join(chunks), messages


@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> StreamingResponse:
    """Streaming chat endpoint that drives the F1 tool-use loop."""

    today = _today()
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
    conversation = _Conversation(user_id=user_id, thread_id=thread_id)

    return StreamingResponse(
        _guarded_stream(langchain_messages, conversation),
        media_type="text/plain",
    )
