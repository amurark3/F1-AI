"""Resolve which drivers a race prediction should cover.

Four sources answer "who is on the grid", in descending order of authority:

1. **The weekend entry list** (:mod:`app.data.session_entries`) — observed fact
   once a session other than FP1 has run. It is the only source that knows
   about a mid-season seat change or a Thursday withdrawal.
2. **Curated adjustments** (:mod:`app.data.driver_availability`) — the manual
   bridge for the window before the first session, when nothing is observed.
   Applied on top of whichever roster below is used.
3. **The previous weekend's entry list** — who was actually in the cars last
   time out. The best guess at this weekend's lineup until it is observed, so a
   grid built on it is labelled provisional. A stand-in on it keeps the car,
   with the seat marked TBC: Hirakawa raced Ocon's Haas in Mexico City, and
   nobody knows who drives it in São Paulo until that entry list is out.
4. **The season championship roster** — a last resort that describes who has
   raced this season, not who is racing this weekend. Once a stand-in has
   driven it holds both the stand-in and the driver they replaced, so it is
   cut to the two drivers who raced each team's cars most recently
   (:mod:`app.data.season_seats`).

Whatever the source, a real grid has at most two cars per team and 22 in all.
:func:`roster_violation` says when a resolved grid breaks that, so the caller
can refuse to publish it.

The previous behaviour used (4) unconditionally and back-filled *every*
championship entrant missing from the session, which re-inserted a withdrawn
driver at the back of the grid even after the real entry list said otherwise.
Timed drivers are now filtered against the resolved roster and back-fill is
limited to it, so an entry list that shrinks actually shrinks the grid.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.data.season_seats import CARS_PER_TEAM, SeasonSeat, current_holders, stand_ins, team_key
from app.data.session_entries import UNAVAILABLE, WeekendEntryList

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from app.data.driver_availability import WeekendAvailability

logger = structlog.get_logger()

SOURCE_ENTRY_LIST = "weekend_entry_list"
SOURCE_PREVIOUS_ENTRY_LIST = "previous_weekend_entry_list"
SOURCE_CHAMPIONSHIP = "championship_position"
SOURCE_MANUAL_ADJUSTMENT = "manual_entry_adjustment"

# Where a driver with no championship entry sorts when the grid is ordered by
# championship position — behind every ranked driver, in code order.
UNRANKED_POSITION = 999

# The 2026 grid: eleven teams of two cars.
MAX_GRID_CARS = 22


@dataclass(frozen=True)
class RosterDriver:
    """A driver the prediction should cover, before any scoring."""

    code: str
    name: str
    team: str
    championship_position: int = UNRANKED_POSITION
    # Why the driver's seat is unconfirmed; ``None`` when it is not in doubt.
    seat_tbc_reason: str | None = None


@dataclass(frozen=True)
class EntryLists:
    """The observed lineups for a weekend, and who has raced each team's cars.

    ``previous`` is only a provisional stand-in while ``current`` is
    unavailable — before the weekend's first counted session. ``seats`` are
    the season's race starts before this round (f1db): they tell a team's
    regular drivers from a stand-in, and cut the championship fallback to the
    cars' current holders.
    """

    current: WeekendEntryList = UNAVAILABLE
    previous: WeekendEntryList = UNAVAILABLE
    seats: tuple[SeasonSeat, ...] = ()


@dataclass(frozen=True)
class GridRoster:
    """The resolved grid plus everything the caller must report about it."""

    drivers: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    data_sources: tuple[str, ...] = ()
    provisional: bool = False


@dataclass(frozen=True)
class RosterViolation:
    """Why a resolved grid cannot be a real one."""

    cars: int
    # (team, driver codes) for each team with more cars than it enters.
    over_limit: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def describe(self) -> str:
        problems = [f"{self.cars} cars for {MAX_GRID_CARS} places on the grid"] if self.cars > MAX_GRID_CARS else []
        problems.extend(f"{team} has {len(codes)} cars ({', '.join(codes)})" for team, codes in self.over_limit)
        return "; ".join(problems)


@dataclass(frozen=True)
class _BaseRoster:
    """The roster chosen before curated adjustments, and how to report it."""

    drivers: tuple[RosterDriver, ...]
    source: str | None
    provisional: bool
    warning: str | None = None


def _roster_from_entry_list(entry_list: WeekendEntryList, championship: list[dict]) -> tuple[RosterDriver, ...]:
    """Entry-list drivers, enriched from the championship for names and ordering.

    f1db's name is canonical ("Nico Hülkenberg", where OpenF1 has
    "HULKENBERG"), and its team stands in when the feed left a car's blank.
    """
    known = {row["code"]: row for row in championship if row.get("code")}
    return tuple(
        RosterDriver(
            code=entry.code,
            name=known.get(entry.code, {}).get("name") or entry.name,
            team=entry.team or known.get(entry.code, {}).get("team") or "",
            championship_position=int(known.get(entry.code, {}).get("position") or UNRANKED_POSITION),
        )
        for entry in entry_list.entries
    )


def _roster_from_championship(championship: list[dict], seats: tuple[SeasonSeat, ...]) -> tuple[RosterDriver, ...]:
    """The championship's drivers who hold a car now, or all of them without race starts to tell."""
    holders = current_holders(seats)
    return tuple(
        RosterDriver(
            code=row["code"],
            name=row.get("name") or row["code"],
            team=row.get("team") or "",
            championship_position=int(row.get("position") or UNRANKED_POSITION),
        )
        for row in championship
        if row.get("code") and (not holders or row["code"] in holders)
    )


