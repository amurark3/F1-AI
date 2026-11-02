"""Constructor, driver standings, and team-intelligence composition.

Whatever the text says a team can still catch, or still be caught by, is
``title_rule.can_still_beat`` over the points still on offer
(``table_reach``): "close the gap", "protect against" and the championship read
appear only while the rule says the rival is in reach. Without a calendar to
count what is left, the text states the gaps and claims nothing about reach.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.data.current_standings import current_standings
from app.services.race_control.table_reach import constructors_reach
from app.services.race_control_common import (
    format_points_value,
    safe_float,
    safe_int,
    team_color,
    team_slug,
)

if TYPE_CHECKING:
    from app.services.race_control.table_reach import TableReach

logger = structlog.get_logger()


def profile_for_team(team_name: str) -> dict:
    slug = team_slug(team_name)
    return {
        "slug": slug,
        "name": team_name,
        "color": team_color(team_name),
        "strengths": [],
        "weaknesses": [],
        "strategy_tendency": "Standing profile unavailable until constructor standings load.",
    }


def _on_offer(points_on_offer: int) -> str:
    if points_on_offer:
        return f"with {format_points_value(points_on_offer)} points still on offer"
    return "with no points left on offer"


def _leader_read(team: str, points: float, reach: TableReach) -> str:
    if reach.decided():
        return (
            f"{team} has clinched the constructors' title with {format_points_value(points)} points: "
            f"no rival can finish ahead {_on_offer(reach.points_on_offer or 0)}."
        )
    return (
        f"{team} leads the constructors' table with {format_points_value(points)} points. "
        "The strategy read is defensive: protect high-value points swings and avoid unnecessary split risk."
    )


def _highest_place(team: str, points: float, reach: TableReach) -> str:
    best = reach.highest_in_reach(team)
    if best is None:
        return "No place ahead is still in reach."
    place, holder = best
    return (
        f"The highest place still in reach is P{place}: {holder.name}, "
        f"{format_points_value(holder.points - points)} points ahead."
    )


def _chaser_read(team: str, position: int, points: float, reach: TableReach) -> str:
    """A team behind the leader: in the title fight, out of it, or unknown without a calendar."""
    off_the_lead = (
        f"{team} is P{position}, {format_points_value(reach.leader_points - points)} points off the constructor lead"
    )
    on_offer = reach.points_on_offer
    if on_offer is None:
        return f"{off_the_lead}. The points still on offer could not be counted, so there is no title read."
    if reach.can_pass(team, reach.rows[0].key):
        return (
            f"{off_the_lead} {_on_offer(on_offer)}. The strategy read is opportunistic: use race scenarios "
            "that can close the championship gap without relying on invented pace data."
        )
    return f"{off_the_lead} {_on_offer(on_offer)}: out of the title fight. {_highest_place(team, points, reach)}"


def _strategy_tendency(team: str, position: int, points: float, reach: TableReach) -> str:
    if position == 1:
        return _leader_read(team, points, reach)
    if reach.leader_points > points:
        return _chaser_read(team, position, points, reach)
    return f"{team} has no constructor points loaded yet. The strategy read stays limited until the standings feed contains scoring data."


def build_team_profile(row: dict, roster: list[dict], reach: TableReach, completed_events: int) -> dict:
    """A team's standing card; ``reach`` is the constructors' table it sits in, with what is left to score."""
    points = safe_float(row.get("points", 0))
    wins = safe_int(row.get("wins", 0))
    position = safe_int(row.get("position", 0))
    gap_to_leader = max(0, reach.leader_points - points)
    events = max(completed_events, 1)
    points_per_event = points / events
    driver_count = len(roster)
    top_driver = max(roster, key=lambda driver: driver.get("points", 0), default=None)
    top_share = (safe_float(top_driver.get("points", 0)) / points * 100) if top_driver and points else 0

    evidence = [
        f"WCC P{position}" if position else "No WCC rank",
        f"{format_points_value(points)} championship pts",
        f"{wins} race win{'s' if wins != 1 else ''}",
        f"{points_per_event:.1f} pts/GP",
    ]
    pressure_points = []
    if gap_to_leader:
        pressure_points.append(f"{format_points_value(gap_to_leader)} pts behind P1")
    else:
        pressure_points.append("Current constructor benchmark")
    if top_driver and points:
        pressure_points.append(f"{top_driver['driver']} has {top_share:.0f}% of team points")
    if driver_count:
        pressure_points.append(f"{driver_count} classified driver{'s' if driver_count != 1 else ''} in standings")

    return {
        "slug": team_slug(row["team"]),
        "name": row["team"],
        "color": team_color(row["team"]),
        "strengths": evidence,
        "weaknesses": pressure_points,
        "strategy_tendency": _strategy_tendency(row["team"], position, points, reach),
        "standing_profile": {
            "WCC position": position,
            "points": points,
            "wins": wins,
            "pts per GP": round(points_per_event, 1),
        },
    }


def points_trend(points: float, completed_events: int) -> list[dict]:
    events = max(completed_events, 1)
    return [
        {"round": race_index, "points": round(points * ((race_index / events) ** 1.08), 1)}
        for race_index in range(1, events + 1)
    ]


# The tables are computed: f1db's last round plus any later round's points.
TEAMS_SOURCE = "computed-standings"


def build_teams(year: int) -> dict:
    """Both championships as of the newest round with published points (``current_standings``)."""
    standings = current_standings(year)
    drivers, constructors = standings.driver_rows(), standings.team_rows()
    # Points per GP divides by the rounds the points cover, not the races the clock says have run.
    completed_events = standings.as_of_round or 0
    reach = constructors_reach(standings)

    teams = []
    for row in constructors:
        roster = [driver for driver in drivers if driver["team"] == row["team"]]
        profile = build_team_profile(row, roster, reach, completed_events)
        teams.append(
            {
                **profile,
                "position": row["position"],
                "points": row["points"],
                "wins": row["wins"],
                "drivers": roster,
                "recent_form": points_trend(row["points"], min(max(completed_events, 1), 5))[-5:],
                "pace_profile": profile["standing_profile"],
            }
        )

    return {
        "year": year,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": TEAMS_SOURCE,
        **standings.meta(),
        "drivers": drivers,
        "teams": teams,
        "error": None if teams else "Constructor standings are unavailable for this season.",
    }


# A constructor within this many points is close enough to act on.
_CLOSE_RIVAL_POINTS = 25

# Share of a team's points coming from one driver before the concentration is
# itself a risk.
_POINTS_CONCENTRATION_RATIO = 0.7


@dataclass(frozen=True)
class IntelContext:
    """A team's standings position, the constructors either side of it, and who can still pass whom."""

    team: str
    position: int
    points: float
    wins: int
    leader: dict
    ahead: dict | None
    behind: dict | None
    gap_ahead: float
    gap_behind: float
    top_driver: dict | None
    roster: list[dict]
    #: The most one team can still score; None without a calendar.
    on_offer: int | None
    #: Whether this team can still pass the one ahead; None when unknown or there is none.
    ahead_in_reach: bool | None
    #: Whether the one behind can still pass this team; None when unknown or there is none.
    behind_in_reach: bool | None
    #: Whether no rival can still finish ahead of the leader; None when unknown.
    decided: bool | None


