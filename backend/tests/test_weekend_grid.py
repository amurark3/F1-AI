"""Tests for weekend grid resolution (app.data.weekend_grid).

The behaviour under test: a race prediction covers the drivers entered for
*that weekend*. The regression that motivated this module put a driver
withdrawn with a wrist injury on the predicted grid at P2, because the grid was
built from the season championship table and every championship entrant absent
from the session was back-filled onto it.
"""

import pytest

from app.data.driver_availability import (
    STATUS_OUT,
    DriverAdjustment,
    WeekendAvailability,
)
from app.data.session_entries import UNAVAILABLE, EntryListDriver, WeekendEntryList
from app.data.weekend_grid import (
    SOURCE_CHAMPIONSHIP,
    SOURCE_ENTRY_LIST,
    SOURCE_MANUAL_ADJUSTMENT,
    SOURCE_PREVIOUS_ENTRY_LIST,
    EntryLists,
    resolve_grid,
)

CHAMPIONSHIP = [
    {"code": "ANT", "name": "Kimi Antonelli", "team": "Mercedes", "position": 1},
    {"code": "HAM", "name": "Lewis Hamilton", "team": "Ferrari", "position": 2},
    {"code": "HAD", "name": "Isack Hadjar", "team": "Red Bull", "position": 8},
    {"code": "LIN", "name": "Arvid Lindblad", "team": "Racing Bulls", "position": 11},
]


def codes(grid):
    return [driver["driver_code"] for driver in grid.drivers]


def withdrawal(driver_code, replacement_code="", replacement_name="", replacement_team=""):
    return WeekendAvailability(
        adjustments=(
            DriverAdjustment(
                driver_code=driver_code,
                status=STATUS_OUT,
                reason="wrist injury",
                source="https://example.test/announcement",
                noted_at="2026-08-20T09:00:00+00:00",
                replacement_code=replacement_code,
                replacement_name=replacement_name,
                replacement_team=replacement_team,
            ),
        )
    )


def entry_list(*driver_codes, session="FP1"):
    by_code = {row["code"]: row for row in CHAMPIONSHIP}
    return WeekendEntryList(
        entries=tuple(
            EntryListDriver(
                code=code,
                name=by_code.get(code, {}).get("name", code),
                team=by_code.get(code, {}).get("team", ""),
            )
            for code in driver_codes
        ),
        session=session,
    )


class TestBeforeAnySessionRuns:
    """No entry list exists yet, so the grid is provisional and says so."""

    def test_falls_back_to_championship_and_flags_it(self):
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(UNAVAILABLE), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM", "HAD", "LIN"]
        assert grid.provisional is True
        assert SOURCE_CHAMPIONSHIP in grid.data_sources
        assert any("provisional lineup" in warning for warning in grid.warnings)

    def test_curated_withdrawal_removes_the_driver(self):
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(UNAVAILABLE), withdrawal("HAD"))

        assert "HAD" not in codes(grid)
        assert SOURCE_MANUAL_ADJUSTMENT in grid.data_sources
        assert any("HAD withdrawn (wrist injury)" in warning for warning in grid.warnings)

    def test_named_replacement_takes_the_seat(self):
        grid = resolve_grid(
            [], CHAMPIONSHIP, EntryLists(UNAVAILABLE), withdrawal("HAD", "DUN", "Ayumu Iwasa", "Red Bull")
        )

        assert "HAD" not in codes(grid)
        assert "DUN" in codes(grid)
        stand_in = next(d for d in grid.drivers if d["driver_code"] == "DUN")
        assert stand_in["team"] == "Red Bull"
        assert stand_in["driver_name"] == "Ayumu Iwasa"

    def test_replacement_already_racing_is_not_duplicated(self):
        grid = resolve_grid(
            [], CHAMPIONSHIP, EntryLists(UNAVAILABLE), withdrawal("HAD", "LIN", "Arvid Lindblad", "Racing Bulls")
        )

        assert codes(grid).count("LIN") == 1

    def test_unreadable_adjustments_are_reported_not_ignored(self):
        availability = WeekendAvailability(ok=False, error="connection refused")
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(UNAVAILABLE), availability)

        assert any("could not be read" in warning for warning in grid.warnings)


