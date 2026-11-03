"""What the championship hangs on this weekend.

Three facts, all arithmetic on the standings and the calendar: how many points
are still on offer, which contenders can still mathematically win, and whether
the leader can settle it at this round.

Points left are counted against the standings, not the clock: the table is
``current_standings``'s (f1db's last round plus each later round's published
points), and a race whose points it does not hold yet is still worth them to
anyone reading it. Counting it as spent would knock contenders out before their
points arrived. Every way this can be wrong overstates what is left, which only
ever delays a verdict.

Whether a rival is still in, and so whether the title is decided, is
``app.data.title_rule``'s call, the rule every title read shares: a lead larger
than what is left decides it, and a lead exactly equal to it decides it only
when the leader would win the count-back. The margin to clinch *at this round*
is quoted on points alone (a lead past what is left after the round): a finish
level with that margin turns on this weekend's places, which nobody knows yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.data import title_rule
from app.data.title_rule import Remaining, Scoring, can_still_beat, max_points
from app.services.race_control.session_weather import session_slots

if TYPE_CHECKING:
    from app.data.current_standings import CurrentStandings
    from app.data.standings_table import Standing

RACE_SESSION = "Race"
SPRINT_SESSION = "Sprint"
# Standings rows shown in the title-fight panel.
CONTENDER_ROWS = 6


@dataclass(frozen=True)
class Championship:
    """One championship: how its entrants score (``title_rule``), and whether its rows name a driver code."""

    scoring: Scoring
    coded: bool


DRIVERS = Championship(scoring=title_rule.DRIVERS, coded=True)
CONSTRUCTORS = Championship(scoring=title_rule.CONSTRUCTORS, coded=False)


@dataclass(frozen=True)
class PointsLeft:
    """Points-paying sessions the standings do not include yet: season-wide, and at this round."""

    races: int
    sprints: int
    races_here: int
    sprints_here: int


def _paying_sessions(event: dict | None, now: datetime | None) -> tuple[int, int]:
    """Races and sprints at ``event``; only those not yet finished when ``now`` is given."""
    names = [slot.name for slot in session_slots(event) if now is None or now < slot.end]
    return names.count(RACE_SESSION), names.count(SPRINT_SESSION)


def _unscored(event: dict | None, through_round: int | None, now: datetime) -> tuple[int, int]:
    """Races and sprints at ``event`` whose points the standings do not hold yet.

    With a known standings round, a later round's sessions all count, run or
    not. Without one (no round in the table yet), the clock is the best guide: a
    session counts until it ends.
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


def _contender(row: Standing, leader: Standing, alive: bool, championship: Championship) -> dict:
    return {
        "position": row.position,
        "name": row.name,
        "code": row.key if championship.coded else None,
        "team": row.team,
        "points": row.points,
        "gap": leader.points - row.points,
        "alive": alive,
    }


def _clinch(rows: tuple[Standing, ...], available: int, here: int) -> dict | None:
    """Whether the leader can settle the title at this round, and by what margin.

    Settled means a lead over every rival larger than what is left after the
    round. The closest rival binds, so the margin is quoted against them; the
    leader must also stay far enough clear of the others still in play.
    """
    leader, rival = rows[0], rows[1]
    lead = leader.points - rival.points
    after = available - here
    margin = after - lead + 1
    return {
        "rival": rival.name,
        "margin_needed": margin,
        "possible": margin <= here,
        "rivals_in_play": sum(1 for row in rows[1:] if leader.points - row.points <= after),
    }


def table_stakes(rows: tuple[Standing, ...], left: PointsLeft, championship: Championship) -> dict | None:
    """One championship's stakes; None until a round has paid points.

    The panel draws every bar as a share of the leader's points, so a table where
    nobody has scored yet (no rows, or a first round that paid none) has no stakes.
    """
    if not rows or rows[0].points <= 0:
        return None
    scoring = championship.scoring
    remaining = Remaining(races=left.races, sprints=left.sprints)
    available = max_points(remaining, scoring)
    here = max_points(Remaining(races=left.races_here, sprints=left.sprints_here), scoring)
    leader = rows[0]
    alive = (True, *(can_still_beat(leader, row, remaining, scoring) for row in rows[1:]))
    rivals_alive = sum(alive[1:])
    decided = len(rows) > 1 and rivals_alive == 0
    return {
        "max_available": available,
        "max_this_weekend": here,
        "leader": _contender(leader, leader, True, championship),
        "contenders": [
            _contender(row, leader, is_alive, championship)
            for row, is_alive in zip(rows[:CONTENDER_ROWS], alive, strict=False)
        ],
        "rivals_alive": rivals_alive,
        "decided": decided,
        "clinch": None if decided or len(rows) < 2 or here == 0 else _clinch(rows, available, here),
    }


def build_championship_stakes(
    events: list[dict],
    selected: dict | None,
    standings: CurrentStandings,
    now: datetime | None = None,
) -> dict:
    """Both championships' stakes for the selected round, with the table's round, status and sources."""
    left = points_left(events, selected, standings.as_of_round, now or datetime.now(UTC))
    return {
        **standings.meta(),
        "races_left": left.races,
        "sprints_left": left.sprints,
        "drivers": table_stakes(standings.drivers, left, DRIVERS),
        "constructors": table_stakes(standings.teams, left, CONSTRUCTORS),
    }
