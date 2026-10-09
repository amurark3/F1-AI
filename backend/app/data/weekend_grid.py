"""Resolve which drivers a race prediction should cover.

Four sources answer "who is on the grid", in descending order of authority:

1. **The weekend entry list** (:mod:`app.data.session_entries`) — observed fact
   once any session has run. It is the only source that knows about a
   mid-season seat change or a Thursday withdrawal.
2. **Curated adjustments** (:mod:`app.data.driver_availability`) — the manual
   bridge for the window before the first session, when nothing is observed.
   Applied on top of whichever roster below is used.
3. **The previous weekend's entry list** — who was actually in the cars last
   time out. The best guess at this weekend's lineup until it is observed, so a
   grid built on it is labelled provisional.
4. **The season championship roster** — a last resort that describes who has
   raced this season, not who is racing this weekend. Once a stand-in has
   driven it holds both the stand-in and the driver they replaced, so it can
   list more drivers than there are seats.

The previous behaviour used (4) unconditionally and back-filled *every*
championship entrant missing from the session, which re-inserted a withdrawn
driver at the back of the grid even after the real entry list said otherwise.
Timed drivers are now filtered against the resolved roster and back-fill is
limited to it, so an entry list that shrinks actually shrinks the grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.data.session_entries import UNAVAILABLE, WeekendEntryList

if TYPE_CHECKING:
    from app.data.driver_availability import WeekendAvailability

logger = structlog.get_logger()

SOURCE_ENTRY_LIST = "weekend_entry_list"
SOURCE_PREVIOUS_ENTRY_LIST = "previous_weekend_entry_list"
SOURCE_CHAMPIONSHIP = "championship_position"
SOURCE_MANUAL_ADJUSTMENT = "manual_entry_adjustment"

# Where a driver with no championship entry sorts when the grid is ordered by
# championship position — behind every ranked driver, in code order.
UNRANKED_POSITION = 999


@dataclass(frozen=True)
class RosterDriver:
    """A driver the prediction should cover, before any scoring."""

    code: str
    name: str
    team: str
    championship_position: int = UNRANKED_POSITION


@dataclass(frozen=True)
class EntryLists:
    """The observed lineups for a weekend: its own, and the previous one's.

    ``previous`` is only a provisional stand-in while ``current`` is
    unavailable — before the weekend's first session has produced timing data.
    """

    current: WeekendEntryList = UNAVAILABLE
    previous: WeekendEntryList = UNAVAILABLE


@dataclass(frozen=True)
class GridRoster:
    """The resolved grid plus everything the caller must report about it."""

    drivers: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    data_sources: tuple[str, ...] = ()
    provisional: bool = False


@dataclass(frozen=True)
class _BaseRoster:
    """The roster chosen before curated adjustments, and how to report it."""

    drivers: tuple[RosterDriver, ...]
    source: str | None
    provisional: bool
    warning: str | None = None


def _roster_from_entry_list(entry_list: WeekendEntryList, championship: list[dict]) -> tuple[RosterDriver, ...]:
    """Entry-list drivers, enriched with championship position for ordering."""
    positions = {row["code"]: int(row["position"]) for row in championship if row.get("code")}
    return tuple(
        RosterDriver(
            code=entry.code,
            name=entry.name,
            team=entry.team,
            championship_position=positions.get(entry.code, UNRANKED_POSITION),
        )
        for entry in entry_list.entries
    )


def _roster_from_championship(championship: list[dict]) -> tuple[RosterDriver, ...]:
    return tuple(
        RosterDriver(
            code=row["code"],
            name=row.get("name") or row["code"],
            team=row.get("team") or "",
            championship_position=int(row.get("position") or UNRANKED_POSITION),
        )
        for row in championship
        if row.get("code")
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


def _base_roster(
    entry_list: WeekendEntryList,
    previous_entry_list: WeekendEntryList,
    championship: list[dict],
) -> _BaseRoster:
    """Pick the most authoritative roster source that has an answer."""
    if entry_list.available:
        return _BaseRoster(
            drivers=_roster_from_entry_list(entry_list, championship),
            source=SOURCE_ENTRY_LIST,
            provisional=False,
        )

    if previous_entry_list.available:
        return _BaseRoster(
            drivers=_roster_from_entry_list(previous_entry_list, championship),
            source=SOURCE_PREVIOUS_ENTRY_LIST,
            provisional=True,
            warning=(
                "Entry list not published yet — provisional lineup carried over "
                "from the previous race weekend; a lineup change announced since "
                "may not be shown"
            ),
        )

    drivers = _roster_from_championship(championship)
    if not drivers:
        return _BaseRoster(drivers=(), source=None, provisional=True)
    return _BaseRoster(
        drivers=drivers,
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
    base = _base_roster(entry_lists.current, entry_lists.previous, championship_roster)
    roster = base.drivers
    provisional = base.provisional
    data_sources: list[str] = [base.source] if base.source else []
    warnings: list[str] = [base.warning] if base.warning else []

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
    )

    return GridRoster(
        drivers=(*kept_timed, *back_filled),
        warnings=tuple(warnings),
        data_sources=tuple(data_sources),
        provisional=provisional,
    )
