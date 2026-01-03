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
from langchain_google_genai import ChatGoogleGenerativeAI

router = APIRouter()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    }
)

llm_with_tools = llm.bind_tools(TOOL_LIST)

if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache('f1_cache')

class ChatRequest(BaseModel):
    messages: List[dict]

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    today = datetime.now().strftime("%B %d, %Y")
    
    # 1. SETUP SYSTEM PROMPT (Persona + Context)
    final_system_prompt = f"""
    {RACE_ENGINEER_PERSONA}
    
    CURRENT CONTEXT:
    - TODAY'S DATE: {today}
    
    TOOL USAGE:
    - **CRITICAL:** If the user asks for "last race", "next race", or "schedule", ALWAYS call `get_season_schedule({today.split(',')[-1].strip()})` FIRST to identify the correct Grand Prix.
    - Use 'get_race_results' (plural) for final classifications.
    - Use 'compare_drivers' for specific lap time comparisons.
    - Use 'perform_web_search' for recent news.
    - If a tool returns a Markdown table, present it exactly as is.
    """
    
    # 2. BUILD MESSAGE HISTORY
    langchain_messages = [SystemMessage(content=final_system_prompt)]
    
    for msg in request.messages:
        if msg['role'] == "user":
            langchain_messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == "assistant":
            langchain_messages.append(AIMessage(content=msg['content']))

    # 3. DEFINE THE GENERATOR (The Brain)
    async def generate():
        try:
            # Safety limit to prevent infinite loops
            max_turns = 5
            turn_count = 0

            # First pass: Ask the model what to do
            print("🤖 ASKING MODEL...")
            current_response = await llm_with_tools.ainvoke(langchain_messages)

            while turn_count < max_turns:
                turn_count += 1
                
                # CASE A: The Model wants to call Tools
                if current_response.tool_calls:
                    print(f"🔄 TURN {turn_count}: Model requested {len(current_response.tool_calls)} tools.")
                    
                    # 1. Add the AI's "Intent" to history (CRITICAL STEP)
                    langchain_messages.append(current_response)
                    
                    # 2. Execute ALL requested tools
                    for tool_call in current_response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]
                        
                        if tool_name in TOOL_MAP:
                            print(f"🛠️ EXECUTING: {tool_name} with args {tool_args}")
                            try:
                                # Run the tool
                                tool_result = TOOL_MAP[tool_name].invoke(tool_args)
                                print(f"✅ RESULT: {str(tool_result)[:50]}...") # Print preview
                            except Exception as tool_err:
                                tool_result = f"Error executing tool {tool_name}: {str(tool_err)}"
                                print(f"❌ TOOL ERROR: {tool_result}")

                            # 3. Add Result to history
                            langchain_messages.append(ToolMessage(
                                tool_call_id=tool_id, 
                                content=str(tool_result), 
                                name=tool_name
                            ))
                    
                    # 4. Loop back: Ask model "What now?" with the new info
                    # It might want another tool (e.g., Get Results), or give the final answer.
                    current_response = await llm_with_tools.ainvoke(langchain_messages)
                
                # CASE B: The Model has a Final Answer (Text)
                else:
                    print("🤖 GENERATING FINAL TEXT...")
                    # Stream the final text response to the user
                    yield current_response.content
                    break # EXIT THE LOOP

        except Exception as e:
            print(f"❌ CRITICAL ERROR IN GENERATE: {str(e)}")
            yield f"**System Error:** My telemetry failed. Reason: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")



@router.get("/schedule/{year}")
async def get_schedule(year: int):
    """
    Returns the full season schedule with UTC timestamps for all sessions.
    The frontend will handle timezone conversions.
    """
    try:
        # include_testing=False keeps it to just the races
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
        
        data = []
        for _, row in schedule.iterrows():
            # Basic Event Details
            event_date_str = row["EventDate"].isoformat()
            if not event_date_str.endswith("Z") and not "+" in event_date_str:
                event_date_str += "Z"
                
            event = {
                "round": int(row["RoundNumber"]),
                "name": row["EventName"],
                "location": f"{row['Location']}, {row['Country']}",
                "date": event_date_str,
                "sessions": {}
            }
            
            # Dynamic Session Loop (Handles Sprints automatically)
            # FastF1 columns are Session1, Session1DateUtc, Session2, etc.
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
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        if not data.content: return []
        
        df = data.content[0]
        results = []
        for _, row in df.iterrows():
            # SAFE TEAM NAME EXTRACTION
            # FastF1 returns 'constructorNames' (list) if a driver drove for multiple teams
            team_name = "Unknown"
            if 'constructorName' in row:
                team_name = row['constructorName']
            elif 'constructorNames' in row:
                # It's a list, take the last one (most recent team)
                names = row['constructorNames']
                if isinstance(names, list) and len(names) > 0:
                    team_name = names[-1]
                else:
                    team_name = str(names)

            results.append({
                "position": int(row['position']),
                "driver": f"{row['givenName']} {row['familyName']}",
                "team": team_name,
                "points": float(row['points']),
                "wins": int(row['wins'])
            })
        return results
    except Exception as e:
        # Print actual error for debugging
        print(f"Driver Standings Error: {e}")
        return []

@router.get("/standings/constructors/{year}")
async def get_constructor_standings(year: int):
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        if not data.content: return []
        
        df = data.content[0]
        results = []
        for _, row in df.iterrows():
            results.append({
                "position": int(row['position']),
                "team": row['constructorName'],
                "points": float(row['points']),
                "wins": int(row['wins'])
            })
        return results
    except Exception as e:
        print(f"Constructor Standings Error: {e}")
        return []

@router.get("/health")
async def health_check():
    """Simple check to see if the server is running."""
    return {"status": "ok", "timestamp": datetime.now()}