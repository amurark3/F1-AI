"""
F1 AI — MCP Server
===================
Exposes all F1 analysis tools via the Model Context Protocol (MCP) so that
Claude Desktop, Cursor, or any MCP-compatible client can call them directly.

Usage:
  python mcp_server.py              # stdio transport (default)
  python mcp_server.py --sse        # SSE transport for web clients

Configure in Claude Desktop / Cursor by pointing to this script.
See README or CLAUDE.md for full setup instructions.
"""

import os
import logging
import asyncio
from datetime import datetime

import fastf1
import pandas as pd
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context
from fastf1.ergast import Ergast

# ---------------------------------------------------------------------------
# Environment & cache setup
# ---------------------------------------------------------------------------
load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(__file__), "f1_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
fastf1.Cache.enable_cache(CACHE_DIR)

# Silence FastF1's verbose logging.
fastf1.logger.set_log_level(logging.ERROR)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("F1 Race Engineer")


# ---------------------------------------------------------------------------
# Helper — shared time-string formatter (mirrors tools.py)
# ---------------------------------------------------------------------------
def _fmt_timedelta(time_val) -> str:
    if pd.isna(time_val):
        return "-"
    s = str(time_val).split("days")[-1].strip()
    if s.startswith("00:"):
        s = s[3:]
    if len(s) > 10:
        s = s[:9]
    return s


# ---------------------------------------------------------------------------
# 1. Season Schedule
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_season_schedule(year: int, ctx: Context) -> str:
    """
    Fetches the full F1 season calendar for a given year.
    Marks each race as Completed or Upcoming relative to today's date.
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()
        schedule = await loop.run_in_executor(
            None, lambda: fastf1.get_event_schedule(year=year, include_testing=False)
        )
        await ctx.report_progress(progress=80, total=100)

        if schedule.empty:
            return f"No schedule data found for {year}."

        today = datetime.now()
        output = [f"### F1 Season Schedule ({year})"]
        output.append(f"*(Current Date: {today.strftime('%Y-%m-%d')})*\n")
        output.append("| Round | Grand Prix | Date | Status |")
        output.append("| :--- | :--------- | :--- | :----- |")

        last_completed = "None"
        for _, row in schedule.iterrows():
            race_date = row["EventDate"]
            gp_name = row["EventName"]
            round_num = row["RoundNumber"]
            date_str = race_date.strftime('%d %b') if pd.notna(race_date) else "TBA"

            if race_date < today:
                status = "Completed"
                last_completed = gp_name
            else:
                status = "Upcoming"

            output.append(f"| {round_num} | {gp_name} | {date_str} | {status} |")

        output.append(f"\n**Last completed race:** {last_completed}")
        await ctx.report_progress(progress=100, total=100)
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching schedule: {e}"


# ---------------------------------------------------------------------------
# 2. Race Results
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_race_results(year: int, grand_prix: str, ctx: Context) -> str:
    """
    Fetches the final race classification for a Grand Prix.
    Returns position, driver, team, grid, position change, time/gap, and points.
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()

        def _fetch():
            session = fastf1.get_session(year, grand_prix, "R")
            session.load(telemetry=False, laps=False, weather=False)
            return session.results.sort_values(by="Position")

        results = await loop.run_in_executor(None, _fetch)
        await ctx.report_progress(progress=80, total=100)

        summary = [f"### Race Classification: {grand_prix} {year}"]
        summary.append("| Pos | Driver | Team | Grid | +/- | Time/Gap | Pts |")
        summary.append("| :-- | :----- | :--- | :--- | :-- | :------- | :-- |")

        for _, row in results.iterrows():
            pos = str(int(row["Position"])) if pd.notna(row["Position"]) else "NC"
            driver = row["Abbreviation"]
            team = row["TeamName"][:15]
            points = str(row["Points"]).rstrip("0").rstrip(".")

            grid = (
                str(int(row["GridPosition"]))
                if pd.notna(row["GridPosition"]) and row["GridPosition"] > 0
                else "PL"
            )

            if grid.isdigit() and pos.isdigit():
                diff = int(grid) - int(pos)
                change = f"+{diff}" if diff > 0 else (f"{diff}" if diff < 0 else "=")
            else:
                change = "-"

            status = row["Status"]
            time_val = row["Time"]
            if status == "Finished":
                time_str = _fmt_timedelta(time_val) if pd.notna(time_val) else "Interval"
            elif "Lap" in str(status):
                time_str = status
            else:
                time_str = f"DNF ({status})"

            summary.append(f"| {pos} | {driver} | {team} | {grid} | {change} | {time_str} | {points} |")

        await ctx.report_progress(progress=100, total=100)
        return "\n".join(summary)
    except Exception as e:
        return f"Failed to fetch race results: {e}"


