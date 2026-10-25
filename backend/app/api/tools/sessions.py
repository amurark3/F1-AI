"""Session-classification tools: sprint, sprint qualifying and qualifying."""

from __future__ import annotations

import fastf1
from langchain_core.tools import tool
import pandas as pd
import structlog

from app.api.tools.formatting import _fmt_driver, _fmt_points, _fmt_timedelta

logger = structlog.get_logger()


def _header(*value_labels: str) -> list[str]:
    """Column headings and the alignment row for one classification table."""
    alignments = (f":{'-' * (len(label) - 1)}" for label in value_labels)
    return [
        f"| Pos | Driver | Team | {' | '.join(value_labels)} |",
        f"| :-- | :----- | :--- | {' | '.join(alignments)} |",
    ]


def _row(position: object, row: pd.Series, *values: str) -> str:
    """One classification line: who the driver is and the team they ran for here.

    The model's memory of the grid predates the current season; given only a
    driver code it filled in the rest itself — "Kimi Antonelli (Alfa Romeo)".
    """
    return f"| {position} | {_fmt_driver(row)} | {row['TeamName']} | {' | '.join(values)} |"


@tool
def get_sprint_results(year: int, grand_prix: str) -> str:
    """
    Fetches the SATURDAY SPRINT RACE results (the short 100 km race) of ONE
    Grand Prix — for 'Sprint', 'Sprint Race' or 'Saturday Race'. Do NOT use
    get_race_results for a sprint. For sprints across several weekends, use
    one query_f1_database query instead of calling this per weekend.

    Returns a Markdown table of finishing positions, drivers, teams, times /
    DNF reasons, and the sprint points each scored.
    """
    logger.info("tool.sprint_results", grand_prix=grand_prix, year=year)
    try:
        session = fastf1.get_session(year, grand_prix, "S")
        # telemetry and weather data are not needed for a results table.
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results.sort_values(by="Position")

        summary = [f"### Sprint Race Results: {grand_prix} {year}", *_header("Time/Status", "Pts")]

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

            summary.append(_row(pos, row, time_str, _fmt_points(row["Points"])))

        return "\n".join(summary)

    except Exception as e:
        return f"Could not fetch Sprint results: {e}"


@tool
def get_sprint_qualifying_results(year: int, grand_prix: str) -> str:
    """Fetches SPRINT QUALIFYING (Shootout) results, split SQ1/SQ2/SQ3.

    Use for 'Sprint Qualifying', 'Shootout', 'SQ' or 'Sprint Quali' — NOT
    get_qualifying_results.
    """
    # FastF1 labels the columns Q1/Q2/Q3 even for shootout data, and laps=True
    # is required because Ergast often lacks SQ split times.
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
            output.extend(_header("SQ1 Time"))
            for i, (_, row) in enumerate(sq1_df.iterrows(), 1):
                if pd.notna(row["Q1"]):
                    output.append(_row(i, row, _fmt_timedelta(row["Q1"])))
            output.append("\n---\n")

        # --- SQ2 ---
        if "Q2" in results.columns and results["Q2"].notna().any():
            sq2_df = results[results["Q2"].notna()].sort_values(by="Q2")
            if not sq2_df.empty:
                output.append("### SQ2 Results")
                output.extend(_header("SQ2 Time"))
                for i, (_, row) in enumerate(sq2_df.iterrows(), 1):
                    output.append(_row(i, row, _fmt_timedelta(row["Q2"])))
                output.append("\n---\n")

        # --- SQ3 ---
        if "Q3" in results.columns and results["Q3"].notna().any():
            sq3_df = results[results["Q3"].notna()].sort_values(by="Q3")
            if not sq3_df.empty:
                output.append("### SQ3 Results (Sprint Pole Position)")
                output.extend(_header("SQ3 Time"))
                for i, (_, row) in enumerate(sq3_df.iterrows(), 1):
                    output.append(_row(i, row, _fmt_timedelta(row["Q3"])))

        # Fallback: if the split-column data is absent, show a simple ordered list.
        if not output:
            output.append(f"### Sprint Qualifying Results ({grand_prix} {year})")
            output.append("*(Detailed SQ1/SQ2/SQ3 split data currently unavailable)*\n")
            output.extend(_header("Time"))
            for _, row in results.sort_values(by="Position").iterrows():
                t = _fmt_timedelta(row["Time"]) if pd.notna(row["Time"]) else "-"
                output.append(_row(row["Position"], row, t))

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
        output.extend(_header("Q1 Time"))
        for i, (_, row) in enumerate(q1_df.iterrows(), 1):
            output.append(_row(i, row, _fmt_timedelta(row["Q1"])))
        output.append("\n---\n")

        # --- Q2 --- (drivers who advanced beyond Q1)
        q2_df = results[results["Q2"].notna()].sort_values(by="Q2")
        if not q2_df.empty:
            output.append("### Q2 Results")
            output.extend(_header("Q2 Time"))
            for i, (_, row) in enumerate(q2_df.iterrows(), 1):
                output.append(_row(i, row, _fmt_timedelta(row["Q2"])))
            output.append("\n---\n")

        # --- Q3 --- (top 10 pole-position shootout)
        q3_df = results[results["Q3"].notna()].sort_values(by="Q3")
        if not q3_df.empty:
            output.append("### Q3 Results (Pole Position)")
            output.extend(_header("Q3 Time"))
            for i, (_, row) in enumerate(q3_df.iterrows(), 1):
                output.append(_row(i, row, _fmt_timedelta(row["Q3"])))

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch qualifying results: {e}"