def _seat_tbc_reason(driver: RosterDriver, replaced: SeasonSeat, event: str) -> str:
    where = f" at the {event}" if event else ""
    return (
        f"{driver.name} raced {driver.team}'s car{where} in place of {replaced.name}; "
        f"the model keeps {driver.name} in the seat until this weekend's entry list is published"
    )


def _flag_stand_ins(
    roster: tuple[RosterDriver, ...], seats: tuple[SeasonSeat, ...], event: str
) -> tuple[RosterDriver, ...]:
    """Mark the seat of every stand-in carried over from an earlier weekend as TBC."""
    replaced = stand_ins(((driver.code, driver.team) for driver in roster), seats)
    return tuple(
        replace(driver, seat_tbc_reason=_seat_tbc_reason(driver, replaced[driver.code], event))
        if driver.code in replaced
        else driver
        for driver in roster
    )


def _apply_adjustments(
    roster: tuple[RosterDriver, ...],
    availability: WeekendAvailability,
) -> tuple[RosterDriver, ...]:
    """Drop withdrawn drivers and add named replacements not already present."""
    withdrawn = availability.withdrawn
    if not withdrawn:
        return roster

    kept = tuple(driver for driver in roster if driver.code not in withdrawn)
    present = {driver.code for driver in kept}
    added = tuple(
        RosterDriver(
            code=adjustment.replacement_code,
            name=adjustment.replacement_name or adjustment.replacement_code,
            team=adjustment.replacement_team,
        )
        for adjustment in availability.replacements
        if adjustment.replacement_code not in present
    )
    return kept + added


def _base_roster(entry_lists: EntryLists, championship: list[dict]) -> _BaseRoster:
    """Pick the most authoritative roster source that has an answer.

    A provisional roster is an earlier weekend's lineup, so a stand-in on it
    may not be in the car this time: their seat is flagged TBC.
    """
    if entry_lists.current.available:
        return _BaseRoster(
            drivers=_roster_from_entry_list(entry_lists.current, championship),
            source=SOURCE_ENTRY_LIST,
            provisional=False,
        )

    if entry_lists.previous.available:
        drivers = _roster_from_entry_list(entry_lists.previous, championship)
        return _BaseRoster(
            drivers=_flag_stand_ins(drivers, entry_lists.seats, entry_lists.previous.event),
            source=SOURCE_PREVIOUS_ENTRY_LIST,
            provisional=True,
            warning=(
                "Entry list not published yet — provisional lineup carried over "
                "from the previous race weekend; a lineup change announced since "
                "may not be shown"
            ),
        )

    drivers = _roster_from_championship(championship, entry_lists.seats)
    if not drivers:
        return _BaseRoster(drivers=(), source=None, provisional=True)
    return _BaseRoster(
        drivers=_flag_stand_ins(drivers, entry_lists.seats, ""),
        source=SOURCE_CHAMPIONSHIP,
        provisional=True,
        warning=(
            "Entry list not published yet — provisional lineup from the "
            "season's championship entrants; a driver withdrawn this "
            "weekend may still be shown"
        ),
    )


def _sorted_roster(roster: tuple[RosterDriver, ...]) -> tuple[RosterDriver, ...]:
    return tuple(sorted(roster, key=lambda driver: (driver.championship_position, driver.code)))


def _seat_status(driver: RosterDriver) -> dict:
    return {"seat_tbc": driver.seat_tbc_reason is not None, "seat_tbc_reason": driver.seat_tbc_reason}


def _timed_entry(driver: dict, roster_by_code: dict[str, RosterDriver]) -> dict:
    """A driver with a session position, with entry-list name/team preferred.

    The entry list carries the seat a driver is in *this* weekend, which the
    championship join can get wrong after a mid-season move. Only called for
    drivers already in the roster — the caller drops the rest and says so.
    """
    known = roster_by_code[driver["driver_code"]]
    return {
        **driver,
        "driver_name": known.name or driver.get("driver_name", ""),
        "team": known.team or driver.get("team", ""),
        **_seat_status(known),
    }


