"""Championship standings and the season calendar."""

from __future__ import annotations

from datetime import datetime, timezone

import fastf1
from fastf1.ergast import Ergast
from langchain_core.tools import tool
import structlog

from app.data.f1db_standings import constructor_standings_detailed, driver_standings_detailed

logger = structlog.get_logger()


@tool
def get_driver_standings(year: int) -> str:
    """
    Fetches the World Drivers' Championship (WDC) standings for `year`.

    Returns a Markdown table of position, driver code, team(s), points, wins.
    Drivers who competed for multiple teams are shown with all teams listed.
    """
    logger.info("tool.driver_standings", year=year)
    try:
        # f1db first — no rate limits and carries the current season.
        detailed = driver_standings_detailed(year)
        if detailed:
            output = [f"### Driver Standings ({year})"]
            output.append("| Pos | Driver | Team | Points | Wins |")
            output.append("| :-- | :----- | :--- | :----- | :--- |")
            output.extend(
                f"| {row['position']} | {row['code']} | {row['team']} | {row['points']:g} | {row['wins']} |"
                for row in detailed
            )
            return "\n".join(output)

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
            output.append(f"| {row['position']} | {row['driverCode']} | {team_str} | {row['points']} | {row['wins']} |")

        return "\n".join(output)

    except Exception as e:
        logger.exception("tool.driver_standings.error", error=str(e))
        return f"Failed to fetch driver standings: {e}"


@tool
def get_constructor_standings(year: int) -> str:
    """
    Fetches the World Constructors' Championship (WCC) standings for `year`.

    Returns a Markdown table of position, team name, points, and wins.
    """
    logger.info("tool.constructor_standings", year=year)
    try:
        # f1db first — no rate limits and carries the current season.
        detailed = constructor_standings_detailed(year)
        if detailed:
            output = [f"### Constructor Standings ({year})"]
            output.append("| Pos | Team | Points | Wins |")
            output.append("| :-- | :--- | :----- | :--- |")
            output.extend(
                f"| {row['position']} | {row['team']} | {row['points']:g} | {row['wins']} |" for row in detailed
            )
            return "\n".join(output)

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
            output.append(f"| {row['position']} | {row['constructorName']} | {row['points']} | {row['wins']} |")

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch constructor standings: {e}"


@tool
def get_season_schedule(year: int) -> str:
    """
    Fetches the full F1 season calendar for `year`.

    Marks each race as 'Completed' or 'Upcoming' relative to today's date,
    and appends a summary of the last completed race to help the LLM resolve
    queries like 'What happened in the last race?'.
    """
    logger.info("tool.season_schedule", year=year)
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
        today = datetime.now(timezone.utc)

        output = [f"### F1 Season Schedule ({year})"]
        output.append(f"*(Current Date: {today.strftime('%Y-%m-%d')})*\n")
        output.append("| Round | Grand Prix | Date | Status |")
        output.append("| :--- | :--------- | :--- | :----- |")

        last_completed = "None"

        for _, row in schedule.iterrows():
            race_date = row["EventDate"]  # FastF1 provides this as a Timestamp
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
