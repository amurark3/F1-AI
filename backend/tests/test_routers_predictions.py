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

A model run outlives the request that started it. A request that gives up
waiting must not release the race, or every retry stacks one more full run
beside the last; on Render's 512 MB instance that is what ran it out of memory
(2026-10-30, Mexico). So a run holds the race lock until it really finishes, and
a request that arrives meanwhile joins it rather than starting another.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import structlog

from app.api.routers import predictions as predictions_router

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SNAPSHOT = {
    "year": 2026,
    "round": 1,
    "predictions": [{"code": "VER", "predicted_position": 1}],
    "prediction_review": {"evaluated": False},
}


@pytest.fixture(autouse=True)
def _clear_locks():
    """The lock and run registries are module-global and would leak between tests."""
    predictions_router.prediction_locks.clear()
    predictions_router.model_runs.clear()
    yield
    predictions_router.prediction_locks.clear()
    predictions_router.model_runs.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """One event loop for the whole test, so a run outlives the request that started it."""
    app = FastAPI()
    app.include_router(predictions_router.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def gate() -> Iterator[threading.Event]:
    """Holds a fake model run open until the test releases it.

    Released on teardown too: the client's event loop joins its worker threads
    on exit, so a run still parked here would stall the suite.
    """
    event = threading.Event()
    yield event
    event.set()


def _wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("condition not met in time")
        time.sleep(0.01)


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
def test_a_slow_model_run_returns_a_retryable_message(client, monkeypatch, gate):
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: None)
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(predictions_router, "get_or_compute_race_prediction", lambda y, r: gate.wait(5) and {})

    body = client.get("/predictions/2026/1").json()

    assert body["predictions"] == []
    assert "still running" in body["error"]
    # Still running is retry-able, not a server fault, so it carries no error id.
    assert "error_id" not in body


@pytest.mark.unit
def test_a_timeout_raised_inside_the_model_is_a_failure_not_a_wait(client, monkeypatch):
    """A socket timeout is a ``TimeoutError`` too; it must not read as "still running"."""
    monkeypatch.setattr(predictions_router.prediction_snapshot_cache, "get", lambda y, r: None)

    def network_timeout(*_args, **_kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(predictions_router, "get_or_compute_race_prediction", network_timeout)

    body = client.get("/predictions/2026/1").json()

    assert body["predictions"] == []
    assert "error_id" in body


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
    monkeypatch.setattr(predictions_router, "get_cached_race_prediction", lambda y, r, phase=None: SNAPSHOT)

    assert client.get("/predictions/2026/1/snapshot").json()["predictions"]


@pytest.mark.unit
def test_snapshot_never_computes_on_a_miss(client, monkeypatch):
    """The whole contract of this route: no model work, ever."""
    monkeypatch.setattr(predictions_router, "get_cached_race_prediction", lambda y, r, phase=None: None)
    monkeypatch.setattr(
        predictions_router,
        "get_or_compute_race_prediction",
        lambda *_a, **_k: pytest.fail("snapshot must not trigger a compute"),
    )

    body = client.get("/predictions/2026/9/snapshot").json()

    assert body["predictions"] == []
    assert body["cache"] == {"status": "missing", "policy": "stored_until_manual_recompute"}
    assert body["model_running"] is False


@pytest.mark.unit
@pytest.mark.parametrize("stored", [SNAPSHOT, None], ids=["hit", "miss"])
def test_snapshot_says_when_that_phase_has_a_run_in_flight(client, monkeypatch, no_review_refresh, stored):
    """How a client waiting on a "computing" answer tells a slow run from one that stopped."""
    monkeypatch.setattr(predictions_router, "get_cached_race_prediction", lambda y, r, phase=None: stored)
    predictions_router.model_runs[(2026, 1, "pre_qualifying")] = object()

    running = client.get("/predictions/2026/1/snapshot", params={"phase": "pre_qualifying"}).json()
    other_phase = client.get("/predictions/2026/1/snapshot", params={"phase": "post_qualifying"}).json()

    assert running["model_running"] is True
    assert other_phase["model_running"] is False


# ---------------------------------------------------------------------------
# POST /predictions/{year}/{round}/compute
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("reason", ["manual_compute", "qualifying_recompute"])
def test_compute_forwards_an_allowed_reason(client, monkeypatch, reason):
    seen: list[str] = []

    def compute(year, round_num, reason, phase=None):
        seen.append(reason)
        return {"year": year, "round": round_num}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    client.post("/predictions/2026/1/compute", params={"reason": reason})

    assert seen == [reason]


@pytest.mark.unit
def test_compute_clamps_an_unknown_reason(client, monkeypatch):
    """`reason` is stored as provenance, so arbitrary query text must not reach it."""
    seen: list[str] = []

    def compute(year, round_num, reason, phase=None):
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
        lambda year, round_num, reason, phase=None: seen.append(reason) or {},
    )

    client.post("/predictions/2026/1/compute")

    assert seen == ["manual_compute"]


