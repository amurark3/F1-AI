"""AI chat router and agent orchestration."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
import structlog

from app.api.errors import client_error_text
from app.api.llm import build_chat_llm
from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.schemas.chat import ChatRequest
from app.api.tool_recovery import is_tool_use_failed, recover_tool_calls
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
    "question now, in full, using only the tool results above. Do not request "
    "any further tools."
)


async def _ainvoke_final(messages: list[BaseMessage], tool_names: frozenset[str]) -> AIMessage:
    """Force a text answer out of the model on the last permitted turn.

    Binding no tools is the cheap path — it drops the entire schema payload from
    one of the most expensive calls in the loop. But a model that has just seen
    several tool calls in the history will sometimes attempt one more anyway,
    and Groq rejects that with a 400 ("attempted to call tool X which was not in
    request.tools") rather than ignoring it — which used to surface as a broken
    stream instead of an answer.

    So: ask nicely and bind nothing, then fall back once to sending the schemas
    with tool calling explicitly disabled, which cannot fail that way. The
    expensive path only runs when the cheap one is refused.
    """
    guided = [*messages, SystemMessage(content=FINAL_TURN_DIRECTIVE)]
    try:
        return await _get_llm(frozenset()).ainvoke(guided)
    except Exception as exc:
        if not is_tool_use_failed(exc):
            raise
        logger.info("agent.final_turn_forced", tools=len(tool_names))
        return await _get_llm(tool_names).bind(tool_choice="none").ainvoke(guided)


async def _ainvoke_with_recovery(messages: list[BaseMessage], tool_names: frozenset[str]) -> AIMessage:
    """Invoke the model, recovering from Groq malformed tool calls.

    When the model emits a tool call as inline text (``<function=...>``), Groq
    returns a tool_use_failed error. We parse the intended call(s) out of it and
    return a synthesized tool-calling message so the agent loop can continue.
    """
    try:
        return await _get_llm(tool_names).ainvoke(messages)
    except Exception as exc:
        if not is_tool_use_failed(exc):
            raise
        recovered = recover_tool_calls(exc)
        if not recovered:
            raise
        logger.info("agent.recovered_tool_calls", count=len(recovered))
        return AIMessage(content="", tool_calls=recovered)


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
    - Use 'perform_web_search' for recent news or information beyond your knowledge.

    PRESENTING RESULTS:
    - When a tool returns a Markdown results table, keep the table intact — but
      do not stop there. Add the analysis: what the numbers mean, the strategic
      or championship implications, and the standout story. You are an analyst,
      not a data terminal.
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


async def _next_response(messages: list[BaseMessage], tool_names: frozenset[str], turn: int) -> AIMessage:
    """Ask for the next turn, offering no tools on the last one permitted.

    Without tools the model answers from what it already has, which saves the
    schema payload and turns what used to be a dead-end error into an answer.
    """
    if turn == MAX_AGENT_TURNS:
        return await _ainvoke_final(messages, tool_names)
    return await _ainvoke_with_recovery(messages, tool_names)


async def _agent_stream(
    messages: list[BaseMessage],
    tool_names: frozenset[str],
    conversation: _Conversation,
) -> AsyncGenerator[str, None]:
    """Drive the tool-use loop, streaming markers and then the final answer."""
    response = await _ainvoke_with_recovery(messages, tool_names)

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
        response = await _next_response(messages, tool_names, turn)

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