def _intel_context(match: dict, roster: list[dict], constructors: list[dict], reach: TableReach) -> IntelContext:
    """Locate a team in the constructor table alongside its nearest rivals, and what each can still reach."""
    team = match["team"]
    position = safe_int(match.get("position", 0))
    points = safe_float(match.get("points", 0))
    ahead = constructors[position - 2] if position > 1 and position - 2 < len(constructors) else None
    behind = constructors[position] if position < len(constructors) else None

    return IntelContext(
        team=team,
        position=position,
        points=points,
        wins=safe_int(match.get("wins", 0)),
        leader=constructors[0],
        ahead=ahead,
        behind=behind,
        gap_ahead=safe_float(ahead["points"] - points) if ahead else 0,
        gap_behind=safe_float(points - behind["points"]) if behind else 0,
        top_driver=max(roster, key=lambda driver: driver.get("points", 0), default=None),
        roster=roster,
        on_offer=reach.points_on_offer,
        ahead_in_reach=reach.can_pass(team, ahead["team"]) if ahead else None,
        behind_in_reach=reach.can_pass(behind["team"], team) if behind else None,
        decided=reach.decided(),
    )


def _ahead_line(ahead: dict, context: IntelContext) -> str:
    named = f"{ahead['team']} by {format_points_value(context.gap_ahead)} points"
    if context.ahead_in_reach:
        return f"Next target ahead: {named}."
    if context.ahead_in_reach is None:
        return f"Next ahead: {named}."
    return f"Next ahead: {named}, out of reach {_on_offer(context.on_offer or 0)}."


def _behind_line(behind: dict, context: IntelContext) -> str:
    named = f"{behind['team']} by {format_points_value(context.gap_behind)} points"
    if context.behind_in_reach:
        return f"Nearest pressure behind: {named}."
    if context.behind_in_reach is None:
        return f"Nearest behind: {named}."
    return f"Nearest behind: {named}, who can no longer catch {context.team} {_on_offer(context.on_offer or 0)}."


