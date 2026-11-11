"""Tests for weekend grid resolution (app.data.weekend_grid).

The behaviour under test: a race prediction covers the drivers entered for
*that weekend*. The regression that motivated this module put a driver
withdrawn with a wrist injury on the predicted grid at P2, because the grid was
built from the season championship table and every championship entrant absent
from the session was back-filled onto it.
"""

import pytest

from app.data.canonical_names import CODE_UNRESOLVED
from app.data.driver_availability import (
    STATUS_OUT,
    DriverAdjustment,
    WeekendAvailability,
)
from app.data.predictions.sessions import _classified_order
from app.data.season_seats import SeasonSeat
from app.data.session_entries import UNAVAILABLE, EntryListDriver, WeekendEntryList
from app.data.weekend_grid import (
    SOURCE_CHAMPIONSHIP,
    SOURCE_ENTRY_LIST,
    SOURCE_MANUAL_ADJUSTMENT,
    SOURCE_PREVIOUS_ENTRY_LIST,
    EntryLists,
    RosterViolation,
    resolve_grid,
    roster_violation,
)
from tests.sao_paulo_2026_support import add_camara_to_f1db, r20_fastf1_qualifying, r20_qualifying_entry_list

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


class TestAQualifierFastF1SentWithoutACode:
    """R20: FastF1 sent Câmara (Q P13, car 51) with no code; the grid dropped him and back-filled him at P23."""

    @staticmethod
    def _r20_grid():
        timed = _classified_order(r20_fastf1_qualifying(), 2026)
        return resolve_grid(timed, [], EntryLists(r20_qualifying_entry_list()), WeekendAvailability())

    @staticmethod
    def _assert_timed_at_p13(grid):
        camara = next(driver for driver in grid.drivers if driver["driver_code"] == "CAM")
        assert camara["position"] == 13
        assert "no_qualifying_time" not in camara
        assert CODE_UNRESOLVED not in camara
        assert [driver["position"] for driver in grid.drivers] == list(range(1, 23))
        assert not any(driver.get("no_qualifying_time") for driver in grid.drivers)
        assert not any("excluded" in warning or "no session time" in warning for warning in grid.warnings)
        assert "nan" not in {driver["driver_code"].lower() for driver in grid.drivers}

    @pytest.mark.integration
    def test_f1dbs_code_keeps_him_timed_at_p13(self, identity_f1db):
        add_camara_to_f1db(identity_f1db)

        self._assert_timed_at_p13(self._r20_grid())

    @pytest.mark.integration
    def test_a_code_no_source_knows_is_matched_by_car_number_on_the_entry_list(self, identity_f1db):
        """f1db v2026.19.0 cannot name him; OpenF1's entry list has car 51 as CAM."""
        self._assert_timed_at_p13(self._r20_grid())

    def test_a_codeless_row_whose_car_is_not_entered_is_excluded_and_reported(self):
        timed = [
            {"driver_code": "ANT", "driver_name": "Kimi Antonelli", "team": "Mercedes", "position": 1},
            {
                "driver_code": "",
                "driver_name": "Rafael Camara",
                "position": 2,
                CODE_UNRESOLVED: True,
                "driver_number": 51,
            },
        ]
        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entry_list("ANT", "HAM")), WeekendAvailability())

        assert codes(grid) == ["ANT", "HAM"]
        assert any("not in the entry list and were excluded" in warning for warning in grid.warnings)

    def test_a_coded_row_is_never_matched_by_car_number(self):
        """A withdrawn driver's time must not pass to whoever took the car."""
        entries = WeekendEntryList(
            entries=(EntryListDriver(code="LIN", name="Arvid Lindblad", team="Racing Bulls", number=41),), session="Q"
        )
        timed = [{"driver_code": "TSU", "driver_name": "Yuki Tsunoda", "position": 1, "driver_number": 41}]

        grid = resolve_grid(timed, CHAMPIONSHIP, EntryLists(entries), WeekendAvailability())

        assert [(driver["driver_code"], driver.get("no_qualifying_time")) for driver in grid.drivers] == [("LIN", True)]


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


