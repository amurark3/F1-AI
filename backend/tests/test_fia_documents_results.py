"""The FIA final classification read from the store, over the 2026 Mexico City GP's real documents."""

from __future__ import annotations

import dataclasses

import pytest

from app.data.fia_documents import store
from app.data.fia_documents.results import final_classification
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
    assert final.codes[50] == "HIR"
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
    assert final.codes[1] == "NOR"


def test_without_an_entry_list_a_car_is_named_by_number_and_printed_name(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held(FINAL_RACE)])

    final = final_classification(2026, 19, "race")

    assert final is not None
    assert final.codes == {}
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
