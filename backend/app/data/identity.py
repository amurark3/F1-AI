"""One season's drivers and teams, keyed by f1db id.

Every source spells the field differently: f1db says "Red Bull", FastF1 "Red
Bull Racing", Jolpica ``red_bull``. Pages that link a name to a driver or team
page need one key that survives all of them, and f1db's ids are it — they are
stable across seasons, where three-letter codes are not (VER is Max, Jos and
Jean-Éric Vergne).

* Display names are f1db ``driver.name`` ("Nico Hülkenberg"), never
  ``full_name``, which is the legal name.
* Team names resolve by **exact** match after folding case and accents, then
  through an alias table. Never by substring: ``"" in "mclaren"`` is true, which
  once scored an empty team string as the championship leader.
* Nothing is copied into Postgres. The directory is read from the local f1db
  file and cached per (year, f1db release), so it refreshes with the data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
from typing import TYPE_CHECKING
import unicodedata

from app.data import f1db_source

if TYPE_CHECKING:
    import sqlite3

# Livery colour per f1db constructor id.
TEAM_COLORS: dict[str, str] = {
    "red-bull": "#3671C6",
    "mclaren": "#FF8000",
    "ferrari": "#E8002D",
    "mercedes": "#27F4D2",
    "aston-martin": "#229971",
    "williams": "#64C4FF",
    "racing-bulls": "#6692FF",
    "haas": "#B6BABD",
    "alpine": "#FF87BC",
    "audi": "#FF0000",
    "cadillac": "#E0D4B8",
    "kick-sauber": "#52E252",
}
NEUTRAL_TEAM_COLOR = "#6B7280"

# Spellings other feeds use, after `fold`. An alias only resolves when its id
# is on that season's grid, so a historical name cannot capture a current team.
TEAM_ALIASES: dict[str, str] = {
    "red bull racing": "red-bull",
    "oracle red bull racing": "red-bull",
    "rb": "racing-bulls",
    "rb f1 team": "racing-bulls",
    "visa cash app rb": "racing-bulls",
    "visa cash app racing bulls": "racing-bulls",
    "haas f1 team": "haas",
    "moneygram haas f1 team": "haas",
    "alpine f1 team": "alpine",
    "bwt alpine f1 team": "alpine",
    "mclaren f1 team": "mclaren",
    "scuderia ferrari": "ferrari",
    "mercedes amg petronas": "mercedes",
    "aston martin aramco": "aston-martin",
    "williams racing": "williams",
    "atlassian williams racing": "williams",
    "audi f1 team": "audi",
    "cadillac f1 team": "cadillac",
    "sauber": "kick-sauber",
    "stake f1 team kick sauber": "kick-sauber",
}

# The sessions that prove a driver raced for a team. Practice is left out so a
# Friday rookie is not listed as part of the line-up.
_ENTRY_QUERY = """
    SELECT rd.driver_id AS id, d.name AS name, d.abbreviation AS code,
           rd.driver_number AS number, rd.constructor_id AS team_id
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ? AND rd.type IN ('QUALIFYING_RESULT', 'STARTING_GRID_POSITION', 'RACE_RESULT')
    ORDER BY r.round
"""

# Everyone entered to race, including drivers with no session yet.
_ENTRANT_QUERY = """
    SELECT sed.driver_id AS id, d.name AS name, d.abbreviation AS code,
           d.permanent_number AS number, sed.constructor_id AS team_id
    FROM season_entrant_driver sed
    JOIN driver d ON d.id = sed.driver_id
    WHERE sed.year = ? AND sed.test_driver = 0
    ORDER BY d.name
"""

_TEAM_QUERY = """
    SELECT c.id AS id, c.name AS name, c.full_name AS full_name
    FROM constructor c
    WHERE c.id IN (SELECT constructor_id FROM season_entrant_driver WHERE year = ? AND test_driver = 0)
"""

_TEAM_STANDING_QUERY = """
    SELECT rcs.constructor_id AS id, rcs.position_number AS position, rcs.points AS points
    FROM race_constructor_standing rcs
    JOIN race r ON r.id = rcs.race_id
    WHERE r.year = ? AND r.round = (
        SELECT MAX(r2.round)
        FROM race_constructor_standing rcs2
        JOIN race r2 ON r2.id = rcs2.race_id
        WHERE r2.year = ?
    )
