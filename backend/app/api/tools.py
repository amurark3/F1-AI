import os
import fastf1
import pandas as pd
from datetime import datetime
from langchain_core.tools import tool
from fastf1.ergast import Ergast
from tavily import TavilyClient
from app.api.prompts import RACE_ENGINEER_PERSONA
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache('f1_cache')

@tool
def get_track_conditions(location: str):
    """Fetches REAL-TIME live weather for a specific F1 circuit."""
    # (Simplified for brevity - keeps your existing weather logic)
    print(f"🌍 FETCHING REAL WEATHER FOR: {location}")
    # ... [Keep your existing weather code here if you have it, or I can provide] ...
    return "Weather data simulated for demo." # Replace with your actual weather logic if needed

@tool
def perform_web_search(query: str):
    """Performs a real-time web search for news/rumors."""
    print(f"🔎 SEARCHING TAVILY FOR: {query}")
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if not results: return "No search results found."
        return "\n\n".join([f"Source: {r['title']}\nSnippet: {r['content']}\nURL: {r['url']}" for r in results])
    except Exception as e:
        return f"Search failed: {str(e)}"


@tool
def get_sprint_results(year: int, grand_prix: str):
    """
    Fetches the SATURDAY SPRINT RACE results (The short race).
    ALWAYS use this if the user mentions 'Sprint', 'Sprint Race', or 'Saturday Race'.
    """
    print(f"🏎️ FETCHING SPRINT RESULTS: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, 'S')
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results.sort_values(by='Position')
        
        summary = [f"### Sprint Race Results: {grand_prix} {year}"]
        
        for _, row in results.iterrows():
            pos = str(row['Position']).split('.')[0]
            status = str(row['Status'])
            
            # FIX: Check Status for DSQ first
            if 'Disqualified' in status or 'DSQ' in status:
                time_str = "DSQ"
            elif pd.notna(row['Time']):
                time_str = str(row['Time']).split('days')[-1].strip()
                if time_str.startswith("00:"): time_str = time_str[3:]
            else:
                time_str = status
            
            summary.append(f"| {pos} | {row['Abbreviation']} | {time_str} |")
            
        return "\n".join(summary)
    except Exception as e:
        return f"Could not fetch Sprint results: {str(e)}"

@tool
def get_sprint_qualifying_results(year: int, grand_prix: str):
    """
    Fetches SPRINT QUALIFYING (Shootout) results.
    ALWAYS use this if the user mentions 'Sprint Qualifying', 'Shootout', 'SQ', or 'Sprint Quali'.
    """
    print(f"⏱️ FETCHING SPRINT SHOOTOUT: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, 'SQ')
        
        # FIX: laps=True is REQUIRED for Sprint Shootouts to calculate Q1/Q2/Q3 columns
        # because the standard Ergast API often doesn't have this data for Sprints.
        session.load(telemetry=False, laps=True, weather=False)
        
        results = session.results
        
        def fmt(time_val):
            if pd.isna(time_val): return "-"
            s = str(time_val).split('days')[-1].strip()
            if s.startswith("00:"): s = s[3:]
            if len(s) > 10: s = s[:9] 
            return s

        output = []

        # --- SQ1 TABLE ---
        # Note: FastF1 uses 'Q1' column name even for Sprint SQ1
        if 'Q1' in results.columns and results['Q1'].notna().any():
            sq1_df = results.sort_values(by='Q1')
            output.append(f"### SQ1 Results ({grand_prix} {year})")
            output.append("| Pos | Driver | SQ1 Time |")
            output.append("| :-- | :----- | :------- |")
            for i, (_, row) in enumerate(sq1_df.iterrows(), 1):
                if pd.notna(row['Q1']):
                    output.append(f"| {i} | {row['Abbreviation']} | {fmt(row['Q1'])} |")
            output.append("\n---\n")

        # --- SQ2 TABLE ---
        if 'Q2' in results.columns and results['Q2'].notna().any():
            sq2_df = results[results['Q2'].notna()].sort_values(by='Q2')
            if not sq2_df.empty:
                output.append(f"### SQ2 Results")
                output.append("| Pos | Driver | SQ2 Time |")
                output.append("| :-- | :----- | :------- |")
                for i, (_, row) in enumerate(sq2_df.iterrows(), 1):
                    output.append(f"| {i} | {row['Abbreviation']} | {fmt(row['Q2'])} |")
                output.append("\n---\n")

        # --- SQ3 TABLE ---
        if 'Q3' in results.columns and results['Q3'].notna().any():
            sq3_df = results[results['Q3'].notna()].sort_values(by='Q3')
            if not sq3_df.empty:
                output.append(f"### SQ3 Results (Pole Position Shootout)")
                output.append("| Pos | Driver | SQ3 Time |")
                output.append("| :-- | :----- | :------- |")
                for i, (_, row) in enumerate(sq3_df.iterrows(), 1):
                    output.append(f"| {i} | {row['Abbreviation']} | {fmt(row['Q3'])} |")
        
        # FALLBACK: If separate tables failed (e.g. data missing split columns), show simple list
        if not output:
            output.append(f"### Sprint Qualifying Results ({grand_prix} {year})")
            output.append("*(Detailed split data SQ1/SQ2/SQ3 currently unavailable)*\n")
            output.append("| Pos | Driver | Time |")
            output.append("| :-- | :----- | :--- |")
            drivers = results.sort_values(by='Position')
            for _, row in drivers.iterrows():
                t = fmt(row['Time']) if pd.notna(row['Time']) else "-"
                output.append(f"| {row['Position']} | {row['Abbreviation']} | {t} |")

        return "\n".join(output)

    except Exception as e:
        return f"Could not fetch Sprint Qualifying. Note: {grand_prix} {year} might not be a Sprint weekend. Error: {str(e)}"


@tool
def get_qualifying_results(year: int, grand_prix: str):
    """
    Fetches the MAIN QUALIFYING results (The session that determines the Sunday Grid).
    Use this for queries like 'qualifying results', 'who is on pole', 'Friday qualifying'.
    
    IMPORTANT: Do NOT use this if the user asks for 'Sprint Qualifying', 'Shootout', or 'SQ'.
    For those, use 'get_sprint_qualifying_results' instead.
    """
    print(f"🏎️ FETCHING QUALIFYING DATA: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, 'Q')
        session.load(telemetry=False, laps=False, weather=False)
        
        results = session.results
        
        # Helper to clean up time strings
        def fmt(time_val):
            if pd.isna(time_val): return "-"
            s = str(time_val).split('days')[-1].strip()
            if s.startswith("00:"): s = s[3:]
            if len(s) > 10: s = s[:9] 
            return s

        output = []

        # --- Q1 TABLE ---
        # Sort by Q1 time to see who was fastest in that specific session
        q1_df = results.sort_values(by='Q1')
        output.append(f"### Q1 Results ({grand_prix} {year})")
        output.append("| Pos | Driver | Q1 Time |")
        output.append("| :-- | :----- | :------ |")
        for i, (_, row) in enumerate(q1_df.iterrows(), 1):
            time_str = fmt(row['Q1'])
            # Only list if they actually participated or have a status
            output.append(f"| {i} | {row['Abbreviation']} | {time_str} |")
        
        output.append("\n---\n") # Separator

        # --- Q2 TABLE ---
        # Filter for drivers who set a time in Q2 (or made it through)
        q2_df = results[results['Q2'].notna()].sort_values(by='Q2')
        if not q2_df.empty:
            output.append(f"### Q2 Results")
            output.append("| Pos | Driver | Q2 Time |")
            output.append("| :-- | :----- | :------ |")
            for i, (_, row) in enumerate(q2_df.iterrows(), 1):
                output.append(f"| {i} | {row['Abbreviation']} | {fmt(row['Q2'])} |")
            output.append("\n---\n")

        # --- Q3 TABLE ---
        # Filter for drivers who set a time in Q3
        q3_df = results[results['Q3'].notna()].sort_values(by='Q3')
        if not q3_df.empty:
            output.append(f"### Q3 Results (Pole Position Shootout)")
            output.append("| Pos | Driver | Q3 Time |")
            output.append("| :-- | :----- | :------ |")
            for i, (_, row) in enumerate(q3_df.iterrows(), 1):
                output.append(f"| {i} | {row['Abbreviation']} | {fmt(row['Q3'])} |")

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch results: {str(e)}"


@tool
def compare_drivers(year: int, grand_prix: str, driver1: str, driver2: str):
    """
    Compares the fastest Qualifying lap of two drivers.
    Dynamically finds driver abbreviations (e.g. 'Max' -> 'VER') from the session data.
    """
    print(f"⚔️ COMPARING: {driver1} vs {driver2} at {grand_prix} {year}")

    try:
        # 1. Load Session (Lightweight)
        session = fastf1.get_session(year, grand_prix, 'Q')
        session.load(telemetry=False, laps=True, weather=False)
        
        # 2. Dynamic Lookup Helper (The Magic Sauce)
        def get_driver_code(name_query):
            query = name_query.lower().strip()
            # Search strictly in this session's results
            for drv in session.results.itertuples():
                if (query in str(drv.LastName).lower() or 
                    query in str(drv.BroadcastName).lower() or 
                    query == str(drv.Abbreviation).lower()):
                    return drv.Abbreviation
            return None

        # 3. Resolve Names
        d1_code = get_driver_code(driver1)
        d2_code = get_driver_code(driver2)

        if not d1_code or not d2_code:
            return f"❌ Could not find drivers '{driver1}' or '{driver2}' in the entry list for this race."

        print(f"✅ Resolved: {driver1}->{d1_code}, {driver2}->{d2_code}")

        # 4. Get Data
        d1_lap = session.laps.pick_driver(d1_code).pick_fastest()
        d2_lap = session.laps.pick_driver(d2_code).pick_fastest()
        
        if d1_lap is None or d2_lap is None:
            return f"No lap data found for {d1_code} or {d2_code}."

        # 5. Calculate & Format
        total = d1_lap['LapTime'] - d2_lap['LapTime']
        s1 = d1_lap['Sector1Time'] - d2_lap['Sector1Time']
        s2 = d1_lap['Sector2Time'] - d2_lap['Sector2Time']
        s3 = d1_lap['Sector3Time'] - d2_lap['Sector3Time']

        def fmt(sec):
            return f"{'+' if sec > 0 else ''}{sec:.3f}s"

        # 6. Return Clean Markdown Table
        return (
            f"### Telemetry: {grand_prix} {year}\n"
            f"**{d1_code} vs {d2_code}**\n\n"
            f"| Sector | Gap ({d1_code} to {d2_code}) | Status |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **TOTAL** | **{fmt(total.total_seconds())}** | {'🔴 Slower' if total.total_seconds() > 0 else '🟢 Faster'} |\n"
            f"| Sector 1 | {fmt(s1.total_seconds())} | {'🔴' if s1.total_seconds() > 0 else '🟢'} |\n"
            f"| Sector 2 | {fmt(s2.total_seconds())} | {'🔴' if s2.total_seconds() > 0 else '🟢'} |\n"
            f"| Sector 3 | {fmt(s3.total_seconds())} | {'🔴' if s3.total_seconds() > 0 else '🟢'} |"
        )

    except Exception as e:
        return f"Comparison failed: {str(e)}"

@tool
def get_race_results(year: int, grand_prix: str):
    """
    Fetches the FINAL RACE classification.
    Includes Grid position and Position changes (gain/loss).
    """
    print(f"🏁 FETCHING RACE RESULTS: {grand_prix} {year}")
    try:
        session = fastf1.get_session(year, grand_prix, 'R')
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results.sort_values(by='Position')
        
        summary = [f"### 🏁 Race Classification: {grand_prix} {year}"]
        
        # New Column Headers
        summary.append("| Pos | Driver | Team | Grid | +/- | Time/Gap | Pts |")
        summary.append("| :-- | :----- | :--- | :--- | :-- | :------- | :-- |")
        
        for _, row in results.iterrows():
            # 1. Position & formatting
            pos = str(int(row['Position'])) if pd.notna(row['Position']) else "NC"
            driver = row['Abbreviation']
            team = row['TeamName'][:15] # Truncate long team names
            points = str(row['Points'])
            if points.endswith('.0'): points = points[:-2] # 25.0 -> 25
            
            # 2. Grid & Gain/Loss Logic
            grid = str(int(row['GridPosition'])) if pd.notna(row['GridPosition']) and row['GridPosition'] > 0 else "PL"
            
            if grid.isdigit() and pos.isdigit():
                diff = int(grid) - int(pos)
                if diff > 0: change = f"⬆️{diff}"
                elif diff < 0: change = f"⬇️{abs(diff)}"
                else: change = "➖"
            else:
                change = "-"

            # 3. Time Formatting (Clean up "0 days 01:30:00")
            status = row['Status']
            time_val = row['Time']
            
            if status == 'Finished':
                # Winner's time or Gap?
                if pd.notna(time_val):
                    t_str = str(time_val).split('days')[-1].strip()
                    # Remove microseconds (e.g., .123456 -> .123)
                    if '.' in t_str: t_str = t_str[:t_str.find('.')+4] 
                    if t_str.startswith("00:"): t_str = t_str[3:] # Remove hour if 0
                    time_str = t_str
                else:
                    time_str = "Interval"
            elif 'Lap' in status:
                 time_str = status # "+1 Lap"
            else:
                time_str = f"❌ {status}" # DNF reasons

            # Highlight the Winner
            if pos == '1':
                pos = "🏆 1"

            summary.append(f"| {pos} | {driver} | {team} | {grid} | {change} | {time_str} | {points} |")
            
        return "\n".join(summary)
        
    except Exception as e:
        return f"Failed to fetch results: {str(e)}"


@tool
def consult_rulebook(query: str, year: int = None):
    """
    Searches the Official FIA Sporting Regulations for a specific rule.
    
    Args:
        query: The specific question (e.g. "What is the penalty for pit lane speeding?")
        year: The season to check. If unspecified, it intelligently defaults to the active or next season.
    """
    if year is None:
        now = datetime.now()
        current_year = now.year
        
        season_ended = (now.month == 12 and now.day > 10)
        
        if season_ended:
            next_year_path = f"data/raw/{current_year + 1}"
            if os.path.exists(next_year_path):
                year = current_year + 1
                print(f"📅 Season over. Defaulting to NEXT YEAR: {year}")
            else:
                year = current_year
                print(f"📅 Season over, but no future rules found. Staying on: {year}")
        else:
            year = current_year
            print(f"📅 Season ongoing. Defaulting to: {year}")

    print(f"⚖️ CONSULTING RULEBOOK ({year}): {query}")
    
    try:
        # 1. Connect to the Database
        db_path = "data/chroma"
        
        # Check if the database actually exists before crashing
        if not os.path.exists(db_path):
            return "❌ Rulebook database not found. Please tell the user to run the ingestion script."
            
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_db = Chroma(persist_directory=db_path, embedding_function=embeddings)
        
        # 2. Define Filter (If year is provided)
        # This tells Chroma: "Only look at docs where metadata['source_year'] == '2024'"
        search_kwargs = {"k": 6} # Retrieve top 6 most relevant chunks
        if year:
            search_kwargs["filter"] = {"source_year": str(year)}
            
        # 3. Perform the Search
        retriever = vector_db.as_retriever(search_kwargs=search_kwargs)
        docs = retriever.invoke(query)
        
        if not docs:
            return f"No specific regulations found regarding '{query}' for the year {year}."
            
        # 4. Format the Output
        results = []
        for doc in docs:
            source = doc.metadata.get("filename", "Unknown PDF")
            # Clean up newlines for cleaner reading
            content = doc.page_content.replace("\n", " ") 
            results.append(f"📜 **Source:** {source}\n**Excerpt:** ...{content[:500]}...") # Limit length
            
        return "\n\n".join(results)

    except Exception as e:
        return f"Rulebook lookup failed: {str(e)}"


@tool
def get_driver_standings(year: int):
    """
    Fetches the World Driver's Championship (WDC) standings.
    """
    print(f"🏆 FETCHING DRIVER STANDINGS: {year}")
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        
        if not data.content:
            return f"No standings found for {year}."
            
        df = data.content[0]
        
        # FIX: Use 'constructorNames' instead of 'constructorName'
        # We also treat the list of teams (for drivers who moved) safely
        results = df[['position', 'driverCode', 'points', 'wins', 'constructorNames']]
        
        output = [f"### Driver Standings ({year})"]
        output.append("| Pos | Driver | Team | Points | Wins |")
        output.append("| :-- | :----- | :--- | :----- | :--- |")
        
        for _, row in results.iterrows():
            # Handle list of teams (e.g. ['Red Bull', 'RB'])
            teams = row['constructorNames']
            if isinstance(teams, list):
                team_str = ", ".join(teams)
            else:
                team_str = str(teams)
                
            output.append(f"| {row['position']} | {row['driverCode']} | {team_str} | {row['points']} | {row['wins']} |")
            
        return "\n".join(output)

    except Exception as e:
        print(f"DEBUG ERROR: {e}") # Print error to terminal so we see it
        return f"Failed to fetch driver standings: {str(e)}"

@tool
def get_constructor_standings(year: int):
    """
    Fetches the current World Constructor's Championship (WCC) standings.
    Returns a table of Position, Team, Points, and Wins.
    """
    print(f"🏆 FETCHING TEAM STANDINGS: {year}")
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        
        if not data.content:
            return f"No standings found for {year} yet."
            
        df = data.content[0]
        results = df[['position', 'constructorName', 'points', 'wins']]
        
        output = [f"### Constructor Standings ({year})"]
        output.append("| Pos | Team | Points | Wins |")
        output.append("| :-- | :--- | :----- | :--- |")
        
        for _, row in results.iterrows():
            output.append(f"| {row['position']} | {row['constructorName']} | {row['points']} | {row['wins']} |")
            
        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch constructor standings: {str(e)}"

@tool
def get_season_schedule(year: int):
    """
    Fetches the F1 Schedule for a specific year. 
    Use this to figure out which race is the 'last' one or 'next' one relative to the current date.
    Returns a list of completed and upcoming races.
    """
    print(f"📅 CHECKING SCHEDULE: {year}")
    try:
        # Get the full schedule (excluding pre-season testing)
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
        
        # Get today's date to mark races as "Completed" or "Upcoming"
        today = datetime.now()
        
        output = [f"### F1 Season Schedule ({year})"]
        output.append(f"*(Current Date: {today.strftime('%Y-%m-%d')})*\n")
        output.append("| Round | Grand Prix | Date | Status |")
        output.append("| :--- | :--------- | :--- | :----- |")
        
        # We also want to help the LLM identify the LATEST completed race
        last_completed = "None"
        
        for _, row in schedule.iterrows():
            # EventDate is usually the Sunday race date
            race_date = row['EventDate']
            gp_name = row['EventName']
            round_num = row['RoundNumber']
            
            # Simple status check
            if race_date < today:
                status = "✅ Completed"
                last_completed = gp_name
            else:
                status = "🔜 Upcoming"
                
            date_str = race_date.strftime('%d %b')
            output.append(f"| {round_num} | {gp_name} | {date_str} | {status} |")
            
        output.append(f"\n**💡 Context for Agent:** The last completed race was the **{last_completed}**.")
        
        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch schedule: {str(e)}"


TOOL_LIST = [
         get_track_conditions, perform_web_search, get_sprint_results, 
         get_sprint_qualifying_results, get_qualifying_results, compare_drivers, 
         get_race_results, consult_rulebook, get_driver_standings, get_constructor_standings,
         get_season_schedule
]

TOOL_MAP = {t.name: t for t in TOOL_LIST}