"""Unit tests for seat attribution and the unit ledger, on hand-built evidence.

The cases are the ones the 2026 documents produced or could produce: a stand-in
printed under his own number in two reports in a row (Azerbaijan repeated
Monza's labels), a team whose two cars both changed hands at once, and a unit a
decision names that no report counted.
"""

from __future__ import annotations

from types import MappingProxyType

from app.services.power_units.evidence import DocumentRef, Evidence, IntroductionEvidence, UsageRowEvidence
from app.services.power_units.ledger import Season, _derived_part, build_seat_ledger
from app.services.power_units.seats import Occupant, Seat, SeatMap, assign_seats
from tests.power_units_support import season_context

REF = DocumentRef(title="Doc 1", url="u", published="", number=1)
RED_BULL = (Seat("red-bull-3", "red-bull", "Red Bull", 3), Seat("red-bull-6", "red-bull", "Red Bull", 6))
SEASON = Season(
    codes=("ICE",),
    allowance=MappingProxyType({"ICE": 4}),
    rounds=(1, 13, 15, 16, 17),
    latest_round=17,
)


def usage(round_num: int, team_id: str | None, number: int, ice: int = 1) -> UsageRowEvidence:
    return UsageRowEvidence(round_num, number, team_id, {"ICE": ice}, REF)


def evidence(*rows: UsageRowEvidence, introductions: tuple[IntroductionEvidence, ...] = ()) -> Evidence:
    return Evidence(
        usage=rows, introductions=introductions, statements=(), decisions=(), unread=(), withdrawn=(), latest=None
    )


def seat_map(**labels: str) -> SeatMap:
    parsed = {
        tuple(int(part) if part.isdigit() else part for part in key.split("__")): value for key, value in labels.items()
    }
    occupants = {
        "red-bull-3": (Occupant(1, 3, "max-verstappen", "Max Verstappen", "VER"),),
        "red-bull-6": (
            Occupant(1, 6, "isack-hadjar", "Isack Hadjar", "HAD"),
            Occupant(13, 30, "liam-lawson", "Liam Lawson", "LAW"),
        ),
    }
    return SeatMap(seats=RED_BULL, occupants=MappingProxyType(occupants), labels=MappingProxyType(parsed))


def test_a_stand_in_number_resolves_through_the_latest_report_label():
    seats = seat_map(**{"15__red-bull__30": "red-bull-6"})
    assert seats.seat_for(16, "red-bull", 30).seat_id == "red-bull-6"
    assert seats.seat_for(16, None, 30).seat_id == "red-bull-6"


def test_a_stand_in_number_with_no_label_falls_back_to_who_raced_it():
    seats = seat_map()
    assert seats.seat_for(13, "red-bull", 30).seat_id == "red-bull-6"
    assert seats.seat_for(14, "red-bull", 30) is None
    assert seats.seat_for(13, "red-bull", 99) is None


def test_a_label_repeated_in_a_later_report_is_remembered():
    # Monza printed Lawson in Red Bull's second car; Azerbaijan's Friday report
    # printed the same line-up again, after Hadjar was back in it.
    reports = evidence(
        usage(13, "red-bull", 3),
        usage(13, "red-bull", 30, ice=6),
        usage(15, "red-bull", 3),
        usage(15, "red-bull", 30, ice=6),
        usage(15, None, 99),
    )
    seats = assign_seats(season_context(), reports)

    assert seats.labels[(13, "red-bull", 30)] == "red-bull-6"
    assert seats.labels[(15, "red-bull", 30)] == "red-bull-6"
    assert seats.warnings == ()


def test_two_unknown_numbers_in_one_team_are_reported_not_guessed():
    seats = assign_seats(season_context(), evidence(usage(15, "red-bull", 30), usage(15, "red-bull", 22)))
    assert len(seats.warnings) == 2
    assert "matches no single car" in seats.warnings[0]
    assert not any(key[0] == 15 for key in seats.labels)


def test_a_unit_no_report_counted_is_listed_with_an_unknown_round():
    named = IntroductionEvidence(round=16, code="ICE", car_number=6, team_id="red-bull", number=3, ref=REF)
    ledger = build_seat_ledger(RED_BULL[1], evidence(introductions=(named,)), seat_map(), SEASON)
    ice = ledger.elements[0]

    assert ice.used == 3
    assert [(part.number, part.round, part.source) for part in ice.parts] == [
        (1, None, "derived"),
        (2, None, "derived"),
        (3, 16, "report"),
    ]
    assert ledger.warnings == (
        "ICE #1: the documents do not show where it was introduced.",
        "ICE #2: the documents do not show where it was introduced.",
    )


def test_consecutive_reports_pin_a_unit_to_the_round_between_them():
    reports = evidence(usage(16, "red-bull", 6, ice=1), usage(17, "red-bull", 6, ice=2))
    ice = build_seat_ledger(RED_BULL[1], reports, seat_map(), SEASON).elements[0]
    first, second = ice.parts
    # Counted going into Bahrain: arrived in rounds 1–15. Counted only going
    # into Singapore, the very next round: it arrived at Bahrain.
    assert (first.round, first.window) == (None, (1, 15))
    assert (second.round, second.window, second.source) == (16, None, "derived")


def test_a_derived_unit_without_any_calendar_has_no_round():
    no_calendar = Season(codes=("ICE",), allowance=MappingProxyType({}), rounds=(), latest_round=None)
    part = _derived_part("ICE", 1, (None, 5), no_calendar)
    assert (part.round, part.window, part.beyond_allowance) == (None, None, False)


def test_a_unit_the_fia_stops_counting_leaves_the_total():
    # Antonelli, 2026: a 4th exhaust announced at Belgium, counted for two
    # rounds, then dropped from every usage report from Monza on.
    named = IntroductionEvidence(round=13, code="ICE", car_number=6, team_id="red-bull", number=4, ref=REF)
    reports = evidence(
        usage(13, "red-bull", 6, ice=3),
        usage(15, "red-bull", 6, ice=4),
        usage(16, "red-bull", 6, ice=4),
        usage(17, "red-bull", 6, ice=3),
        introductions=(named,),
    )
    ledger = build_seat_ledger(RED_BULL[1], reports, seat_map(), SEASON)
    ice = ledger.elements[0]

    assert ice.used == 3
    fourth = ice.parts[-1]
    assert (fourth.number, fourth.round, fourth.not_counted_from) == (4, 13, 17)
    assert fourth.as_dict()["not_counted_from"] == 17
    assert next(item for item in ledger.rounds if item.round == 13).penalty_status == "none"


def test_a_unit_beyond_the_allowance_the_fia_stops_counting_is_not_pending():
    named = IntroductionEvidence(round=16, code="ICE", car_number=6, team_id="red-bull", number=5, ref=REF)
    reports = evidence(usage(16, "red-bull", 6, ice=4), usage(17, "red-bull", 6, ice=4), introductions=(named,))
    ledger = build_seat_ledger(RED_BULL[1], reports, seat_map(), SEASON)
    assert ledger.elements[0].used == 4
    assert next(item for item in ledger.rounds if item.round == 16).penalty_status == "none"
