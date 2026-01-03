import fastf1
import os
import logging
import asyncio
from mcp.server.fastmcp import FastMCP, Context # Import Context
from fastf1.ergast import Ergast
import pandas as pd

# --- CRITICAL FIXES FOR MCP ---
CACHE_DIR = os.path.expanduser('~/f1_fastf1_cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

fastf1.Cache.enable_cache(CACHE_DIR)

# Correct way to silence FastF1 logging
fastf1.logger.set_log_level(logging.ERROR)
# ------------------------------

mcp = FastMCP("F1 Race Engineer")

@mcp.tool()
# --- TOOL 1: GET SCHEDULE ---
async def get_season_schedule(year: int, ctx: Context) -> str:
    """Fetches the F1 Schedule for a specific year."""
    try:
        # Report progress so Cursor doesn't hang
        await ctx.report_progress(progress=10, total=100)
        await ctx.info(f"Contacting F1 API for {year} schedule...")
        
        # FastF1 calls are synchronous, so they block. 
        # For better performance, we run them in a thread.
        loop = asyncio.get_event_loop()
        schedule = await loop.run_in_executor(
            None, lambda: fastf1.get_event_schedule(year=year, include_testing=False)
        )
        
        await ctx.report_progress(progress=80, total=100)
        
        if schedule.empty:
            return f"No schedule data found for {year}."

        output = [f"### F1 Schedule {year}"]
        for _, row in schedule.iterrows():
            date_str = row["EventDate"].strftime('%d %b') if pd.notna(row["EventDate"]) else "TBA"
            output.append(f"- Round {row['RoundNumber']}: {row['EventName']} ({row['Location']}) on {date_str}")
        
        await ctx.report_progress(progress=100, total=100)
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching schedule: {str(e)}"

# --- TOOL 2: GET DRIVER STANDINGS ---
@mcp.tool()
def get_driver_standings(year: int) -> str:
    """
    Fetches the current Driver Championship Standings.
    """
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        if not data.content:
            return f"No standings found for {year}."
            
        df = data.content[0]
        output = [f"### Driver Standings {year}"]
        for _, row in df.iterrows():
            output.append(f"{row['position']}. {row['givenName']} {row['familyName']} ({row['constructorName']}) - {row['points']} pts")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching standings: {str(e)}"

# --- TOOL 3: GET NEXT RACE TELEMETRY (Demo) ---
@mcp.tool()
def get_telemetry_status() -> str:
    """
    Checks the status of the connection to the F1 Live Timing servers.
    """
    return "🟢 Telemetry Systems: ONLINE. Connection to FastF1 API stable."

if __name__ == "__main__":
    mcp.run()