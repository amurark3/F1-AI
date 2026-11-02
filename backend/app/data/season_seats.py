"""Who has raced each team's cars this season, read from f1db's race starts.

The championship table cannot say who is in a team's cars. It lists everyone
who has raced this season, so once a stand-in has raced it holds the stand-in
and the driver they replaced side by side. Tsunoda raced Racing Bulls' car in
R12–R14 while Lawson stepped up for the injured Hadjar, and the table still
listed Racing Bulls three times after Hadjar returned: the R20 prediction showed
23 drivers for 22 cars.

Race starts answer the two questions a lineup needs:

* **Who holds a team's two cars now:** whoever raced them most recently. A seat
  is one of a team's two cars, not a car number, because a stand-in races under
  their own number (Hirakawa raced Ocon's Haas as car 50; Ocon's is 31), so a
  number cannot pair a stand-in with the driver they replaced. Each driver
  counts for their latest team only.
* **Who are a team's regulars:** the two drivers with the most starts for it.
  A driver in its car who is neither is standing in, and the seat stays
  unconfirmed until the next entry list is published.

Only rounds before the one being predicted count, so recomputing a past race
sees the season as it stood then.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING

from app.data.f1db_source import connect
from app.data.identity import TEAM_ALIASES, fold

if TYPE_CHECKING:
    from collections.abc import Iterable

# A Formula 1 team enters two cars.
CARS_PER_TEAM = 2

_SEATS_QUERY = """
    SELECT d.abbreviation AS code, d.name AS name, con.name AS team,
           COUNT(*) AS starts, MAX(r.round) AS last_round
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor con ON con.id = rd.constructor_id
    WHERE r.year = ? AND r.round < ? AND rd.type = 'RACE_RESULT' AND d.abbreviation IS NOT NULL
    GROUP BY rd.driver_id, rd.constructor_id
    ORDER BY con.name, d.abbreviation
"""


@dataclass(frozen=True)
class SeasonSeat:
    """One driver's race starts for one team this season."""

    code: str
    name: str
    team: str
    starts: int
    last_round: int


def team_key(name: str) -> str:
    """One key per team, however a feed spells it.

    OpenF1 says "Haas F1 Team" and "Red Bull Racing", f1db "Haas" and "Red
    Bull"; both resolve to the same key through :mod:`app.data.identity`'s
    alias table, without a database read.
    """
    folded = fold(name)
    return fold(TEAM_ALIASES.get(folded, folded))


def season_seats(year: int, before_round: int) -> tuple[SeasonSeat, ...]:
    """Every (driver, team) pairing that started a race in ``year`` before ``before_round``."""
    with connect() as conn:
        rows = conn.execute(_SEATS_QUERY, (year, before_round)).fetchall()
    return tuple(
        SeasonSeat(
            code=row["code"],
            name=row["name"],
            team=row["team"],
            starts=int(row["starts"]),
            last_round=int(row["last_round"]),
        )
        for row in rows
    )


def _by_team(seats: Iterable[SeasonSeat]) -> dict[str, list[SeasonSeat]]:
    ordered = sorted(seats, key=lambda seat: team_key(seat.team))
    return {key: list(group) for key, group in groupby(ordered, key=lambda seat: team_key(seat.team))}


def current_holders(seats: Iterable[SeasonSeat]) -> frozenset[str]:
    """The drivers in each team's two cars: per team, the two who raced it most recently.

    Lawson raced Red Bull's car in R12–R14 and Racing Bulls' before and after,
    so he counts for Racing Bulls, where he last raced, and nowhere else.
    """
    latest = {seat.code: seat for seat in sorted(seats, key=lambda seat: (seat.last_round, seat.starts))}
    holders = (
        seat.code
        for team in _by_team(latest.values()).values()
        for seat in sorted(team, key=lambda seat: (-seat.last_round, -seat.starts, seat.code))[:CARS_PER_TEAM]
    )
    return frozenset(holders)


def regulars(seats: Iterable[SeasonSeat], team: str) -> tuple[SeasonSeat, ...]:
    """A team's two regular drivers: the most starts for it, the more recent first on a tie."""
    team_seats = _by_team(seats).get(team_key(team), [])
    ranked = sorted(team_seats, key=lambda seat: (-seat.starts, -seat.last_round, seat.code))
    return tuple(ranked[:CARS_PER_TEAM])


def _replaced_regular(
    car: tuple[str, str], cars: tuple[tuple[str, str], ...], seats: tuple[SeasonSeat, ...]
) -> SeasonSeat | None:
    """The regular whose car ``car``'s driver raced, or ``None`` when they are a regular."""
    code, team = car
    team_regulars = regulars(seats, team)
    if code in {seat.code for seat in team_regulars}:
        return None
    in_team = {other for other, other_team in cars if team_key(other_team) == team_key(team)}
    return next((seat for seat in team_regulars if seat.code not in in_team), None)


def stand_ins(lineup: Iterable[tuple[str, str]], seats: Iterable[SeasonSeat]) -> dict[str, SeasonSeat]:
    """The drivers of a lineup standing in, each with the regular whose car they raced.

    ``lineup`` is ``(driver code, team)`` per car. A driver counts as standing
    in when they are not one of the team's regulars and a regular is missing
    from the team's cars. A chain is followed seat by seat: with Hadjar out,
    Lawson stood in for him at Red Bull and Tsunoda for Lawson at Racing Bulls.
    A team with no starts this season has no regulars, so nobody in it can be
    judged a stand-in.
    """
    cars = tuple(lineup)
    history = tuple(seats)
    found = ((car[0], _replaced_regular(car, cars, history)) for car in cars)
    return {code: regular for code, regular in found if regular is not None}
