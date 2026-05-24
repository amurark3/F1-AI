"""AI chat router and agent orchestration."""

import asyncio
import os
from datetime import datetime

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory

from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.schemas.chat import ChatRequest
from app.api.tools import TOOL_LIST, TOOL_MAP
from app.config import MAX_AGENT_TURNS, LLM_MODEL_NAME, LLM_TEMPERATURE, TOOL_TIMEOUT_SECONDS

logger = structlog.get_logger()
router = APIRouter(tags=["chat"])


llm = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME,
    temperature=LLM_TEMPERATURE,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
)
llm_with_tools = llm.bind_tools(TOOL_LIST)


def build_system_prompt(today: str) -> str:
    return f"""
    {RACE_ENGINEER_PERSONA}

    CURRENT CONTEXT:
    - TODAY'S DATE: {today}

    TOOL USAGE:
    - **CRITICAL:** If the user asks for "last race", "next race", or "schedule",
      ALWAYS call `get_season_schedule({today.split(',')[-1].strip()})` FIRST to
      identify the correct Grand Prix name before calling any results tool.
    - Use 'get_race_results' for final race classifications.
    - Use 'compare_drivers' for specific lap-time comparisons.
    - Use 'perform_web_search' for recent news or information beyond your knowledge.
    - If a tool returns a Markdown table, present it exactly as-is.
    """


def build_langchain_messages(request: ChatRequest, today: str):
    messages = [SystemMessage(content=build_system_prompt(today))]
    for msg in request.messages:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    return messages


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Streaming chat endpoint that drives the F1 tool-use loop."""

    today = datetime.now().strftime("%B %d, %Y")
    langchain_messages = build_langchain_messages(request, today)

    async def generate():
        try:
            current_response = await llm_with_tools.ainvoke(langchain_messages)

            for turn_count in range(1, MAX_AGENT_TURNS + 1):
                if not current_response.tool_calls:
                    logger.info("agent.generating_response")
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

                current_response = await llm_with_tools.ainvoke(langchain_messages)

            yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."
        except Exception as exc:
            logger.error("agent.critical_error", error=str(exc))
            yield f"**System Error:** My telemetry failed. Reason: {exc}"

    return StreamingResponse(generate(), media_type="text/plain")