# ---------------------------------------------------------------------------
# 3. Qualifying Results
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_qualifying_results(year: int, grand_prix: str, ctx: Context) -> str:
    """
    Fetches the main qualifying results (Q1/Q2/Q3) that determine the Sunday grid.
    Do NOT use this for Sprint Qualifying — use get_sprint_qualifying_results instead.
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()

        def _fetch():
            session = fastf1.get_session(year, grand_prix, "Q")
            session.load(telemetry=False, laps=False, weather=False)
            return session.results

        results = await loop.run_in_executor(None, _fetch)
        await ctx.report_progress(progress=80, total=100)

        output = []
        for phase, col in [("Q1", "Q1"), ("Q2", "Q2"), ("Q3", "Q3")]:
            if col in results.columns and results[col].notna().any():
                phase_df = results[results[col].notna()].sort_values(by=col) if col != "Q1" else results.sort_values(by=col)
                output.append(f"### {phase} Results ({grand_prix} {year})")
                output.append(f"| Pos | Driver | {phase} Time |")
                output.append(f"| :-- | :----- | :------ |")
                for i, (_, row) in enumerate(phase_df.iterrows(), 1):
                    if pd.notna(row[col]):
                        output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row[col])} |")
                output.append("")

        await ctx.report_progress(progress=100, total=100)
        return "\n".join(output) if output else f"No qualifying data for {grand_prix} {year}."
    except Exception as e:
        return f"Failed to fetch qualifying results: {e}"


# ---------------------------------------------------------------------------
# 4. Sprint Results
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_sprint_results(year: int, grand_prix: str, ctx: Context) -> str:
    """
    Fetches Saturday sprint race results. Use this if the user mentions 'Sprint' or 'Sprint Race'.
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()

        def _fetch():
            session = fastf1.get_session(year, grand_prix, "S")
            session.load(telemetry=False, laps=False, weather=False)
            return session.results.sort_values(by="Position")

        results = await loop.run_in_executor(None, _fetch)
        await ctx.report_progress(progress=80, total=100)

        summary = [f"### Sprint Race Results: {grand_prix} {year}"]
        for _, row in results.iterrows():
            pos = str(row["Position"]).split(".")[0]
            status = str(row["Status"])
            if "Disqualified" in status or "DSQ" in status:
                time_str = "DSQ"
            elif pd.notna(row["Time"]):
                time_str = _fmt_timedelta(row["Time"])
            else:
                time_str = status
            summary.append(f"| {pos} | {row['Abbreviation']} | {time_str} |")

        await ctx.report_progress(progress=100, total=100)
        return "\n".join(summary)
    except Exception as e:
        return f"Could not fetch Sprint results: {e}"


