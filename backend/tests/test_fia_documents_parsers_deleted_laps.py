"""The 2026 Mexico City GP's deleted-lap sheets, every session."""

from __future__ import annotations

import pytest

from app.data.fia_documents.kinds import KIND_DELETED_LAPS, document_kind
from app.data.fia_documents.parsers.deleted_laps import (
    REASON_OTHER,
    REASON_TRACK_LIMITS,
    REASON_YELLOW_FLAGS,
    DeletedLap,
    parse_deleted_laps,
)
from app.data.fia_documents.text import DocumentParseError
from tests.fia_documents_support import MEXICO_2026, mexico

pytestmark = pytest.mark.unit


def test_the_qualifying_sheet_reads_every_lap_with_its_time_of_day():
    sheet = parse_deleted_laps(mexico(48)[1])

    assert (sheet.document, sheet.session, sheet.date, sheet.reason) == (
        48,
        "Qualifying",
        "2026-10-31",
        REASON_TRACK_LIMITS,
    )
    assert sheet.fact == "The F1 Cars below did not use the track at turns 1, 4, 9, 11, 12, 13 and 14."
    assert len(sheet.laps) == 9
    assert sheet.laps[0] == DeletedLap(18, 4, "Lance Stroll Aston Martin Aramco F1 Team", "15:02:38", "1:29.337")
    # A lap that ended in the pit lane prints no time.
    assert sheet.laps[2] == DeletedLap(11, 1, "Sergio Perez Cadillac Formula 1 Team", "15:15:49", None)


def test_a_double_yellow_sheet_is_told_apart_from_track_limits():
    sheet = parse_deleted_laps(mexico(49)[1])

    assert sheet.reason == REASON_YELLOW_FLAGS
    assert [(lap.car, lap.lap_time) for lap in sheet.laps] == [(10, None), (16, "1:41.066"), (55, "1:31.549")]


def test_every_sheet_of_the_weekend_reads_out_laps_and_in_laps_included():
    sheets = [
        parse_deleted_laps(MEXICO_2026[title]["text"])
        for title in MEXICO_2026
        if document_kind(title) == KIND_DELETED_LAPS
    ]

    assert [(sheet.document, sheet.session, len(sheet.laps)) for sheet in sheets] == [
        (20, "Free Practice 1", 26),
        (21, "Free Practice 1", 5),
        (27, "Free Practice 2", 18),
        (44, "Free Practice 3", 24),
        (48, "Qualifying", 9),
        (49, "Qualifying", 3),
        (80, "Race", 13),
    ]
    # Doc 21 opens on an out-lap ("OUT"): kept, without a time.
    assert sheets[1].laps[0] == DeletedLap(62, 10, "Gabriele Mini BWT Alpine F1 Team", "12:42:20", None)
    # The race's: Piastri's 1:22.148 at 14:34:07, among others.
    assert DeletedLap(81, 12, "Oscar Piastri McLaren Mastercard F1 Team", "14:34:07", "1:22.148") in sheets[-1].laps


def test_a_fact_that_is_neither_track_limits_nor_flags_reads_other():
    text = "Session Race\nFact The cars below exceeded the limit.\nNo. Turn Car Driver\n1 3 44 Lewis Hamilton Ferrari 14:00:00 1:20.000\n"

    sheet = parse_deleted_laps(text)

    assert (sheet.reason, sheet.document, sheet.date) == (REASON_OTHER, None, None)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Fact Nothing.\nNo. Turn Car\n1 3 44 Lewis Hamilton Ferrari 14:00:00 1:20.000\n", "without a session"),
        ("Session Race\nFact The cars below.\nNo. Turn Car\n", "without a session, a fact or a row"),
        (
            "Session Race\nFact The cars.\nNo. Turn Car\n1 3 44 A B 14:00:00 1:20.000\n3 3 16 C D 14:01:00 1:21.000\n",
            r"not 1\.\.N",
        ),
    ],
)
def test_a_sheet_missing_a_part_or_a_row_is_refused(text, message):
    with pytest.raises(DocumentParseError, match=message):
        parse_deleted_laps(text)
