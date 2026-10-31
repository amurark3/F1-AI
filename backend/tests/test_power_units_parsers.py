"""Tests for the FIA power-unit document parsers.

Fixtures are the text pypdf extracts from real 2026 documents, quirks and all:
names split mid-word ("Geor ge Russell"), column headings broken across lines,
non-breaking spaces on the cover page, and the second wording a mid-weekend
report uses ("is using a new … for the remainder of the Competition").
"""

from datetime import date
from pathlib import Path

import pytest

from app.data.power_units import elements
from app.data.power_units.cover import parse_cover
from app.data.power_units.decision import (
    OUTCOME_BACK_OF_GRID,
    OUTCOME_GRID_DROP,
    OUTCOME_OTHER,
    OUTCOME_PIT_LANE,
    parse_decision,
)
from app.data.power_units.documents import (
    KIND_DECISION,
    KIND_NEW_ELEMENTS,
    KIND_UNRELATED,
    KIND_USAGE_REPORT,
    KIND_WITHDRAWAL,
    classify,
    parse_document,
)
from app.data.power_units.new_elements import parse_new_elements
from app.data.power_units.rescission import is_withdrawal_notice_title, marks_withdrawn, withdrawn_numbers
from app.data.power_units.text import DocumentParseError, clean, compact, squash
from app.data.power_units.usage_report import parse_usage_report

FIXTURES = Path(__file__).parent / "fixtures" / "power_units"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------


def test_clean_replaces_typographic_spaces_and_drops_zero_width():
    assert clean("GRAND\u00a0PRIX\u2009X\u200bY\ufeff") == "GRAND PRIX XY"


def test_compact_ignores_split_words_and_accents():
    assert compact("Ser gio Pérez") == compact("Sergio Perez") == "sergioperez"
    assert compact("Hülkenber g") == "hulkenberg"


def test_squash_collapses_line_breaks():
    assert squash("  a\n  b\tc ") == "a b c"


# ---------------------------------------------------------------------------
# elements
# ---------------------------------------------------------------------------


def test_the_2026_vocabulary_has_seven_elements():
    assert [element.code for element in elements.elements_for(2026)] == [
        "ICE",
        "TC",
        "EXH",
        "MGU-K",
        "ES",
        "PU-CE",
        "PU-ANC",
    ]


def test_a_season_not_yet_read_has_no_vocabulary():
    assert elements.elements_for(2027) == ()
    assert 2026 in elements.SUPPORTED_SEASONS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ICE", "ICE"), (" pu-ce ", "PU-CE"), ("CE", "PU-CE"), ("MGUK", "MGU-K"), ("ANC", "PU-ANC"), ("EX", "EXH")],
)
def test_canonical_code_maps_printed_codes(raw, expected):
    assert elements.canonical_code(raw, 2026) == expected


def test_canonical_code_rejects_unknown_codes_and_seasons():
    assert elements.canonical_code("MGU-H", 2026) is None
    assert elements.canonical_code("ICE", 2025) is None


# ---------------------------------------------------------------------------
# cover
# ---------------------------------------------------------------------------


def test_cover_reads_event_race_day_and_document_number_through_nbsp():
    cover = parse_cover(fixture("decision_usa_car5.txt"))
    assert cover.season == 2026
    assert cover.event == "United States Grand Prix"
    assert cover.race_day == date(2026, 10, 25)
    assert cover.document_number == 15
    # A stewards' decision encloses no report, so it does not say its round.
    assert cover.round is None


def test_cover_reads_the_round_the_enclosed_report_is_numbered_for():
    assert parse_cover(fixture("usage_singapore.txt")).round == 17
    # The event code is the FIA's own, hyphenated for Barcelona.
    assert parse_cover("2026 BARCELONA-CATALUNYA GRAND PRIX\nEnclosed 07 BCN-CAT GP 26 TDR8.pdf\n").round == 7


def test_cover_handles_a_range_across_a_month_end():
    cover = parse_cover("2026 MEXICO CITY GRAND PRIX\n30 October - 01 November 2026\nDocument 3\n")
    assert cover.race_day == date(2026, 11, 1)
    assert cover.event == "Mexico City Grand Prix"


def test_cover_range_without_a_year_takes_the_headline_season():
    # Mexico City 2026: the FIA left the year off the range on every cover.
    cover = parse_cover("2026 MEXICO CITY GRAND PRIX\n30 October - 01 November\nThe Stewards\nDocument 17\n")
    assert cover.race_day == date(2026, 11, 1)


