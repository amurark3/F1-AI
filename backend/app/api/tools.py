"""
LLM-Callable Tools
==================
Each function decorated with @tool is registered as a callable tool that the
Gemini model can invoke during the agentic loop in routes.py.

Available tools
---------------
  get_track_conditions        — Stub; returns placeholder weather text (not yet implemented).
  perform_web_search          — Real-time web search via Tavily API.
  get_sprint_results          — Sprint race (Saturday short race) classification.
  get_sprint_qualifying_results — Sprint Qualifying / Shootout results split by SQ1/SQ2/SQ3.
  get_qualifying_results      — Main Qualifying results split by Q1/Q2/Q3.
  compare_drivers             — Fastest-lap telemetry comparison between two drivers.
  get_race_results            — Full race classification with grid delta and points.
  consult_rulebook            — Semantic search of FIA regulations via ChromaDB.
  get_driver_standings        — World Drivers' Championship table (via Ergast).
  get_constructor_standings   — World Constructors' Championship table (via Ergast).
  get_season_schedule         — Full season calendar with completed/upcoming status.

TOOL_LIST and TOOL_MAP (at the bottom of this file) are imported by routes.py
to bind tools to the LLM and dispatch them by name.
"""

import os
import fastf1
import pandas as pd
from datetime import datetime
from langchain_core.tools import tool
from fastf1.ergast import Ergast
from tavily import TavilyClient
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Enable FastF1 disk cache to avoid re-downloading session data on every call.
if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache("f1_cache")


# ---------------------------------------------------------------------------
# Helper — shared time-string formatter
# ---------------------------------------------------------------------------
def _fmt_timedelta(time_val) -> str:
    """
    Converts a pandas Timedelta (or NaT) to a clean lap-time string.

    Examples:
      0 days 00:01:23.456 → "1:23.456"
      0 days 00:00:45.123 → "45.123"
      NaT                 → "-"
    """
    if pd.isna(time_val):
        return "-"
    s = str(time_val).split("days")[-1].strip()
    if s.startswith("00:"):
        s = s[3:]        # Remove the leading "00:" hour field when zero
    if len(s) > 10:
        s = s[:9]        # Trim sub-millisecond precision
    return s


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_track_conditions(location: str):
    """
    Fetches weather conditions for a given F1 circuit location.

    NOTE: This is currently a placeholder stub. Live weather integration
    has not been implemented yet.  The model should mention to the user
    that real-time weather is unavailable.
    """
    print(f"🌍 TRACK CONDITIONS REQUESTED FOR: {location} (stub — not yet implemented)")
    return (
        "Live weather data is not yet available. "
        "Please check a weather service or the official F1 app for current conditions."
    )


