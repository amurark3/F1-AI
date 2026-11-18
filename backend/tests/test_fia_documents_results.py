"""The FIA final classification read from the store, over the 2026 Mexico City GP's real documents."""

from __future__ import annotations

import dataclasses

import pytest

from app.data.fia_documents import store
from app.data.fia_documents.results import fia_deleted_laps, fia_starting_grid, final_classification
from app.data.fia_documents.store import FiaStoreError
from tests.fia_documents_support import MEXICO_2026, held, hold

pytestmark = pytest.mark.unit

FINAL_RACE = "Doc 86 - Final Race Classification"
REVISED_ENTRY_LIST = "Doc 37 - Revised Entry List"


def test_the_final_race_classification_is_document_86_with_the_entry_lists_codes(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    final = final_classification(2026, 19, "race")

    assert final is not None
    assert (final.classification.document, final.classification.final) == (86, True)
    assert final.url == MEXICO_2026[FINAL_RACE]["url"]
    assert [entry.car for entry in final.classification.entries[:3]] == [3, 44, 12]
    # Hirakawa's debut: f1db did not know him yet, the entry list did.
    assert final.entries[50].tla == "HIR"
    assert final.driver(2026, 50, "Ryo HIRAKAWA").code == "HIR"


def test_time_penalties_are_read_from_the_classifications_notes(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)
    final = final_classification(2026, 19, "race")

    assert final is not None
    # Car 10's stop-and-go was converted to 30 seconds after the flag.
    assert {car: final.time_penalty(car) for car in (81, 10, 43, 3)} == {81: 10, 10: 30, 43: 10, 3: 0}


def test_the_provisional_classification_is_never_read_as_final(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held(title) for title in MEXICO_2026 if title != FINAL_RACE])

    assert final_classification(2026, 19, "race") is None


def test_a_round_without_a_sprint_has_no_final_sprint_classification(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    assert final_classification(2026, 19, "sprint") is None


def test_a_withdrawn_final_classification_does_not_stand(monkeypatch, tmp_path):
    recalled = dataclasses.replace(held(FINAL_RACE), withdrawn="unlisted")
    hold(monkeypatch, tmp_path, [recalled, held(REVISED_ENTRY_LIST)])

    assert final_classification(2026, 19, "race") is None


def test_an_unreadable_correction_falls_back_to_the_last_one_that_reads(monkeypatch, tmp_path):
    original = held(FINAL_RACE)
    garbled = dataclasses.replace(
        original, url=original.url + "-corrected", title="Doc 90 - Final Race Classification", text="nothing to read"
    )
    hold(monkeypatch, tmp_path, [original, garbled])

    final = final_classification(2026, 19, "race")

    assert final is not None
    assert final.classification.document == 86


def test_an_unreadable_entry_list_falls_back_to_the_previous_one(monkeypatch, tmp_path):
    revised = held(REVISED_ENTRY_LIST)
    hold(monkeypatch, tmp_path, [held(FINAL_RACE), held("Doc 11 - Entry List"), dataclasses.replace(revised, text="?")])

    final = final_classification(2026, 19, "race")

    assert final is not None
    assert final.entries[1].tla == "NOR"


def test_without_an_entry_list_a_car_is_named_by_number_and_printed_name(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held(FINAL_RACE)])

    final = final_classification(2026, 19, "race")

    assert final is not None
    assert final.entries == {}
    assert final.driver(2026, 3, "Max VERSTAPPEN").name == "Max Verstappen"


def test_a_round_the_store_has_nothing_for_is_not_landed(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [])

    assert final_classification(2026, 19, "race") is None


def test_a_store_outage_reads_as_not_landed_so_callers_fall_back(monkeypatch, tmp_path):
    files = hold(monkeypatch, tmp_path)

    def down(year: int) -> frozenset[str]:
        raise FiaStoreError("connection refused")

    monkeypatch.setattr(files, "events", down)

    assert store.STORE is files
    assert final_classification(2026, 19, "race") is None