# ---------------------------------------------------------------------------
# 5. Sprint Qualifying
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_sprint_qualifying_results(year: int, grand_prix: str, ctx: Context) -> str:
    """
    Fetches sprint qualifying (Shootout) results broken into SQ1/SQ2/SQ3.
    Use this for 'Sprint Qualifying', 'Shootout', or 'SQ'.
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()

        def _fetch():
            session = fastf1.get_session(year, grand_prix, "SQ")
            session.load(telemetry=False, laps=True, weather=False)
            return session.results

        results = await loop.run_in_executor(None, _fetch)
        await ctx.report_progress(progress=80, total=100)

        output = []
        for phase, col in [("SQ1", "Q1"), ("SQ2", "Q2"), ("SQ3", "Q3")]:
            if col in results.columns and results[col].notna().any():
                phase_df = results[results[col].notna()].sort_values(by=col)
                output.append(f"### {phase} Results ({grand_prix} {year})")
                output.append(f"| Pos | Driver | {phase} Time |")
                output.append(f"| :-- | :----- | :------- |")
                for i, (_, row) in enumerate(phase_df.iterrows(), 1):
                    output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row[col])} |")
                output.append("")

        if not output:
            output.append(f"### Sprint Qualifying Results ({grand_prix} {year})")
            output.append("*(Detailed SQ1/SQ2/SQ3 split data unavailable)*")

        await ctx.report_progress(progress=100, total=100)
        return "\n".join(output)
    except Exception as e:
        return f"Could not fetch Sprint Qualifying. {grand_prix} {year} might not be a Sprint weekend. Error: {e}"


# ---------------------------------------------------------------------------
# 6. Driver Comparison (Telemetry)
# ---------------------------------------------------------------------------
@mcp.tool()
async def compare_drivers(year: int, grand_prix: str, driver1: str, driver2: str, ctx: Context) -> str:
    """
    Compares the fastest qualifying lap of two drivers sector by sector.
    Accepts partial name matches (e.g. 'Max' instead of 'VER').
    """
    try:
        await ctx.report_progress(progress=10, total=100)
        loop = asyncio.get_event_loop()

        def _fetch():
            session = fastf1.get_session(year, grand_prix, "Q")
            session.load(telemetry=False, laps=True, weather=False)
            return session

        session = await loop.run_in_executor(None, _fetch)
        await ctx.report_progress(progress=60, total=100)

        def get_driver_code(name_query: str):
            query = name_query.lower().strip()
            for drv in session.results.itertuples():
                if (
                    query in str(drv.LastName).lower()
                    or query in str(drv.BroadcastName).lower()
                    or query == str(drv.Abbreviation).lower()
                ):
                    return drv.Abbreviation
            return None

        d1_code = get_driver_code(driver1)
        d2_code = get_driver_code(driver2)
        if not d1_code or not d2_code:
            return f"Could not find drivers '{driver1}' or '{driver2}' in the entry list."

        d1_lap = session.laps.pick_driver(d1_code).pick_fastest()
        d2_lap = session.laps.pick_driver(d2_code).pick_fastest()
        if d1_lap is None or d2_lap is None:
            return f"No lap data found for {d1_code} or {d2_code}."

        total = d1_lap["LapTime"] - d2_lap["LapTime"]
        s1 = d1_lap["Sector1Time"] - d2_lap["Sector1Time"]
        s2 = d1_lap["Sector2Time"] - d2_lap["Sector2Time"]
        s3 = d1_lap["Sector3Time"] - d2_lap["Sector3Time"]

        def fmt(sec):
            return f"{'+' if sec > 0 else ''}{sec:.3f}s"

        await ctx.report_progress(progress=100, total=100)
        return (
            f"### Telemetry: {grand_prix} {year}\n"
            f"**{d1_code} vs {d2_code}**\n\n"
            f"| Sector | Gap ({d1_code} vs {d2_code}) |\n"
            f"| :--- | :--- |\n"
            f"| **TOTAL** | **{fmt(total.total_seconds())}** |\n"
            f"| Sector 1 | {fmt(s1.total_seconds())} |\n"
            f"| Sector 2 | {fmt(s2.total_seconds())} |\n"
            f"| Sector 3 | {fmt(s3.total_seconds())} |"
        )
    except Exception as e:
        return f"Comparison failed: {e}"


# ---------------------------------------------------------------------------
# 7. Driver Standings
# ---------------------------------------------------------------------------
@mcp.tool()
def get_driver_standings(year: int) -> str:
    """
    Fetches the World Drivers' Championship standings for a given year.
    Falls back to entry list with 0 points for seasons that haven't started.
    """
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)

        if data.content:
            df = data.content[0]
            output = [f"### Driver Standings ({year})"]
            output.append("| Pos | Driver | Team | Points | Wins |")
            output.append("| :-- | :----- | :--- | :----- | :--- |")
            for _, row in df.iterrows():
                teams = row.get("constructorNames", row.get("constructorName", "Unknown"))
                team_str = ", ".join(teams) if isinstance(teams, list) else str(teams)
                output.append(
                    f"| {row['position']} | {row.get('driverCode', '???')} | {team_str} "
                    f"| {row['points']} | {row['wins']} |"
                )
            return "\n".join(output)

        # No standings yet — build entry list.
        constructors_df = ergast.get_constructor_info(season=year)
        if constructors_df.empty:
            return f"No driver data found for {year}."
        output = [f"### {year} Entry List (Season not started — 0 points)"]
        pos = 1
        for _, crow in constructors_df.iterrows():
            cid = crow["constructorId"]
            team = crow["constructorName"]
            drivers_df = ergast.get_driver_info(season=year, constructor=cid)
            for _, drow in drivers_df.iterrows():
                output.append(f"{pos}. {drow['givenName']} {drow['familyName']} ({team}) — 0 pts")
                pos += 1
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching standings: {e}"


# ---------------------------------------------------------------------------
# 8. Constructor Standings
# ---------------------------------------------------------------------------
@mcp.tool()
def get_constructor_standings(year: int) -> str:
    """
    Fetches the World Constructors' Championship standings for a given year.
    Falls back to entry list with 0 points for seasons that haven't started.
    """
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)

        if data.content:
            df = data.content[0]
            output = [f"### Constructor Standings ({year})"]
            output.append("| Pos | Team | Points | Wins |")
            output.append("| :-- | :--- | :----- | :--- |")
            for _, row in df.iterrows():
                output.append(f"| {row['position']} | {row['constructorName']} | {row['points']} | {row['wins']} |")
            return "\n".join(output)

        constructors_df = ergast.get_constructor_info(season=year)
        if constructors_df.empty:
            return f"No constructor data found for {year}."
        output = [f"### {year} Constructor Entry List (Season not started — 0 points)"]
        for idx, (_, row) in enumerate(constructors_df.iterrows(), 1):
            output.append(f"{idx}. {row['constructorName']} — 0 pts")
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching constructor standings: {e}"


# ---------------------------------------------------------------------------
# 9. Rulebook Search (RAG)
# ---------------------------------------------------------------------------
@mcp.tool()
def consult_rulebook(query: str, year: int = None) -> str:
    """
    Searches the official FIA regulations (Sporting, Technical, Financial)
    for text relevant to the query. Covers 2024-2026 regulations.
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_chroma import Chroma

        if year is None:
            now = datetime.now()
            year = now.year + 1 if (now.month == 12 and now.day > 10) else now.year

        db_path = os.path.join(os.path.dirname(__file__), "data", "chroma")
        if not os.path.exists(db_path):
            return "Rulebook database not found. Run `python app/rag/ingest.py` from the backend directory."

        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_db = Chroma(persist_directory=db_path, embedding_function=embeddings)
        retriever = vector_db.as_retriever(
            search_kwargs={"k": 6, "filter": {"source_year": str(year)}}
        )
        docs = retriever.invoke(query)

        if not docs:
            return f"No regulations found for '{query}' in the {year} rulebook."

        results = []
        for doc in docs:
            source = doc.metadata.get("filename", "Unknown PDF")
            content = doc.page_content.replace("\n", " ")
            results.append(f"**Source:** {source}\n**Excerpt:** ...{content[:500]}...")
        return "\n\n".join(results)
    except Exception as e:
        return f"Rulebook lookup failed: {e}"


