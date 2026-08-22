"""Resolve which drivers a race prediction should cover.

Three sources answer "who is on the grid", in descending order of authority:

1. **The weekend entry list** (:mod:`app.data.session_entries`) — observed fact
   once any session has run. It is the only source that knows about a
   mid-season seat change or a Thursday withdrawal.
2. **Curated adjustments** (:mod:`app.data.driver_availability`) — the manual
   bridge for the window before the first session, when nothing is observed.
3. **The season championship roster** — a fallback that describes who has
   raced this season, not who is racing this weekend. Correct most weekends and
   wrong exactly when a driver is withdrawn, so a grid built on it is labelled
   provisional.

The previous behaviour used (3) unconditionally and back-filled *every*
championship entrant missing from the session, which re-inserted a withdrawn
driver at the back of the grid even after the real entry list said otherwise.
Timed drivers are now filtered against the resolved roster and back-fill is
limited to it, so an entry list that shrinks actually shrinks the grid.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.driver_availability import WeekendAvailability
from app.data.session_entries import WeekendEntryList

logger = structlog.get_logger()

SOURCE_ENTRY_LIST = "weekend_entry_list"
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
class GridRoster:
    """The resolved grid plus everything the caller must report about it."""

    drivers: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    data_sources: tuple[str, ...] = ()
    provisional: bool = False


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


def _sorted_roster(roster: tuple[RosterDriver, ...]) -> tuple[RosterDriver, ...]:
    return tuple(sorted(roster, key=lambda driver: (driver.championship_position, driver.code)))


def _timed_entry(driver: dict, roster_by_code: dict[str, RosterDriver]) -> dict:
    """A driver with a session position, with entry-list name/team preferred.

    The entry list carries the seat a driver is in *this* weekend, which the
    championship join can get wrong after a mid-season move.
    """
    known = roster_by_code.get(driver["driver_code"])
    if known is None:
        return dict(driver)
    return {
        **driver,
        "driver_name": known.name or driver.get("driver_name", ""),
        "team": known.team or driver.get("team", ""),
    }


def resolve_grid(
    timed_drivers: list[dict],
    championship_roster: list[dict],
    entry_list: WeekendEntryList,
    availability: WeekendAvailability,
) -> GridRoster:
    """Build the driver list a prediction should score.

    Args:
        timed_drivers: Drivers with a qualifying/practice position, in order.
        championship_roster: ``driver_standings_detailed`` rows for the season.
        entry_list: The weekend's observed entry list, possibly unavailable.
        availability: Curated adjustments recorded for this round.

    Returns:
        The resolved grid, plus the warnings and data sources that make its
        provenance visible to the caller.
    """
    warnings: list[str] = []
    data_sources: list[str] = []

    if entry_list.available:
        roster = _roster_from_entry_list(entry_list, championship_roster)
        data_sources.append(SOURCE_ENTRY_LIST)
        provisional = False
    else:
        roster = _roster_from_championship(championship_roster)
        provisional = True
        if roster:
            data_sources.append(SOURCE_CHAMPIONSHIP)
            warnings.append(
                "Entry list not published yet — provisional lineup from the "
                "season's championship entrants; a driver withdrawn this "
                "weekend may still be shown"
            )

    if not availability.ok:
        warnings.append(
            "Driver availability adjustments could not be read; a recorded "
            "withdrawal may not be reflected in this grid"
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
        _timed_entry(driver, roster_by_code)
        for driver in timed_drivers
        if driver["driver_code"] in roster_by_code
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
        back_filled.append({
            "driver_code": driver.code,
            "driver_name": driver.name,
            "team": driver.team,
            "position": next_pos,
            "no_qualifying_time": True,
        })
        next_pos += 1

    if back_filled and kept_timed:
        warnings.append(
            f"{len(back_filled)} entered driver(s) had no session time; "
            "included at the back of the grid"
        )

    logger.info(
        "weekend_grid.resolved",
        entry_list_session=entry_list.session,
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
