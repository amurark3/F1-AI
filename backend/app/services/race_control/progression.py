"""Every round's championship table, and the round each title was clinched.

Per round: f1db's published table for the rounds it holds, the computed table
(``CurrentStandings.round_tables``) for the rounds after its base. A round f1db
does not hold is provisional.

Clinch round: f1db's own decider flag when it marks one; otherwise the first
computed round where the shared title rule (``table_reach``) says no rival can
still finish ahead. The rule is not used on f1db's rounds because f1db's
calendar has no session times before 2024: nothing would count as left and
every older title would "clinch" in round 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.data.current_standings import current_standings
from app.data.f1db_standings import championship_deciders, standings_by_round
from app.data.title_rule import CONSTRUCTORS, DRIVERS, Scoring
from app.services.race_control import table_reach
from app.services.race_control.strategy_context import season_events

if TYPE_CHECKING:
    from app.data.standings_table import Standing

logger = structlog.get_logger()


@dataclass(frozen=True)
class _Table:
    rows: tuple[Standing, ...]
    published: dict[int, dict[str, tuple]]
    computed: tuple[tuple[int, tuple[Standing, ...]], ...]
    decider: int | None
    scoring: Scoring


def _calendar(year: int) -> dict[int, dict]:
    try:
        return {event["round"]: event for event in season_events(year)}
    except Exception as exc:
        logger.warning("race_control.progression.calendar_failed", year=year, error=str(exc))
        return {}


def _round_row(round_num: int, calendar: dict[int, dict], held: set[int]) -> dict:
    event = calendar.get(round_num)
    return {
        "round": round_num,
        "name": event["name"] if event else None,
        "location": event["location"] if event else None,
        "sprint": event["is_sprint"] if event else None,
        "provisional": round_num not in held,
    }


def _cells(table: _Table) -> dict[int, dict[str, tuple]]:
    computed = {n: {row.key: (row.points, row.position) for row in rows} for n, rows in table.computed}
    return {**table.published, **computed}


def _entrants(table: _Table, rounds: range) -> list[dict]:
    cells = _cells(table)
    entrants = []
    for row in table.rows:
        found = [cells.get(n, {}).get(row.key) for n in rounds]
        entrants.append(
            {
                "key": row.key,
                "name": row.name,
                "team": row.team,
                "points": [cell[0] if cell else None for cell in found],
                "positions": [cell[1] if cell else None for cell in found],
            }
        )
    return entrants


def _clinch_round(table: _Table, year: int) -> int | None:
    if table.decider is not None:
        return table.decider
    for round_num, rows in table.computed:
        reach = table_reach.TableReach(rows, table.scoring, table_reach.remaining_after(year, round_num))
        if reach.decided():
            return round_num
    return None


def _clinched(table: _Table, year: int, calendar: dict[int, dict]) -> dict | None:
    round_num = _clinch_round(table, year)
    if round_num is None:
        return None
    # shortcut: f1db's calendar has no session times before 2024, so is_sprint reads false there; the page shows the current season only.
    after = [event for n, event in calendar.items() if n > round_num]
    return {
        "round": round_num,
        "races_left": len(after) if calendar else None,
        "sprints_left": sum(1 for event in after if event["is_sprint"]) if calendar else None,
    }


def _championship(table: _Table, rounds: range, year: int, calendar: dict[int, dict]) -> dict:
    return {"entrants": _entrants(table, rounds), "clinched": _clinched(table, year, calendar)}


def build_standings_progression(year: int) -> dict:
    """Both championships after every round of ``year``, and the round each title was clinched."""
    standings = current_standings(year)
    published_drivers, published_teams = standings_by_round(year)
    driver_decider, team_decider = championship_deciders(year)
    rounds = range(1, (standings.as_of_round or 0) + 1)
    calendar = _calendar(year)
    drivers = _Table(
        standings.drivers,
        published_drivers,
        tuple((n, table.drivers) for n, table in standings.round_tables),
        driver_decider,
        DRIVERS,
    )
    teams = _Table(
        standings.teams,
        published_teams,
        tuple((n, table.teams) for n, table in standings.round_tables),
        team_decider,
        CONSTRUCTORS,
    )
    held = set(published_drivers)
    return {
        "year": year,
        **standings.meta(),
        "rounds": [_round_row(n, calendar, held) for n in rounds],
        "drivers": _championship(drivers, rounds, year, calendar),
        "constructors": _championship(teams, rounds, year, calendar),
    }
