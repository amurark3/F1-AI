"""Race-classification and driver-comparison tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import tool
import pandas as pd
import structlog

from app.api.errors import tool_error_text
from app.api.tools.provenance import Provenance, Sourced, chip, classification_chips, f1db_chip
from app.api.tools.rounds import resolve_event
from app.api.tools.sessions import NO_TIME, driver_label, points_cell, source_line, time_cell
from app.data.openf1.session_laps import load_session_laps
from app.services.analysis.lap_selection import fastest_valid_lap
from app.services.race_results import build_session_result, official_grid
from app.utils.lap_deltas import LAP_DELTA_COLUMNS, delta_indicator, format_delta, lap_deltas

if TYPE_CHECKING:
    from app.data.openf1.laps import Lap
    from app.data.openf1.sessions import EntryDriver

logger = structlog.get_logger()


def _lap_times(lap: Lap) -> pd.Series:
    """The lap's total and sector times as the Timedelta row :func:`lap_deltas` compares; a missing time is NaT."""
    times = (lap.time, *lap.sectors)
    return pd.Series(dict(zip(LAP_DELTA_COLUMNS, (pd.to_timedelta(time, unit="s") for time in times), strict=True)))


def _find_driver(drivers: dict[int, EntryDriver], query: str) -> EntryDriver | None:
    """The entry whose name contains ``query`` (a surname or part of one) or whose code is it."""
    wanted = query.lower().strip()
    return next(
        (driver for driver in drivers.values() if wanted in driver.name.lower() or wanted == driver.code.lower()),
        None,
    )


@tool
def compare_drivers(year: int, grand_prix: str, driver1: str, driver2: str) -> str | None:
    """Compares two drivers' fastest Qualifying lap, sector by sector.

    Driver names may be partial ('Max' works as well as 'VER').
    """
    # Returns a Markdown table of total gap and per-sector deltas, with green/red
    # indicators relative to driver2. The laps are OpenF1's; a deleted lap is not a candidate.
    logger.info("tool.compare_drivers", driver1=driver1, driver2=driver2, grand_prix=grand_prix, year=year)
    try:
        round_num, event_name = resolve_event(year, grand_prix)
        session = load_session_laps(year, round_num, "Q")
        if session is None:
            return f"No qualifying session found for {grand_prix} {year}."

        first, second = _find_driver(session.drivers, driver1), _find_driver(session.drivers, driver2)
        if first is None or second is None:
            return f"Could not find drivers '{driver1}' or '{driver2}' in the entry list for {grand_prix} {year}."

        d1_code, d2_code = first.code, second.code
        logger.debug("tool.compare_drivers.resolved", d1_code=d1_code, d2_code=d2_code)

        d1_lap = fastest_valid_lap(session.laps_of(first.number))
        d2_lap = fastest_valid_lap(session.laps_of(second.number))
        if d1_lap is None or d2_lap is None:
            return f"No lap data found for {d1_code} or {d2_code}."

        # Positive = d1 is slower than d2. None where a sector time is missing.
        total, s1, s2, s3 = lap_deltas(_lap_times(d1_lap), _lap_times(d2_lap), LAP_DELTA_COLUMNS)

        text = (
            f"### Telemetry: {grand_prix} {year}\n"
            f"**{d1_code} vs {d2_code}**\n\n"
            f"| Sector | Gap ({d1_code} to {d2_code}) | Status |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **TOTAL** | **{format_delta(total)}** | {delta_indicator(total, labelled=True)} |\n"
            f"| Sector 1 | {format_delta(s1)} | {delta_indicator(s1)} |\n"
            f"| Sector 2 | {format_delta(s2)} | {delta_indicator(s2)} |\n"
            f"| Sector 3 | {format_delta(s3)} | {delta_indicator(s3)} |"
        )
        provenance = Provenance(sources=(chip("OpenF1 laps", "qualifying"),), subject=f"{event_name} {year} qualifying")
        return Sourced(text, provenance)

    except Exception as e:
        return f"Comparison failed: {tool_error_text('tool.compare_drivers.failed', e)}"


