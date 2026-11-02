"""A championship table, moved on one round at a time. Pure: no I/O.

A round's points are added as published, then the table is ordered the way the
FIA orders it: points first, then a count-back of Grand Prix finishing places
(most wins, then most second places, and so on down). Sprint places take no
part. Checked against every round of f1db's 2024–2026 tables: the count-back
reproduced f1db's order in all of them, while carrying the previous order over
got most rounds wrong. Where the count-back is level too, the previous order
stands, and a driver new to the table goes after everyone already in it.

Drivers are keyed by their three-letter code and teams by f1db's team name,
the keys the rest of the standings code already uses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Finishing places the count-back compares; no Grand Prix has classified more.
COUNTBACK_PLACES = 40


@dataclass(frozen=True)
class Standing:
    """One row of a championship table: a driver (keyed by code) or a team (keyed by name)."""

    key: str
    name: str
    #: A driver's team in their latest round; a team row's own name.
    team: str
    points: float
    #: Classified Grand Prix places this season, for the wins and the count-back.
    finishes: tuple[int, ...] = ()
    #: Place in the table; ``None`` until ranked.
    position: int | None = None

    @property
    def wins(self) -> int:
        return self.finishes.count(1)


@dataclass(frozen=True)
class Score:
    """What one car scored in one points-paying session."""

    code: str
    name: str
    #: f1db's name for the team whose car it was.
    team: str
    points: float
    #: The classified Grand Prix place; ``None`` for a sprint or a car not classified.
    finish: int | None = None


@dataclass(frozen=True)
class Table:
    """The drivers' and the teams' championship, in order."""

    drivers: tuple[Standing, ...] = ()
    teams: tuple[Standing, ...] = ()


def _countback(finishes: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(-finishes.count(place) for place in range(1, COUNTBACK_PLACES + 1))


def _order(row: Standing) -> tuple:
    return (-row.points, _countback(row.finishes), row.position is None, row.position or 0, row.key)


def ranked(rows: Iterable[Standing]) -> tuple[Standing, ...]:
    """``rows`` in championship order, each with its place set."""
    return tuple(replace(row, position=place) for place, row in enumerate(sorted(rows, key=_order), start=1))


def _credited(row: Standing | None, key: str, name: str, score: Score) -> Standing:
    start = row or Standing(key=key, name=name, team=score.team, points=0.0)
    finishes = start.finishes if score.finish is None else (*start.finishes, score.finish)
    return replace(start, team=score.team, points=start.points + score.points, finishes=finishes)


def _credit_all(rows: tuple[Standing, ...], scores: tuple[Score, ...], *, by_team: bool) -> tuple[Standing, ...]:
    table = {row.key: row for row in rows}
    for score in scores:
        key = score.team if by_team else score.code
        table[key] = _credited(table.get(key), key, key if by_team else score.name, score)
    return tuple(table.values())


def add_round(table: Table, scores: Iterable[Score]) -> Table:
    """``table`` with a round's scores added and both championships re-ordered."""
    scored = tuple(scores)
    return Table(
        drivers=ranked(_credit_all(table.drivers, scored, by_team=False)),
        teams=ranked(_credit_all(table.teams, scored, by_team=True)),
    )
