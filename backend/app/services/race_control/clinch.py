"""What each championship hangs on, race by race: decided (where, with what to spare) or open (what the leader must do next).

The rule is ``app.data.title_rule``'s (``decided``, ``needs_at``, ``earliest``); this builds
the payload around it. Where a decided title was clinched is read from the standings
progression (``progression.build_standings_progression``): f1db's own decider flag for rounds
it holds, the title rule for computed rounds. Seasons before 2025 are not calculated: their
points rules differ (the fastest-lap point in 2019-24, double points in 2014, a 3-2-1 sprint
in 2021).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.current_standings import current_standings
from app.data.title_rule import Remaining, decided, earliest, max_points, needs_at, total
from app.services.race_control.progression import build_standings_progression
from app.services.race_control.stakes import CONSTRUCTORS, DRIVERS, entrant, need_row, paying_sessions
from app.services.race_control.strategy_context import season_events

if TYPE_CHECKING:
    from app.data.standings_table import Standing
    from app.services.race_control.stakes import Championship

FIRST_YEAR = 2025


@dataclass(frozen=True)
class _Season:
    year: int
    #: Calendar entries after the table's round.
    upcoming: list[dict]


def _event(event: dict) -> dict:
    return {"round": event["round"], "name": event["name"], "venue": event["location"].split(",")[0].strip()}


def _decided_at(table: str, championship: Championship, year: int) -> dict | None:
    """Where the title was clinched, from the progression; None when it does not say."""
    progression = build_standings_progression(year)
    clinched = progression[table]["clinched"]
    if clinched is None or clinched["races_left"] is None:
        return None
    index = next(i for i, row in enumerate(progression["rounds"]) if row["round"] == clinched["round"])
    row = progression["rounds"][index]
    points = sorted(e["points"][index] for e in progression[table]["entrants"] if e["points"][index] is not None)
    left = Remaining(clinched["races_left"], clinched["sprints_left"])
    return {
        **_event(row),
        "lead": points[-1] - points[-2],
        "left": max_points(left, championship.scoring),
        "races_to_spare": left.races,
        "sprints_to_spare": left.sprints,
        "provisional": row["provisional"],
    }


def _next(
    upcoming: list[dict], parts: tuple[Remaining, ...], rows: tuple[Standing, ...], championship: Championship
) -> tuple[dict, dict | None]:
    scoring = championship.scoring
    first = earliest(rows, parts, scoring)
    needs = needs_at(rows, parts[0], total(parts[1:]), scoring)
    return {
        **_event(upcoming[0]),
        "races": parts[0].races,
        "sprints": parts[0].sprints,
        "max_points": max_points(parts[0], scoring),
        "possible": first == 0,
        "needs": [need_row(need, championship) for need in needs],
    }, None if first is None else _event(upcoming[first])


def _title(rows: tuple[Standing, ...], table: str, championship: Championship, season: _Season) -> dict | None:
    if len(rows) < 2 or rows[0].points <= 0:
        return None
    parts = tuple(Remaining(*paying_sessions(event, None)) for event in season.upcoming)
    left = total(parts)
    title = {
        "decided": decided(rows, left, championship.scoring),
        "leader": {**entrant(rows[0], championship), "points": rows[0].points},
        "max_available": max_points(left, championship.scoring),
        "next": None,
        "earliest": None,
        "decided_at": None,
    }
    if title["decided"]:
        return {**title, "decided_at": _decided_at(table, championship, season.year)}
    if not season.upcoming:
        return title
    following, soonest = _next(season.upcoming, parts, rows, championship)
    return {**title, "next": following, "earliest": soonest}


def build_clinch(year: int) -> dict:
    """Both championships' title state after the latest round: decided (where) or what the leader must do next."""
    if year < FIRST_YEAR:
        return {
            "year": year,
            "as_of_round": None,
            "provisional": False,
            "sources": [],
            "drivers": None,
            "constructors": None,
        }
    standings = current_standings(year)
    through = standings.as_of_round or 0
    season = _Season(year, [event for event in season_events(year) if event["round"] > through])
    return {
        "year": year,
        **standings.meta(),
        "drivers": _title(standings.drivers, "drivers", DRIVERS, season),
        "constructors": _title(standings.teams, "constructors", CONSTRUCTORS, season),
    }
