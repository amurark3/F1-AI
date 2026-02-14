"""
API Routes
==========
Defines all HTTP endpoints for the F1 AI backend:

  POST /api/chat                       — Streaming AI chat with tool orchestration
  GET  /api/schedule/{year}            — Full season calendar with UTC session times
  GET  /api/standings/drivers/{year}   — World Drivers' Championship standings
  GET  /api/standings/constructors/{year} — World Constructors' Championship standings
  GET  /api/health                     — Liveness probe

The chat endpoint implements an agentic loop:
  1. Build message history with system prompt.
  2. Call the LLM; it may request one or more tools.
  3. Execute every requested tool and append results to history.
  4. Repeat until the model produces a plain-text final answer (or max_turns is reached).
  5. Stream the final text back to the client.
"""

import os
import pandas as pd
import fastf1
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from fastapi.responses import StreamingResponse
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from fastf1.ergast import Ergast

from app.api.tools import TOOL_LIST, TOOL_MAP
from app.api.prompts import RACE_ENGINEER_PERSONA

router = APIRouter()

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
# safety_settings are relaxed because the assistant discusses race incidents,
# crashes, and driver retirements — content that generic filters can misflag.
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    },
)

# Bind all available tools so the model can call them by name.
llm_with_tools = llm.bind_tools(TOOL_LIST)

# ---------------------------------------------------------------------------
# FastF1 cache — speeds up repeated session data requests significantly.
# ---------------------------------------------------------------------------
if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache("f1_cache")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat."""
    messages: List[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint that drives an agentic tool-use loop.

    The client should read the response as a plain-text stream (text/plain).
    Each chunk is a fragment of the final assistant message.
    """
    today = datetime.now().strftime("%B %d, %Y")

    # Build a system prompt that injects today's date and tool-usage rules.
    final_system_prompt = f"""
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

    # Seed the message history with the system prompt, then replay the
    # conversation so the model has full context.
    langchain_messages = [SystemMessage(content=final_system_prompt)]

    for msg in request.messages:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))

    async def generate():
        """
        Inner async generator that drives the agentic loop and yields text chunks.

        The loop runs at most `max_turns` times to prevent runaway tool calls.
        Each turn is one of:
          - CASE A: Model requests tools  → execute them, append results, continue.
          - CASE B: Model returns text    → stream it to the client, break.
        """
        try:
            max_turns = 5
            turn_count = 0

            print("🤖 ASKING MODEL...")
            current_response = await llm_with_tools.ainvoke(langchain_messages)

            while turn_count < max_turns:
                turn_count += 1

                if current_response.tool_calls:
                    # CASE A — model wants to call tools
                    print(f"🔄 TURN {turn_count}: Model requested {len(current_response.tool_calls)} tool(s).")

                    # Append the AI's "intent" message before tool results;
                    # LangChain requires this ordering in the message list.
                    langchain_messages.append(current_response)

                    for tool_call in current_response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]

                        if tool_name in TOOL_MAP:
                            print(f"🛠️  EXECUTING: {tool_name} with args {tool_args}")
                            try:
                                tool_result = TOOL_MAP[tool_name].invoke(tool_args)
                                print(f"✅ RESULT (preview): {str(tool_result)[:80]}...")
                            except Exception as tool_err:
                                # Surface the error as a tool message so the model
                                # can decide how to handle it gracefully.
                                tool_result = f"Error executing tool '{tool_name}': {tool_err}"
                                print(f"❌ TOOL ERROR: {tool_result}")

                            langchain_messages.append(
                                ToolMessage(
                                    tool_call_id=tool_id,
                                    content=str(tool_result),
                                    name=tool_name,
                                )
                            )

                    # Ask the model what to do next given the tool results.
                    current_response = await llm_with_tools.ainvoke(langchain_messages)

                else:
                    # CASE B — model has a final text answer; stream it.
                    print("🤖 GENERATING FINAL TEXT...")
                    yield current_response.content
                    return  # Exit the generator cleanly

            # If we exhausted max_turns without a text answer, tell the user.
            yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."

        except Exception as e:
            print(f"❌ CRITICAL ERROR IN GENERATE: {e}")
            yield f"**System Error:** My telemetry failed. Reason: {e}"

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/schedule/{year}")
async def get_schedule(year: int):
    """
    Returns the full season schedule for `year` with UTC timestamps.

    Each event includes all sessions (Practice 1-3, Qualifying, Sprint,
    Sprint Qualifying, Race) when available. Sprint weekends are detected
    automatically by FastF1.

    The frontend is responsible for converting UTC times to the user's timezone.
    """
    try:
        # include_testing=False omits pre-season test events.
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)

        data = []
        for _, row in schedule.iterrows():
            # Ensure the event date is always UTC-suffixed for JS Date parsing.
            event_date_str = row["EventDate"].isoformat()
            if not event_date_str.endswith("Z") and "+" not in event_date_str:
                event_date_str += "Z"

            event = {
                "round": int(row["RoundNumber"]),
                "name": row["EventName"],
                "location": f"{row['Location']}, {row['Country']}",
                "date": event_date_str,
                "sessions": {},
            }

            # FastF1 uses Session1…Session5 columns; iterate to capture all
            # sessions including sprints without hard-coding session names.
            for i in range(1, 6):
                s_name_col = f"Session{i}"
                s_date_col = f"Session{i}DateUtc"

                if s_name_col in row and pd.notna(row[s_name_col]):
                    session_name = row[s_name_col]
                    session_date = row[s_date_col]
                    if pd.notna(session_date):
                        event["sessions"][session_name] = session_date.isoformat()

            data.append(event)

        return data

    except Exception as e:
        return {"error": str(e)}


@router.get("/standings/drivers/{year}")
async def get_driver_standings(year: int):
    """
    Returns World Drivers' Championship standings for `year`.

    Each entry contains: position, driver full name, team, points, wins.

    Note: A driver who switched teams mid-season will have multiple
    constructor names; we take the most recent (last) one.
    """
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        if not data.content:
            return []

        df = data.content[0]
        results = []
        for _, row in df.iterrows():
            # FastF1/Ergast returns either 'constructorName' (string) for
            # single-team drivers, or 'constructorNames' (list) for drivers
            # who raced for multiple teams in one season.
            team_name = "Unknown"
            if "constructorName" in row:
                team_name = row["constructorName"]
            elif "constructorNames" in row:
                names = row["constructorNames"]
                team_name = names[-1] if isinstance(names, list) and names else str(names)

            results.append({
                "position": int(row["position"]),
                "driver": f"{row['givenName']} {row['familyName']}",
                "team": team_name,
                "points": float(row["points"]),
                "wins": int(row["wins"]),
            })
        return results

    except Exception as e:
        print(f"Driver Standings Error: {e}")
        return []


@router.get("/standings/constructors/{year}")
async def get_constructor_standings(year: int):
    """
    Returns World Constructors' Championship standings for `year`.

    Each entry contains: position, team name, points, wins.
    """
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        if not data.content:
            return []

        df = data.content[0]
        results = []
        for _, row in df.iterrows():
            results.append({
                "position": int(row["position"]),
                "team": row["constructorName"],
                "points": float(row["points"]),
                "wins": int(row["wins"]),
            })
        return results

    except Exception as e:
        print(f"Constructor Standings Error: {e}")
        return []


@router.get("/health")
async def health_check():
    """Liveness probe — returns 200 OK when the server is running."""
    return {"status": "ok", "timestamp": datetime.now()}
