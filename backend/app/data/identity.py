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
* Drivers resolve through ``resolve_driver`` / ``canonical_driver``: by f1db
  id, then code, then car number, then folded name, the code and number only
  within the season. A key that fits several drivers settles nothing, and none
  of them is picked.
* Nothing is copied into Postgres. The directory is read from the local f1db
  file and cached per (year, f1db release), so it refreshes with the data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import groupby, takewhile
from operator import itemgetter
import threading
from types import MappingProxyType
from typing import TYPE_CHECKING, TypedDict, Unpack
import unicodedata

from app.data import f1db_source

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
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
    SELECT rd.driver_id AS id, d.name AS name, d.first_name AS first_name, d.last_name AS last_name,
           d.abbreviation AS code, rd.driver_number AS number, rd.constructor_id AS team_id
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ? AND rd.type IN ('QUALIFYING_RESULT', 'STARTING_GRID_POSITION', 'RACE_RESULT')
    ORDER BY r.round
"""

# Everyone entered to race, including drivers with no session yet.
_ENTRANT_QUERY = """
    SELECT sed.driver_id AS id, d.name AS name, d.first_name AS first_name, d.last_name AS last_name,
           d.abbreviation AS code, d.permanent_number AS number, sed.constructor_id AS team_id
    FROM season_entrant_driver sed
    JOIN driver d ON d.id = sed.driver_id
    WHERE sed.year = ? AND sed.test_driver = 0
    ORDER BY d.name
"""

# Everyone who drove in any session of the season, practice included: a Friday
# rookie's feed row has to resolve to them, or make its code ambiguous (VER is
# Vergne in the 2014 races and Max Verstappen in FP1), never to someone else.
_PARTICIPANT_QUERY = """
    SELECT rd.driver_id AS id, d.name AS name, d.first_name AS first_name, d.last_name AS last_name,
           d.abbreviation AS code, rd.driver_number AS number, rd.constructor_id AS team_id
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ?
    ORDER BY r.round
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
    #: The display name ("Carlos Sainz Jr."). Never build one from the parts below.
    name: str
    code: str | None
    number: int | None
    team_id: str
    #: f1db's name parts. ``first_name`` can be a legal name: Jak Crawford's is "Carlton".
    first_name: str
    last_name: str


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


@dataclass(frozen=True)
class CanonicalDriver:
    """How to print a driver: f1db's identity when the inputs resolve, else the feed's own words.

    Resolved, every field is f1db's (``name`` is ``driver.name``, never the legal
    ``full_name``). Unresolved, ``id`` is ``None``, ``name`` is the feed's name in
    display case, ``last_name`` is the surname the feed shouted (or ``None``) and
    ``code`` is the feed's code.
    """

    name: str
    last_name: str | None
    code: str | None
    id: str | None

    @property
    def resolved(self) -> bool:
        return self.id is not None


class DriverKeys(TypedDict, total=False):
    """What a feed row may name a driver by; ``resolve_driver`` tries them in this order."""

    driver_id: str | None
    code: str | None
    #: The number the car raced with that season, as an int or digits.
    number: int | str | None
    name: str | None


@dataclass(frozen=True)
class _DriverIndex:
    """One season's drivers by each key a feed names them with; a key lists every driver it fits."""

    entries: Mapping[str, DriverEntry]
    codes: Mapping[str, tuple[str, ...]]
    numbers: Mapping[int, tuple[str, ...]]
    names: Mapping[str, tuple[str, ...]]


# Surname particles f1db writes in lower case after a given name ("Nyck de Vries",
# "Pedro de la Rosa", "Giedo van der Garde") and capitalises when the surname
# stands alone ("De Vries").
_PARTICLES = frozenset({"da", "de", "der", "di", "la", "van", "von"})

_cache: dict[tuple[int, str | None], SeasonDirectory] = {}
_index_cache: dict[tuple[int, str | None], _DriverIndex] = {}
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