@tool
def perform_web_search(query: str):
    """
    Performs a real-time web search for F1 news, rumours, or recent events.

    Uses the Tavily search API. Returns the top 3 results with title,
    snippet, and source URL.  Use this for anything that may have changed
    after the model's knowledge cut-off (e.g. transfer rumours, latest news).
    """
    print(f"🔎 SEARCHING TAVILY FOR: {query}")
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if not results:
            return "No search results found."
        return "\n\n".join(
            f"Source: {r['title']}\nSnippet: {r['content']}\nURL: {r['url']}"
            for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"


@tool
def get_sprint_results(year: int, grand_prix: str):
    """
    Fetches the SATURDAY SPRINT RACE results (the short 100 km race).

    ALWAYS use this tool if the user mentions 'Sprint', 'Sprint Race', or
    'Saturday Race'.  Do NOT use get_race_results for sprint weekends.

    Returns a Markdown table of finishing positions, driver abbreviations,
    and times / DNF reasons.
    """
    print(f"🏎️  FETCHING SPRINT RESULTS: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, "S")
        # telemetry and weather data are not needed for a results table.
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results.sort_values(by="Position")

        summary = [f"### Sprint Race Results: {grand_prix} {year}"]

        for _, row in results.iterrows():
            pos = str(row["Position"]).split(".")[0]
            status = str(row["Status"])

            # DSQ takes priority over any time value.
            if "Disqualified" in status or "DSQ" in status:
                time_str = "DSQ"
            elif pd.notna(row["Time"]):
                time_str = _fmt_timedelta(row["Time"])
            else:
                time_str = status  # DNF / +1 Lap / etc.

            summary.append(f"| {pos} | {row['Abbreviation']} | {time_str} |")

        return "\n".join(summary)

    except Exception as e:
        return f"Could not fetch Sprint results: {e}"


@tool
def get_sprint_qualifying_results(year: int, grand_prix: str):
    """
    Fetches SPRINT QUALIFYING (Shootout) results broken into SQ1 / SQ2 / SQ3.

    ALWAYS use this tool if the user mentions 'Sprint Qualifying', 'Shootout',
    'SQ', or 'Sprint Quali'.  Do NOT use get_qualifying_results for this.

    Note: FastF1 uses column names Q1/Q2/Q3 even for sprint shootout data;
    laps=True is required because Ergast often lacks SQ split times.
    """
    print(f"⏱️  FETCHING SPRINT SHOOTOUT: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, "SQ")
        # laps=True is required: Ergast often doesn't carry SQ1/SQ2/SQ3 columns,
        # so FastF1 derives them from the lap data instead.
        session.load(telemetry=False, laps=True, weather=False)
        results = session.results

        output = []

        # --- SQ1 ---
        # FastF1 stores SQ1 times in the 'Q1' column (naming follows Qualifying).
        if "Q1" in results.columns and results["Q1"].notna().any():
            sq1_df = results.sort_values(by="Q1")
            output.append(f"### SQ1 Results ({grand_prix} {year})")
            output.append("| Pos | Driver | SQ1 Time |")
            output.append("| :-- | :----- | :------- |")
            for i, (_, row) in enumerate(sq1_df.iterrows(), 1):
                if pd.notna(row["Q1"]):
                    output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q1'])} |")
            output.append("\n---\n")

        # --- SQ2 ---
        if "Q2" in results.columns and results["Q2"].notna().any():
            sq2_df = results[results["Q2"].notna()].sort_values(by="Q2")
            if not sq2_df.empty:
                output.append("### SQ2 Results")
                output.append("| Pos | Driver | SQ2 Time |")
                output.append("| :-- | :----- | :------- |")
                for i, (_, row) in enumerate(sq2_df.iterrows(), 1):
                    output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q2'])} |")
                output.append("\n---\n")

        # --- SQ3 ---
        if "Q3" in results.columns and results["Q3"].notna().any():
            sq3_df = results[results["Q3"].notna()].sort_values(by="Q3")
            if not sq3_df.empty:
                output.append("### SQ3 Results (Sprint Pole Position)")
                output.append("| Pos | Driver | SQ3 Time |")
                output.append("| :-- | :----- | :------- |")
                for i, (_, row) in enumerate(sq3_df.iterrows(), 1):
                    output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q3'])} |")

        # Fallback: if the split-column data is absent, show a simple ordered list.
        if not output:
            output.append(f"### Sprint Qualifying Results ({grand_prix} {year})")
            output.append("*(Detailed SQ1/SQ2/SQ3 split data currently unavailable)*\n")
            output.append("| Pos | Driver | Time |")
            output.append("| :-- | :----- | :--- |")
            for _, row in results.sort_values(by="Position").iterrows():
                t = _fmt_timedelta(row["Time"]) if pd.notna(row["Time"]) else "-"
                output.append(f"| {row['Position']} | {row['Abbreviation']} | {t} |")

        return "\n".join(output)

    except Exception as e:
        return (
            f"Could not fetch Sprint Qualifying. "
            f"Note: {grand_prix} {year} might not be a Sprint weekend. Error: {e}"
        )


@tool
def get_qualifying_results(year: int, grand_prix: str):
    """
    Fetches the MAIN QUALIFYING results (determines the Sunday race grid).

    Returns separate tables for Q1, Q2, and Q3 with each driver's best
    lap time for that session segment.

    IMPORTANT: Do NOT use this for Sprint Qualifying / Shootout sessions.
    Use get_sprint_qualifying_results for those.
    """
    print(f"🏎️  FETCHING QUALIFYING DATA: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, "Q")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results

        output = []

        # --- Q1 --- (all drivers who set a time)
        q1_df = results.sort_values(by="Q1")
        output.append(f"### Q1 Results ({grand_prix} {year})")
        output.append("| Pos | Driver | Q1 Time |")
        output.append("| :-- | :----- | :------ |")
        for i, (_, row) in enumerate(q1_df.iterrows(), 1):
            output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q1'])} |")
        output.append("\n---\n")

        # --- Q2 --- (drivers who advanced beyond Q1)
        q2_df = results[results["Q2"].notna()].sort_values(by="Q2")
        if not q2_df.empty:
            output.append("### Q2 Results")
            output.append("| Pos | Driver | Q2 Time |")
            output.append("| :-- | :----- | :------ |")
            for i, (_, row) in enumerate(q2_df.iterrows(), 1):
                output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q2'])} |")
            output.append("\n---\n")

        # --- Q3 --- (top 10 pole-position shootout)
        q3_df = results[results["Q3"].notna()].sort_values(by="Q3")
        if not q3_df.empty:
            output.append("### Q3 Results (Pole Position)")
            output.append("| Pos | Driver | Q3 Time |")
            output.append("| :-- | :----- | :------ |")
            for i, (_, row) in enumerate(q3_df.iterrows(), 1):
                output.append(f"| {i} | {row['Abbreviation']} | {_fmt_timedelta(row['Q3'])} |")

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch qualifying results: {e}"


@tool
def compare_drivers(year: int, grand_prix: str, driver1: str, driver2: str):
    """
    Compares the fastest Qualifying lap of two drivers, sector by sector.

    Accepts partial name matches so the model can pass 'Max' instead of 'VER'.
    The lookup searches LastName, BroadcastName, and Abbreviation fields.

    Returns a Markdown table showing total gap and per-sector deltas,
    with green/red indicators for faster/slower relative to driver2.
    """
    print(f"⚔️  COMPARING: {driver1} vs {driver2} at {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, "Q")
        # laps=True is required to access per-driver fastest lap data.
        session.load(telemetry=False, laps=True, weather=False)

        def get_driver_code(name_query: str) -> str | None:
            """Resolve a name/partial name to the driver's 3-letter abbreviation."""
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
            return (
                f"Could not find drivers '{driver1}' or '{driver2}' "
                f"in the entry list for {grand_prix} {year}."
            )

        print(f"✅ Resolved: {driver1} → {d1_code}, {driver2} → {d2_code}")

        d1_lap = session.laps.pick_driver(d1_code).pick_fastest()
        d2_lap = session.laps.pick_driver(d2_code).pick_fastest()

        if d1_lap is None or d2_lap is None:
            return f"No lap data found for {d1_code} or {d2_code}."

        # Calculate deltas (positive = d1 is slower than d2)
        total = d1_lap["LapTime"] - d2_lap["LapTime"]
        s1 = d1_lap["Sector1Time"] - d2_lap["Sector1Time"]
        s2 = d1_lap["Sector2Time"] - d2_lap["Sector2Time"]
        s3 = d1_lap["Sector3Time"] - d2_lap["Sector3Time"]

        def fmt_delta(sec) -> str:
            return f"{'+' if sec > 0 else ''}{sec:.3f}s"

        return (
            f"### Telemetry: {grand_prix} {year}\n"
            f"**{d1_code} vs {d2_code}**\n\n"
            f"| Sector | Gap ({d1_code} to {d2_code}) | Status |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **TOTAL** | **{fmt_delta(total.total_seconds())}** | "
            f"{'🔴 Slower' if total.total_seconds() > 0 else '🟢 Faster'} |\n"
            f"| Sector 1 | {fmt_delta(s1.total_seconds())} | "
            f"{'🔴' if s1.total_seconds() > 0 else '🟢'} |\n"
            f"| Sector 2 | {fmt_delta(s2.total_seconds())} | "
            f"{'🔴' if s2.total_seconds() > 0 else '🟢'} |\n"
            f"| Sector 3 | {fmt_delta(s3.total_seconds())} | "
            f"{'🔴' if s3.total_seconds() > 0 else '🟢'} |"
        )

    except Exception as e:
        return f"Comparison failed: {e}"


@tool
def get_race_results(year: int, grand_prix: str):
    """
    Fetches the FINAL RACE classification for a Grand Prix.

    Returns a table with: finishing position, driver, team (truncated to 15
    chars), starting grid position, position change (+/- arrows), race time
    or gap, and championship points scored.

    Handles DNFs, DSQs, and lapped cars via the 'Status' column.
    """
    print(f"🏁 FETCHING RACE RESULTS: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, "R")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results.sort_values(by="Position")

        summary = [f"### Race Classification: {grand_prix} {year}"]
        summary.append("| Pos | Driver | Team | Grid | +/- | Time/Gap | Pts |")
        summary.append("| :-- | :----- | :--- | :--- | :-- | :------- | :-- |")

        for _, row in results.iterrows():
            pos = str(int(row["Position"])) if pd.notna(row["Position"]) else "NC"
            driver = row["Abbreviation"]
            # Truncate long team names to keep the table readable.
            team = row["TeamName"][:15]
            points = str(row["Points"])
            if points.endswith(".0"):
                points = points[:-2]  # "25.0" → "25"

            # Grid position: "PL" indicates a pit-lane start.
            grid = (
                str(int(row["GridPosition"]))
                if pd.notna(row["GridPosition"]) and row["GridPosition"] > 0
                else "PL"
            )

            # Position change from grid to finish.
            if grid.isdigit() and pos.isdigit():
                diff = int(grid) - int(pos)
                change = f"⬆️{diff}" if diff > 0 else (f"⬇️{abs(diff)}" if diff < 0 else "➖")
            else:
                change = "-"

            # Format race time or gap-to-leader.
            status = row["Status"]
            time_val = row["Time"]

            if status == "Finished":
                if pd.notna(time_val):
                    t_str = str(time_val).split("days")[-1].strip()
                    # Trim to 3 decimal places.
                    if "." in t_str:
                        t_str = t_str[: t_str.find(".") + 4]
                    if t_str.startswith("00:"):
                        t_str = t_str[3:]
                    time_str = t_str
                else:
                    time_str = "Interval"
            elif "Lap" in status:
                time_str = status          # "+1 Lap", "+2 Laps", etc.
            else:
                time_str = f"❌ {status}"  # DNF / accident / mechanical

            if pos == "1":
                pos = "🏆 1"

            summary.append(f"| {pos} | {driver} | {team} | {grid} | {change} | {time_str} | {points} |")

        return "\n".join(summary)

    except Exception as e:
        return f"Failed to fetch race results: {e}"


@tool
def consult_rulebook(query: str, year: int = None):
    """
    Searches the official FIA regulations (Sporting, Technical, Financial)
    for text relevant to `query`.

    The regulations are stored as vector embeddings in a local ChromaDB
    database populated by running backend/app/rag/ingest.py.

    Args:
        query: A natural-language question, e.g. "What is the penalty for
               exceeding the pit-lane speed limit?"
        year:  The season year to restrict results to (e.g. 2025).
               Defaults intelligently to the current season; switches to the
               next year's regulations in late December when available.
    """
    # --- Year resolution logic ---
    if year is None:
        now = datetime.now()
        current_year = now.year
        # After mid-December the season is over; prefer next-year regs if present.
        season_ended = now.month == 12 and now.day > 10

        if season_ended and os.path.exists(f"data/raw/{current_year + 1}"):
            year = current_year + 1
            print(f"📅 Season over. Defaulting to next year's regulations: {year}")
        else:
            year = current_year
            print(f"📅 Using current season regulations: {year}")

    print(f"⚖️  CONSULTING RULEBOOK ({year}): {query}")

    try:
        db_path = "data/chroma"

        if not os.path.exists(db_path):
            return (
                "Rulebook database not found. "
                "Please run `python app/rag/ingest.py` from the backend directory first."
            )

        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_db = Chroma(persist_directory=db_path, embedding_function=embeddings)

        # Filter by year metadata so rules from different seasons don't mix.
        search_kwargs = {
            "k": 6,  # Return the 6 most relevant chunks
            "filter": {"source_year": str(year)},
        }

        retriever = vector_db.as_retriever(search_kwargs=search_kwargs)
        docs = retriever.invoke(query)

        if not docs:
            return f"No regulations found for '{query}' in the {year} rulebook."

        results = []
        for doc in docs:
            source = doc.metadata.get("filename", "Unknown PDF")
            # Collapse newlines for cleaner display; limit excerpt length.
            content = doc.page_content.replace("\n", " ")
            results.append(f"**Source:** {source}\n**Excerpt:** ...{content[:500]}...")

        return "\n\n".join(results)

    except Exception as e:
        return f"Rulebook lookup failed: {e}"


@tool
def get_driver_standings(year: int):
    """
    Fetches the World Drivers' Championship (WDC) standings for `year`.

    Returns a Markdown table of position, driver code, team(s), points, wins.
    Drivers who competed for multiple teams are shown with all teams listed.
    """
    print(f"🏆 FETCHING DRIVER STANDINGS: {year}")
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)

        if not data.content:
            return f"No driver standings found for {year}."

        df = data.content[0]
        results = df[["position", "driverCode", "points", "wins", "constructorNames"]]

        output = [f"### Driver Standings ({year})"]
        output.append("| Pos | Driver | Team | Points | Wins |")
        output.append("| :-- | :----- | :--- | :----- | :--- |")

        for _, row in results.iterrows():
            # constructorNames is a list when a driver changed teams mid-season.
            teams = row["constructorNames"]
            team_str = ", ".join(teams) if isinstance(teams, list) else str(teams)
            output.append(
                f"| {row['position']} | {row['driverCode']} | {team_str} "
                f"| {row['points']} | {row['wins']} |"
            )

        return "\n".join(output)

    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        return f"Failed to fetch driver standings: {e}"


@tool
def get_constructor_standings(year: int):
    """
    Fetches the World Constructors' Championship (WCC) standings for `year`.

    Returns a Markdown table of position, team name, points, and wins.
    """
    print(f"🏆 FETCHING CONSTRUCTOR STANDINGS: {year}")
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)

        if not data.content:
            return f"No constructor standings found for {year}."

        df = data.content[0]
        results = df[["position", "constructorName", "points", "wins"]]

        output = [f"### Constructor Standings ({year})"]
        output.append("| Pos | Team | Points | Wins |")
        output.append("| :-- | :--- | :----- | :--- |")

        for _, row in results.iterrows():
            output.append(
                f"| {row['position']} | {row['constructorName']} "
                f"| {row['points']} | {row['wins']} |"
            )

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch constructor standings: {e}"


@tool
def get_season_schedule(year: int):
    """
    Fetches the full F1 season calendar for `year`.

    Marks each race as 'Completed' or 'Upcoming' relative to today's date,
    and appends a summary of the last completed race to help the LLM resolve
    queries like 'What happened in the last race?'.
    """
    print(f"📅 CHECKING SCHEDULE: {year}")
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
        today = datetime.now()

        output = [f"### F1 Season Schedule ({year})"]
        output.append(f"*(Current Date: {today.strftime('%Y-%m-%d')})*\n")
        output.append("| Round | Grand Prix | Date | Status |")
        output.append("| :--- | :--------- | :--- | :----- |")

        last_completed = "None"

        for _, row in schedule.iterrows():
            race_date = row["EventDate"]   # FastF1 provides this as a Timestamp
            gp_name = row["EventName"]
            round_num = row["RoundNumber"]

            if race_date < today:
                status = "✅ Completed"
                last_completed = gp_name
            else:
                status = "🔜 Upcoming"

            output.append(f"| {round_num} | {gp_name} | {race_date.strftime('%d %b')} | {status} |")

        # Provide explicit context for the LLM to avoid hallucinating race names.
        output.append(f"\n**Context:** The last completed race was the **{last_completed}**.")

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch schedule: {e}"


# ---------------------------------------------------------------------------
# ML Predictions & Scenario Analysis
# ---------------------------------------------------------------------------

@tool
def predict_race_results(year: int, grand_prix: str):
    """
    Predicts the finishing order for a Grand Prix using a machine learning
    model trained on historical F1 data (2018-2025).

    The model considers qualifying position, constructor strength, driver
    recent form, historical track performance, and DNF probability.

    Use this when the user asks about predictions, expected results, or
    "who will win" questions for races.

    Parameters:
        year: The season year (e.g. 2025).
        grand_prix: The name of the Grand Prix (e.g. "Monaco", "British").
    """
    from app.ml.predict import predict_race
    return predict_race(year, grand_prix)


@tool
def calculate_championship_scenario(year: int, driver: str):
    """
    Calculates how many points per remaining race a driver needed to win
    the World Drivers' Championship, computed after each round of the season.

    Shows the progression of mathematical possibility throughout the year.

    Use this when the user asks about championship battles, title scenarios,
    "could X have won the title", or points needed to win.

    Parameters:
        year: The season year (e.g. 2024).
        driver: The driver's last name (e.g. "Norris", "Verstappen").
    """
    from app.ml.scenario import calculate_title_scenario
    return calculate_title_scenario(year, driver)


# ---------------------------------------------------------------------------
# Tool registry — imported by routes.py
# ---------------------------------------------------------------------------
TOOL_LIST = [
    get_track_conditions,
    perform_web_search,
    get_sprint_results,
    get_sprint_qualifying_results,
    get_qualifying_results,
    compare_drivers,
    get_race_results,
    consult_rulebook,
    get_driver_standings,
    get_constructor_standings,
    get_season_schedule,
    predict_race_results,
    calculate_championship_scenario,
]

# Map tool name → tool object for O(1) dispatch in the agentic loop.
TOOL_MAP = {t.name: t for t in TOOL_LIST}
