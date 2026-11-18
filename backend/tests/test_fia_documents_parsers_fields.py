"""The header and note readers the FIA document parsers share."""

from __future__ import annotations

import pytest

from app.data.fia_documents.parsers.fields import RuledNote, document_date, document_number, number, ruled_notes

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("token", "value"), [("50", 50), ("one", 1), ("One", 1), ("ten", 10)])
def test_a_count_reads_as_digits_or_a_word(token, value):
    assert number(token) == value


def test_the_header_gives_the_document_number_and_its_date():
    header = "From The Stewards      Document 48\nTo All Teams      Date  31 October 2026\n"

    assert document_number(header) == 48
    assert document_date(header) == "2026-10-31"


@pytest.mark.parametrize("text", ["No header here", "Date 31 Octember 2026", "Date 31 November 2026"])
def test_a_header_without_a_readable_date_or_number_gives_none(text):
    assert document_date(text) is None
    assert document_number(text) is None


def test_ruled_notes_survive_line_breaks_and_lines_without_a_reason_or_a_document():
    block = (
        "Car 30 - Required to start from the pit lane - Car modified - Stewards' \ndocument no. 65\n"
        "Car 77 - Permitted to start\n"
    )

    assert ruled_notes(block) == (
        RuledNote(30, "Required to start from the pit lane", "Car modified", 65),
        RuledNote(77, "Permitted to start", None, None),
    )