def _grid_cell(code: str, grid: dict[str, int | None]) -> str:
    """The slot the car started from; "PL" for the pit lane, "-" when no published grid names it."""
    if code not in grid:
        return NO_TIME
    return "PL" if grid[code] is None else str(grid[code])


def _change_cell(grid: str, position: int | None) -> str:
    """Places gained or lost from the slot to the flag; "-" for a car with no place."""
    if not grid.isdigit() or position is None:
        return "-"
    diff = int(grid) - position
    return f"⬆️{diff}" if diff > 0 else (f"⬇️{abs(diff)}" if diff < 0 else "➖")


@tool
def get_race_results(year: int, grand_prix: str) -> str:
    """
    Fetches the FINAL RACE classification for a Grand Prix.

    Returns a table with: finishing position, driver, team (truncated to 15
    chars), starting grid position, position change (+/- arrows), race time
    or gap, and championship points scored.

    A car that did not finish reads DNF (or DNS, DSQ, NC) with its reason in
    place of a position; lapped cars show their gap in laps.
    """
    logger.info("tool.race_results", grand_prix=grand_prix, year=year)
    try:
        round_num, event_name = resolve_event(year, grand_prix)
        race = build_session_result(year, round_num, "race")
        if race is None:
            return f"No race classification is published for {grand_prix} {year} yet."
        grid = official_grid(year, round_num)

        summary = [
            f"### Race Classification: {grand_prix} {year}",
            source_line(race["final"]),
            "",
            "| Pos | Driver | Team | Grid | +/- | Time/Gap | Pts |",
            "| :-- | :----- | :--- | :--- | :-- | :------- | :-- |",
        ]
        for row in race["classification"]:
            start = _grid_cell(row["driver_code"], grid)
            place = row["position"]
            pos = row["status"] if place is None else ("🏆 1" if place == 1 else str(place))
            summary.append(
                f"| {pos} | {driver_label(row['driver_name'], row['driver_code'])} | {(row['team'] or NO_TIME)[:15]} "
                f"| {start} | {_change_cell(start, place)} | {time_cell(row)} | {points_cell(row['points'])} |"
            )
        sources = classification_chips(race["sources"], final=race["final"])
        if grid:
            sources = (*sources, f1db_chip("starting grid"))
        return Sourced("\n".join(summary), Provenance(sources=sources, subject=f"{event_name} {year}"))

    except Exception as e:
        return f"Failed to fetch race results: {tool_error_text('tool.get_race_results.failed', e)}"


@tool
def get_race_anomalies(year: int, round_num: int) -> str:
    """Notable stories from a completed race: biggest position gains/losses
    vs the grid, one-sided teammate battles, and retirements.

    Use for what was surprising or notable, or to add colour to a result.
    """
    logger.info("tool.race_anomalies", year=year, round_num=round_num)
    try:
        from app.services.anomaly import detect_race_anomalies

        result = detect_race_anomalies(year, round_num)
        if not result.get("available"):
            return f"No completed-race data available for {year} Round {round_num}."
        anomalies = result.get("anomalies", [])
        if not anomalies:
            return Sourced(
                f"### {year} Round {round_num}: no major anomalies — a clean, orderly race.",
                Provenance(sources=(f1db_chip(f"R{round_num} result"),), subject=f"{year} round {round_num}"),
            )
        lines = [f"### Notable stories — {year} Round {round_num}", ""]
        lines.extend(f"- {a['detail']}" for a in anomalies)
        return Sourced(
            "\n".join(lines),
            Provenance(sources=(f1db_chip(f"R{round_num} result"),), subject=f"{year} round {round_num}"),
        )
    except Exception as exc:
        logger.warning("tool.race_anomalies.error", error=str(exc))
        return f"Anomaly analysis failed: {tool_error_text('tool.get_race_anomalies.failed', exc)}"