# ---------------------------------------------------------------------------
# 10. Web Search
# ---------------------------------------------------------------------------
@mcp.tool()
def perform_web_search(query: str) -> str:
    """
    Performs a real-time web search for F1 news, rumours, or recent events using Tavily.
    Returns the top 3 results.
    """
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = client.search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if not results:
            return "No search results found."
        return "\n\n".join(
            f"Source: {r['title']}\nSnippet: {r['content']}\nURL: {r['url']}"
            for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"


# ---------------------------------------------------------------------------
# 11. Health Check
# ---------------------------------------------------------------------------
@mcp.tool()
def health_check() -> str:
    """Checks if the F1 Race Engineer backend and all data sources are operational."""
    checks = []
    # FastF1
    try:
        fastf1.get_event_schedule(year=2024, include_testing=False)
        checks.append("FastF1 API: OK")
    except Exception as e:
        checks.append(f"FastF1 API: ERROR ({e})")
    # Ergast
    try:
        Ergast().get_driver_standings(season=2024)
        checks.append("Ergast API: OK")
    except Exception as e:
        checks.append(f"Ergast API: ERROR ({e})")
    # Rulebook
    db_path = os.path.join(os.path.dirname(__file__), "data", "chroma")
    checks.append(f"Rulebook DB: {'OK' if os.path.exists(db_path) else 'NOT FOUND'}")
    # Tavily
    checks.append(f"Web Search: {'OK' if os.getenv('TAVILY_API_KEY') else 'NO API KEY'}")

    return "### F1 Race Engineer — System Status\n" + "\n".join(f"- {c}" for c in checks)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