FINAL_GRID = "Doc 67 - Final Starting Grid"


def test_the_final_starting_grid_wins_with_the_final_qualifying_classification(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    found = fia_starting_grid(2026, 19)

    assert found is not None
    assert (found.grid.document, found.grid.final, found.url) == (67, True, MEXICO_2026[FINAL_GRID]["url"])
    assert found.qualifying is not None
    assert found.qualifying.document == 59
    assert [note.document for note in found.rulings(30)] == [58, 34, 65]
    assert found.driver(2026, 50).code == "HIR"


def test_a_sprint_document_never_answers_for_the_race(monkeypatch, tmp_path):
    grid, race = held(FINAL_GRID), held(FINAL_RACE)
    hold(
        monkeypatch,
        tmp_path,
        [
            grid,
            race,
            dataclasses.replace(grid, url=grid.url + "-sprint", title="Doc 91 - Sprint Final Starting Grid"),
            dataclasses.replace(race, url=race.url + "-sprint", title="Doc 92 - Sprint Final Race Classification"),
        ],
    )

    found = fia_starting_grid(2026, 19)
    final = final_classification(2026, 19, "race")

    assert found is not None
    assert final is not None
    assert (found.url, final.url) == (grid.url, race.url)


def test_no_grid_before_the_fia_publishes_one(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held(FINAL_RACE)])

    assert fia_starting_grid(2026, 19) is None


def test_the_rounds_documents_are_read_once_a_minute(monkeypatch, tmp_path):
    files = hold(monkeypatch, tmp_path)
    reads: list[str] = []
    load = files.load_event
    monkeypatch.setattr(files, "load_event", lambda year, event: reads.append(event) or load(year, event))

    final_classification(2026, 19, "race")
    fia_starting_grid(2026, 19)

    assert len(reads) == 1


QUALIFYING_TRACK_LIMITS = "Doc 48 - Infringement - Qualifying Deleted Lap Times"
QUALIFYING_DOUBLE_YELLOW = "Doc 49 - Infringement - Qualifying Deleted Lap Times - Double Yellow"


def _timed(rows: tuple) -> list[tuple[int, str]]:
    return [(row.car, row.lap_time) for row in rows if row.lap_time is not None]


def test_every_deleted_lap_sheet_of_the_session_counts(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    qualifying = fia_deleted_laps(2026, 19, "qualifying")

    # Track limits (doc 48) and the double yellow (doc 49), "PIT" rows included without a time.
    assert len(qualifying) == 12
    assert _timed(qualifying) == [
        (18, "1:29.337"),
        (6, "1:19.035"),
        (44, "1:23.081"),
        (87, "1:17.847"),
        (16, "1:41.066"),
        (55, "1:31.549"),
    ]
    assert len(fia_deleted_laps(2026, 19, "Race")) == 13
    assert fia_deleted_laps(2026, 19, "Sprint") == ()


def test_a_withdrawn_or_unreadable_deleted_lap_sheet_does_not_count(monkeypatch, tmp_path):
    withdrawn = dataclasses.replace(held(QUALIFYING_TRACK_LIMITS), withdrawn="unlisted")
    garbled = dataclasses.replace(
        held(QUALIFYING_TRACK_LIMITS), url="https://example.test/48b", text="Session Qualifying"
    )
    hold(monkeypatch, tmp_path, [withdrawn, garbled, held(QUALIFYING_DOUBLE_YELLOW)])

    assert _timed(fia_deleted_laps(2026, 19, "Qualifying")) == [(16, "1:41.066"), (55, "1:31.549")]


def test_no_deleted_laps_while_the_store_is_down(monkeypatch, tmp_path):
    files = hold(monkeypatch, tmp_path)

    def down(year: int) -> frozenset[str]:
        raise FiaStoreError("connection refused")

    monkeypatch.setattr(files, "events", down)

    assert fia_deleted_laps(2026, 19, "Qualifying") == ()