def test_cover_reads_an_abbreviated_month():
    # Austria 2026: "Jun", not "June".
    cover = parse_cover("2026 AUSTRIAN GRAND PRIX\n26 - 28 Jun 2026\nDocument 9\n")
    assert cover.race_day == date(2026, 6, 28)


@pytest.mark.parametrize(
    "text",
    ["Some page\n31 - 32 Smarch 2026\n", "Some page\n30 October - 01 November\n", "no cover at all"],
)
def test_cover_fields_are_none_when_absent_or_invalid(text):
    cover = parse_cover(text)
    assert cover.season is None
    assert cover.event is None
    assert cover.race_day is None
    assert cover.document_number is None
    assert cover.round is None


# ---------------------------------------------------------------------------
# usage report
# ---------------------------------------------------------------------------


def test_usage_report_reads_split_headings_and_every_car():
    report = parse_usage_report(fixture("usage_singapore.txt"))
    assert report.codes == ("ICE", "TC", "EXH", "MGU-K", "ES", "PU-CE", "PU-ANC")
    assert len(report.rows) == 22
    hadjar = next(row for row in report.rows if row.car_number == 6)
    assert dict(hadjar.counts) == {"ICE": 7, "TC": 6, "EXH": 6, "MGU-K": 4, "ES": 4, "PU-CE": 4, "PU-ANC": 7}
    russell = next(row for row in report.rows if row.car_number == 63)
    assert russell.entrant == "Mercedes Geor ge Russell"


def test_usage_report_takes_columns_from_the_document():
    report = parse_usage_report(fixture("usage_abu_dhabi_2025.txt"))
    assert report.codes == ("ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX")
    assert len(report.rows) == 20


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no table at all", "no table heading"),
        ("N° Car Name ICE\n81 A B 1\n", "no Driver column"),
        ("N° Car Driver ICE XYZ\n81 A B 1 2\n", "unrecognised column heading"),
        ("N° Car Driver\n81 Somebody\n", "no element columns"),
        ("N° Car Driver ICE\n81 A B 1\n81 A B 2\n", "appears twice"),
        ("N° Car Driver ICE\n81 Somebody without counts\n", "no driver rows"),
    ],
)
def test_usage_report_refuses_anything_it_cannot_read_in_full(text, message):
    with pytest.raises(DocumentParseError, match=message):
        parse_usage_report(text)


# ---------------------------------------------------------------------------
# new elements
# ---------------------------------------------------------------------------


def test_new_elements_reads_every_section_and_the_stated_allowance():
    report = parse_new_elements(fixture("new_elements_italy.txt"))
    assert len(report.introductions) == 39
    assert dict(report.stated_allowance) == {
        "ICE": 4,
        "TC": 4,
        "EXH": 4,
        "MGU-K": 3,
        "ES": 3,
        "PU-CE": 3,
        "PU-ANC": 6,
    }
    antonelli = next(item for item in report.introductions if item.car_number == 12 and item.code == "ICE")
    assert antonelli.previously_used == 4
    assert antonelli.number == 5


def test_new_elements_reads_the_mid_weekend_wording():
    report = parse_new_elements(fixture("new_elements_italy_1.txt"))
    assert {(item.code, item.car_number, item.number) for item in report.introductions} == {
        ("ICE", 30, 6),
        ("TC", 30, 6),
        ("EXH", 30, 6),
        ("MGU-K", 30, 4),
        ("PU-ANC", 30, 7),
    }


def test_new_elements_section_without_an_allowance_sentence_states_nothing():
    text = "The following driver will start with a new turbocharger (TC):\nNumber Car Driver Previously used TC\n05 Audi Gabriel Bortoleto 3\n"
    report = parse_new_elements(text)
    assert report.introductions[0].number == 4
    assert dict(report.stated_allowance) == {}


def test_new_elements_refuses_a_report_without_sections_or_rows():
    with pytest.raises(DocumentParseError, match="no element sections"):
        parse_new_elements("Technical Delegate's Report\nnothing new")
    with pytest.raises(DocumentParseError, match="lists no cars"):
        parse_new_elements("The following driver will start with a new turbocharger (TC):\nno table\n")


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------