def seat(code, name, team, starts, last_round):
    return SeasonSeat(code=code, name=name, team=team, starts=starts, last_round=last_round)


# Haas through Mexico City's previous round: Ocon and Bearman are its regulars.
HAAS_SEATS = (
    seat("BEA", "Oliver Bearman", "Haas", 18, 18),
    seat("OCO", "Esteban Ocon", "Haas", 18, 18),
)
HAAS_CHAMPIONSHIP = [
    {"code": "BEA", "name": "Oliver Bearman", "team": "Haas", "position": 13},
    {"code": "OCO", "name": "Esteban Ocon", "team": "Haas", "position": 16},
]


def haas_lineup(*cars, session="R", event="Mexico City Grand Prix"):
    return WeekendEntryList(
        entries=tuple(EntryListDriver(code=code, name=name, team=team) for code, name, team in cars),
        session=session,
        event=event,
    )


MEXICO_HAAS = haas_lineup(("BEA", "Oliver Bearman", "Haas F1 Team"), ("HIR", "Ryo Hirakawa", "Haas F1 Team"))


class TestSeatTbc:
    """A stand-in from last weekend is kept in the car, and the seat is flagged."""

    def test_a_stand_in_carried_over_from_last_weekend_is_flagged(self):
        grid = resolve_grid(
            [], HAAS_CHAMPIONSHIP, EntryLists(UNAVAILABLE, MEXICO_HAAS, seats=HAAS_SEATS), WeekendAvailability()
        )

        hirakawa = next(d for d in grid.drivers if d["driver_code"] == "HIR")
        assert hirakawa["seat_tbc"] is True
        assert hirakawa["seat_tbc_reason"] == (
            "Ryo Hirakawa raced Haas F1 Team's car at the Mexico City Grand Prix in place of Esteban Ocon; "
            "the model keeps Ryo Hirakawa in the seat until this weekend's entry list is published"
        )
        assert any(warning.startswith("Seat TBC: Ryo Hirakawa raced") for warning in grid.warnings)

    def test_a_regular_driver_is_not_flagged(self):
        grid = resolve_grid(
            [], HAAS_CHAMPIONSHIP, EntryLists(UNAVAILABLE, MEXICO_HAAS, seats=HAAS_SEATS), WeekendAvailability()
        )

        bearman = next(d for d in grid.drivers if d["driver_code"] == "BEA")
        assert bearman["seat_tbc"] is False
        assert bearman["seat_tbc_reason"] is None

    def test_a_list_with_no_event_still_explains_the_seat(self):
        lineup = haas_lineup(("BEA", "Oliver Bearman", "Haas"), ("HIR", "Ryo Hirakawa", "Haas"), event="")
        grid = resolve_grid(
            [], HAAS_CHAMPIONSHIP, EntryLists(UNAVAILABLE, lineup, seats=HAAS_SEATS), WeekendAvailability()
        )

        hirakawa = next(d for d in grid.drivers if d["driver_code"] == "HIR")
        assert hirakawa["seat_tbc_reason"].startswith("Ryo Hirakawa raced Haas's car in place of Esteban Ocon;")

    def test_this_weekends_own_list_is_fact_not_tbc(self):
        """Once the stand-in is on this weekend's list, the seat is confirmed."""
        grid = resolve_grid([], HAAS_CHAMPIONSHIP, EntryLists(MEXICO_HAAS, seats=HAAS_SEATS), WeekendAvailability())

        assert not any(d["seat_tbc"] for d in grid.drivers)

    def test_a_timed_driver_keeps_the_seat_flag(self):
        timed = [{"driver_code": "HIR", "driver_name": "Ryo Hirakawa", "team": "Haas", "position": 1}]
        grid = resolve_grid(
            timed, HAAS_CHAMPIONSHIP, EntryLists(UNAVAILABLE, MEXICO_HAAS, seats=HAAS_SEATS), WeekendAvailability()
        )

        assert grid.drivers[0]["driver_code"] == "HIR"
        assert grid.drivers[0]["seat_tbc"] is True


