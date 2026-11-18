"""The 2026 Mexico City GP's entry lists and Haas's driver change."""

from __future__ import annotations

import pytest

from app.data.fia_documents.parsers.entry_list import DriverChange, EntryRow, parse_driver_change, parse_entry_list
from app.data.fia_documents.text import DocumentParseError, compact
from tests.fia_documents_support import mexico

pytestmark = pytest.mark.unit

HEAD = "No. TLA Driver Nat Team Constructor\n"
NORRIS = "1 NOR Lando Norris GBR McLaren Mastercard F1 Team McLaren Mercedes\n"
RESERVES = "In addition to the list of cars and drivers eligible\n"


def _by_tla(entry_list):
    return {row.tla: row for row in entry_list.rows}


def test_the_entry_list_has_twenty_two_cars_and_ten_reserves_with_their_real_numbers():
    entries = parse_entry_list(mexico(11)[1])
    rows = _by_tla(entries)

    assert (entries.document, entries.revised, len(entries.rows)) == (11, False, 32)
    assert [row.car for row in entries.rows if not row.reserve] == [
        81, 1, 63, 12, 3, 6, 16, 44, 23, 55, 41, 30, 18, 14, 31, 87, 27, 5, 10, 43, 11, 77,
    ]  # fmt: skip
    # The footnote glued to the number ("13 NOR", "632 RUS", "3110 OCO") is not part of it.
    assert (rows["NOR"].car, rows["RUS"].car, rows["OCO"].car) == (1, 63, 31)
    assert rows["OCO"] == EntryRow(31, "OCO", "Esteban Ocon", "FRA", "TGR Haas F1 Team", "Haas Ferrari", False)
    assert rows["HIR"] == EntryRow(50, "HIR", "Ryo Hirakawa", "JPN", "TGR Haas F1 Team", "Haas Ferrari", True)
    assert [row.car for row in entries.rows if row.reserve] == [36, 72, 67, 98, 91, 25, 46, 34, 62, 50]


def test_printed_text_is_kept_and_compared_compactly():
    rows = _by_tla(parse_entry_list(mexico(11)[1]))

    assert rows["ALO"].team == "Aston Martin Aram co F1 Team"
    assert compact(rows["ALO"].team) == compact(rows["STR"].team)
    assert rows["VER"].team == "Oracle Red Bull Racing"
    assert rows["VER"].constructor == "Red Bull Racing Red Bull Ford"
    assert rows["LEC"].team == "Scuderia Ferrari HP"
    assert rows["LEC"].constructor == "Ferrari"
    assert rows["ANT"].team == "Mercedes -AMG PETRONAS F1 Team"


def test_the_revised_list_has_hirakawa_in_car_50_in_place_of_ocon():
    entries = parse_entry_list(mexico(37)[1])
    rows = _by_tla(entries)

    assert (entries.document, entries.revised, len(entries.rows)) == (37, True, 22)
    assert not any(row.reserve for row in entries.rows)
    assert "OCO" not in rows
    assert (rows["HIR"].car, rows["HIR"].team) == (50, "TGR Haas F1 Team")
    assert (rows["NOR"].car, rows["VER"].car, rows["LAW"].car) == (1, 3, 30)
    assert rows["BOT"].team == "Cadilla c Formula 1 Team"


def test_the_driver_change_decision_names_the_swap():
    change = parse_driver_change(mexico(36)[1])

    assert change == DriverChange(36, "TGR Haas F1 Team", 31, "Esteban Ocon", "Ryo Hirakawa", 50)


def test_a_driver_change_without_a_new_number_leaves_it_open():
    text = (
        "The Stewards have received a request from Team X to change the driver of car 7, A B. "
        "In accordance with Article B1.7.2, the Stewards grant permission for the driver, C D, to participate in it."
    )

    change = parse_driver_change(text)

    assert (change.car, change.outgoing, change.incoming, change.incoming_car, change.document) == (
        7,
        "A B",
        "C D",
        None,
        None,
    )


def test_a_list_without_footnotes_reads_as_printed():
    entries = parse_entry_list("Title Entry List\n" + HEAD + NORRIS)

    assert [(row.car, row.tla) for row in entries.rows] == [(1, "NOR")]
    assert entries.revised is False
    assert parse_entry_list(HEAD + NORRIS).revised is False


@pytest.mark.parametrize(
    "text",
    [
        NORRIS,  # no header
        HEAD,  # no rows
        HEAD + "81 PIA Oscar Piastri\n",  # unreadable row
        HEAD + "81 PIA Oscar Piastri AUS Unknown Outfit Whatever\n",  # team not recognised
        HEAD + NORRIS + RESERVES + "67 FOR Leonardo Fornaroli ITA McLaren Mastercard F1 Team McLaren Mercedes\n",
        HEAD + NORRIS + RESERVES + "1 FOR Leonardo Fornaroli ITA McLaren Mastercard F1 Team McLaren Mercedes\n",
        # reserve 1 has no car of its team to carry footnote 1
        HEAD + NORRIS + RESERVES + "136 IWA Ayumu Iwasa JPN Oracle Red Bull Racing Red Bull Racing Red Bull Ford\n",
    ],
)
def test_a_list_that_cannot_be_read_exactly_is_refused(text):
    with pytest.raises(DocumentParseError):
        parse_entry_list(text)


def test_a_document_that_is_not_a_driver_change_is_refused():
    with pytest.raises(DocumentParseError):
        parse_driver_change(mexico(37)[1])
