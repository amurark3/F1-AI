"""Weekend entry list, read from OpenF1's ``drivers`` list for the weekend's sessions.

Who is racing is a *per-weekend* fact, not a season one. Drivers are withdrawn
for injury, illness or penalty and reserves take the seat, so a grid built from
the season championship table predicts drivers who are not at the track.

OpenF1 lists the cars of every session. How that list is read:

* **Only a session that has started counts.** OpenF1 fills in a weekend's
  drivers days ahead: on 2 Nov 2026 every São Paulo session already listed
  Ocon, the day after Hirakawa raced his Haas in Mexico City and before any
  entry list was out. That is a placeholder, not an entry list.
* **FP1 is never the lineup.** It is where teams run their mandatory rookie
  outings: nine of Mexico City's FP1 cars had a rookie in a race driver's seat,
  Tsolov in Lawson's Racing Bulls among them.
* **The newest session that has run wins.** A withdrawal after FP2 is already
  reflected in qualifying.
* **A blank team is filled from the same car in the weekend's other sessions.**
  The Mexico City race list has no team for Hirakawa's car 50, while
  qualifying names it Haas.
* **Names are f1db's.** OpenF1 writes "Ryo HIRAKAWA" and "Haas F1 Team"; an
  entry prints "Ryō Hirakawa" and "Haas" (:mod:`app.data.canonical_names`).
  The code and car number stay OpenF1's.

Before any session counts, ``load_weekend_entry_list`` reports "unavailable"
rather than guessing, so callers fall back to a provisional roster and label
it as provisional.

This used to read FastF1's session results, which cannot load since F1's live
timing archive started requiring a login (2026-10-15). Every prediction then
fell back to the championship table, which is how the R20 roster reached 23.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.data.openf1.client import OpenF1UnavailableError, new_client
from app.data.openf1.sessions import canonical_entry, entry_list, weekend_sessions
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from collections.abc import Iterable

    import httpx

    from app.data.openf1.sessions import EntryDriver, OpenF1Session

logger = structlog.get_logger()

# Sessions whose cars are not the race lineup: FP1 carries the rookie outings.
ROOKIE_SESSION_CODES = frozenset({"FP1"})

# A resolved entry list is re-read periodically rather than pinned for the life
# of the process: a driver can withdraw between sessions, and the newer session
# is what should then be believed.
ENTRY_LIST_TTL_SECONDS = 1800.0

# An unavailable entry list must never be cached like a resolved one. Doing so
# would pin "the weekend has not started" for the whole process, so the entry
# list would still be missing hours after the cars ran.
ENTRY_LIST_RETRY_SECONDS = 300.0


@dataclass(frozen=True)
class EntryListDriver:
    """One car entered for a race weekend, and who drives it."""

    code: str
    name: str
    team: str
    number: int | None = None


@dataclass(frozen=True)
class WeekendEntryList:
    """The drivers entered for a weekend, and which session said so.

    ``session`` is ``None`` when no session of the weekend has counted yet.
    That is a different state from an empty entry list and callers must treat
    it as "unknown", never as "nobody is racing". ``event`` names the Grand
    Prix, for messages that cite it; the caller that knows the calendar sets it.
    """

    entries: tuple[EntryListDriver, ...] = ()
    session: str | None = None
    event: str = ""

    @property
    def available(self) -> bool:
        return self.session is not None and bool(self.entries)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(entry.code for entry in self.entries)

    def by_code(self) -> dict[str, EntryListDriver]:
        return {entry.code: entry for entry in self.entries}


UNAVAILABLE = WeekendEntryList()

_cache: TtlCache[tuple[int, int], WeekendEntryList] = TtlCache()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sessions_run(sessions: Iterable[OpenF1Session], now: datetime) -> tuple[OpenF1Session, ...]:
    """The weekend's sessions that have started, newest first."""
    started = [session for session in sessions if session.date_start is not None and session.date_start <= now]
    return tuple(sorted(started, key=lambda session: session.date_start or now, reverse=True))


def _fill_teams(
    client: httpx.Client, cars: dict[int, EntryDriver], others: Iterable[OpenF1Session]
) -> dict[int, EntryDriver]:
    """Name each blank team from the same car in the weekend's other sessions, newest first.

    A car number belongs to one driver, so even FP1 can name a team here.
    """
    for session in others:
        blank = [number for number, car in cars.items() if not car.team]
        if not blank:
            break
        named = entry_list(client, session.session_key)
        found = {number: named[number].team for number in blank if number in named and named[number].team}
        cars = {number: replace(car, team=found.get(number, car.team)) for number, car in cars.items()}
    return cars


def _entry(car: EntryDriver, year: int) -> EntryListDriver:
    """One car under f1db's driver and team names, keeping OpenF1's code and number."""
    named = canonical_entry(car, year)
    return EntryListDriver(code=car.code, name=named.name or car.code, team=named.team, number=car.number)


def _read_weekend(client: httpx.Client, year: int, round_num: int) -> WeekendEntryList:
    run = _sessions_run(weekend_sessions(client, year, round_num), _utc_now())
    for session in run:
        if session.code in ROOKIE_SESSION_CODES:
            continue
        cars = entry_list(client, session.session_key)
        if cars:
            cars = _fill_teams(client, cars, (other for other in run if other != session))
            entries = tuple(_entry(car, year) for car in sorted(cars.values(), key=lambda car: car.number))
            return WeekendEntryList(entries=entries, session=session.code)
    return UNAVAILABLE


def load_weekend_entry_list(year: int, round_num: int) -> WeekendEntryList:
    """Return the drivers entered for ``round_num``, from the newest session that counts.

    Returns :data:`UNAVAILABLE` when no session other than FP1 has started, or
    OpenF1 cannot answer (it is closed to everyone while a session is live).
    """
    key = (year, round_num)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    try:
        with new_client() as client:
            result = _read_weekend(client, year, round_num)
    # The calendar lookup reaches FastF1's schedule backend, which raises
    # ValueError/KeyError for a bad season and OSError for a network failure.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("entry_list.openf1_unavailable", year=year, round=round_num, error=str(exc))
        result = UNAVAILABLE

    _cache.put(key, result, ENTRY_LIST_TTL_SECONDS if result.available else ENTRY_LIST_RETRY_SECONDS)
    logger.info(
        "entry_list.loaded" if result.available else "entry_list.unavailable",
        year=year,
        round=round_num,
        session=result.session,
        drivers=len(result.entries),
    )
    return result