@pytest.mark.unit
def test_a_compute_that_outlives_its_wait_reports_it_is_still_running(client, monkeypatch, gate):
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        predictions_router,
        "compute_and_store_race_prediction",
        lambda year, round_num, reason, phase=None: gate.wait(5) and {},
    )

    body = client.post("/predictions/2026/1/compute", params={"phase": "pre_qualifying"}).json()

    assert body["predictions"] == []
    assert body["risk_predictions"] == []
    assert body["prediction_phase"] == "pre_qualifying"
    assert body["cache"]["status"] == "computing"
    # Not an error: the run carries on and stores its snapshot.
    assert "error" not in body


@pytest.mark.unit
def test_a_second_click_joins_the_run_in_flight(client, monkeypatch, gate):
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.05)
    runs: list[int] = []

    def compute(year, round_num, reason, phase=None):
        runs.append(round_num)
        gate.wait(5)
        return {"year": year, "round": round_num, "predictions": [{"code": "ANT"}]}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    first = client.post("/predictions/2026/19/compute").json()
    second = client.post("/predictions/2026/19/compute").json()
    runs_while_in_flight = list(runs)
    gate.set()
    _wait_until(lambda: not predictions_router.model_runs)

    assert first["cache"]["status"] == "computing"
    assert second["cache"]["status"] == "computing"
    assert runs_while_in_flight == [19]
    assert runs == [19]


@pytest.mark.unit
def test_the_race_stays_locked_until_an_abandoned_run_finishes(client, monkeypatch, gate):
    """The other phase of the same race must queue behind a run its request gave up on."""
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.05)
    events: list[tuple[str, str]] = []

    def compute(year, round_num, reason, phase=None):
        events.append(("start", phase))
        if phase == "pre_qualifying":
            gate.wait(5)
        events.append(("end", phase))
        return {"predictions": [{"code": "RUS"}]}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    client.post("/predictions/2026/19/compute", params={"phase": "pre_qualifying"})
    client.post("/predictions/2026/19/compute", params={"phase": "post_qualifying"})
    started_while_locked = list(events)
    gate.set()
    _wait_until(lambda: not predictions_router.model_runs)

    assert started_while_locked == [("start", "pre_qualifying")]
    assert events == [
        ("start", "pre_qualifying"),
        ("end", "pre_qualifying"),
        ("start", "post_qualifying"),
        ("end", "post_qualifying"),
    ]


@pytest.mark.unit
def test_a_finished_run_is_forgotten_so_the_next_click_recomputes(client, monkeypatch):
    runs: list[int] = []

    def compute(year, round_num, reason, phase=None):
        runs.append(round_num)
        return {"predictions": []}

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    client.post("/predictions/2026/19/compute")
    client.post("/predictions/2026/19/compute")

    assert runs == [19, 19]
    assert predictions_router.model_runs == {}


@pytest.mark.unit
def test_a_run_that_fails_after_its_request_gave_up_is_logged(client, monkeypatch, gate):
    monkeypatch.setattr(predictions_router, "FASTF1_TIMEOUT_SECONDS", 0.05)

    def compute(*_args, **_kwargs):
        gate.wait(5)
        raise RuntimeError("upstream 503")

    monkeypatch.setattr(predictions_router, "compute_and_store_race_prediction", compute)

    with structlog.testing.capture_logs() as logs:
        client.post("/predictions/2026/19/compute")
        gate.set()
        _wait_until(lambda: not predictions_router.model_runs)

    failure = next(entry for entry in logs if entry["event"] == "api.predictions.model_run_failed")
    assert failure["error"] == "upstream 503"


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
    monkeypatch.setattr(predictions_router, "get_prediction_review", lambda y, r, phase: {"evaluated": True, "hits": 3})

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

    def slow(_year, _round, _phase):
        import time

        time.sleep(0.3)
        return {"evaluated": True}

    monkeypatch.setattr(predictions_router, "get_prediction_review", slow)

    result = await predictions_router._with_scored_review(dict(SNAPSHOT))

    assert result["prediction_review"] == {"evaluated": False}, "the stored review is served unchanged"


@pytest.mark.unit
async def test_review_refresh_swallows_a_scoring_failure(monkeypatch):
    def explode(_year, _round, _phase):
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


@pytest.mark.unit
def test_a_cancelled_model_run_is_forgotten_without_reading_its_error():
    """Loop shutdown cancels a run; reading its exception would raise inside the callback."""

    class _CancelledRun:
        def cancelled(self):
            return True

        def exception(self):
            raise AssertionError("a cancelled run has no exception to read")

    run = _CancelledRun()
    predictions_router.model_runs[(2026, 19, "auto")] = run

    with structlog.testing.capture_logs() as logs:
        predictions_router._forget_model_run((2026, 19, "auto"), run)

    assert predictions_router.model_runs == {}
    assert logs == []


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
