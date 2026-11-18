"""The 2026 Mexico City GP's practice, qualifying and race classifications."""

from __future__ import annotations

import pytest

from app.data.fia_documents.parsers.classifications import FastestLap, parse_classification
from app.data.fia_documents.parsers.fields import RuledNote
from app.data.fia_documents.text import DocumentParseError
from tests.fia_documents_support import MEXICO_2026, mexico

pytestmark = pytest.mark.unit

FINAL_ORDER = (3, 44, 12, 16, 1, 63, 30, 5, 6, 50, 23, 55, 81, 27, 43, 11, 10)
RACE_HEAD = "Title Final Race Classification\nNO DRIVER NAT ENTRANT LAPS TIME GAP INT KM/H FASTEST ON PTS\n"
WINNER = "1 3 Max VERSTAPPEN\n Oracle Red Bull Racing 71 2:20:28.772 130.419 1:19.328 50 25\n"


def test_the_final_race_classification_reads_as_the_fia_ruled_it():
    result = parse_classification(mexico(86)[1])

    assert (result.document, result.session, result.final) == (86, "Race", True)
    classified = [entry for entry in result.entries if entry.status == "classified"]
    assert tuple(entry.car for entry in classified) == FINAL_ORDER
    assert [entry.position for entry in classified] == list(range(1, 18))
    assert [entry.points for entry in classified] == [25, 18, 15, 12, 10, 8, 6, 4, 2, 1] + [None] * 7
    assert [entry.car for entry in classified if entry.penalised] == [81, 43, 10]
    winner, second = classified[:2]
    assert (winner.driver, winner.team, winner.laps, winner.time) == (
        "Max VERSTAPPEN",
        "Oracle Red Bull Racing",
        71,
        "2:20:28.772",
    )
    assert (winner.gap, winner.interval, winner.fastest) == (None, None, "1:19.328")
    assert (second.gap, second.interval) == ("0.799", "0.799")
    assert classified[-1].team == "BWT Alpine F1 Team"
    assert [entry.team for entry in classified if entry.car == 11] == ["Cadillac Formula 1 Team"]


def test_the_retirements_are_not_classified_with_their_laps_and_reason():
    result = parse_classification(mexico(86)[1])

    retired = [entry for entry in result.entries if entry.status == "not_classified"]
    assert [(entry.car, entry.laps, entry.reason) for entry in retired] == [
        (41, 58, "DNF"),
        (87, 47, "DNF"),
        (77, 42, "DNF"),
        (18, 5, "DNF"),
        (14, 5, "DNF"),
    ]
    assert all(entry.position is None and entry.gap is None and entry.points is None for entry in retired)
    assert retired[0].time == "2:01:05.146"
    assert len(result.entries) == 22


def test_the_final_race_carries_the_penalties_and_the_fastest_lap():
    result = parse_classification(mexico(86)[1])

    assert result.fastest_lap == FastestLap(44, "Lewis HAMILTON", "Scuderia Ferrari HP", "1:19.268", 50)
    assert result.penalties == (
        RuledNote(81, "10 second time penalty", "Causing a collision", 79),
        RuledNote(
            10,
            "Stop and go penalty converted to 30 second time penalty",
            "Failing to slow for double-waved yellow flags",
            84,
        ),
        RuledNote(43, "10 second time penalty", "Failing to slow for yellow flags", 85),
    )


def test_the_provisional_race_has_the_pre_penalty_order():
    result = parse_classification(mexico(75)[1])

    assert (result.document, result.final) == (75, False)
    order = [entry.car for entry in result.entries if entry.status == "classified"]
    assert order.index(81) == 6  # Piastri 7th
    assert order.index(43) == 7  # Colapinto 8th
    assert order.index(10) == 9  # Gasly 10th
    assert result.penalties == ()
    assert not any(entry.penalised for entry in result.entries)


def test_final_qualifying_puts_lawson_under_disqualified_with_no_position():
    result = parse_classification(mexico(59)[1])

    assert (result.session, result.final) == ("Qualifying", True)
    lawson = result.entries[-1]
    assert (lawson.car, lawson.status, lawson.position, lawson.penalised) == (30, "disqualified", None, True)
    assert (lawson.q1, lawson.q2, lawson.q3) == (None, None, None)
    assert [entry.position for entry in result.entries[:-1]] == list(range(1, 22))
    assert result.penalties == (RuledNote(30, "Disqualified", "Technical nonconformity", 57),)
    assert result.fastest_lap == FastestLap(44, "Lewis HAMILTON", "Scuderia Ferrari HP", "1:16.514", None)