def _intel_evidence(context: IntelContext) -> list[str]:
    """The standings facts the rest of the intel is reasoned from."""
    leader_gap = max(0, context.leader["points"] - context.points)
    evidence = [
        f"WCC P{context.position} with {format_points_value(context.points)} points.",
        f"{context.wins} constructor win{'s' if context.wins != 1 else ''} in the standings feed.",
        f"Leader gap: {format_points_value(leader_gap)} points to {context.leader['team']}.",
    ]
    if context.top_driver:
        evidence.append(
            f"Top scorer: {context.top_driver['driver']} with {format_points_value(context.top_driver['points'])} points."
        )
    if context.ahead:
        evidence.append(_ahead_line(context.ahead, context))
    if context.behind:
        evidence.append(_behind_line(context.behind, context))
    return evidence


def _intel_threats(context: IntelContext) -> list[str]:
    """What could cost this team places, with an explicit note when nothing does.

    A neighbour counts only while the title rule keeps them in reach.
    """
    threats = []
    if context.ahead and context.ahead_in_reach and context.gap_ahead <= _CLOSE_RIVAL_POINTS:
        threats.append(
            f"{context.ahead['team']} is within {format_points_value(context.gap_ahead)} points ahead; covering them can matter immediately."
        )
    if context.behind and context.behind_in_reach and context.gap_behind <= _CLOSE_RIVAL_POINTS:
        threats.append(
            f"{context.behind['team']} is only {format_points_value(context.gap_behind)} points behind; one race swing can change the order."
        )
    if (
        context.top_driver
        and context.points
        and (safe_float(context.top_driver["points"]) / context.points) >= _POINTS_CONCENTRATION_RATIO
    ):
        threats.append(
            f"Points are concentrated through {context.top_driver['driver']}; losing that car has high constructor impact."
        )
    if not threats:
        threats.append(_no_threat_note(context))
    return threats


def _no_threat_note(context: IntelContext) -> str:
    if context.on_offer is None:
        return "The points still on offer could not be counted, so no table threat is read."
    return "No close constructor-table threat is visible from current standings alone."


def _intel_opportunities(context: IntelContext) -> list[str]:
    """Where this team's position gives it something to play for, by the title rule."""
    opportunities = []
    if context.ahead and context.ahead_in_reach:
        opportunities.append(
            f"Close the gap to {context.ahead['team']} by targeting points swings above {format_points_value(context.gap_ahead)}."
        )
    if context.behind and context.behind_in_reach:
        opportunities.append(
            f"Protect against {context.behind['team']} by prioritising finishes that keep the gap above {format_points_value(context.gap_behind)}."
        )
    if len(context.roster) > 1:
        opportunities.append(
            "Use both cars in scenario planning because the roster has multiple classified points sources."
        )
    if context.position == 1 and not context.decided:
        opportunities.append(
            "Leader control: minimise low-probability strategy branches when direct rivals are behind."
        )
    return opportunities


def build_intel(team_slug_value: str, year: int | None = None) -> dict:
    """A team's place in the constructors' table and the rivals either side, as of ``current_standings``."""
    resolved_year = year or datetime.now(UTC).year
    standings = current_standings(resolved_year)
    drivers, constructors = standings.driver_rows(), standings.team_rows()
    table = {"year": resolved_year, "source": TEAMS_SOURCE, **standings.meta()}
    if not constructors:
        return {
            **table,
            "status": "data_unavailable",
            "team": profile_for_team(team_slug_value.replace("-", " ").title()),
            "upgrade_watch": [],
            "threats": [],
            "opportunities": [],
            "error": "Constructor standings are unavailable.",
        }

    match = next((row for row in constructors if team_slug(row["team"]) == team_slug_value), None)
    if not match:
        return {
            **table,
            "status": "team_not_found",
            "team": profile_for_team(team_slug_value.replace("-", " ").title()),
            "upgrade_watch": [],
            "threats": [],
            "opportunities": [],
            "available_teams": [{"slug": team_slug(row["team"]), "name": row["team"]} for row in constructors],
            "error": f"Team '{team_slug_value}' was not found in the constructor standings.",
        }

    roster = [driver for driver in drivers if driver["team"] == match["team"]]
    reach = constructors_reach(standings)
    # Points per GP divides by the rounds the table covers, as on the standings page.
    profile = build_team_profile(match, roster, reach, standings.as_of_round or 0)
    context = _intel_context(match, roster, constructors, reach)

    return {
        **table,
        "status": "ok",
        "team": profile,
        "drivers": roster,
        "upgrade_watch": _intel_evidence(context),
        "threats": _intel_threats(context),
        "opportunities": _intel_opportunities(context),
        "error": None,
    }