class TestCarriedOverFromThePreviousWeekend:
    """Before this weekend's entry list exists, the last weekend's lineup is used.

    The championship table lists everyone who has raced this season, so after a
    stand-in drives it holds both the stand-in and the driver they replaced —
    23 drivers for 22 seats. The previous weekend's entry list holds only the
    people actually in the cars.
    """

    def test_stand_in_who_no_longer_races_is_not_predicted(self):
        championship_with_stand_in = [
            *CHAMPIONSHIP,
            {"code": "TSU", "name": "Yuki Tsunoda", "team": "Racing Bulls", "position": 20},
        ]
        previous = entry_list("ANT", "HAM", "HAD", "LIN", session="Q")
        grid = resolve_grid([], championship_with_stand_in, EntryLists(UNAVAILABLE, previous), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM", "HAD", "LIN"]

    def test_carried_over_grid_is_provisional_and_says_where_it_came_from(self):
        grid = resolve_grid(
            [], CHAMPIONSHIP, EntryLists(UNAVAILABLE, entry_list("ANT", "HAM", session="Q")), WeekendAvailability()
        )

        assert grid.provisional is True
        assert SOURCE_PREVIOUS_ENTRY_LIST in grid.data_sources
        assert SOURCE_CHAMPIONSHIP not in grid.data_sources
        assert any("carried over from the previous race weekend" in w for w in grid.warnings)

    def test_this_weekends_entry_list_wins_over_the_previous_one(self):
        grid = resolve_grid(
            [],
            CHAMPIONSHIP,
            EntryLists(entry_list("ANT", "HAM", "LIN"), entry_list("ANT", "HAM", "HAD", session="Q")),
            WeekendAvailability(),
        )

        assert codes(grid) == ["ANT", "HAM", "LIN"]
        assert grid.provisional is False
        assert SOURCE_PREVIOUS_ENTRY_LIST not in grid.data_sources

    def test_curated_withdrawal_applies_to_the_carried_over_lineup(self):
        grid = resolve_grid(
            [],
            CHAMPIONSHIP,
            EntryLists(UNAVAILABLE, entry_list("ANT", "HAM", "HAD", "LIN", session="Q")),
            withdrawal("HAD", "TSU", "Yuki Tsunoda", "Racing Bulls"),
        )

        assert "HAD" not in codes(grid)
        assert "TSU" in codes(grid)

    def test_championship_is_the_fallback_when_neither_entry_list_exists(self):
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(UNAVAILABLE, UNAVAILABLE), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM", "HAD", "LIN"]
        assert SOURCE_CHAMPIONSHIP in grid.data_sources


class TestOnceASessionHasRun:
    """The weekend's own entry list is authoritative over the season table."""

    def test_championship_entrant_absent_from_entry_list_is_not_back_filled(self):
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAM", "LIN")), WeekendAvailability())

        assert "HAD" not in codes(grid)
        assert grid.provisional is False
        assert SOURCE_ENTRY_LIST in grid.data_sources

    def test_entered_driver_without_a_time_still_gets_predicted(self):
        timed = [{"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 1}]
        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAM", "LIN")), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM", "LIN"]
        back_filled = [d for d in grid.drivers if d.get("no_qualifying_time")]
        assert {d["driver_code"] for d in back_filled} == {"HAM", "LIN"}

    def test_back_filled_drivers_line_up_behind_the_slowest_timed_driver(self):
        timed = [
            {"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 1},
            {"driver_code": "HAM", "driver_name": "Lewis Hamilton", "team": "Ferrari", "position": 2},
        ]
        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAM", "LIN")), WeekendAvailability())

        assert [d["position"] for d in grid.drivers] == [1, 2, 3]

    def test_back_fill_order_follows_championship_position(self):
        roster = entry_list("LIN", "HAM", "ANT")
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(roster), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM", "LIN"]

    def test_driver_with_no_championship_entry_sorts_last(self):
        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(entry_list("DUN", "ANT")), WeekendAvailability())

        assert codes(grid) == ["ANT", "DUN"]

    def test_entry_list_team_wins_over_a_stale_session_team(self):
        timed = [{"driver_code": "HAM", "driver_name": "Lewis Hamilton", "team": "Mercedes", "position": 1}]
        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entry_list("HAM")), WeekendAvailability())

        assert grid.drivers[0]["team"] == "Ferrari"

    def test_driver_withdrawn_after_setting_a_time_is_removed(self):
        timed = [
            {"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 1},
            {"driver_code": "HAD", "driver_name": "Isack Hadjar", "team": "Red Bull", "position": 2},
        ]
        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAD")), withdrawal("HAD"))

        assert "HAD" not in codes(grid)
        assert any("not in the entry list and were excluded" in w for w in grid.warnings)


class TestNoRosterAtAll:
    def test_timed_drivers_are_still_scored_and_the_gap_reported(self):
        timed = [{"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 1}]
        grid = resolve_grid(timed, [], EntryLists(UNAVAILABLE), WeekendAvailability())

        assert codes(grid) == ["ANT"]
        assert grid.provisional is True
        assert any("No entry list or championship roster" in w for w in grid.warnings)

    def test_empty_everything_yields_an_empty_grid(self):
        grid = resolve_grid([], [], EntryLists(UNAVAILABLE), WeekendAvailability())

        assert grid.drivers == ()


class TestEntryListValueObject:
    def test_unavailable_is_not_available(self):
        assert UNAVAILABLE.available is False
        assert UNAVAILABLE.codes == frozenset()

    def test_a_session_with_no_entries_is_not_available(self):
        assert WeekendEntryList(entries=(), session="FP1").available is False

    @pytest.mark.parametrize("session", ["Q", "FP1"])
    def test_codes_and_lookup(self, session):
        resolved = entry_list("ANT", "HAM", session=session)

        assert resolved.available is True
        assert resolved.codes == {"ANT", "HAM"}
        assert resolved.by_code()["HAM"].team == "Ferrari"


class TestAdjustmentsThatWithdrawNobody:
    def test_an_adjustment_that_is_not_a_withdrawal_leaves_the_roster_whole(self):
        """Only ``out`` is a status today. A future one (say, a doubtful driver)
        must be reported without quietly removing anyone from the grid."""
        doubtful = WeekendAvailability(
            adjustments=(
                DriverAdjustment(
                    driver_code="HAM",
                    status="doubtful",
                    reason="illness",
                    source="https://example.test/announcement",
                    noted_at="2026-08-20T09:00:00+00:00",
                ),
            )
        )

        grid = resolve_grid([], CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAM", "LIN")), doubtful)

        assert codes(grid) == ["ANT", "HAM", "LIN"]
        assert SOURCE_MANUAL_ADJUSTMENT in grid.data_sources
