"""Tests for app.services.predictions — the snapshot read/compute/store facade.

The risk this file pins is the *snapshot policy*: a stored prediction must be
served back unchanged, a fresh compute must be written to the cache exactly
once with the right provenance reason, and a compute that produced no
predictions must NOT be stored (that would freeze an empty snapshot in place
until someone manually recomputed it).

The document store and the compute path are both faked here; the enrichment
those functions wrap has its own coverage in the router tests.
"""

from __future__ import annotations

import pytest

from app.services import predictions as service


class _RecordingCache:
    """Stand-in for ``prediction_snapshot_cache`` that records every write."""

    def __init__(self, stored: dict | None = None) -> None:
        self.stored = stored
        self.set_calls: list[tuple[int, int, dict, str]] = []

    def get(self, year: int, round_num: int) -> dict | None:
        return self.stored

    def set(self, year: int, round_num: int, result: dict, *, reason: str) -> dict:
        self.set_calls.append((year, round_num, result, reason))
        return {**result, "cache_status": "stored"}


@pytest.fixture
def cache(monkeypatch):
    """Install a recording cache and neutralise the review rebuild."""
    recording = _RecordingCache()
    monkeypatch.setattr(service, "prediction_snapshot_cache", recording)
    monkeypatch.setattr(service, "build_prediction_review", lambda year, round_num: {"evaluated": False})
    return recording


def _snapshot(**fields) -> dict:
    """A minimal computed result with one prediction row."""
    base = {
        "year": 2026,
        "round": 2,
        "predictions": [
            {"driver_name": "Max Verstappen", "driver_code": "VER", "confidence_low": 60, "confidence_high": 80}
        ],
        "data_sources": ["qualifying"],
    }
    return {**base, **fields}


@pytest.mark.unit
def test_get_cached_returns_none_when_nothing_is_stored(cache):
    cache.stored = None

    assert service.get_cached_race_prediction(2026, 2) is None


@pytest.mark.unit
def test_get_cached_enriches_the_stored_snapshot_without_recomputing(cache, monkeypatch):
    monkeypatch.setattr(service, "compute_race_predictions", lambda *_: pytest.fail("must not recompute a cached race"))
    cache.stored = _snapshot()

    result = service.get_cached_race_prediction(2026, 2)

    assert result["model_summary"]["leader_code"] == "VER"
    assert cache.set_calls == []


@pytest.mark.unit
def test_compute_and_store_writes_the_snapshot_with_the_given_reason(cache, monkeypatch):
    monkeypatch.setattr(service, "compute_race_predictions", lambda year, round_num: _snapshot())

    result = service.compute_and_store_race_prediction(2026, 2, reason="qualifying_recompute")

    assert [(y, r, reason) for y, r, _, reason in cache.set_calls] == [(2026, 2, "qualifying_recompute")]
    # The enriched payload is built from what the cache returned, not the raw compute.
    assert result["cache_status"] == "stored"


@pytest.mark.unit
def test_compute_and_store_refuses_to_store_an_empty_result(cache, monkeypatch):
    monkeypatch.setattr(service, "compute_race_predictions", lambda year, round_num: _snapshot(predictions=[]))

    result = service.compute_and_store_race_prediction(2026, 2)

    assert cache.set_calls == [], "an empty result must not be frozen into the snapshot cache"
    assert result["model_summary"]["status"] == "data_unavailable"


@pytest.mark.unit
def test_get_or_compute_serves_the_cached_snapshot(cache, monkeypatch):
    monkeypatch.setattr(service, "compute_race_predictions", lambda *_: pytest.fail("cache hit must not compute"))
    cache.stored = _snapshot()

    assert service.get_or_compute_race_prediction(2026, 2)["model_summary"]["leader_code"] == "VER"


@pytest.mark.unit
def test_get_or_compute_records_first_compute_as_the_reason(cache, monkeypatch):
    monkeypatch.setattr(service, "compute_race_predictions", lambda year, round_num: _snapshot())

    service.get_or_compute_race_prediction(2026, 2)

    assert cache.set_calls[0][3] == "first_compute"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12, 12.0),
        ("7.5", 7.5),
        (None, 0.0),
        ("", 0.0),
        ("not-a-number", 0.0),
        ([1, 2], 0.0),
    ],
)
def test_safe_number_coerces_or_degrades_to_zero(value, expected):
    assert service.safe_number(value) == expected
