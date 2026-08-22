"""Tests for curated driver availability adjustments (app.data.driver_availability).

The behaviour under test: an adjustment is validated and attributed on write,
tolerant of malformed rows on read, and a store outage is reported rather than
being mistaken for "no adjustments" — which would quietly restore a withdrawn
driver to the grid.
"""

import pytest

from app.data import driver_availability as availability_module
from app.data.driver_availability import (
    InvalidAdjustment,
    clear_driver_adjustment,
    load_weekend_availability,
    record_driver_out,
    round_key,
)
from app.data.store_types import ReadResult, WriteResult

YEAR = 2026
ROUND = 15


class FakeStore:
    """In-memory document store that can be told to fail."""

    def __init__(self, payload=None, readable=True, durable=True):
        self.payload = payload
        self.readable = readable
        self.durable = durable
        self.writes = []

    def read(self, name):
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append(payload)
        self.payload = payload
        return WriteResult(ok=True, durable=self.durable)


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(availability_module, "document_store", fake)
    return fake


def stored(driver_code="HAD", **overrides):
    row = {
        "driver_code": driver_code,
        "status": "out",
        "reason": "wrist injury",
        "source": "https://example.test/announcement",
        "noted_at": "2026-08-20T09:00:00+00:00",
        "replacement_code": "",
        "replacement_name": "",
        "replacement_team": "",
    }
    return {**row, **overrides}


class TestLoad:
    def test_no_document_means_no_adjustments(self, store):
        result = load_weekend_availability(YEAR, ROUND)

        assert result.ok is True
        assert result.adjustments == ()
        assert result.withdrawn == frozenset()

    def test_reads_the_round_it_was_asked_for(self, store):
        store.payload = {"rounds": {round_key(YEAR, ROUND): [stored()], round_key(YEAR, 16): [stored("ALO")]}}

        result = load_weekend_availability(YEAR, ROUND)

        assert result.withdrawn == {"HAD"}

    def test_a_failed_read_is_not_an_empty_override_set(self, store):
        store.readable = False

        result = load_weekend_availability(YEAR, ROUND)

        assert result.ok is False
        assert result.error == "connection refused"
        assert result.adjustments == ()

    @pytest.mark.parametrize(
        "row",
        [
            "not a dict",
            {"driver_code": "HADJAR", "status": "out"},
            {"driver_code": "HAD", "status": "maybe"},
            {"status": "out"},
        ],
    )
    def test_malformed_rows_are_discarded_not_raised(self, store, row):
        store.payload = {"rounds": {round_key(YEAR, ROUND): [row, stored("ALO")]}}

        result = load_weekend_availability(YEAR, ROUND)

        assert result.withdrawn == {"ALO"}

    def test_missing_attribution_is_labelled_rather_than_invented(self, store):
        store.payload = {"rounds": {round_key(YEAR, ROUND): [stored(reason="", source="")]}}

        note = load_weekend_availability(YEAR, ROUND).notes[0]

        assert "reason not recorded" in note
        assert "source not recorded" in note

    def test_replacement_appears_in_the_note(self, store):
        store.payload = {
            "rounds": {
                round_key(YEAR, ROUND): [
                    stored(replacement_code="DUN", replacement_name="Ayumu Iwasa", replacement_team="Red Bull")
                ]
            }
        }

        result = load_weekend_availability(YEAR, ROUND)

        assert len(result.replacements) == 1
        assert "replaced by Ayumu Iwasa" in result.notes[0]


class TestRecord:
    def test_records_a_withdrawal_with_attribution(self, store):
        result = record_driver_out(YEAR, ROUND, "had", "wrist injury", "https://example.test/x")

        assert result.ok is True
        row = store.payload["rounds"][round_key(YEAR, ROUND)][0]
        assert row["driver_code"] == "HAD"
        assert row["reason"] == "wrist injury"
        assert row["noted_at"]

    def test_re_recording_supersedes_rather_than_duplicates(self, store):
        record_driver_out(YEAR, ROUND, "HAD", "wrist injury", "https://example.test/x")
        record_driver_out(YEAR, ROUND, "HAD", "hand surgery", "https://example.test/y")

        rows = store.payload["rounds"][round_key(YEAR, ROUND)]
        assert len(rows) == 1
        assert rows[0]["reason"] == "hand surgery"

    def test_other_rounds_survive_a_write(self, store):
        store.payload = {"rounds": {round_key(YEAR, 16): [stored("ALO")]}}

        record_driver_out(YEAR, ROUND, "HAD", "wrist injury", "https://example.test/x")

        assert store.payload["rounds"][round_key(YEAR, 16)]

    def test_a_write_on_top_of_a_failed_read_is_refused(self, store):
        store.readable = False

        result = record_driver_out(YEAR, ROUND, "HAD", "wrist injury", "https://example.test/x")

        assert result.ok is False
        assert store.writes == []

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"driver_code": "HADJAR"},
            {"driver_code": ""},
            {"reason": "  "},
            {"source": ""},
            {"replacement_code": "TOO_LONG"},
            {"source": "https://<announcement-url>"},
            {"reason": "<why>"},
        ],
    )
    def test_invalid_input_is_rejected_at_the_boundary(self, store, kwargs):
        args = {
            "driver_code": "HAD",
            "reason": "wrist injury",
            "source": "https://example.test/x",
            **kwargs,
        }
        with pytest.raises(InvalidAdjustment):
            record_driver_out(YEAR, ROUND, **args)

        assert store.writes == []


class TestClear:
    def test_removes_only_the_named_driver(self, store):
        store.payload = {"rounds": {round_key(YEAR, ROUND): [stored("HAD"), stored("ALO")]}}

        clear_driver_adjustment(YEAR, ROUND, "HAD")

        assert load_weekend_availability(YEAR, ROUND).withdrawn == {"ALO"}

    def test_clearing_on_a_failed_read_is_refused(self, store):
        store.readable = False

        result = clear_driver_adjustment(YEAR, ROUND, "HAD")

        assert result.ok is False
        assert store.writes == []

    def test_rejects_an_invalid_code(self, store):
        with pytest.raises(InvalidAdjustment):
            clear_driver_adjustment(YEAR, ROUND, "NOPE")
