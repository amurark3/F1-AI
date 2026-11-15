"""Race classification loading and post-race debrief generation.

The classification is :func:`app.services.race_results.build_session_result`'s:
f1db's, or OpenF1's until f1db holds the race. No FastF1 request is made. A car
that did not finish has no ``position``: its ``status`` reads DNF (or DNS, DSQ,
NC) with the reason f1db gives, never a place.

Drivers and teams are printed under f1db's names ("Kimi Antonelli", "Racing
Bulls"). Every sentence here is built from those rows, so it names drivers
and teams the same way. See :mod:`app.data.canonical_names`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from app.data.f1db_calendar import season_schedule
from app.services.race_control_common import safe_float
from app.services.race_results import build_session_result, official_grid


@dataclass(frozen=True)
class DebriefSections:
    """The derived views of a classification that the race control notes read.

    All four are computed from the same results list, so they are built once and
    passed together rather than threaded through as parallel arguments.
    """

    podium: list[dict]
    movers: list[dict]
    constructor_impact: list[dict]
    reliability: list[dict]


def build_race_debrief(year: int, round_num: int) -> dict:
    detail = load_race_classification(year, round_num)
    podium = detail.get("podium") or []
    results = detail.get("race_results") or []
    winner = podium[0] if podium else None
    movers = sorted(
        [row for row in results if row.get("grid") and row.get("position")],
        key=lambda row: row["grid"] - row["position"],
        reverse=True,
    )[:3]
    constructor_impact = build_constructor_impact(results)
    reliability = [row for row in results if row.get("status") and row["status"] != "Finished"]

    return {
        "year": year,
        "round": round_num,
        "race": detail.get("name", f"Round {round_num}"),
        "location": detail.get("location", ""),
        "podium": podium,
        "headline": (
            build_debrief_headline(detail, winner, results) if winner else "Race classification is not available yet."
        ),
        "strategy_winners": movers,
        "takeaways": build_debrief_takeaways(results, podium),
        "podium_cause": build_podium_cause(podium),
        "constructor_impact": constructor_impact,
        "reliability_watch": reliability[:5],
        "classification": results[:10],
        "race_control_notes": build_race_control_notes(
            results,
            DebriefSections(
                podium=podium,
                movers=movers,
                constructor_impact=constructor_impact,
                reliability=reliability,
            ),
        ),
        "final": detail.get("final", False),
        "sources": detail.get("sources", []),
        "insight_source": "Derived from race classification, grid positions, finishing status, and points.",
        "incidents": [],
    }


def build_debrief_headline(detail: dict, winner: dict | None, _results: list[dict]) -> str:
    if not winner:
        return "Race classification is not available yet."

    start = winner.get("grid")
    finish = winner.get("position")
    if start and finish:
        if start == finish:
            return f"{winner['full_name']} converted pole or track position into the race win at {detail.get('name', 'the Grand Prix')}."
        if start > finish:
            gained = start - finish
            return f"{winner['full_name']} won from P{start}, gaining {gained} place{'s' if gained != 1 else ''} against the starting grid."

    points = winner.get("points")
    if points:
        return f"{winner['full_name']} led the final classification and banked {points:g} points for {winner.get('team', 'the team')}."
    return f"{winner['full_name']} topped the final classification."


def build_debrief_takeaways(results: list[dict], podium: list[dict]) -> list[str]:
    if not results:
        return []

    takeaways: list[str] = []
    rows_with_grid = [row for row in results if row.get("grid") and row.get("position")]
    movers = sorted(rows_with_grid, key=lambda row: row["grid"] - row["position"], reverse=True)
    losses = sorted(rows_with_grid, key=lambda row: row["grid"] - row["position"])

    if podium:
        podium_teams = defaultdict(int)
        for row in podium:
            podium_teams[row.get("team", "Unknown")] += 1
        top_team, count = max(podium_teams.items(), key=lambda item: item[1])
        takeaways.append(
            f"{top_team} placed {count} car{'s' if count != 1 else ''} on the podium, shaping the main points swing."
        )

    if movers:
        best = movers[0]
        gain = best["grid"] - best["position"]
        if gain > 0:
            takeaways.append(
                f"{best['full_name'] or best['driver']} gained {gain} position{'s' if gain != 1 else ''} from the grid, the clearest strategy or execution gain."
            )

    if losses:
        worst = losses[0]
        loss = worst["position"] - worst["grid"]
        if loss > 0:
            takeaways.append(
                f"{worst['full_name'] or worst['driver']} lost {loss} position{'s' if loss != 1 else ''} versus the grid, flagging a compromised race branch."
            )

    team_points: dict[str, float] = defaultdict(float)
    for row in results:
        team_points[row.get("team", "Unknown")] += safe_float(row.get("points", 0))
    if team_points:
        team, points = max(team_points.items(), key=lambda item: item[1])
        if points > 0:
            takeaways.append(f"{team} scored the strongest constructor haul with {points:g} points.")

    non_standard_statuses = [row for row in results if row.get("status") and row["status"] != "Finished"]
    if non_standard_statuses:
        takeaways.append(
            f"{len(non_standard_statuses)} car{'s' if len(non_standard_statuses) != 1 else ''} had non-standard finish statuses, so reliability and incident exposure mattered."
        )

    return takeaways[:4]


def build_podium_cause(podium: list[dict]) -> list[dict]:
    rows = []
    for row in podium:
        grid = row.get("grid")
        position = row.get("position")
        delta = grid - position if grid and position else None
        if delta is None:
            call = "Classification result"
        elif delta > 0:
            call = f"Made up {delta} place{'s' if delta != 1 else ''}"
        elif delta < 0:
            call = f"Lost {abs(delta)} place{'s' if delta != -1 else ''} but held podium"
        else:
            call = "Converted starting position"
        rows.append(
            {
                "position": position,
                "driver": row.get("driver"),
                "full_name": row.get("full_name") or row.get("driver"),
                "team": row.get("team"),
                "grid": grid,
                "points": row.get("points", 0),
                "delta": delta,
                "call": call,
            }
        )
    return rows


def build_constructor_impact(results: list[dict]) -> list[dict]:
    team_points: dict[str, float] = defaultdict(float)
    finishers: dict[str, int] = defaultdict(int)
    for row in results:
        team = row.get("team", "Unknown")
        team_points[team] += safe_float(row.get("points", 0))
        if row.get("position"):
            finishers[team] += 1
    return [
        {"team": team, "points": points, "classified_cars": finishers.get(team, 0)}
        for team, points in sorted(team_points.items(), key=lambda item: item[1], reverse=True)
        if points > 0
    ][:6]


def build_race_control_notes(results: list[dict], sections: DebriefSections) -> list[dict]:
    notes = []
    if sections.podium:
        notes.append(
            {
                "label": "Podium shape",
                "detail": ", ".join(f"P{row.get('position')} {row.get('driver')}" for row in sections.podium),
            }
        )
    if sections.movers:
        best = sections.movers[0]
        notes.append(
            {
                "label": "Execution swing",
                "detail": f"{best.get('full_name') or best.get('driver')} gained {best.get('grid') - best.get('position')} places from the grid.",
            }
        )
    if sections.constructor_impact:
        leader = sections.constructor_impact[0]
        notes.append(
            {
                "label": "Constructor haul",
                "detail": f"{leader['team']} led the points take with {leader['points']:g} points.",
            }
        )
    if sections.reliability:
        count = len(sections.reliability)
        notes.append(
            {
                "label": "Reliability / incidents",
                "detail": f"{count} non-standard finish status{'es' if count != 1 else ''} in classification.",
            }
        )
    if not results:
        notes.append(
            {
                "label": "Awaiting classification",
                "detail": "Final race classification has not been published or loaded yet.",
            }
        )
    return notes


def load_race_classification(year: int, round_num: int) -> dict:
    schedule = season_schedule(year)
    event_row = schedule[schedule["RoundNumber"] == round_num]
    if event_row.empty:
        return {"error": f"Round {round_num} not found for {year}", "race_results": [], "podium": []}

    event = event_row.iloc[0]
    result = {
        "round": round_num,
        "name": event["EventName"],
        "location": f"{event['Location']}, {event['Country']}",
        "race_results": [],
        "podium": [],
    }

    race_date = next(
        (
            event[f"Session{i}DateUtc"].to_pydatetime()
            for i in range(1, 6)
            if event.get(f"Session{i}") == "Race" and pd.notna(event.get(f"Session{i}DateUtc"))
        ),
        None,
    )
    if not race_date or datetime.now(UTC).replace(tzinfo=None) <= race_date + pd.Timedelta(hours=3):
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
