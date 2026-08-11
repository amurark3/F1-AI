"""Tests for app.api.routers.predictions — the prediction REST surface.

Four endpoints with genuinely different contracts, and the differences are the
point:

* ``GET /predictions/{y}/{r}`` is the legacy route and **computes on a miss**.
* ``GET .../snapshot`` must **never** trigger model work — it returns whatever
  is stored, or an explicit "missing" envelope. A client on the snapshot route
  is promising not to spend a FastF1 load; if that guarantee slips, the page
  that polls it starts driving the model.
* ``POST .../compute`` is the only route that recomputes deliberately, and it
  clamps ``reason`` to a known set so an arbitrary query string cannot end up
  recorded as provenance on a stored snapshot.

Concurrency matters here too: the per-race lock is what stops two simultaneous
cache misses from both paying for a model run, and the review refresh must give
up after a short wait rather than holding the request open.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import predictions as predictions_router

SNAPSHOT = {
    "year": 2026,
    "round": 1,
    "predictions": [{"code": "VER", "predicted_position": 1}],
    "prediction_review": {"evaluated": False},
}


@pytest.fixture(autouse=True)
def _clear_locks():
    """The lock registry is module-global and would leak between tests."""
    predictions_router.prediction_locks.clear()
    yield
    predictions_router.prediction_locks.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(predictions_router.router)
    return TestClient(app)


@pytest.fixture
def no_review_refresh(monkeypatch):
    """Leave the stored review untouched, so tests isolate the route's own logic."""
    monkeypatch.setattr(predictions_router, "_with_scored_review", _identity)


async def _identity(result):
    return result


# ---------------------------------------------------------------------------
# GET /predictions/{year}/{round}
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_cached_snapshot_is_served_without_computing(client, monkeypatch, no_review_refresh):
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: SNAPSHOT)
    monkeypatch.setattr(predictions_router, "enrich_prediction_result", lambda result: {**result, "enriched": True})
    monkeypatch.setattr(
        predictions_router,
        "get_or_compute_race_prediction",
        lambda *_a, **_k: pytest.fail("a cache hit must not compute"),
    )

    body = client.get("/predictions/2026/1").json()

    assert body["enriched"] is True


@pytest.mark.unit
def test_a_cache_miss_computes_and_returns_the_result(client, monkeypatch):
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: None)
    monkeypatch.setattr(predictions_router, "get_or_compute_race_prediction", lambda y, r: {"year": y, "round": r})

    body = client.get("/predictions/2026/3").json()

    assert body == {"year": 2026, "round": 3}


@pytest.mark.unit
def test_a_snapshot_that_appears_while_waiting_on_the_lock_is_served(client, monkeypatch, no_review_refresh):
    """Double-checked locking: the second caller must not recompute."""
    calls = {"n": 0}

    def get(_year, _round):
        calls["n"] += 1
        # Miss on the pre-lock check, hit on the re-check inside the lock.
        return None if calls["n"] == 1 else SNAPSHOT

    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", get)
    monkeypatch.setattr(predictions_router, "enrich_prediction_result", lambda result: result)
    monkeypatch.setattr(
        predictions_router,
        "get_or_compute_race_prediction",
        lambda *_a, **_k: pytest.fail("the re-check hit must short-circuit the compute"),
    )

    assert client.get("/predictions/2026/1").json()["round"] == 1


@pytest.mark.unit
def test_a_slow_data_source_returns_a_retryable_message(client, monkeypatch):
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: None)
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.01)

    def slow(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(predictions_router, "get_or_compute_race_prediction", slow)

    body = client.get("/predictions/2026/1").json()

    assert body["predictions"] == []
    assert "timed out" in body["error"]
    # A timeout is retry-able, not a server fault, so it carries no error id.
    assert "error_id" not in body


@pytest.mark.unit
def test_a_compute_failure_returns_a_client_safe_error(client, monkeypatch):
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: None)

    def explode(*_args, **_kwargs):
        raise ValueError("no such column: race_data.qualifying_q3")

    monkeypatch.setattr(predictions_router, "get_or_compute_race_prediction", explode)

    body = client.get("/predictions/2026/1").json()

    assert body["predictions"] == []
    assert "error_id" in body
    assert "qualifying_q3" not in str(body)


