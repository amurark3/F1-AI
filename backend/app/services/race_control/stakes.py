"""What the championship hangs on this weekend.

Three facts, all arithmetic on the standings and the calendar: how many points
are still on offer, which contenders can still mathematically win, and whether
the leader can settle it at this round.

Points left are counted against the standings, not the clock. f1db publishes a
race's standings a day or two after it, and for that long a race that has run
is still worth its points to anyone reading the table; counting it as spent
would knock contenders out before their points arrived. Every way this can be
wrong overstates what is left, which only ever delays a verdict.

A tie on points is decided on countback, which this module does not model, so
a tie is never presented as a clinch — a contender level on maximum points is
still alive, and a leader whose lead only equals what is left has not won.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.race_control.session_weather import session_slots

RACE_SESSION = "Race"
SPRINT_SESSION = "Sprint"
# Standings rows shown in the title-fight panel.
CONTENDER_ROWS = 6


@dataclass(frozen=True)
class Scoring:
    """The most one entrant can score in a race and in a sprint."""

    per_race: int
    per_sprint: int
    name_key: str


# A driver's best is a win. A constructor scores with both cars, so its best is a
# one-two: 25 + 18 in a race and 8 + 7 in a sprint.
DRIVERS = Scoring(per_race=25, per_sprint=8, name_key="driver")
CONSTRUCTORS = Scoring(per_race=25 + 18, per_sprint=8 + 7, name_key="team")


@dataclass(frozen=True)
class PointsLeft:
    """Points-paying sessions the standings do not include yet: season-wide, and at this round."""

    races: int
    sprints: int
    races_here: int
    sprints_here: int


@dataclass(frozen=True)
class Standings:
    drivers: list[dict]
    constructors: list[dict]
    # The last round the tables include; None when unknown (the live Ergast fallback).
    through_round: int | None


def _paying_sessions(event: dict | None, now: datetime | None) -> tuple[int, int]:
    """Races and sprints at ``event``; only those not yet finished when ``now`` is given."""
    names = [slot.name for slot in session_slots(event) if now is None or now < slot.end]
    return names.count(RACE_SESSION), names.count(SPRINT_SESSION)


def _unscored(event: dict | None, through_round: int | None, now: datetime) -> tuple[int, int]:
    """Races and sprints at ``event`` whose points the standings do not hold yet.

    With a known standings round, a later round's sessions all count, run or
    not. Without one, the clock is the best guide: a session counts until it ends.
    """
    if through_round is None:
        return _paying_sessions(event, now)
    if (event or {}).get("round", 0) > through_round:
        return _paying_sessions(event, None)
    return 0, 0


def points_left(events: list[dict], selected: dict | None, through_round: int | None, now: datetime) -> PointsLeft:
    """Races and sprints still worth points to the standings, across the season and at ``selected``."""
    counts = [_unscored(event, through_round, now) for event in events]
    races_here, sprints_here = _unscored(selected, through_round, now)
    return PointsLeft(
        races=sum(races for races, _ in counts),
        sprints=sum(sprints for _, sprints in counts),
        races_here=races_here,
        sprints_here=sprints_here,
    )


def _contender(row: dict, leader_points: float, available: int, scoring: Scoring) -> dict:
    gap = leader_points - row["points"]
    return {
        "position": row["position"],
        "name": row[scoring.name_key],
        "code": row.get("code"),
        "team": row.get("team"),
        "points": row["points"],
        "gap": gap,
        "alive": gap <= available,
    }


def _clinch(rows: list[dict], available: int, here: int, scoring: Scoring) -> dict | None:
    """Whether the leader can settle the title at this round, and by what margin.

    Settled means a lead over every rival larger than what is left after the
    round. The closest rival binds, so the margin is quoted against them; the
    leader must also stay far enough clear of the others still in play.
    """
    if len(rows) < 2 or here == 0:
        return None
    leader, rival = rows[0], rows[1]
    lead = leader["points"] - rival["points"]
    if lead > available:
        return None
    after = available - here
    margin = after - lead + 1
    return {
        "rival": rival[scoring.name_key],
        "margin_needed": margin,
        "possible": margin <= here,
        "rivals_in_play": sum(1 for row in rows[1:] if leader["points"] - row["points"] <= after),
    }


def _scored(rows: list[dict]) -> list[dict]:
    """Rows with a points total; one without cannot be placed against the leader."""
    return [row for row in rows if isinstance(row.get("points"), (int, float)) and not isinstance(row["points"], bool)]


def table_stakes(standings: list[dict], left: PointsLeft, scoring: Scoring) -> dict | None:
    """One championship's stakes; None when there are no standings to read."""
    rows = _scored(standings)
    if not rows:
        return None
    available = left.races * scoring.per_race + left.sprints * scoring.per_sprint
    here = left.races_here * scoring.per_race + left.sprints_here * scoring.per_sprint
    leader_points = rows[0]["points"]
    contenders = [_contender(row, leader_points, available, scoring) for row in rows[:CONTENDER_ROWS]]
    rivals_alive = sum(1 for row in rows[1:] if leader_points - row["points"] <= available)
    return {
        "max_available": available,
        "max_this_weekend": here,
        "leader": contenders[0],
        "contenders": contenders,
        "rivals_alive": rivals_alive,
        "decided": len(rows) > 1 and rivals_alive == 0,
        "clinch": _clinch(rows, available, here, scoring),
    }


def build_championship_stakes(
    events: list[dict],
    selected: dict | None,
    standings: Standings,
    now: datetime | None = None,
) -> dict:
    """Both championships' stakes for the selected round."""
    left = points_left(events, selected, standings.through_round, now or datetime.now(UTC))
    return {
        "through_round": standings.through_round,
        "races_left": left.races,
        "sprints_left": left.sprints,
        "drivers": table_stakes(standings.drivers, left, DRIVERS),
        "constructors": table_stakes(standings.constructors, left, CONSTRUCTORS),
    }
