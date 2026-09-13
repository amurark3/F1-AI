"""Tests for the phase parameter on the prediction routes.

The behaviour under test: a client can ask for — and recompute — one of a
race's two prediction phases, and a client that asks for neither keeps the
behaviour it had before phases existed.
"""

import asyncio

import pytest

from app.api.routers import predictions as router_module
from app.api.routers.predictions import compute_predictions, get_prediction_snapshot
from app.data.predictions import PHASE_POST_QUALIFYING, PHASE_PRE_QUALIFYING

pytestmark = pytest.mark.unit

YEAR = 2026
ROUND = 9


@pytest.fixture(autouse=True)
def reviewed_phases(monkeypatch):
    """Record which phase each review refresh asked for, without a FastF1 load.

    Scoring a stored snapshot normally loads the race result, so the routes are
    pointed at a recorder instead — which also makes the phase they pass visible.
    """
    seen: list[str | None] = []

    def _review(year, round_num, phase=None):
        seen.append(phase)
        return {"evaluated": True}

    monkeypatch.setattr(router_module, "get_prediction_review", _review)
    return seen


def _stored(phase: str | None) -> dict:
    return {"year": YEAR, "round": ROUND, "prediction_phase": phase, "predictions": [{"driver_code": "NOR"}]}


def test_a_snapshot_request_carries_its_phase_to_the_store(monkeypatch):
    seen: list[str | None] = []

    def _get(year, round_num, phase=None):
        seen.append(phase)
        return _stored(phase)

    monkeypatch.setattr(router_module, "get_cached_race_prediction", _get)

    result = asyncio.run(get_prediction_snapshot(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING))

    assert seen == [PHASE_PRE_QUALIFYING]
    assert result["prediction_phase"] == PHASE_PRE_QUALIFYING


def test_an_unknown_phase_reads_the_latest_snapshot(monkeypatch):
    seen: list[str | None] = []

    def _get(year, round_num, phase=None):
        seen.append(phase)
        return _stored(None)

    monkeypatch.setattr(router_module, "get_cached_race_prediction", _get)

    asyncio.run(get_prediction_snapshot(YEAR, ROUND, phase="during_qualifying"))

    assert seen == [None]


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (PHASE_PRE_QUALIFYING, "No stored pre-qualifying prediction. Run the model to create one."),
        (PHASE_POST_QUALIFYING, "No stored post-qualifying prediction. Run the model to create one."),
        (None, "No stored prediction snapshot. Run the model to create one."),
    ],
)
def test_an_empty_tab_says_which_prediction_is_missing(monkeypatch, phase, expected):
    monkeypatch.setattr(router_module, "get_cached_race_prediction", lambda *a, **k: None)

    result = asyncio.run(get_prediction_snapshot(YEAR, ROUND, phase=phase))

    assert result["error"] == expected
    assert result["prediction_phase"] == phase
    assert result["cache"]["status"] == "missing"


def test_a_recompute_targets_only_the_requested_phase(monkeypatch):
    seen: list[dict] = []

    def _compute(year, round_num, *, reason, phase):
        seen.append({"reason": reason, "phase": phase})
        return _stored(phase)

    monkeypatch.setattr(router_module, "compute_and_store_race_prediction", _compute)

    asyncio.run(
        compute_predictions(YEAR, ROUND, reason="qualifying_recompute", phase=PHASE_POST_QUALIFYING)
    )

    assert seen == [{"reason": "qualifying_recompute", "phase": PHASE_POST_QUALIFYING}]


def test_a_recompute_with_an_unknown_phase_lets_the_data_decide(monkeypatch):
    seen: list[dict] = []

    def _compute(year, round_num, *, reason, phase):
        seen.append({"reason": reason, "phase": phase})
        return _stored(phase)

    monkeypatch.setattr(router_module, "compute_and_store_race_prediction", _compute)

    asyncio.run(compute_predictions(YEAR, ROUND, reason="nonsense", phase="nonsense"))

    assert seen == [{"reason": "manual_compute", "phase": None}]


def test_a_failed_recompute_still_names_the_tab_it_was_for(monkeypatch):
    def _boom(year, round_num, *, reason, phase):
        raise RuntimeError("fastf1 exploded")

    monkeypatch.setattr(router_module, "compute_and_store_race_prediction", _boom)

    result = asyncio.run(compute_predictions(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING))

    assert result["prediction_phase"] == PHASE_PRE_QUALIFYING
    assert result["predictions"] == []


def test_a_served_snapshot_is_scored_against_the_phase_being_viewed(monkeypatch, reviewed_phases):
    monkeypatch.setattr(
        router_module, "get_cached_race_prediction", lambda *a, **k: _stored(PHASE_PRE_QUALIFYING)
    )

    result = asyncio.run(get_prediction_snapshot(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING))

    assert reviewed_phases == [PHASE_PRE_QUALIFYING]
    assert result["prediction_review"] == {"evaluated": True}