# ---------------------------------------------------------------------------
# GET /predictions/{year}/{round}/snapshot
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_snapshot_returns_the_stored_prediction(client, monkeypatch, no_review_refresh):
    monkeypatch.setattr(predictions_router, "get_cached_race_prediction", lambda y, r: SNAPSHOT)

    assert client.get("/predictions/2026/1/snapshot").json()["predictions"]


@pytest.mark.unit
def test_snapshot_never_computes_on_a_miss(client, monkeypatch):
    """The whole contract of this route: no model work, ever."""
    monkeypatch.setattr(predictions_router, "get_cached_race_prediction", lambda y, r: None)
    monkeypatch.setattr(
        predictions_router,
        "get_or_compute_race_prediction",
        lambda *_a, **_k: pytest.fail("snapshot must not trigger a compute"),
    )

    body = client.get("/predictions/2026/9/snapshot").json()

    assert body["predictions"] == []
    assert body["cache"] == {"status": "missing", "policy": "stored_until_manual_recompute"}


# ---------------------------------------------------------------------------
# POST /predictions/{year}/{round}/compute
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("reason", ["manual_compute", "qualifying_recompute"])
def test_compute_forwards_an_allowed_reason(client, monkeypatch, reason):
    seen: list[str] = []

    def compute(year, round_num, reason):
        seen.append(reason)
        return {"year": year, "round": round_num}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    client.post("/predictions/2026/1/compute", params={"reason": reason})

    assert seen == [reason]


@pytest.mark.unit
def test_compute_clamps_an_unknown_reason(client, monkeypatch):
    """`reason` is stored as provenance, so arbitrary query text must not reach it."""
    seen: list[str] = []

    def compute(year, round_num, reason):
        seen.append(reason)
        return {}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    client.post("/predictions/2026/1/compute", params={"reason": "because-i-said-so"})

    assert seen == ["manual_compute"]


@pytest.mark.unit
def test_compute_defaults_to_manual(client, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        predictions_router,
        "compute_and_store_race_prediction",
        lambda year, round_num, reason: seen.append(reason) or {},
    )

    client.post("/predictions/2026/1/compute")

    assert seen == ["manual_compute"]


