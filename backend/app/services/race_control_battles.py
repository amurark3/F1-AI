"""Legacy driver comparison helper for the archived Priority Call screen."""

from __future__ import annotations

from app.services.race_control_common import (
    completed_race_count,
    find_driver,
    get_driver_options,
    pluralise,
)


def battle_fact(key: str, label: str, driver1: dict, driver2: dict, value1: str, value2: str) -> dict:
    return {
        "key": key,
        "label": label,
        "values": {
            driver1["code"]: value1,
            driver2["code"]: value2,
        },
    }


def build_driver_battle(year: int, driver1: str, driver2: str) -> dict:
    driver_feed = get_driver_options(year)
    standings = driver_feed["drivers"]
    if not standings:
        return {
            "year": year,
            "status": "data_unavailable",
            "source": driver_feed["source"],
            "drivers": [],
            "metrics": [],
            "summary": "Driver standings are unavailable, so no priority call has been generated.",
            "recommendation": "Reconnect the standings feed or choose a season with completed standings data.",
            "data_limitations": ["No fallback or synthetic driver scores are used on this screen."],
            "error": driver_feed["error"],
        }

    d1 = find_driver(standings, driver1)
    d2 = find_driver(standings, driver2)
    if not d1 or not d2:
        missing = driver1 if not d1 else driver2
        return {
            "year": year,
            "status": "driver_not_found",
            "source": driver_feed["source"],
            "drivers": [driver for driver in (d1, d2) if driver],
            "available_drivers": standings,
            "metrics": [],
            "summary": f"'{missing}' was not found in the {year} driver standings.",
            "recommendation": "Select drivers from the standings-backed list rather than typing an abbreviation.",
            "data_limitations": ["Driver matching accepts codes, full names, and Ergast driver ids."],
            "error": f"Driver '{missing}' not found.",
        }

    if d1["code"] == d2["code"]:
        return {
            "year": year,
            "status": "invalid_selection",
            "source": driver_feed["source"],
            "drivers": [d1],
            "metrics": [],
            "summary": "Choose two different drivers to compare.",
            "recommendation": "Use the driver selectors to build a valid battle profile.",
            "data_limitations": [],
            "error": "Both selected drivers are the same.",
        }

    team_points: dict[str, float] = {}
    for driver in standings:
        team_points[driver["team"]] = team_points.get(driver["team"], 0) + driver["points"]

    def team_share(driver: dict) -> float:
        total = team_points.get(driver["team"], 0)
        return (driver["points"] / total) * 100 if total else 0

    completed_races = completed_race_count(year)
    d1_rate = d1["points"] / completed_races if completed_races else None
    d2_rate = d2["points"] / completed_races if completed_races else None
    points_gap = abs(d1["points"] - d2["points"])
    position_gap = abs(d1["position"] - d2["position"])
    wins_gap = abs(d1["wins"] - d2["wins"])
    same_team = d1["team"] == d2["team"]

    raw_leader, raw_chaser = (
        (d1, d2)
        if (d1["points"], d1["wins"], -d1["position"]) >= (d2["points"], d2["wins"], -d2["position"])
        else (d2, d1)
    )
    close_call = points_gap < 10 and position_gap <= 1 and wins_gap <= 1
    priority_confidence = "Low" if close_call else "High" if points_gap >= 50 or position_gap >= 5 else "Medium"

    facts = [
        battle_fact("wdc_position", "Championship position", d1, d2, f"P{d1['position']}", f"P{d2['position']}"),
        battle_fact("points", "Championship points", d1, d2, f"{d1['points']:g}", f"{d2['points']:g}"),
        battle_fact("wins", "Race wins", d1, d2, pluralise(d1["wins"], "win"), pluralise(d2["wins"], "win")),
        battle_fact("team_share", "Share of team points", d1, d2, f"{team_share(d1):.1f}%", f"{team_share(d2):.1f}%"),
    ]
    if completed_races and d1_rate is not None and d2_rate is not None:
        facts.append(
            battle_fact(
                "points_per_race",
                "Points per completed GP",
                d1,
                d2,
                f"{d1_rate:.1f}",
                f"{d2_rate:.1f}",
            )
        )

    decision_factors = [
        f"Points gap: {points_gap:g} point{'s' if points_gap != 1 else ''}.",
        f"Championship order gap: {position_gap} position{'s' if position_gap != 1 else ''}.",
        f"Wins gap: {wins_gap} race win{'s' if wins_gap != 1 else ''}.",
    ]
    if same_team:
        decision_factors.append("Same team comparison: this is useful for first pit call, upgrade priority, and avoiding a strategy split that hurts constructor points.")
    else:
        decision_factors.append("Rival comparison: this is useful for deciding which car to cover when pit windows overlap.")
    if completed_races:
        decision_factors.append(f"Scoring rate uses {completed_races} completed Grand Prix event{'s' if completed_races != 1 else ''}.")

    if close_call:
        summary = (
            f"{d1['name']} and {d2['name']} are close enough that standings alone should not decide priority."
        )
        recommendation = (
            "Do not assign priority from standings alone. Wait for qualifying, tyre degradation, and live track-position data before splitting strategy."
        )
    else:
        summary = f"{raw_leader['name']} has the stronger standings case: P{raw_leader['position']} with {raw_leader['points']:g} points versus P{raw_chaser['position']} with {raw_chaser['points']:g}."
        if same_team:
            recommendation = (
                f"Give {raw_leader['name']} first call only if both cars converge on the same pit window. Keep "
                f"{raw_chaser['name']} available for an offset that protects constructor points."
            )
        else:
            recommendation = (
                f"Treat {raw_leader['name']} as the higher-priority rival in scenario planning. Cover undercut windows when "
                f"{raw_leader['team']} is inside pit-loss range, but override this with live tyre and track-position evidence."
            )

    return {
        "year": year,
        "status": "ok",
        "source": driver_feed["source"],
        "drivers": [d1, d2],
        "summary": summary,
        "metrics": [],
        "facts": facts,
        "decision_factors": decision_factors,
        "priority": {
            "code": None if close_call else raw_leader["code"],
            "driver": "No automatic priority" if close_call else raw_leader["name"],
            "team": None if close_call else raw_leader["team"],
            "confidence": priority_confidence,
            "basis": "current championship standings",
        },
        "recommendation": recommendation,
        "comparison": {
            "points_gap": round(points_gap, 1),
            "position_gap": position_gap,
            "wins_gap": wins_gap,
            "context": "same-team" if same_team else "rival-comparison",
        },
        "data_limitations": [
            "Uses real championship standings only.",
            "Does not claim live race pace, sector strength, tyre degradation, or telemetry until session data is connected.",
        ],
        "error": None,
    }
