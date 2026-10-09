"""Tests for durable prediction history (app.data.predictions.history).

This module is the only writer of the document every accuracy number is later
computed from, and every write is a read-modify-write of one shared document.
The failure this file exists to prevent is the expensive one: a *failed read*
being treated as an empty history, so the next save replaces an entire season of
accumulated predictions with the single race in hand. That is exactly the outage
``ReadResult.ok`` was introduced for, and ``save_prediction`` must refuse to
write when it cannot see what is already there.

The rest is the same theme at smaller scale: a race that has not happened yet
fails every FastF1 load, so the retry must be rate-limited rather than paid on
every page view; and a classification row whose position will not parse must
drop out of *all three* result maps together, or the maps disagree about who was
classified.

The document store and FastF1 are both replaced at the module boundary — the
namespace these functions resolve the names in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pytest

from app.data.predictions import history as history_module
from app.data.predictions.history import (
    ACTUAL_RESULT_RETRY_SECONDS,
    _classify_results,
    _load_prediction_history,
    _read_prediction_history,
    _save_prediction_history,
    _should_attempt_actual_load,
    record_actual_result,
    save_prediction,
)
from app.data.store_types import ReadResult, WriteResult

YEAR = 2026
ROUND = 4
KEY = f"({YEAR},{ROUND})"


@dataclass
class _FakeStore:
    """A document store scripted per test: readable/writable, and what it holds."""

    document: object = field(default_factory=dict)
    read_ok: bool = True
    write_ok: bool = True
    writes: list[dict] = field(default_factory=list)

    def read(self, name: str) -> ReadResult:
        if not self.read_ok:
            return ReadResult(ok=False, error="backend unreachable")
        return ReadResult(payload=self.document)

    def write(self, name: str, payload: dict) -> WriteResult:
        self.writes.append(payload)
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="backend unreachable")
        self.document = payload
        return WriteResult()


@pytest.fixture
def store(monkeypatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(history_module, "document_store", fake)
    return fake


@pytest.fixture(autouse=True)
def _clear_retry_deadlines():
    """Retry deadlines are module-global and would leak across tests."""
    history_module._actual_result_attempts.clear()
    yield
    history_module._actual_result_attempts.clear()


def _predictions(**overrides: object) -> dict:
    """A compute_race_predictions-shaped payload, minimally populated."""
    payload = {
        "generated_at": "2026-05-24T10:00:00+00:00",
        "prediction_phase": "post_qualifying",
        "data_sources": ["qualifying"],
        "predictions": [
            {"driver_code": "VER", "position": 1},
            {"driver_code": "NOR", "position": 2},
        ],
        "risk_predictions": [
            {
                "driver_code": "NOR",
                "dnf_risk_pct": 22,
                "crash_risk_pct": 11,
                "mechanical_risk_pct": 14,
                "risk_level": "high",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _results_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reading and writing the document
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_successful_read_reports_the_document_and_that_it_was_readable(store):
    store.document = {KEY: {"predicted_positions": {"VER": 1}}}

    assert _read_prediction_history() == (store.document, True)


@pytest.mark.unit
def test_a_failed_read_is_distinguishable_from_an_empty_history(store):
    store.read_ok = False

    history, readable = _read_prediction_history()

    # The pair is the whole point: {} alone cannot tell a caller whether it is
    # safe to write.
    assert history == {}
    assert readable is False


@pytest.mark.unit
def test_a_payload_of_the_wrong_shape_is_treated_as_no_history(store):
    store.document = ["not", "a", "document"]

    assert _read_prediction_history() == ({}, True)


@pytest.mark.unit
def test_loading_history_hides_the_readability_flag_from_read_only_callers(store):
    store.read_ok = False

    assert _load_prediction_history() == {}


@pytest.mark.unit
def test_a_failed_write_is_reported_rather_than_raised(store):
    store.write_ok = False

    _save_prediction_history({"a": 1})

    assert store.writes == [{"a": 1}]


# ---------------------------------------------------------------------------
# Saving a prediction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_saved_prediction_records_positions_risks_and_provenance(store):
    save_prediction(YEAR, ROUND, _predictions())

    entry = store.document[KEY]
    assert entry["predicted_positions"] == {"VER": 1, "NOR": 2}
    assert entry["risk_predictions"]["NOR"]["dnf_risk_pct"] == 22
    assert entry["prediction_phase"] == "post_qualifying"
    assert entry["data_sources"] == ["qualifying"]
    assert len(entry["snapshots"]) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "predictions",
    [
        pytest.param([], id="no_predictions"),
        pytest.param([{"driver_code": "", "position": 1}], id="no_driver_code"),
        pytest.param([{"driver_code": "VER", "position": None}], id="no_position"),
    ],
)
def test_a_prediction_with_no_usable_finishing_order_is_not_stored(store, predictions):
    save_prediction(YEAR, ROUND, _predictions(predictions=predictions))

    assert store.writes == []


@pytest.mark.unit
def test_a_risk_row_without_a_driver_code_is_dropped(store):
    save_prediction(YEAR, ROUND, _predictions(risk_predictions=[{"dnf_risk_pct": 30}]))

    assert store.document[KEY]["risk_predictions"] == {}


@pytest.mark.unit
def test_saving_is_skipped_entirely_when_the_existing_history_cannot_be_read(store):
    store.read_ok = False

    save_prediction(YEAR, ROUND, _predictions())

    # Losing one race's snapshot is recoverable; overwriting a season is not.
    assert store.writes == []


@pytest.mark.unit
def test_a_second_prediction_for_the_same_race_appends_a_snapshot(store):
    save_prediction(YEAR, ROUND, _predictions(prediction_phase="pre_qualifying"))
    save_prediction(YEAR, ROUND, _predictions(prediction_phase="post_qualifying"))

    entry = store.document[KEY]
    phases = [snapshot["prediction_phase"] for snapshot in entry["snapshots"]]
    assert phases == ["pre_qualifying", "post_qualifying"]
    # The top-level fields track the newest snapshot, which is what gets served.
    assert entry["prediction_phase"] == "post_qualifying"


@pytest.mark.unit
def test_only_the_eight_most_recent_snapshots_are_retained(store):
    for run in range(10):
        save_prediction(YEAR, ROUND, _predictions(generated_at=f"2026-05-24T{run:02d}:00:00+00:00"))

    snapshots = store.document[KEY]["snapshots"]
    assert len(snapshots) == 8
    assert snapshots[0]["generated_at"] == "2026-05-24T02:00:00+00:00"
    assert snapshots[-1]["generated_at"] == "2026-05-24T09:00:00+00:00"


@pytest.mark.unit
def test_re_saving_a_prediction_does_not_discard_the_recorded_result(store):
    save_prediction(YEAR, ROUND, _predictions())
    store.document[KEY]["actual_positions"] = {"VER": 1, "NOR": 5}
    store.document[KEY]["actual_statuses"] = {"NOR": "Engine"}
    store.document[KEY]["actual_incidents"] = {"NOR": {"dnf": True}}

    save_prediction(YEAR, ROUND, _predictions())

    entry = store.document[KEY]
    assert entry["actual_positions"] == {"VER": 1, "NOR": 5}
    assert entry["actual_statuses"] == {"NOR": "Engine"}
    assert entry["actual_incidents"] == {"NOR": {"dnf": True}}


@pytest.mark.unit
def test_a_generated_at_is_stamped_when_the_payload_carries_none(store):
    payload = _predictions()
    del payload["generated_at"]

    save_prediction(YEAR, ROUND, payload)

    assert store.document[KEY]["generated_at"].startswith("20")


# ---------------------------------------------------------------------------
# Retry back-off
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_result_load_is_attempted_once_then_backed_off():
    assert _should_attempt_actual_load(YEAR, ROUND) is True
    # A race that has not run yet fails every load, so an unguarded retry would
    # cost a slow FastF1 round trip on every request.
    assert _should_attempt_actual_load(YEAR, ROUND) is False


@pytest.mark.unit
def test_the_back_off_expires_so_a_finished_race_is_eventually_picked_up(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(history_module.time, "monotonic", lambda: clock[0])

    assert _should_attempt_actual_load(YEAR, ROUND) is True
    clock[0] += ACTUAL_RESULT_RETRY_SECONDS + 1

    assert _should_attempt_actual_load(YEAR, ROUND) is True


@pytest.mark.unit
def test_back_off_is_tracked_per_race():
    _should_attempt_actual_load(YEAR, ROUND)

    assert _should_attempt_actual_load(YEAR, ROUND + 1) is True


# ---------------------------------------------------------------------------
# Classifying a race result
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classification_splits_a_result_into_positions_statuses_and_flags():
    positions, statuses, incidents = _classify_results(
        _results_frame(
            [
                {"Abbreviation": "VER", "Position": 1.0, "Status": "Finished"},
                {"Abbreviation": "NOR", "Position": 15.0, "Status": "Accident"},
            ]
        )
    )

    assert positions == {"VER": 1, "NOR": 15}
    assert statuses["NOR"] == "Accident"
    assert incidents["NOR"] == {"dnf": True, "crash": True, "mechanical": False}
    assert incidents["VER"]["dnf"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "row",
    [
        pytest.param({"Abbreviation": "", "Position": 3.0, "Status": "Finished"}, id="no_code"),
        pytest.param({"Abbreviation": "HUL", "Position": None, "Status": "Finished"}, id="null_position"),
        pytest.param({"Abbreviation": "HUL", "Position": "DNS", "Status": "Did not start"}, id="unparsable_position"),
    ],
)
def test_a_row_that_cannot_be_placed_contributes_to_none_of_the_three_maps(row):
    positions, statuses, incidents = _classify_results(
        _results_frame([{"Abbreviation": "VER", "Position": 1.0, "Status": "Finished"}, row])
    )

    # A status without its position would leave the maps disagreeing about who
    # was classified, which the review table renders directly.
    assert set(positions) == set(statuses) == set(incidents) == {"VER"}


# ---------------------------------------------------------------------------
# Recording the actual result
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    results: object


class _FakeFastF1:
    """Stands in for the ``fastf1`` module inside ``history``."""

    def __init__(self, results: object = None, error: Exception | None = None) -> None:
        self.results = results
        self.error = error
        self.calls: list[tuple] = []

    def get_session(self, year: int, round_num: int, session: str):
        self.calls.append((year, round_num, session))
        if self.error is not None:
            raise self.error
        return _FakeLoadableSession(self.results)


class _FakeLoadableSession:
    def __init__(self, results: object) -> None:
        self.results = results

    def load(self, telemetry: bool = True, laps: bool = True, weather: bool = True) -> None:
        return


@pytest.fixture
def fastf1_results(monkeypatch):
    """Install a scripted FastF1 and hand the test the double back."""

    def _install(results: object = None, error: Exception | None = None) -> _FakeFastF1:
        fake = _FakeFastF1(results=results, error=error)
        monkeypatch.setattr(history_module, "fastf1", fake)
        return fake

    return _install


@pytest.mark.unit
def test_a_finished_race_records_positions_statuses_and_incidents(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    fastf1_results(
        _results_frame(
            [
                {"Abbreviation": "VER", "Position": 1.0, "Status": "Finished"},
                {"Abbreviation": "NOR", "Position": 18.0, "Status": "Engine"},
            ]
        )
    )

    record_actual_result(YEAR, ROUND)

    entry = store.document[KEY]
    assert entry["actual_positions"] == {"VER": 1, "NOR": 18}
    assert entry["actual_statuses"]["NOR"] == "Engine"
    assert entry["actual_incidents"]["NOR"]["mechanical"] is True


@pytest.mark.unit
def test_a_race_with_no_stored_prediction_is_never_fetched(store, fastf1_results):
    fake = fastf1_results(_results_frame([{"Abbreviation": "VER", "Position": 1.0, "Status": "Finished"}]))

    record_actual_result(YEAR, ROUND)

    # Nothing to compare against, so the slow session load is pointless.
    assert fake.calls == []


@pytest.mark.unit
def test_an_already_recorded_result_is_not_fetched_again(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    store.document[KEY]["actual_positions"] = {"VER": 1}
    fake = fastf1_results(_results_frame([{"Abbreviation": "VER", "Position": 2.0, "Status": "Finished"}]))

    record_actual_result(YEAR, ROUND)

    assert fake.calls == []
    assert store.document[KEY]["actual_positions"] == {"VER": 1}


@pytest.mark.unit
def test_a_backed_off_race_is_not_fetched_again_within_the_window(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    fake = fastf1_results(_results_frame([]))

    record_actual_result(YEAR, ROUND)
    record_actual_result(YEAR, ROUND)

    assert len(fake.calls) == 1


@pytest.mark.unit
def test_a_failing_session_load_leaves_the_stored_prediction_untouched(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    writes_before = len(store.writes)
    fastf1_results(error=ConnectionError("ergast is down"))

    record_actual_result(YEAR, ROUND)

    assert len(store.writes) == writes_before
    assert store.document[KEY]["actual_positions"] is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "results",
    [pytest.param(None, id="no_results_object"), pytest.param([], id="empty_classification")],
)
def test_a_race_with_no_classification_yet_records_nothing(store, fastf1_results, results):
    save_prediction(YEAR, ROUND, _predictions())
    writes_before = len(store.writes)
    fastf1_results(results if results is None else _results_frame(results))

    record_actual_result(YEAR, ROUND)

    assert len(store.writes) == writes_before


@pytest.mark.unit
def test_a_result_whose_rows_are_all_unusable_records_nothing(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    writes_before = len(store.writes)
    fastf1_results(_results_frame([{"Abbreviation": "", "Position": 1.0, "Status": "Finished"}]))

    record_actual_result(YEAR, ROUND)

    assert len(store.writes) == writes_before


@pytest.mark.unit
def test_a_result_for_a_race_removed_from_history_mid_flight_is_dropped(store, fastf1_results):
    save_prediction(YEAR, ROUND, _predictions())
    fastf1_results(_results_frame([{"Abbreviation": "VER", "Position": 1.0, "Status": "Finished"}]))
    store.document = {}

    record_actual_result(YEAR, ROUND)

    assert store.document == {}