class TestEntryListGaps:
    def test_a_blank_team_is_taken_from_the_championship(self):
        lineup = haas_lineup(("OCO", "Esteban OCON", ""))
        grid = resolve_grid([], HAAS_CHAMPIONSHIP, EntryLists(lineup), WeekendAvailability())

        assert grid.drivers[0]["team"] == "Haas"

    def test_f1dbs_name_is_preferred_to_the_feeds(self):
        lineup = haas_lineup(("OCO", "Esteban OCON", "Haas F1 Team"))
        grid = resolve_grid([], HAAS_CHAMPIONSHIP, EntryLists(lineup), WeekendAvailability())

        assert grid.drivers[0]["driver_name"] == "Esteban Ocon"
        assert grid.drivers[0]["team"] == "Haas F1 Team"


class TestChampionshipFallbackSeats:
    """With no entry list at all, the championship table is cut to two cars per team."""

    RACING_BULLS = (
        {"code": "LAW", "name": "Liam Lawson", "team": "Racing Bulls", "position": 9},
        {"code": "LIN", "name": "Arvid Lindblad", "team": "Racing Bulls", "position": 11},
        {"code": "TSU", "name": "Yuki Tsunoda", "team": "Racing Bulls", "position": 20},
    )
    SEATS = (
        seat("LAW", "Liam Lawson", "Racing Bulls", 15, 18),
        seat("LIN", "Arvid Lindblad", "Racing Bulls", 18, 18),
        seat("TSU", "Yuki Tsunoda", "Racing Bulls", 3, 14),
    )

    def test_a_stand_in_whose_driver_is_back_is_dropped(self):
        grid = resolve_grid([], list(self.RACING_BULLS), EntryLists(seats=self.SEATS), WeekendAvailability())

        assert codes(grid) == ["LAW", "LIN"]

    def test_without_race_starts_the_table_is_used_whole(self):
        grid = resolve_grid([], list(self.RACING_BULLS), EntryLists(), WeekendAvailability())

        assert codes(grid) == ["LAW", "LIN", "TSU"]


def roster(*cars):
    return [{"driver_code": code, "team": team} for code, team in cars]


class TestRosterViolation:
    def test_a_real_grid_passes(self):
        assert roster_violation(roster(("BEA", "Haas F1 Team"), ("HIR", "Haas F1 Team"))) is None

    def test_a_third_car_for_one_team_is_a_violation(self):
        violation = roster_violation(roster(("BEA", "Haas F1 Team"), ("HIR", "Haas F1 Team"), ("OCO", "Haas")))

        assert violation == RosterViolation(cars=3, over_limit=(("Haas F1 Team", ("BEA", "HIR", "OCO")),))
        assert violation.describe() == "Haas F1 Team has 3 cars (BEA, HIR, OCO)"

    def test_more_cars_than_the_grid_holds_is_a_violation(self):
        violation = roster_violation(roster(*((f"D{index:02d}", f"Team {index}") for index in range(23))))

        assert violation is not None
        assert violation.over_limit == ()
        assert violation.describe() == "23 cars for 22 places on the grid"

    def test_both_problems_are_reported_together(self):
        cars = [
            *((f"D{index:02d}", f"Team {index}") for index in range(20)),
            ("A", "Haas"),
            ("B", "Haas"),
            ("C", "Haas"),
        ]

        assert (
            roster_violation(roster(*cars)).describe() == "23 cars for 22 places on the grid; Haas has 3 cars (A, B, C)"
        )

    def test_cars_with_no_team_are_not_counted_as_one_team(self):
        assert roster_violation(roster(("A", ""), ("B", ""), ("C", ""))) is None
