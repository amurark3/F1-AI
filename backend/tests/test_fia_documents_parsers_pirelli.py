"""The 2026 Mexico City GP's Pirelli preview."""

from __future__ import annotations

import pytest

from app.data.fia_documents.parsers.pirelli import TyreNomination, parse_pirelli_preview
from app.data.fia_documents.text import DocumentParseError
from tests.fia_documents_support import mexico

pytestmark = pytest.mark.unit


def test_mexico_runs_c3_hard_c4_medium_c5_soft_whatever_order_they_are_listed_in():
    assert parse_pirelli_preview(mexico(2)[1]) == TyreNomination(
        hard="C3", medium="C4", soft="C5", q3="C5", mandatory_race=("C3", "C4")
    )


def test_the_q3_and_mandatory_tyres_are_optional():
    result = parse_pirelli_preview("Compound\nC1\nC2\nC3\nIntermediate\n")

    assert (result.hard, result.medium, result.soft) == ("C1", "C2", "C3")
    assert result.q3 is None
    assert result.mandatory_race == ()


@pytest.mark.parametrize(
    "text",
    [
        "no compounds here",
        "Compound\nC3\nC4\nIntermediate\n",
        "Compound\nC3\nC4\nC5\nC1\nIntermediate\n",
        "Compound\nC3\nC3\nC4\nIntermediate\n",
    ],
)
def test_anything_but_three_distinct_compounds_is_refused(text):
    with pytest.raises(DocumentParseError):
        parse_pirelli_preview(text)
