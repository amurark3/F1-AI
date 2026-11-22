"""What a standings tool read, as chips, and the one chart it can draw: who can still reach a place."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.api.tools.provenance import Provenance, ReachChart, ReachRow, chip
from app.services.race_control_common import pluralise

if TYPE_CHECKING:
    from app.data.current_standings import CurrentStandings
    from app.data.standings_table import Standing
    from app.services.race_control.table_reach import TableReach

ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def _source_chips(standings: CurrentStandings) -> tuple[str, ...]:
    chips = []
    for source in standings.sources:
        if source["role"] == "base":
            chips.append(chip("f1db", f"standings after R{source['through_round']}", version=source["version"]))
        elif source["role"] == "points":
            chips.append(chip(source["source"], f"R{source['round']}", "provisional"))
    return tuple(chips)


def _fight(reach: TableReach) -> tuple[int, tuple[Standing, ...]] | None:
    """The first place some row below can still pass, with the row holding it and every such chaser."""
    if reach.remaining is None:
        return None
    for index, target in enumerate(reach.rows):
        chasers = tuple(row for row in reach.rows[index + 1 :] if reach.can_pass(row.key, target.key))
        if chasers:
            return index + 1, (target, *chasers)
    return None


def _title(place: int, count: int, championship: str, standings: CurrentStandings) -> str:
    noun = "drivers" if championship == "drivers" else "teams"
    goal = "win the title" if place == 1 else f"finish {ORDINALS[place - 1] if place <= len(ORDINALS) else f'P{place}'}"
    suffix = " · provisional" if standings.provisional else ""
    return f"{count} {noun} can still {goal} · points after round {standings.as_of_round} → most possible{suffix}"


def _basis_chip(reach: TableReach) -> str:
    remaining = reach.remaining
    sprints = f" + {pluralise(remaining.sprints, 'sprint')}" if remaining.sprints else ""
    return f"{pluralise(remaining.races, 'race')}{sprints} left · {reach.points_on_offer} pts max"


def standings_provenance(
    standings: CurrentStandings, reach: TableReach, championship: Literal["drivers", "constructors"]
) -> Provenance:
    """Subject, chips and (when the places are still contested) the reach chart of a standings table."""
    subject = (
        f"{standings.year} standings after round {standings.as_of_round}"
        if standings.as_of_round
        else f"{standings.year} standings"
    )
    sources = _source_chips(standings)
    fight = _fight(reach)
    if fight is None:
        return Provenance(sources=sources, subject=subject)
    place, rows = fight
    offer = reach.points_on_offer
    chart = ReachChart(
        title=_title(place, len(rows), championship, standings),
        championship=championship,
        year=standings.year,
        rows=tuple(ReachRow(row.key, row.name, row.team, row.points, row.points + offer) for row in rows),
    )
    return Provenance(sources=(*sources, _basis_chip(reach)), subject=subject, chart=chart)
