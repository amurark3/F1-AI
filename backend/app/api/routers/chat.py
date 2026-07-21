"""AI chat router and agent orchestration."""

import asyncio
from datetime import datetime

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.api.llm import build_chat_llm
from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.schemas.chat import ChatRequest
from app.api.tool_recovery import is_tool_use_failed, recover_tool_calls
from app.api.tools import TOOL_LIST, TOOL_MAP
from app.config import MAX_AGENT_TURNS, TOOL_TIMEOUT_SECONDS
from app.data.memory import build_memory_context, save_message

logger = structlog.get_logger()
router = APIRouter(tags=["chat"])


llm = build_chat_llm()
llm_with_tools = llm.bind_tools(TOOL_LIST)


async def _ainvoke_with_recovery(messages):
    """Invoke the model, recovering from Groq/Llama malformed tool calls.

    When Llama emits a tool call as inline text (``<function=...>``), Groq
    returns a tool_use_failed error. We parse the intended call(s) out of it and
    return a synthesized tool-calling message so the agent loop can continue.
    """
    try:
        return await llm_with_tools.ainvoke(messages)
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
      ALWAYS call `get_season_schedule({today.split(',')[-1].strip()})` FIRST to
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


def build_langchain_messages(request: ChatRequest, today: str, memory_context: str = ""):
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


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Streaming chat endpoint that drives the F1 tool-use loop."""

    today = datetime.now().strftime("%B %d, %Y")
    user_id = request.user_id
    thread_id = request.thread_id or "default"
    latest_user_text = _latest_user_text(request)

    # Personalisation + semantic recall (no-op without a user_id or database).
    memory_context = ""
    if user_id:
        memory_context = await asyncio.to_thread(
            build_memory_context, user_id, latest_user_text, thread_id
        )
        if latest_user_text:
            await asyncio.to_thread(
                save_message, user_id, thread_id, "user", latest_user_text
            )

    langchain_messages = build_langchain_messages(request, today, memory_context)

    async def generate():
        try:
            current_response = await _ainvoke_with_recovery(langchain_messages)

            for turn_count in range(1, MAX_AGENT_TURNS + 1):
                if not current_response.tool_calls:
                    logger.info("agent.generating_response")
                    if user_id and current_response.content:
                        await asyncio.to_thread(
                            save_message, user_id, thread_id, "assistant",
                            str(current_response.content),
                        )
                    yield current_response.content
                    return

                logger.info("agent.turn", turn=turn_count, tool_count=len(current_response.tool_calls))
                langchain_messages.append(current_response)

                for tool_call in current_response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    if tool_name not in TOOL_MAP:
                        continue

                    friendly = tool_name.replace("_", " ").title()
                    yield f"[TOOL_START]{friendly}[/TOOL_START]"
                    try:
                        tool_result = await asyncio.wait_for(
                            asyncio.to_thread(TOOL_MAP[tool_name].invoke, tool_args),
                            timeout=TOOL_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        tool_result = f"Tool '{tool_name}' timed out after {TOOL_TIMEOUT_SECONDS} seconds. The data source may be slow — try again."
                        logger.warning("tool.timeout", tool=tool_name, timeout_seconds=TOOL_TIMEOUT_SECONDS)
                    except Exception as exc:
                        tool_result = f"Error executing tool '{tool_name}': {exc}"
                        logger.error("tool.error", tool=tool_name, error=str(exc))

                    langchain_messages.append(ToolMessage(tool_call_id=tool_id, content=str(tool_result), name=tool_name))
                    yield f"[TOOL_END]{friendly}[/TOOL_END]"

                current_response = await _ainvoke_with_recovery(langchain_messages)

            yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."
        except Exception as exc:
            if "rate limit" in str(exc).lower() or "429" in str(exc):
                logger.warning("agent.rate_limited", error=str(exc))
                yield "**Box, box:** The engine is rate-limited right now (free tier). Give it a few seconds and try again."
                return
            logger.error("agent.critical_error", error=str(exc))
            yield f"**System Error:** My telemetry failed. Reason: {exc}"

    return StreamingResponse(generate(), media_type="text/plain")
