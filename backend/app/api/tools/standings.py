"""Championship standings and the season calendar."""

from __future__ import annotations

from datetime import UTC, datetime

import fastf1
from langchain_core.tools import tool
import pandas as pd
import structlog

from app.api.tools.standings_facts import freshness_line, title_line
from app.data.current_standings import current_standings
from app.services.race_control.table_reach import constructors_reach, drivers_reach

logger = structlog.get_logger()


@tool
def get_driver_standings(year: int) -> str:
    """
    Fetches the World Drivers' Championship (WDC) standings for `year`.

    Returns the round the table runs to and whether it is provisional or
    confirmed, a Markdown table of position, driver code, team, points and
    wins, and where the title stands (decided for whom, or who can still
    catch the leader). Quote those facts as given; do not work them out.
    """
    logger.info("tool.driver_standings", year=year)
    try:
        standings = current_standings(year)
        if not standings.drivers:
            return f"No driver standings found for {year}."
        return "\n".join(
            (
                f"### Driver Standings ({year})",
                freshness_line(standings),
                "",
                "| Pos | Driver | Team | Points | Wins |",
                "| :-- | :----- | :--- | :----- | :--- |",
                *(
                    f"| {row.position} | {row.key} | {row.team} | {row.points:g} | {row.wins} |"
                    for row in standings.drivers
                ),
                "",
                title_line(drivers_reach(standings), "Drivers'"),
            )
        )
    except Exception as e:
        logger.exception("tool.driver_standings.error", error=str(e))
        return f"Failed to fetch driver standings: {e}"


@tool
def get_constructor_standings(year: int) -> str:
    """
    Fetches the World Constructors' Championship (WCC) standings for `year`.

    Returns the round the table runs to and whether it is provisional or
    confirmed, a Markdown table of position, team name, points and wins, and
    where the title stands (decided for whom, or who can still catch the
    leader). Quote those facts as given; do not work them out.
    """
    logger.info("tool.constructor_standings", year=year)
    try:
        standings = current_standings(year)
        if not standings.teams:
            return f"No constructor standings found for {year}."
        return "\n".join(
            (
                f"### Constructor Standings ({year})",
                freshness_line(standings),
                "",
                "| Pos | Team | Points | Wins |",
                "| :-- | :--- | :----- | :--- |",
                *(f"| {row.position} | {row.key} | {row.points:g} | {row.wins} |" for row in standings.teams),
                "",
                title_line(constructors_reach(standings), "Constructors'"),
            )
        )
    except Exception as e:
        logger.exception("tool.constructor_standings.error", error=str(e))
        return f"Failed to fetch constructor standings: {e}"


def _naive_utc(value: object) -> pd.Timestamp:
    """Drop the timezone from an event date so it compares against a naive now.

    FastF1 returns ``EventDate`` as a tz-naive ``datetime64[ns]``. Comparing that
    against a tz-aware ``datetime`` raises, and the raise is swallowed by the
    tool's except clause — every row would be reported as a fetch failure.
    """
    stamp = pd.Timestamp(value)
    return stamp.tz_convert(None) if stamp.tzinfo else stamp


def _weekend_format(event_format: object) -> str:
    """Sprint or Standard, from FastF1's ``EventFormat``.

    FastF1 has spelled the sprint format three ways since 2021 — ``sprint``,
    ``sprint_shootout`` and ``sprint_qualifying`` — so match the prefix.
    """
    return "Sprint" if str(event_format).startswith("sprint") else "Standard"


@tool
def get_season_schedule(year: int) -> str:
    """
    Fetches the full F1 season calendar for `year`.

    Flags each round as a Sprint or Standard weekend, marks it 'Completed' or
    'Upcoming' relative to today's date, and names the last completed race to
    help resolve queries like 'What happened in the last race?'.
    """
    logger.info("tool.season_schedule", year=year)
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
        today = datetime.now(UTC).replace(tzinfo=None)

        output = [f"### F1 Season Schedule ({year})"]
        output.append(f"*(Current Date: {today.strftime('%Y-%m-%d')})*\n")
        output.append("| Round | Grand Prix | Date | Format | Status |")
        output.append("| :--- | :--------- | :--- | :----- | :----- |")

        last_completed = "None"

        for _, row in schedule.iterrows():
            race_date = _naive_utc(row["EventDate"])  # FastF1 provides this as a Timestamp
            gp_name = row["EventName"]
            round_num = row["RoundNumber"]

            if race_date < today:
                status = "✅ Completed"
                last_completed = gp_name
            else:
                status = "🔜 Upcoming"

            weekend = _weekend_format(row["EventFormat"])
            output.append(f"| {round_num} | {gp_name} | {race_date.strftime('%d %b')} | {weekend} | {status} |")

        # Provide explicit context for the LLM to avoid hallucinating race names.
        output.append(f"\n**Context:** The last completed race was the **{last_completed}**.")

        return "\n".join(output)

    except Exception as e:
        return f"Failed to fetch schedule: {e}"
