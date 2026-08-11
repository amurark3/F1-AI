"""Session-classification tools: sprint, sprint qualifying and qualifying."""

from __future__ import annotations

import fastf1
from langchain_core.tools import tool
import pandas as pd
import structlog

from app.api.tools.formatting import _fmt_timedelta

logger = structlog.get_logger()


@tool
def get_sprint_results(year: int, grand_prix: str) -> str:
    """
    Fetches the SATURDAY SPRINT RACE results (the short 100 km race).

    ALWAYS use this tool if the user mentions 'Sprint', 'Sprint Race', or
    'Saturday Race'.  Do NOT use get_race_results for sprint weekends.

    Returns a Markdown table of finishing positions, driver abbreviations,
    and times / DNF reasons.
    """
    logger.info("tool.sprint_results", grand_prix=grand_prix, year=year)
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
def get_sprint_qualifying_results(year: int, grand_prix: str) -> str:
    """
    Fetches SPRINT QUALIFYING (Shootout) results broken into SQ1 / SQ2 / SQ3.

    ALWAYS use this tool if the user mentions 'Sprint Qualifying', 'Shootout',
    'SQ', or 'Sprint Quali'.  Do NOT use get_qualifying_results for this.

    Note: FastF1 uses column names Q1/Q2/Q3 even for sprint shootout data;
    laps=True is required because Ergast often lacks SQ split times.
    """
    logger.info("tool.sprint_qualifying", grand_prix=grand_prix, year=year)
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
        return f"Could not fetch Sprint Qualifying. Note: {grand_prix} {year} might not be a Sprint weekend. Error: {e}"


@tool
def get_qualifying_results(year: int, grand_prix: str) -> str:
    """
    Fetches the MAIN QUALIFYING results (determines the Sunday race grid).

    Returns separate tables for Q1, Q2, and Q3 with each driver's best
    lap time for that session segment.

    IMPORTANT: Do NOT use this for Sprint Qualifying / Shootout sessions.
    Use get_sprint_qualifying_results for those.
    """
    logger.info("tool.qualifying", grand_prix=grand_prix, year=year)
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