def test_qualifying_times_stop_where_the_car_was_knocked_out():
    result = parse_classification(mexico(46)[1])

    assert result.final is False
    by_position = {entry.position: entry for entry in result.entries}
    assert (by_position[1].q1, by_position[1].q2, by_position[1].q3) == ("1:17.341", "1:16.953", "1:16.514")
    assert (by_position[11].q1, by_position[11].q2, by_position[11].q3) == ("1:17.868", "1:17.306", None)
    assert (by_position[22].q1, by_position[22].q2) == ("1:19.852", None)


def test_practice_reads_best_time_and_laps_including_a_car_with_no_time():
    first = parse_classification(mexico(19)[1])
    third = parse_classification(mexico(43)[1])

    assert (first.session, first.final, first.fastest_lap) == ("Free Practice 1", False, None)
    leader, second = first.entries[:2]
    assert (leader.car, leader.time, leader.laps, leader.gap) == (16, "1:18.128", 29, None)
    assert (second.gap, second.interval) == ("0.659", "0.659")
    untimed = third.entries[-2:]
    assert [(entry.car, entry.time, entry.laps) for entry in untimed] == [(5, None, 2), (11, None, 1)]
    assert untimed[0].team == "Audi Revolut F1 Team"


def test_every_classification_of_the_weekend_parses():
    titles = [title for title in MEXICO_2026 if "Classification" in title]

    assert len(titles) == 7
    for title in titles:
        assert parse_classification(MEXICO_2026[title]["text"]).entries


def test_a_lapped_car_and_a_car_that_did_not_start_read_structurally():
    text = (
        RACE_HEAD
        + WINNER
        + "2 1 Lando NORRIS\n McLaren Mastercard F1 Team 70 2:20:28.772 1 LAP 1 LAP 130.419 1:19.328 50 18\n"
        + "3 44 Lewis HAMILTON\n Scuderia Ferrari HP 70 2:20:29.000 1:02.345 0.500 130.000 1:19.900 50 15\n"
        + "DID NOT START\n87 Oliver BEARMAN\n TGR Haas F1 Team\n"
    )

    result = parse_classification(text)

    assert [(entry.car, entry.gap, entry.interval) for entry in result.entries] == [
        (3, None, None),
        (1, "1 LAP", "1 LAP"),
        (44, "1:02.345", "0.500"),
        (87, None, None),
    ]
    assert result.entries[-1].status == "did_not_start"
    assert result.fastest_lap is None


@pytest.mark.parametrize(
    "text",
    [
        "NO DRIVER NAT ENTRANT LAPS TIME\n",  # no title
        "Title Final Race Classification\n",  # no header
        "Title Final Race Classification\nNO DRIVER NAT ENTRANT POINTS\n1 3 Max VERSTAPPEN\n Red Bull 25\n",
        RACE_HEAD,  # no rows
        RACE_HEAD + "2 44 Lewis HAMILTON\n Scuderia Ferrari HP 70 2:20:29.000\n",  # positions skip 1
        RACE_HEAD + WINNER + "garbage\n Team\n",  # unreadable row
        RACE_HEAD + WINNER + "NOT CLASSIFIED\n41 Arvid LINDBLAD\n",  # team line missing
        RACE_HEAD + WINNER + "NOT CLASSIFIED\n41 Arvid LINDBLAD\n 58 2:01:05.146\n",  # no team
        RACE_HEAD + WINNER + "NOT CLASSIFIED\n41 Arvid LINDBLAD\n Team 58 oops 1\n",  # unreadable figures
        RACE_HEAD + "1 3 Max VERSTAPPEN\n Oracle Red Bull Racing\n",  # classified, no figures
        RACE_HEAD + WINNER + "FASTEST LAP\n44 Lewis HAMILTON\n Scuderia Ferrari HP no time\n",
    ],
)
def test_a_document_that_is_not_a_classification_is_refused(text):
    with pytest.raises(DocumentParseError):
        parse_classification(text)