@pytest.mark.unit
def test_compute_timeout_returns_a_retryable_message(client, monkeypatch):
    def slow(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", slow)

    body = client.post("/predictions/2026/1/compute").json()

    assert body["predictions"] == []
    assert body["risk_predictions"] == []
    assert "timed out" in body["error"]


@pytest.mark.unit
def test_compute_failure_returns_a_client_safe_error(client, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("model artifact ridge_v7.joblib not found")

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", explode)

    body = client.post("/predictions/2026/1/compute").json()

    assert "error_id" in body
    assert "ridge_v7" not in str(body)


# ---------------------------------------------------------------------------
# GET /predictions/{year}/{round}/postmortem
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_postmortem_returns_a_stored_analysis_without_regenerating(client, monkeypatch):
    import app.services.self_improvement as si

    monkeypatch.setattr(si, "get_postmortem", lambda y, r: {"available": True, "summary": "tyre call"})
    monkeypatch.setattr(si, "generate_miss_postmortem", lambda *_a: pytest.fail("must not regenerate"))

    assert client.get("/predictions/2026/1/postmortem").json()["summary"] == "tyre call"


@pytest.mark.unit
def test_postmortem_is_generated_on_demand_when_absent(client, monkeypatch):
    import app.services.self_improvement as si

    monkeypatch.setattr(si, "get_postmortem", lambda y, r: None)
    monkeypatch.setattr(si, "generate_miss_postmortem", lambda y, r: {"available": True, "generated": True})

    assert client.get("/predictions/2026/1/postmortem").json()["generated"] is True


@pytest.mark.unit
def test_postmortem_explains_why_it_is_unavailable(client, monkeypatch):
    import app.services.self_improvement as si

    monkeypatch.setattr(si, "get_postmortem", lambda y, r: None)
    monkeypatch.setattr(si, "generate_miss_postmortem", lambda y, r: None)

    body = client.get("/predictions/2026/9/postmortem").json()

    assert body["available"] is False
    assert "not evaluated yet" in body["reason"].lower()


# ---------------------------------------------------------------------------
# _with_scored_review — scoring a stored snapshot once the race has run
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_review_refresh_scores_an_unevaluated_snapshot(monkeypatch):
    monkeypatch.setattr(predictions_router, "get_prediction_review", lambda y, r: {"evaluated": True, "hits": 3})

    result = await predictions_router._with_scored_review(dict(SNAPSHOT))

    assert result["prediction_review"] == {"evaluated": True, "hits": 3}


@pytest.mark.unit
async def test_review_refresh_skips_an_already_evaluated_snapshot(monkeypatch):
    monkeypatch.setattr(
        predictions_router,
        "get_prediction_review",
        lambda *_a: pytest.fail("an evaluated review must not be recomputed"),
    )

    stored = {**SNAPSHOT, "prediction_review": {"evaluated": True}}

    assert await predictions_router._with_scored_review(stored) == stored


@pytest.mark.unit
async def test_review_refresh_skips_a_snapshot_with_no_predictions(monkeypatch):
    monkeypatch.setattr(predictions_router, "get_prediction_review", lambda *_a: pytest.fail("nothing to score"))

    empty = {"year": 2026, "round": 1, "predictions": []}

    assert await predictions_router._with_scored_review(empty) == empty


@pytest.mark.unit
@pytest.mark.parametrize(
    "result",
    [
        {"predictions": [{"code": "VER"}], "year": 0, "round": 1},
        {"predictions": [{"code": "VER"}], "year": 2026, "round": None},
        {"predictions": [{"code": "VER"}]},
    ],
    ids=["no-year", "no-round", "neither"],
)
async def test_review_refresh_needs_a_race_to_score_against(monkeypatch, result):
    monkeypatch.setattr(
        predictions_router,
        "get_prediction_review",
        lambda *_a: pytest.fail("cannot score without a race identity"),
    )

    assert await predictions_router._with_scored_review(result) == result


@pytest.mark.unit
async def test_review_refresh_gives_up_after_its_short_budget(monkeypatch):
    """The page must stay fast; a slow load finishes in the background instead."""
    monkeypatch.setattr(predictions_router, "REVIEW_REFRESH_TIMEOUT_SECONDS", 0.01)

    def slow(_year, _round):
        import time

        time.sleep(0.3)
        return {"evaluated": True}

    monkeypatch.setattr(predictions_router, "get_prediction_review", slow)

    result = await predictions_router._with_scored_review(dict(SNAPSHOT))

    assert result["prediction_review"] == {"evaluated": False}, "the stored review is served unchanged"


@pytest.mark.unit
async def test_review_refresh_swallows_a_scoring_failure(monkeypatch):
    def explode(_year, _round):
        raise RuntimeError("FastF1 session unavailable")

    monkeypatch.setattr(predictions_router, "get_prediction_review", explode)

    result = await predictions_router._with_scored_review(dict(SNAPSHOT))

    assert result["prediction_review"] == {"evaluated": False}


@pytest.mark.unit
def test_a_late_review_failure_is_logged_not_dropped(capsys):
    """A refresh that outran its wait must still report why it failed."""

    class _FailedTask:
        def cancelled(self):
            return False

        def exception(self):
            return RuntimeError("late boom")

    predictions_router._log_late_review(_FailedTask())

    assert "review_refresh_failed" in capsys.readouterr().out


@pytest.mark.unit
def test_a_late_review_success_is_logged(capsys):
    class _OkTask:
        def cancelled(self):
            return False

        def exception(self):
            return None

    predictions_router._log_late_review(_OkTask())

    assert "review_refreshed_late" in capsys.readouterr().out


@pytest.mark.unit
def test_a_cancelled_review_task_is_ignored(capsys):
    class _CancelledTask:
        def cancelled(self):
            return True

        def exception(self):
            raise AssertionError("a cancelled task has no exception to read")

    predictions_router._log_late_review(_CancelledTask())

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# _prediction_lock
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_each_race_gets_its_own_lock_reused_across_calls():
    first = predictions_router._prediction_lock((2026, 1))
    again = predictions_router._prediction_lock((2026, 1))
    other = predictions_router._prediction_lock((2026, 2))

    assert first is again, "the same race must serialise on one lock"
    assert first is not other, "different races must not block each other"