def test_decision_with_a_grid_drop():
    decision = parse_decision(fixture("decision_singapore_car63.txt"))
    assert decision is not None
    assert decision.car_number == 63
    assert decision.driver == "George Russell"
    assert decision.competitor == "Mercedes-AMG PETRONAS F1 Team"
    assert decision.session is None
    assert [(item.code, item.number) for item in decision.elements] == [("ICE", 5), ("TC", 5), ("EXH", 5), ("MGU-K", 4)]
    assert (decision.outcome, decision.places, decision.nominal_places) == (OUTCOME_GRID_DROP, 40, None)


def test_decision_records_the_session_the_elements_first_ran_in():
    decision = parse_decision(fixture("decision_italy_car30.txt"))
    assert decision is not None
    assert decision.session == "Free Practice 3"
    assert decision.places == 35
    assert ("PU-ANC", 7) in [(item.code, item.number) for item in decision.elements]


def test_pit_lane_decision_keeps_the_superseded_places_apart():
    decision = parse_decision(fixture("decision_singapore_car14_pitlane.txt"))
    assert decision is not None
    assert decision.outcome == OUTCOME_PIT_LANE
    assert decision.places is None
    assert decision.nominal_places == 5


def test_a_decision_about_something_else_is_not_a_power_unit_decision():
    assert parse_decision(fixture("decision_italy_car30_parc_ferme.txt")) is None


DECISION_TEMPLATE = """From The Stewards
No / Driver 7 - Test Driver
Competitor Test Team
Fact The following Power Unit elements have been used:
{elements}
Infringement Breach of Article B8.2.2.
Decision {decision}
Reason Because.
"""


@pytest.mark.parametrize(
    ("decision", "outcome"),
    [
        ("Required to start the race from the back of the grid.", OUTCOME_BACK_OF_GRID),
        ("A reprimand.", OUTCOME_OTHER),
    ],
)
def test_decision_outcomes_without_a_place_count(decision, outcome):
    parsed = parse_decision(DECISION_TEMPLATE.format(elements="4th MGU-K", decision=decision))
    assert parsed is not None
    assert parsed.outcome == outcome
    assert parsed.places is None
    assert parsed.competitor == "Test Team"


def test_decision_without_driver_or_decision_line_is_refused():
    text = DECISION_TEMPLATE.format(elements="4th MGU-K", decision="Drop of 10 grid positions.")
    with pytest.raises(DocumentParseError, match="no driver or decision"):
        parse_decision(text.replace("No / Driver 7 - Test Driver\n", ""))


def test_decision_naming_no_element_is_refused():
    text = DECISION_TEMPLATE.format(elements="(none listed)", decision="Drop of 10 grid positions.")
    with pytest.raises(DocumentParseError, match="names no power-unit elements"):
        parse_decision(text)


def test_decision_without_infringement_line_reads_elements_to_the_end():
    text = "From The Stewards\nNo / Driver 7 - X\nDecision Drop of 10 grid positions.\nReason R\nFact The following Power Unit elements has been used:\n5th Engine (ICE)\n"
    parsed = parse_decision(text)
    assert parsed is not None
    assert [(item.code, item.number) for item in parsed.elements] == [("ICE", 5)]
    assert parsed.competitor == ""


# ---------------------------------------------------------------------------
# classification and dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("usage_singapore.txt", KIND_USAGE_REPORT),
        ("usage_abu_dhabi_2025.txt", KIND_USAGE_REPORT),
        ("new_elements_usa.txt", KIND_NEW_ELEMENTS),
        ("decision_usa_car43.txt", KIND_DECISION),
        ("decision_italy_car30_parc_ferme.txt", KIND_UNRELATED),
    ],
)
def test_classify_reads_the_template_not_the_title(name, kind):
    assert classify(fixture(name)) == kind


def test_a_technical_delegate_report_about_something_else_is_unrelated():
    text = "From The FIA Formula 1 Technical Delegate\nDescription Car Presentation Submissions\n"
    assert classify(text) == KIND_UNRELATED


@pytest.mark.parametrize(
    ("name", "kind", "body_type"),
    [
        ("usage_singapore.txt", KIND_USAGE_REPORT, "UsageReport"),
        ("new_elements_italy.txt", KIND_NEW_ELEMENTS, "NewElementsReport"),
        ("decision_usa_car5.txt", KIND_DECISION, "PuDecision"),
    ],
)
def test_parse_document_dispatches_by_kind(name, kind, body_type):
    parsed = parse_document(fixture(name))
    assert parsed.kind == kind
    assert type(parsed.body).__name__ == body_type
    assert parsed.cover.season == 2026


