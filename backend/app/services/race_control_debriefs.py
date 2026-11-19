"""Race classification loading and the post-race debrief's summary.

The classification is :func:`app.services.race_results.build_session_result`'s:
the FIA's final classification or f1db's, or OpenF1's until either holds the
race. No FastF1 request is made. A car that did not finish has no ``position``:
its ``status`` reads DNF (or DNS, DSQ, NC) with the reason f1db gives, never a
place.

Drivers and teams are printed under f1db's names ("Kimi Antonelli", "Racing
Bulls"). See :mod:`app.data.canonical_names`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from app.data.f1db_calendar import season_schedule
from app.services.race_control.progression import build_standings_progression
from app.services.race_control_common import safe_float
from app.services.race_grid import build_starting_grid
from app.services.race_results import build_session_result, official_grid


def _race_event(year: int, round_num: int) -> dict | None:
    """The round's name, location and whether its race is over (start + 3 h); None for an unknown round."""
    schedule = season_schedule(year)
    event_row = schedule[schedule["RoundNumber"] == round_num]
    if event_row.empty:
        return None

    event = event_row.iloc[0]
    race_date = next(
        (
            event[f"Session{i}DateUtc"].to_pydatetime()
            for i in range(1, 6)
            if event.get(f"Session{i}") == "Race" and pd.notna(event.get(f"Session{i}DateUtc"))
        ),
        None,
    )
    return {
        "name": event["EventName"],
        "location": f"{event['Location']}, {event['Country']}",
        "finished": bool(race_date) and datetime.now(UTC).replace(tzinfo=None) > race_date + pd.Timedelta(hours=3),
    }


def _titles(year: int, round_num: int) -> list[dict]:
    """The championships clinched at this round, drivers' then constructors', with the points that decided them."""
    progression = build_standings_progression(year)
    rounds = [row["round"] for row in progression["rounds"]]
    if round_num not in rounds:
        return []
    index = rounds.index(round_num)
    titles = []
    for table in ("drivers", "constructors"):
        championship = progression[table]
        clinched = championship["clinched"]
        if clinched is None or clinched["round"] != round_num:
            continue
        standing = sorted(
            (row for row in championship["entrants"] if row["points"][index] is not None),
            key=lambda row: -row["points"][index],
        )
        champion, runner_up = standing[0], (standing[1] if len(standing) > 1 else None)
        points = champion["points"][index]
        titles.append(
            {
                "table": table,
                "name": champion["name"],
                "team": champion["team"],
                "points": points,
                "lead": None if runner_up is None else points - runner_up["points"][index],
                "runner_up": None if runner_up is None else runner_up["name"],
                "races_left": clinched["races_left"],
                "provisional": progression["rounds"][index]["provisional"],
            }
        )
    return titles


def _grid_slots(year: int, round_num: int) -> tuple[dict[str, dict], dict]:
    """Each car's slot on the official grid, and the grid's status; a provisional or stand-in grid is never read."""
    grid = build_starting_grid(year, round_num)
    official = grid["available"] and not grid["provisional"]
    slots = {row["driver_code"]: row for row in grid["grid"]} if official else {}
    return slots, {"available": official, "fia_document": grid["fia_document"] if official else None}


def build_race_debrief(year: int, round_num: int) -> dict:
    """The debrief's summary: the classification with each car's start, the grid's status and the titles clinched."""
    event = _race_event(year, round_num)
    race = build_session_result(year, round_num, "race") if event and event["finished"] else None
    reason = None
    if event is None:
        reason = f"Round {round_num} not found for {year}"
    elif race is None:
        reason = "The race hasn't been classified yet."
    summary = {
        "year": year,
        "round": round_num,
        "race": event["name"] if event else f"Round {round_num}",
        "location": event["location"] if event else "",
        "available": race is not None,
        "reason": reason,
        "final": False,
        "sources": [],
        "classification": [],
        "grid": {"available": False, "fia_document": None},
        "titles": [],
    }
    if race is None:
        return summary
    slots, grid = _grid_slots(year, round_num)
    return {
        **summary,
        "final": race["final"],
        "sources": race["sources"],
        "classification": [
            {
                **row,
                "grid": slots[row["driver_code"]]["position"] if row["driver_code"] in slots else None,
                "pit_lane": row["driver_code"] in slots and slots[row["driver_code"]]["pit_lane"],
            }
            for row in race["classification"]
        ],
        "grid": grid,
        "titles": _titles(year, round_num),
    }


def load_race_classification(year: int, round_num: int) -> dict:
    event = _race_event(year, round_num)
    if event is None:
        return {"error": f"Round {round_num} not found for {year}", "race_results": [], "podium": []}

    result = {
        "round": round_num,
        "name": event["name"],
        "location": event["location"],
        "race_results": [],
        "podium": [],
    }
    if not event["finished"]:
        return result

    race = build_session_result(year, round_num, "race")
    if race is None:
        return result
    grid = official_grid(year, round_num)
    rows = [_classification_row(row, grid) for row in race["classification"]]
    result["race_results"] = rows
    result["sources"] = race["sources"]
    result["final"] = race["final"]
    result["podium"] = sorted(
        [row for row in rows if row["position"] and row["position"] <= 3], key=lambda row: row["position"]
    )
    return result


def _status_text(row: dict) -> str:
    """ "Finished", or how the race ended: "DNF (Engine)", "DSQ", "DNS", "NC"."""
    if row["status"] == "Finished":
        return "Finished"
    return f"{row['status']} ({row['reason']})" if row["reason"] else row["status"]


def _classification_row(row: dict, grid: dict[str, int | None]) -> dict:
    """One classification row in the debrief's shape; a pit-lane start or an unlisted car has no grid slot."""
    return {
        "position": row["position"],
        "driver": row["driver_code"],
        "full_name": row["driver_name"],
        "team": row["team"] or "Unknown",
        "grid": grid.get(row["driver_code"]),
        "points": safe_float(row["points"]),
        "status": _status_text(row),
    }