def _latest_entries(rows: Iterable[sqlite3.Row]) -> tuple[DriverEntry, ...]:
    """One entry per driver, from their last row: rows come in round order."""
    latest = {
        row["id"]: DriverEntry(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            number=as_int(row["number"]),
            team_id=row["team_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
        )
        for row in rows
    }
    return tuple(latest.values())


def _drivers(conn: sqlite3.Connection, year: int) -> tuple[DriverEntry, ...]:
    # The entry list first, then session rows in round order on top of it, so
    # each driver keeps their latest team and number and an entrant who has
    # not driven yet is still listed.
    return _latest_entries(
        [*conn.execute(_ENTRANT_QUERY, (year,)).fetchall(), *conn.execute(_ENTRY_QUERY, (year,)).fetchall()]
    )


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


def _cached[T](store: dict[tuple[int, str | None], T], year: int, read: Callable[[int], T]) -> T:
    """``read(year)``, kept in ``store`` until f1db's next release."""
    key = (year, f1db_source.installed_version())
    with _cache_lock:
        cached = store.get(key)
    if cached is not None:
        return cached
    value = read(year)
    with _cache_lock:
        store[key] = value
    return value


def _read_directory(year: int) -> SeasonDirectory:
    with f1db_source.connect() as conn:
        return SeasonDirectory(year=year, drivers=_drivers(conn, year), teams=_teams(conn, year))


def season_directory(year: int) -> SeasonDirectory:
    """Every driver and team of ``year``, cached until f1db's next release."""
    return _cached(_cache, year, _read_directory)


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


def _group[K](pairs: Iterable[tuple[K | None, str]]) -> Mapping[K, tuple[str, ...]]:
    """Each key with every driver id it fits; blank keys are dropped."""
    ordered = sorted({(key, driver_id) for key, driver_id in pairs if key is not None and key != ""})
    return MappingProxyType(
        {key: tuple(driver_id for _key, driver_id in group) for key, group in groupby(ordered, key=itemgetter(0))}
    )


def _read_index(year: int) -> _DriverIndex:
    directory = season_directory(year).drivers
    with f1db_source.connect() as conn:
        rows = conn.execute(_PARTICIPANT_QUERY, (year,)).fetchall()
    # The directory's entry wins for a driver in both: it is the record the season's pages show.
    entries = {entry.id: entry for entry in (*_latest_entries(rows), *directory)}
    return _DriverIndex(
        entries=MappingProxyType(entries),
        codes=_group((fold(entry.code or ""), entry.id) for entry in entries.values()),
        # Every number raced that season, plus an entrant's permanent number before their first session.
        numbers=_group([*((as_int(row["number"]), row["id"]) for row in rows), *((e.number, e.id) for e in directory)]),
        names=_group(
            (key, entry.id) for entry in entries.values() for key in (fold(entry.name), fold(entry.last_name or ""))
        ),
    )


def _driver_index(year: int) -> _DriverIndex:
    return _cached(_index_cache, year, _read_index)


def _wanted(keys: DriverKeys) -> tuple[str, str, int | None, str]:
    """The keys in lookup form; an unknown keyword is a caller's typo and fails loudly."""
    unknown = sorted(set(keys) - set(DriverKeys.__annotations__))
    if unknown:
        msg = f"unknown driver keys: {', '.join(unknown)}"
        raise TypeError(msg)
    return (
        (keys.get("driver_id") or "").strip(),
        fold(keys.get("code") or ""),
        as_int(keys.get("number")),
        fold(keys.get("name") or ""),
    )


def resolve_driver(year: int, **keys: Unpack[DriverKeys]) -> DriverEntry | None:
    """The f1db driver a feed row names in ``year``, or ``None``.

    Keys are tried in order: f1db id, three-letter code, car number (the one
    raced that season, not the permanent one), then the name or surname after
    folding case and accents. Each counts only among the drivers of ``year``.
    The first key that fits exactly one driver decides; a key that fits none
    or several is passed over, and no driver is ever picked among several.
    """
    wanted = _wanted(keys)
    if all(key is None or key == "" for key in wanted):
        return None
    index = _driver_index(year)
    wanted_id, wanted_code, wanted_number, wanted_name = wanted
    candidates = (
        (wanted_id,) if wanted_id in index.entries else (),
        index.codes.get(wanted_code, ()),
        index.numbers.get(wanted_number, ()),
        index.names.get(wanted_name, ()),
    )
    return next((index.entries[ids[0]] for ids in candidates if len(ids) == 1), None)


def canonical_driver(year: int, **keys: Unpack[DriverKeys]) -> CanonicalDriver:
    """The identity to print for a feed row: f1db's when it resolves, the feed's own words recased otherwise."""
    entry = resolve_driver(year, **keys)
    if entry is not None:
        return CanonicalDriver(name=entry.name, last_name=entry.last_name, code=entry.code, id=entry.id)
    return feed_driver(**keys)


def feed_driver(**keys: Unpack[DriverKeys]) -> CanonicalDriver:
    """The feed's own words in display case, with no id: what a row prints when nobody is resolved.

    Reads nothing, so an emit point can fall back to it when f1db cannot be read.
    """
    text = keys.get("name") or ""
    return CanonicalDriver(
        name=normalize_feed_name(text),
        last_name=_feed_surname(text),
        code=(keys.get("code") or "").strip().upper() or None,
        id=None,
    )


def normalize_feed_name(text: str) -> str:
    """A feed's shouted name in display case, inventing nothing ("Lando NORRIS" -> "Lando Norris").

    Only words written in capitals change. Particles after a given name go
    lower case the way f1db writes them ("Nyck DE VRIES" -> "Nyck de Vries").
    """
    return " ".join(_display_word(word, follows=position > 0) for position, word in enumerate(text.split()))


def _display_word(word: str, *, follows: bool) -> str:
    if not word.isupper():
        return word
    if follows and word.lower() in _PARTICLES:
        return word.lower()
    return word.title()


def _feed_surname(text: str) -> str | None:
    """The surname a feed marks by shouting it after the given name ("Nyck DE VRIES" -> "De Vries")."""
    words = text.split()
    given = tuple(takewhile(lambda word: not word.isupper(), words))
    surname = words[len(given) :]
    if not given or not surname or not all(word.isupper() for word in surname):
        return None
    return normalize_feed_name(" ".join(surname))


def clear_cache() -> None:
    """Drop every cached directory and driver index — for tests."""
    with _cache_lock:
        _cache.clear()
        _index_cache.clear()
