"""The stewards' summons and decisions of the 2026 Mexico City GP, read as the penalty log needs them."""

from __future__ import annotations

import pytest

from app.data.fia_documents.kinds import KIND_PENALTY, document_kind
from app.data.fia_documents.parsers.stewards import (
    STATUS_DECIDED,
    STATUS_SUMMONED,
    Outcome,
    StewardsDecision,
    outcomes,
    parse_stewards_decision,
)
from app.data.fia_documents.text import DocumentParseError
from tests.fia_documents_support import MEXICO_2026, mexico

pytestmark = pytest.mark.unit

APPENDIX_L_2D = "ISC Appendix L Chapter IV Article 2 d)"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (
            17,
            StewardsDecision(
                document=17,
                status=STATUS_DECIDED,
                car=77,
                driver="Valtteri Bottas",
                competitor="Cadillac Formula 1 Team",
                session="Free Practice 1",
                incident_time="13:05",
                offence="PU elements",
                articles=("B8.2.2", "B8.2.3"),
                decision="Drop of 50 grid positions for the next Race in which the driver participates.",
                outcomes=(Outcome("grid_drop", 50),),
            ),
        ),
        (
            33,
            StewardsDecision(
                document=33,
                status=STATUS_DECIDED,
                car=3,
                driver="Max Verstappen",
                competitor="Oracle Red Bull Racing",
                session="Free Practice 2",
                incident_time="16:22",
                offence="Turn 14 incident with Car 30",
                articles=(APPENDIX_L_2D,),
                decision=(
                    "A drop of one grid position for the next race in which the driver competes. "
                    "One penalty point is imposed, making a total of 1 for the 12 month period."
                ),
                outcomes=(Outcome("grid_drop", 1), Outcome("penalty_points", 1)),
            ),
        ),
        (
            57,
            StewardsDecision(
                document=57,
                status=STATUS_DECIDED,
                car=30,
                driver="Liam Lawson",
                competitor="Visa Cash App Racing Bulls F1 Team",
                session="Qualifying",
                incident_time="15:47",
                offence="Technical nonconformity",
                articles=("C5.12.6", "C5.12.7"),
                decision="Car 30 is disqualified from the results of the Provisional Qualifying Classifications.",
                outcomes=(Outcome("disqualified"),),
            ),
        ),
        (
            65,
            StewardsDecision(
                document=65,
                status=STATUS_DECIDED,
                car=30,
                driver="Liam Lawson",
                competitor="Visa Cash App Racing Bulls F1 Team",
                session="Qualifying",
                incident_time="10:56",
                offence="Changes made during Parc Ferme",
                articles=("B3.4.3", "B3.5.3", "B3.5.4"),
                decision="Required to start the Race from the pit lane.",
                outcomes=(Outcome("pit_lane_start"),),
            ),
        ),
        (
            79,
            StewardsDecision(
                document=79,
                status=STATUS_DECIDED,
                car=81,
                driver="Oscar Piastri",
                competitor="McLaren Mastercard F1 Team",
                session="Race",
                incident_time="16:04",
                offence="Causing a collision",
                articles=(APPENDIX_L_2D,),
                decision="10 second time penalty imposed after the Race.",
                outcomes=(Outcome("time_penalty", 10),),
            ),
        ),
    ],
)
def test_the_acceptance_documents_read_exactly(number, expected):
    assert parse_stewards_decision(*mexico(number)) == expected


def test_every_penalty_document_of_the_weekend_reads():
    titles = [title for title in MEXICO_2026 if document_kind(title) == KIND_PENALTY]
    read = [parse_stewards_decision(title, MEXICO_2026[title]["text"]) for title in titles]

    assert len(read) == 35
    summoned = [entry for entry in read if entry.status == STATUS_SUMMONED]
    assert [entry.document for entry in summoned] == [16, 23, 24, 30, 35, 55, 72, 73, 77, 78, 82]
    assert all(entry.outcomes == () and entry.decision is None and entry.hearing for entry in summoned)
    assert all(entry.outcomes and entry.session and entry.articles for entry in read if entry.status == STATUS_DECIDED)


def test_a_summons_names_the_car_the_hearing_and_the_alleged_breach():
    assert parse_stewards_decision(*mexico(82)) == StewardsDecision(
        document=82,
        status=STATUS_SUMMONED,
        car=63,
        driver="George Russell",
        competitor="Mercedes-AMG PETRONAS F1 Team",
        session=None,
        incident_time=None,
        offence="Alleged failure to attend mandatory post-race commitments",
        articles=("B10.1.4e",),
        decision=None,
        outcomes=(),
        hearing="19:00",
    )


def test_a_summons_of_a_team_reads_the_car_from_the_form_and_the_flags_appendix():
    team = parse_stewards_decision(*mexico(16))
    flags = parse_stewards_decision(*mexico(77))

    assert (team.car, team.driver, team.competitor) == (98, "Freddie Slater", "Audi Revolut F1 Team")
    assert team.offence == "Alleged release of car 98 in an unsafe condition"
    assert flags.articles == ("ISC Appendix H Article 2.5.5 b)",)


@pytest.mark.parametrize(
    ("number", "imposed"),
    [
        (84, (Outcome("stop_and_go"), Outcome("penalty_points", 2))),
        (85, (Outcome("time_penalty", 10), Outcome("penalty_points", 1))),
        (83, (Outcome("fine", 5000),)),
        (68, (Outcome("fine", 1000),)),
        (41, (Outcome("warning"),)),
        (45, (Outcome("reprimand"),)),
        (76, (Outcome("no_further_action"),)),
    ],
)
def test_each_kind_of_outcome_reads_with_its_value(number, imposed):
    assert parse_stewards_decision(*mexico(number)).outcomes == imposed


@pytest.mark.parametrize(
    ("line", "imposed"),
    [
        ("Drive through penalty.", (Outcome("drive_through"),)),
        ("Required to start from the back of the starting grid.", (Outcome("back_of_grid"),)),
        ("3 place grid penalty for the next race.", (Outcome("grid_drop", 3),)),
        ("The car was admitted to the race.", ()),
    ],
)
def test_outcomes_read_the_rarer_penalties_too(line, imposed):
    assert outcomes(line) == imposed


def test_a_car_named_only_in_the_title_and_a_sentence_ending_article():
    text = (
        "Document 9\nTime 12:00\nCompetitor Example Racing\nSession Race\nFact Overtook under yellow.\n"
        "Infringement Breach of Article B1.8.4a.\nDecision 5 second time penalty.\nReason Seen on video.\n"
    )
    decision = parse_stewards_decision("Doc 9 - Infringement - Car 7 - Overtaking under yellow", text)

    assert (decision.car, decision.driver, decision.incident_time) == (7, None, None)
    assert decision.articles == ("B1.8.4a",)


@pytest.mark.parametrize(
    ("title", "text", "message"),
    [
        ("Doc 1 - Timetable", "", "not a stewards'"),
        ("Doc 2 - Summons - Audi - Covering of components", "No driver line here.", "no car named"),
        ("Doc 3 - Infringement - Car 4 - Something", "Decision The car was admitted.\nReason Fine.", "no outcome"),
        ("Doc 4 - Decision - Car 4 - Something", "Fact Nothing decided.", "no outcome"),
    ],
)
def test_a_document_that_is_not_a_readable_ruling_is_refused(title, text, message):
    with pytest.raises(DocumentParseError, match=message):
        parse_stewards_decision(title, text)
