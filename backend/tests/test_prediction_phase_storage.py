"""Tests for storing and serving a race's two prediction phases side by side.

The behaviour under test: each phase is written and read as its own snapshot,
so recomputing one leaves the other exactly as it was — the guarantee the two
prediction tabs rest on.
"""

import pytest

from app.data.predictions import PHASE_POST_QUALIFYING, PHASE_PRE_QUALIFYING
from app.data.store_types import ReadResult, WriteResult
from app.services import prediction_cache as cache_module
from app.services import predictions as service_module
from app.services.prediction_cache import (
    PREDICTION_LOGIC_VERSION,
    PredictionSnapshotCache,
)
from app.services.predictions import (
    compute_and_store_race_prediction,
    get_cached_race_prediction,
)

pytestmark = pytest.mark.unit

YEAR = 2026
ROUND = 9


class FakeDocumentStore:
    """An in-memory stand-in that answers reads and records writes."""

    def __init__(self) -> None:
        self.payload: dict | None = None

    def read(self, name: str) -> ReadResult:
        return ReadResult(payload=self.payload)

    def write(self, name: str, payload: dict) -> WriteResult:
        self.payload = payload
        return WriteResult()


def _result(phase: str, winner: str) -> dict:
    return {
        "year": YEAR,
        "round": ROUND,
        "logic_version": PREDICTION_LOGIC_VERSION,
        "prediction_phase": phase,
        "predictions": [{"position": 1, "driver_code": winner, "confidence_low": 60, "confidence_high": 80}],
        "risk_predictions": [],
    }


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setattr(cache_module, "document_store", FakeDocumentStore())
    instance = PredictionSnapshotCache()
    monkeypatch.setattr(service_module, "prediction_snapshot_cache", instance)
    return instance


def _winner(snapshot: dict | None) -> str | None:
    return (snapshot or {}).get("predictions", [{}])[0].get("driver_code")


# ---------------------------------------------------------------------------
# Reading each phase
# ---------------------------------------------------------------------------

def test_each_phase_is_served_from_its_own_snapshot(cache):
    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))
    cache.set(YEAR, ROUND, _result(PHASE_POST_QUALIFYING, "NOR"))

    assert _winner(cache.get(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)) == "VER"
    assert _winner(cache.get(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)) == "NOR"


def test_asking_for_no_phase_serves_the_most_recent_snapshot(cache):
    cache.set(YEAR, ROUND, _result(PHASE_POST_QUALIFYING, "NOR"))
    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))

    assert _winner(cache.get(YEAR, ROUND)) == "VER"


def test_a_phase_with_no_snapshot_is_a_miss_not_the_other_phase(cache):
    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))

    assert cache.get(YEAR, ROUND, phase=PHASE_POST_QUALIFYING) is None


def test_a_race_with_no_snapshots_at_all_is_a_miss(cache):
    assert cache.get(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING) is None
    assert cache.get(YEAR, ROUND) is None


def test_an_unknown_phase_falls_back_to_the_latest_snapshot(cache):
    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))

    assert _winner(cache.get(YEAR, ROUND, phase="during_qualifying")) == "VER"


def test_a_snapshot_from_superseded_logic_is_a_miss_for_its_phase(cache):
    stale = {**_result(PHASE_PRE_QUALIFYING, "VER"), "logic_version": PREDICTION_LOGIC_VERSION - 1}
    cache.set(YEAR, ROUND, stale)

    assert cache.get(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING) is None


def test_stored_phases_are_reported_in_a_stable_order(cache):
    cache.set(YEAR, ROUND, _result(PHASE_POST_QUALIFYING, "NOR"))
    assert cache.phases_stored(YEAR, ROUND) == [PHASE_POST_QUALIFYING]

    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))
    assert cache.phases_stored(YEAR, ROUND) == [PHASE_PRE_QUALIFYING, PHASE_POST_QUALIFYING]


def test_a_race_never_predicted_has_no_stored_phases(cache):
    assert cache.phases_stored(YEAR, ROUND) == []


# ---------------------------------------------------------------------------
# Recomputing one phase
# ---------------------------------------------------------------------------

def test_recomputing_one_phase_leaves_the_other_untouched(cache, monkeypatch):
    cache.set(YEAR, ROUND, _result(PHASE_PRE_QUALIFYING, "VER"))
    cache.set(YEAR, ROUND, _result(PHASE_POST_QUALIFYING, "NOR"))

    monkeypatch.setattr(
        service_module,
        "compute_race_predictions",
        lambda year, round_num, phase=None: _result(PHASE_PRE_QUALIFYING, "PIA"),
    )
    compute_and_store_race_prediction(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)

    assert _winner(get_cached_race_prediction(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)) == "PIA"
    assert _winner(get_cached_race_prediction(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)) == "NOR"


def test_a_post_qualifying_request_is_refused_before_qualifying_runs(cache, monkeypatch):
    # The model can only answer pre-qualifying until the session has run, and
    # filing that answer under the post-qualifying tab would misreport it.
    monkeypatch.setattr(
        service_module,
        "compute_race_predictions",
        lambda year, round_num, phase=None: _result(PHASE_PRE_QUALIFYING, "VER"),
    )

    result = compute_and_store_race_prediction(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)

    assert result["predictions"] == []
    assert "Qualifying has not run yet" in result["error"]
    assert cache.get(YEAR, ROUND, phase=PHASE_POST_QUALIFYING) is None


def test_a_pre_qualifying_request_is_stored_even_after_qualifying_has_run(cache, monkeypatch):
    monkeypatch.setattr(
        service_module,
        "compute_race_predictions",
        lambda year, round_num, phase=None: _result(PHASE_PRE_QUALIFYING, "VER"),
    )

    compute_and_store_race_prediction(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)

    assert _winner(cache.get(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)) == "VER"


def test_a_compute_that_produced_nothing_is_not_stored(cache, monkeypatch):
    monkeypatch.setattr(
        service_module,
        "compute_race_predictions",
        lambda year, round_num, phase=None: {"year": YEAR, "round": ROUND, "predictions": [], "error": "no data"},
    )

    result = compute_and_store_race_prediction(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)

    assert result["error"] == "no data"
    assert cache.get(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING) is None


def test_the_requested_phase_reaches_the_model(cache, monkeypatch):
    seen: list[str | None] = []

    def _record(year, round_num, phase=None):
        seen.append(phase)
        return _result(PHASE_PRE_QUALIFYING, "VER")

    monkeypatch.setattr(service_module, "compute_race_predictions", _record)
    compute_and_store_race_prediction(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)
    compute_and_store_race_prediction(YEAR, ROUND, phase="nonsense")

    assert seen == [PHASE_PRE_QUALIFYING, None]
