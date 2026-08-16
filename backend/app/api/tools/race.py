"""Race-classification and driver-comparison tools."""

from __future__ import annotations

import fastf1
from langchain_core.tools import tool
import pandas as pd
import structlog

from app.utils.lap_deltas import LAP_DELTA_COLUMNS, delta_indicator, format_delta, lap_deltas

logger = structlog.get_logger()


@tool
def compare_drivers(year: int, grand_prix: str, driver1: str, driver2: str) -> str | None:
    """
    Compares the fastest Qualifying lap of two drivers, sector by sector.

    Accepts partial name matches so the model can pass 'Max' instead of 'VER'.
    The lookup searches LastName, BroadcastName, and Abbreviation fields.

    Returns a Markdown table showing total gap and per-sector deltas,
    with green/red indicators for faster/slower relative to driver2.
    """
    logger.info("tool.compare_drivers", driver1=driver1, driver2=driver2, grand_prix=grand_prix, year=year)
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
            return f"Could not find drivers '{driver1}' or '{driver2}' in the entry list for {grand_prix} {year}."

        logger.debug("tool.compare_drivers.resolved", d1_code=d1_code, d2_code=d2_code)

        d1_lap = session.laps.pick_drivers(d1_code).pick_fastest()
        d2_lap = session.laps.pick_drivers(d2_code).pick_fastest()

        if d1_lap is None or d2_lap is None:
            return f"No lap data found for {d1_code} or {d2_code}."

        # Positive = d1 is slower than d2. None where a sector time is missing.
        total, s1, s2, s3 = lap_deltas(d1_lap, d2_lap, LAP_DELTA_COLUMNS)

        return (
            f"### Telemetry: {grand_prix} {year}\n"
            f"**{d1_code} vs {d2_code}**\n\n"
            f"| Sector | Gap ({d1_code} to {d2_code}) | Status |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **TOTAL** | **{format_delta(total)}** | {delta_indicator(total, labelled=True)} |\n"
            f"| Sector 1 | {format_delta(s1)} | {delta_indicator(s1)} |\n"
            f"| Sector 2 | {format_delta(s2)} | {delta_indicator(s2)} |\n"
            f"| Sector 3 | {format_delta(s3)} | {delta_indicator(s3)} |"
        )

    except Exception as e:
        return f"Comparison failed: {e}"


def _format_race_time(status: str, time_val: object) -> str:
    """Race time, lap deficit or retirement reason for the classification table.

    Only the winner carries an absolute time; everyone else classified carries a
    gap, and FastF1 renders both as a timedelta that has to be trimmed.
    """
    if status != "Finished":
        if "Lap" in status:
            return status  # "+1 Lap", "+2 Laps", etc.
        return f"❌ {status}"  # DNF / accident / mechanical

    if not pd.notna(time_val):
        return "Interval"

    text = str(time_val).split("days")[-1].strip()
    if "." in text:
        # Trim to 3 decimal places.
        text = text[: text.find(".") + 4]
    return text.removeprefix("00:")


@tool
def get_race_results(year: int, grand_prix: str) -> str:
    """
    Fetches the FINAL RACE classification for a Grand Prix.

    Returns a table with: finishing position, driver, team (truncated to 15
    chars), starting grid position, position change (+/- arrows), race time
    or gap, and championship points scored.

    Handles DNFs, DSQs, and lapped cars via the 'Status' column.
    """
    logger.info("tool.race_results", grand_prix=grand_prix, year=year)
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
            points = points.removesuffix(".0")  # "25.0" → "25"

            # Grid position: "PL" indicates a pit-lane start.
            grid = str(int(row["GridPosition"])) if pd.notna(row["GridPosition"]) and row["GridPosition"] > 0 else "PL"

            # Position change from grid to finish.
            if grid.isdigit() and pos.isdigit():
                diff = int(grid) - int(pos)
                change = f"⬆️{diff}" if diff > 0 else (f"⬇️{abs(diff)}" if diff < 0 else "➖")
            else:
                change = "-"

            # Format race time or gap-to-leader.
            time_str = _format_race_time(row["Status"], row["Time"])

            if pos == "1":
                pos = "🏆 1"

            summary.append(f"| {pos} | {driver} | {team} | {grid} | {change} | {time_str} | {points} |")

        return "\n".join(summary)

    except Exception as e:
        return f"Failed to fetch race results: {e}"


@tool
def get_race_anomalies(year: int, round_num: int) -> str:
    """
    Surfaces the notable stories from a completed race: biggest position
    gains/losses vs the grid, one-sided teammate battles, and retirements.

    Use when the user asks what was surprising, notable, or the standout
    stories of a race — or proactively when discussing a race result, to add
    colour beyond the raw classification.
    """
    logger.info("tool.race_anomalies", year=year, round_num=round_num)
    try:
        from app.services.anomaly import detect_race_anomalies

        result = detect_race_anomalies(year, round_num)
        if not result.get("available"):
            return f"No completed-race data available for {year} Round {round_num}."
        anomalies = result.get("anomalies", [])
        if not anomalies:
            return f"### {year} Round {round_num}: no major anomalies — a clean, orderly race."
        lines = [f"### Notable stories — {year} Round {round_num}", ""]
        lines.extend(f"- {a['detail']}" for a in anomalies)
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("tool.race_anomalies.error", error=str(exc))
        return f"Anomaly analysis failed: {exc}"
