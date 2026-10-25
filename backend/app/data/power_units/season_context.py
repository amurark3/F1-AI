"""What f1db knows about a season that the power-unit documents do not say.

The FIA documents name a car by its number and an event by its title. Tying
them to the rest of the app needs two things from f1db:

* the calendar — each round's race day, name and three-letter code — which is
  how a document's cover date becomes a round number;
* the race-weekend entry list of every round — car number, driver, team —
  which is how a car number becomes a driver, and how a stand-in is told apart
  from the driver whose car they took.

Entries are read from qualifying, grid and race rows only. Practice rows are
left out on purpose: f1db lists every FP1 rookie (Herta, Iwasa, Browning, Aron
at Monza 2026), and those runs use the race driver's car and elements — they
are not seat changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import structlog

from app.data.f1db_source import connect
from app.data.power_units.text import compact

if TYPE_CHECKING:
    import sqlite3

logger = structlog.get_logger()

_CALENDAR_QUERY = """
    SELECT r.round AS round, r.date AS race_day, gp.short_name AS name, gp.abbreviation AS code
    FROM race r
    JOIN grand_prix gp ON gp.id = r.grand_prix_id
    WHERE r.year = ?
    ORDER BY r.round
"""

_ENTRIES_QUERY = """
    SELECT DISTINCT r.round AS round,
           rd.driver_number AS car_number,
           d.id AS driver_id,
           d.name AS driver_name,
           d.abbreviation AS driver_code,
           c.id AS constructor_id,
           c.name AS constructor_name
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor c ON c.id = rd.constructor_id
    WHERE r.year = ?
      AND rd.type IN ('QUALIFYING_RESULT', 'STARTING_GRID_POSITION', 'RACE_RESULT')
      AND rd.driver_number IS NOT NULL
    ORDER BY r.round, c.id, rd.driver_number
"""


@dataclass(frozen=True)
class SeasonRound:
    """One Grand Prix of the season."""

    round: int
    race_day: date
    #: f1db's short name, e.g. "Italian GP".
    name: str
    #: Three-letter code, e.g. "ITA".
    code: str


@dataclass(frozen=True)
class Entry:
    """One car at one round's race weekend."""

    round: int
    car_number: int
    driver_id: str
    driver_name: str
    driver_code: str
    constructor_id: str
    constructor_name: str


@dataclass(frozen=True)
class SeasonContext:
    """The season's calendar and every round's race-weekend entries."""

    year: int
    rounds: tuple[SeasonRound, ...]
    entries: tuple[Entry, ...]

    def round_on(self, race_day: date) -> SeasonRound | None:
        """The round whose race is on ``race_day``."""
        return next((item for item in self.rounds if item.race_day == race_day), None)

    def entries_at(self, round_num: int) -> tuple[Entry, ...]:
        return tuple(entry for entry in self.entries if entry.round == round_num)

    def driver_for_car(self, car_number: int, round_num: int) -> Entry | None:
        """Who raced ``car_number`` at ``round_num`` — or, for a round f1db does
        not hold yet, the latest earlier round that number was raced."""
        exact = next(
            (entry for entry in self.entries if entry.round == round_num and entry.car_number == car_number),
            None,
        )
        if exact is not None:
            return exact
        earlier = [entry for entry in self.entries if entry.car_number == car_number and entry.round < round_num]
        return earlier[-1] if earlier else None

    def constructors(self) -> dict[str, str]:
        """``{constructor_id: name}`` for every team entered this season."""
        return {entry.constructor_id: entry.constructor_name for entry in self.entries}

    def team_named(self, printed: str) -> str | None:
        """The season's team a printed entrant or competitor names, if any.

        The team leads every FIA form ("Red Bull Racing RB Ford Max
        Verstappen", "Oracle Red Bull Racing"), sometimes behind a sponsor
        ("Atlassian Williams Mercedes"), and the power-unit supplier — often
        another team's name — follows it. So the earliest match wins, and the
        longest among matches at the same place.
        """
        text = compact(printed)
        found = [
            (position, -len(key), constructor_id)
            for constructor_id, name in self.constructors().items()
            if (key := compact(name)) and (position := text.find(key)) >= 0
        ]
        return min(found)[2] if found else None


def _round(row: sqlite3.Row) -> SeasonRound:
    return SeasonRound(
        round=int(row["round"]),
        race_day=date.fromisoformat(row["race_day"]),
        name=row["name"],
        code=row["code"] or "",
    )


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        round=int(row["round"]),
        car_number=int(row["car_number"]),
        driver_id=row["driver_id"],
        driver_name=row["driver_name"],
        driver_code=row["driver_code"] or "",
        constructor_id=row["constructor_id"],
        constructor_name=row["constructor_name"],
    )


def load_season_context(year: int) -> SeasonContext:
    """Read the season's calendar and entries from f1db."""
    with connect() as conn:
        rounds = tuple(_round(row) for row in conn.execute(_CALENDAR_QUERY, (year,)).fetchall())
        entries = tuple(_entry(row) for row in conn.execute(_ENTRIES_QUERY, (year,)).fetchall())
    logger.info("power_units.season_context", year=year, rounds=len(rounds), entries=len(entries))
    return SeasonContext(year=year, rounds=rounds, entries=entries)
