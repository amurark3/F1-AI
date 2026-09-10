"""Tests for single-flight race prediction computation.

Computing a snapshot costs a stack of FastF1 session loads. Two requests
arriving together for the same race — two tabs, or the command centre's own
segments — used to pay for it twice, on a host with a fraction of a CPU.

The behaviour under test: the second request waits for the first and reuses
the snapshot it stored, and predictions for different races still run
independently.
"""

import threading

import pytest

from app.services import predictions as predictions_module
from app.services.predictions import get_or_compute_race_prediction

pytestmark = pytest.mark.unit

YEAR = 2026
ROUND = 15

SNAPSHOT = {
    "predictions": [
        {"driver_code": "NOR", "driver_name": "Lando Norris", "team": "McLaren", "confidence_low": 60, "confidence_high": 80},
    ],
    "data_sources": ["trained_ml_model"],
}


class FakeSnapshotCache:
    """Holds snapshots the way the durable cache would, without a store."""

    def __init__(self) -> None:
        self.entries: dict[tuple[int, int], dict] = {}

    def get(self, year: int, round_num: int) -> dict | None:
        return self.entries.get((year, round_num))


@pytest.fixture
def cache(monkeypatch):
    fake = FakeSnapshotCache()
    monkeypatch.setattr(predictions_module, "prediction_snapshot_cache", fake)
    monkeypatch.setattr(predictions_module, "_compute_locks", {})
    return fake


def test_a_stored_snapshot_is_never_recomputed(cache, monkeypatch):
    cache.entries[(YEAR, ROUND)] = SNAPSHOT
    monkeypatch.setattr(
        predictions_module,
        "compute_and_store_race_prediction",
        lambda *args, **kwargs: pytest.fail("stored snapshot must not be recomputed"),
    )

    result = get_or_compute_race_prediction(YEAR, ROUND)

    assert result["predictions"] == SNAPSHOT["predictions"]


def test_the_compute_runs_while_holding_that_race_lock(cache, monkeypatch):
    held: list[bool] = []

    def compute(year, round_num, *, reason="manual_compute"):
        held.append(predictions_module._compute_lock(year, round_num).locked())
        return SNAPSHOT

    monkeypatch.setattr(predictions_module, "compute_and_store_race_prediction", compute)

    get_or_compute_race_prediction(YEAR, ROUND)

    assert held == [True]


def test_a_concurrent_request_waits_and_reuses_the_snapshot(cache, monkeypatch):
    computing = threading.Event()
    release = threading.Event()
    computed: list[int] = []

    def compute(year, round_num, *, reason="manual_compute"):
        computed.append(round_num)
        computing.set()
        release.wait(timeout=5)
        cache.entries[(year, round_num)] = SNAPSHOT
        return SNAPSHOT

    monkeypatch.setattr(predictions_module, "compute_and_store_race_prediction", compute)

    results: list[dict] = []

    def request():
        results.append(get_or_compute_race_prediction(YEAR, ROUND))

    first = threading.Thread(target=request)
    first.start()
    assert computing.wait(timeout=5), "first request never reached the compute"

    second = threading.Thread(target=request)
    second.start()
    release.set()

    first.join(timeout=5)
    second.join(timeout=5)

    assert computed == [ROUND]
    assert len(results) == 2
    assert all(result["predictions"] == SNAPSHOT["predictions"] for result in results)


def test_different_races_are_not_serialised_behind_each_other(cache, monkeypatch):
    started = threading.Event()
    computed: list[int] = []

    def compute(year, round_num, *, reason="manual_compute"):
        computed.append(round_num)
        if round_num == ROUND:
            started.set()
            # Holds this race's lock; a different race must not be blocked by it.
            assert other_finished.wait(timeout=5), "a different race was blocked"
        return SNAPSHOT

    other_finished = threading.Event()
    monkeypatch.setattr(predictions_module, "compute_and_store_race_prediction", compute)

    blocking = threading.Thread(target=lambda: get_or_compute_race_prediction(YEAR, ROUND))
    blocking.start()
    assert started.wait(timeout=5)

    get_or_compute_race_prediction(YEAR, ROUND + 1)
    other_finished.set()
    blocking.join(timeout=5)

    assert sorted(computed) == [ROUND, ROUND + 1]
