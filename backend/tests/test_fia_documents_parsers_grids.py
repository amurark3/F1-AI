"""The 2026 Mexico City GP's provisional and final starting grids."""

from __future__ import annotations

import pytest

from app.data.fia_documents.parsers.fields import RuledNote
from app.data.fia_documents.parsers.grids import GridSlot, PitLaneStart, parse_starting_grid
from app.data.fia_documents.text import DocumentParseError
from tests.fia_documents_support import mexico

pytestmark = pytest.mark.unit

# Slot order of R19's grid: the PDF prints the even slots first, then the odd.
ORDER = (44, 63, 16, 12, 3, 1, 6, 41, 10, 27, 43, 81, 5, 87, 55, 23, 14, 50, 18, 11, 77)
PENALTIES = (
    RuledNote(77, "50 place grid penalty", "Additional power unit elements have been used", 17),
    RuledNote(3, "1 place grid penalty", "Causing a collision", 33),
    RuledNote(30, "1 place grid penalty", "Driving erratically", 34),
)
PERMITTED = (RuledNote(30, "Permitted to start", None, 58),)
LAWSON = "Liam LAWSON Visa Cash App Racing Bulls F1 Team"


def test_the_provisional_grid_puts_every_car_in_slot_order_with_the_reasons():
    grid = parse_starting_grid(mexico(60)[1])

    assert (grid.document, grid.final) == (60, False)
    assert tuple(slot.car for slot in grid.slots) == (*ORDER, 30)
    assert grid.slots[0] == GridSlot(1, 44, "Lewis HAMILTONScuderia Ferrari HP", "1:16.514", penalised=False)
    assert grid.slots[4] == GridSlot(5, 3, "Max VERSTAPPEN Oracle Red Bull Racing", "1:16.692", penalised=True)
    # Lawson, disqualified from qualifying (doc 57), has no time and the last slot.
    assert grid.slots[-1] == GridSlot(22, 30, LAWSON, None, penalised=True)
    assert grid.pit_lane == ()
    assert grid.notes == PERMITTED
    assert grid.penalties == PENALTIES


def test_the_final_grid_moves_lawson_to_the_pit_lane_and_says_why():
    grid = parse_starting_grid(mexico(67)[1])

    assert (grid.document, grid.final) == (67, True)
    assert tuple(slot.car for slot in grid.slots) == ORDER
    assert grid.pit_lane == (PitLaneStart(30, LAWSON),)
    assert grid.notes == PERMITTED
    assert grid.penalties == (
        *PENALTIES,
        RuledNote(
            30,
            "Required to start from the pit lane",
            "Car modified whilst under Parc Fermé conditions and additional power unit elements have been used",
            65,
        ),
    )


def test_a_grid_with_no_notes_has_none():
    grid = parse_starting_grid("Final Starting Grid\n1 4 Lando NORRISMcLaren 1:10.000\n2 81 Oscar PIASTRIMcLaren\n")

    assert grid.final
    assert (grid.notes, grid.penalties, grid.pit_lane, grid.document) == ((), (), (), None)
    assert grid.slots[1].time is None


@pytest.mark.parametrize(
    "text",
    ["Provisional Starting Grid\nNo rows were published.", "1 4 Lando NORRISMcLaren 1:10.000\n3 81 Oscar PIASTRI"],
)
def test_a_grid_whose_slots_are_not_one_to_n_is_refused(text):
    with pytest.raises(DocumentParseError, match=r"not 1\.\.N"):
        parse_starting_grid(text)
