"""The championship standings as of the newest round with published points.

Standings used to come from f1db alone, so between a race and f1db's next
release (about 10 hours after Mexico 2026, sometimes days) the site showed the
previous round. Taking one live feed's table as-is is no better: the morning
after Mexico, OpenF1's and Jolpica's were both wrong. So, per
``docs/DATA_SOURCES.md`` ("Standings rule"):

1. **Base:** f1db's table after its last round (``f1db_standings``).
2. **Later rounds:** each round's points from OpenF1 ``session_result``
   (``standings_rounds``), added and re-ordered (``standings_table``).
3. **Provisional** until f1db publishes those rounds itself.
4. **Cross-checked** against OpenF1 ``championship_*`` and Jolpica
   (``standings_cross_check``); the computed value is always the one served.

Payloads carry ``as_of_round``, ``provisional`` and ``sources`` (:meth:`CurrentStandings.meta`).
A finished season is f1db's alone and is never looked up past it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import reduce

import structlog

from app.data.f1db_source import installed_version
from app.data.f1db_standings import (
    constructor_standings_detailed,
    driver_standings_detailed,
    season_finishes,
    standings_round,
)
from app.data.standings_cross_check import CrossCheck, cross_check
from app.data.standings_rounds import RoundPoints, later_rounds
from app.data.standings_table import Standing, Table, add_round
from app.utils.ttl_cache import TtlCache

logger = structlog.get_logger()

F1DB_SOURCE = "f1db"
POINTS_SOURCE = "openf1-session-result"
# A provisional table can still move as post-race penalties land; a confirmed
# one is re-read sooner so a race that has just ended is picked up.
PROVISIONAL_TTL_SECONDS = 30 * 60
CONFIRMED_TTL_SECONDS = 5 * 60


@dataclass(frozen=True)
class CurrentStandings:
    """Both championships after ``as_of_round``, and where each part of them came from."""

    year: int
    drivers: tuple[Standing, ...]
    teams: tuple[Standing, ...]
    #: The last round the table includes; ``None`` before any.
    as_of_round: int | None
    #: True while any round in the table is not yet in f1db.
    provisional: bool
    sources: tuple[dict, ...] = ()

    def driver_rows(self) -> list[dict]:
        """Driver rows in the shape the standings endpoints have always sent."""
        return [
            {
                "position": row.position,
                "code": row.key,
                "driver": row.name,
                "team": row.team,
                "points": row.points,
                "wins": row.wins,
            }
            for row in self.drivers
        ]

    def team_rows(self) -> list[dict]:
        """Constructor rows in the shape the standings endpoints have always sent."""
        return [
            {"position": row.position, "team": row.key, "points": row.points, "wins": row.wins} for row in self.teams
        ]

    def meta(self) -> dict:
        """The freshness fields every standings payload carries."""
        return {"as_of_round": self.as_of_round, "provisional": self.provisional, "sources": list(self.sources)}


_cache: TtlCache[tuple[int, str | None], CurrentStandings] = TtlCache()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def f1db_table(year: int) -> tuple[int, Table]:
    """f1db's last round of ``year`` and its tables; ``(0, Table())`` when it holds none."""
    base_round = standings_round(year) or 0
    if not base_round:
        return 0, Table()
    driver_places, team_places = season_finishes(year, base_round)
    drivers = tuple(
        Standing(
            key=row["code"],
            name=row["name"],
            team=row["team"],
            points=row["points"],
            finishes=driver_places.get(row["code"], ()),
            position=row["position"],
        )
        for row in driver_standings_detailed(year)
    )
    teams = tuple(
        Standing(
            key=row["team"],
            name=row["team"],
            team=row["team"],
            points=row["points"],
            finishes=team_places.get(row["team"], ()),
            position=row["position"],
        )
        for row in constructor_standings_detailed(year)
    )
    return base_round, Table(drivers=drivers, teams=teams)


def _sources(
    base_round: int, version: str | None, rounds: tuple[RoundPoints, ...], checks: tuple[CrossCheck, ...]
) -> tuple[dict, ...]:
    base = (
        ({"source": F1DB_SOURCE, "role": "base", "through_round": base_round, "version": version},)
        if base_round
        else ()
    )
    added = tuple(
        {"source": POINTS_SOURCE, "role": "points", "round": points.round, "sessions": list(points.sessions)}
        for points in rounds
    )
    return (*base, *added, *(check.as_source() for check in checks))


def _compute(year: int, version: str | None) -> CurrentStandings:
    base_round, base = f1db_table(year)
    # A finished season is f1db's alone; only a live one can be ahead of it.
    rounds = later_rounds(year, base_round) if year >= _utc_now().year else ()
    table = reduce(lambda current, points: add_round(current, points.scores), rounds, base)
    checks = cross_check(year, table, rounds[-1]) if rounds else ()
    return CurrentStandings(
        year=year,
        drivers=table.drivers,
        teams=table.teams,
        as_of_round=(rounds[-1].round if rounds else base_round) or None,
        provisional=bool(rounds),
        sources=_sources(base_round, version, rounds, checks),
    )


def current_standings(year: int) -> CurrentStandings:
    """Both championships of ``year`` as of the newest round with published points."""
    version = installed_version()
    key = (year, version)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = _compute(year, version)
    _cache.put(key, result, PROVISIONAL_TTL_SECONDS if result.provisional else CONFIRMED_TTL_SECONDS)
    logger.info(
        "standings.computed",
        year=year,
        as_of_round=result.as_of_round,
        provisional=result.provisional,
        drivers=len(result.drivers),
    )
    return result