def test_parse_document_of_an_unrelated_document_has_no_body():
    parsed = parse_document(fixture("decision_italy_car30_parc_ferme.txt"))
    assert parsed.kind == KIND_UNRELATED
    assert parsed.body is None
    assert parsed.cover.document_number == 57


# ---------------------------------------------------------------------------
# withdrawals and rescissions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "marked"),
    [
        ("Doc 44 - Infringement - Car 6 - Changes to PU elements (Withdrawn)", True),
        ("Doc 44 - RESCINDED - Infringement - Car 6", True),
        ("Doc 45 - Corrected Infringement - Car 6 - Changes to PU elements", False),
        ("Doc 20 - Infringement - Car 63 - Changes to PU elements", False),
    ],
)
def test_marks_withdrawn_reads_an_event_page_title(title, marked):
    assert marks_withdrawn(title) is marked


def test_a_withdrawal_notice_title_is_worth_collecting():
    assert is_withdrawal_notice_title("Doc 60 - Withdrawal of Document 44")
    assert is_withdrawal_notice_title("Doc 61 - Decision rescinding Doc 41")
    assert not is_withdrawal_notice_title("Doc 22 - Summons - Car 44 - Alleged Yellow Flag Infringement")


@pytest.mark.parametrize(
    ("text", "own", "expected"),
    [
        ("Document 44 is hereby withdrawn.", 60, {44}),
        ("This decision replaces Document 37.", 45, {37}),
        ("The decisions in Documents 51 and 52 are rescinded.", 70, {51, 52}),
        ("Docs 12, 13 & 14 have been cancelled.", 30, {12, 13, 14}),
        # A document cannot take itself back, nor anything published after it.
        ("Document 45 replaces Document 37.", 45, {37}),
        ("Document 50 is withdrawn.", 45, set()),
        # Everyday B8.2.7 vocabulary is not a withdrawal.
        ("Car 30, the replacement driver for Car 6 (document 33), used a new ICE.", 41, set()),
        ("The Stewards, having received a report from the Technical Delegate (document 13), decided.", 14, set()),
        # A competitor withdrawing its own petition takes back nothing the FIA published.
        ("Mercedes are withdrawing the petition for Review of the decision in Document 95.", 104, set()),
        ("The team withdrew its request (Document 61).", 104, set()),
    ],
)
def test_withdrawn_numbers_reads_what_a_document_takes_back(text, own, expected):
    assert withdrawn_numbers(text, own) == frozenset(expected)


def test_withdrawn_numbers_without_an_own_number_keeps_every_reference():
    assert withdrawn_numbers("Document 44 is withdrawn.", None) == frozenset({44})


def test_a_notice_that_only_takes_back_documents_is_a_withdrawal():
    notice = (
        "2026 ITALIAN GRAND PRIX\n04 - 06 September 2026\nFrom The Stewards\nDocument 90\nDocument 41 is withdrawn.\n"
    )
    parsed = parse_document(notice)
    assert parsed.kind == KIND_WITHDRAWAL
    assert parsed.withdraws == frozenset({41})
    assert parsed.body is None


def test_any_document_can_take_an_earlier_one_back():
    corrected = clean(fixture("decision_usa_car43.txt")).replace(
        "Decisions of the Stewards", "This decision replaces Document 12. Decisions of the Stewards"
    )
    parsed = parse_document(corrected)
    assert parsed.kind == KIND_DECISION
    assert parsed.withdraws == frozenset({12})
    assert parse_document(fixture("decision_usa_car43.txt")).withdraws == frozenset()


def test_a_bracketed_code_may_carry_spaces():
    text = (
        "The following driver is using  a new power unit ancillary component ( PU-ANC) for the remainder\n"
        "of the Competition:\nNumber Car Driver Previously used PU-ANC\n01 McLaren Mercedes Lando Norris 3\n"
    )
    assert [(item.code, item.number) for item in parse_new_elements(text).introductions] == [("PU-ANC", 4)]
    decision = parse_decision(DECISION_TEMPLATE.format(elements="4th Energy Store ( ES )", decision="A reprimand."))
    assert decision is not None
    assert decision.elements[0].code == "ES"


def test_a_date_range_with_an_en_dash():
    assert parse_cover("2026 MONACO GRAND PRIX\n05 – 07 June 2026\n").race_day == date(2026, 6, 7)