def resolve_grid(
    timed_drivers: list[dict],
    championship_roster: list[dict],
    entry_lists: EntryLists,
    availability: WeekendAvailability,
) -> GridRoster:
    """Build the driver list a prediction should score.

    Args:
        timed_drivers: Drivers with a qualifying/practice position, in order.
        championship_roster: ``driver_standings_detailed`` rows for the season.
        entry_lists: The weekend's observed entry list, possibly unavailable,
            and the most recent weekend's, used as the provisional lineup
            while the weekend's own is unavailable.
        availability: Curated adjustments recorded for this round.

    Returns:
        The resolved grid, plus the warnings and data sources that make its
        provenance visible to the caller.
    """
    base = _base_roster(entry_lists, championship_roster)
    roster = base.drivers
    provisional = base.provisional
    data_sources: list[str] = [base.source] if base.source else []
    warnings: list[str] = [base.warning] if base.warning else []
    warnings.extend(f"Seat TBC: {driver.seat_tbc_reason}" for driver in roster if driver.seat_tbc_reason)

    if not availability.ok:
        warnings.append(
            "Driver availability adjustments could not be read; a recorded withdrawal may not be reflected in this grid"
        )
    elif availability.adjustments:
        roster = _apply_adjustments(roster, availability)
        data_sources.append(SOURCE_MANUAL_ADJUSTMENT)
        warnings.extend(availability.notes)

    if not roster:
        # No roster source answered. Scoring the timed drivers alone is still
        # better than returning nothing, and the caller reports the gap.
        return GridRoster(
            drivers=tuple(dict(driver) for driver in timed_drivers),
            warnings=(*warnings, "No entry list or championship roster available for this round"),
            data_sources=tuple(data_sources),
            provisional=True,
        )

    roster_by_code = {driver.code: driver for driver in roster}
    kept_timed = [
        _timed_entry(driver, roster_by_code) for driver in timed_drivers if driver["driver_code"] in roster_by_code
    ]
    dropped = len(timed_drivers) - len(kept_timed)
    if dropped:
        warnings.append(f"{dropped} driver(s) with session times are not in the entry list and were excluded")

    present = {driver["driver_code"] for driver in kept_timed}
    missing = [driver for driver in _sorted_roster(roster) if driver.code not in present]

    # Back-filled drivers line up behind the slowest actual qualifier (or from
    # P1 when no session has run), in championship order, so they start from a
    # realistic slot rather than an arbitrary one.
    next_pos = max((driver.get("position", 0) for driver in kept_timed), default=0) + 1
    back_filled: list[dict] = []
    for driver in missing:
        back_filled.append(
            {
                "driver_code": driver.code,
                "driver_name": driver.name,
                "team": driver.team,
                "position": next_pos,
                "no_qualifying_time": True,
                **_seat_status(driver),
            }
        )
        next_pos += 1

    if back_filled and kept_timed:
        warnings.append(f"{len(back_filled)} entered driver(s) had no session time; included at the back of the grid")

    logger.info(
        "weekend_grid.resolved",
        entry_list_session=entry_lists.current.session,
        roster_source=base.source,
        provisional=provisional,
        timed=len(kept_timed),
        back_filled=len(back_filled),
        withdrawn=sorted(availability.withdrawn),
        seat_tbc=sorted(driver.code for driver in roster if driver.seat_tbc_reason),
    )

    return GridRoster(
        drivers=(*kept_timed, *back_filled),
        warnings=tuple(warnings),
        data_sources=tuple(data_sources),
        provisional=provisional,
    )


def roster_violation(drivers: Iterable[Mapping]) -> RosterViolation | None:
    """Why ``drivers`` cannot be a real grid, or ``None`` when they can.

    At most two cars per team and 22 in all. A car whose team is unknown counts
    toward the total only: blank names are not one team.
    """
    cars = tuple(drivers)
    teams = Counter(team_key(car.get("team") or "") for car in cars)
    over = sorted(key for key, count in teams.items() if key and count > CARS_PER_TEAM)
    over_limit = tuple(
        (
            next(car["team"] for car in cars if team_key(car.get("team") or "") == key),
            tuple(sorted(car["driver_code"] for car in cars if team_key(car.get("team") or "") == key)),
        )
        for key in over
    )
    if len(cars) <= MAX_GRID_CARS and not over_limit:
        return None
    return RosterViolation(cars=len(cars), over_limit=over_limit)