"""


@dataclass(frozen=True)
class DriverEntry:
    id: str
    name: str
    code: str | None
    number: int | None
    team_id: str


@dataclass(frozen=True)
class TeamEntry:
    id: str
    name: str
    full_name: str
    color: str
    position: int | None
    points: float
    #: Other feeds' spellings, already folded, so a client can resolve them too.
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeasonDirectory:
    year: int
    drivers: tuple[DriverEntry, ...]
    teams: tuple[TeamEntry, ...]

    def as_dict(self) -> dict:
        return {
            "year": self.year,
            "drivers": [asdict(item) for item in self.drivers],
            "teams": [{**asdict(item), "aliases": list(item.aliases)} for item in self.teams],
        }


_cache: dict[tuple[int, str | None], SeasonDirectory] = {}
_cache_lock = threading.Lock()


def fold(text: str) -> str:
    """Case-, accent- and punctuation-insensitive form of a name."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = "".join(char if char.isalnum() else " " for char in stripped.casefold())
    return " ".join(cleaned.split())


def as_int(value: object) -> int | None:
    """An integer column that f1db sometimes stores as text (car numbers)."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def team_color(constructor_id: str) -> str:
    return TEAM_COLORS.get(constructor_id, NEUTRAL_TEAM_COLOR)


def _drivers(conn: sqlite3.Connection, year: int) -> tuple[DriverEntry, ...]:
    # The entry list first, then session rows in round order on top of it, so
    # each driver keeps their latest team and number and an entrant who has
    # not driven yet is still listed.
    rows = [*conn.execute(_ENTRANT_QUERY, (year,)).fetchall(), *conn.execute(_ENTRY_QUERY, (year,)).fetchall()]
    latest: dict[str, DriverEntry] = {}
    for row in rows:
        latest[row["id"]] = DriverEntry(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            number=as_int(row["number"]),
            team_id=row["team_id"],
        )
    return tuple(latest.values())


def _teams(conn: sqlite3.Connection, year: int) -> tuple[TeamEntry, ...]:
    standings = {row["id"]: row for row in conn.execute(_TEAM_STANDING_QUERY, (year, year)).fetchall()}
    teams = []
    for row in conn.execute(_TEAM_QUERY, (year,)).fetchall():
        standing = standings.get(row["id"])
        teams.append(
            TeamEntry(
                id=row["id"],
                name=row["name"],
                full_name=row["full_name"] or row["name"],
                color=team_color(row["id"]),
                position=int(standing["position"]) if standing and standing["position"] is not None else None,
                points=float(standing["points"] or 0) if standing else 0.0,
                aliases=tuple(sorted(alias for alias, team_id in TEAM_ALIASES.items() if team_id == row["id"])),
            )
        )
    # Championship order, with unranked teams last and alphabetical.
    return tuple(sorted(teams, key=lambda team: (team.position is None, team.position or 0, team.name)))


def season_directory(year: int) -> SeasonDirectory:
    """Every driver and team of ``year``, cached until f1db's next release."""
    key = (year, f1db_source.installed_version())
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    with f1db_source.connect() as conn:
        directory = SeasonDirectory(year=year, drivers=_drivers(conn, year), teams=_teams(conn, year))
    with _cache_lock:
        _cache[key] = directory
    return directory


def resolve_team(year: int, name: str) -> str | None:
    """The f1db constructor id ``name`` refers to in ``year``, or ``None``."""
    wanted = fold(name)
    if not wanted:
        return None
    teams = season_directory(year).teams
    for team in teams:
        if wanted in (fold(team.id), fold(team.name), fold(team.full_name)):
            return team.id
    alias = TEAM_ALIASES.get(wanted)
    return alias if alias in {team.id for team in teams} else None


def resolve_team_name(year: int, name: str) -> str | None:
    """f1db's name for the team ``name`` refers to in ``year`` ("Red Bull Racing" -> "Red Bull"), or ``None``."""
    team_id = resolve_team(year, name)
    return next((team.name for team in season_directory(year).teams if team.id == team_id), None)


def clear_cache() -> None:
    """Drop every cached directory — for tests."""
    with _cache_lock:
        _cache.clear()
