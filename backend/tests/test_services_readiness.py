"""Tests for app.services.readiness — startup warm-up and the /api/ready state.

The behaviour that matters is the failure contract. Warm-up runs against a
cold container: any step can fail or hang, and the rule is that it must never
strand the client — the run always finishes, ``ready`` always ends true, and
the first failure is surfaced on the state rather than swallowed. The state
object is a frozen snapshot replaced wholesale, so a reader can never observe
a half-updated record.

No step here sleeps: the timeout branch is driven by shrinking the configured
timeout to zero, which cancels the worker before it ever runs.
"""

from __future__ import annotations

import pytest

from app.services import readiness


@pytest.fixture(autouse=True)
def _reset_state():
    """Warm-up state is process-global; each test must start cold."""
    readiness._state = readiness._INITIAL_STATE
    yield
    readiness._state = readiness._INITIAL_STATE


def _step(stage: str, run) -> readiness.WarmupStep:
    return readiness.WarmupStep(stage, f"Doing {stage}", run)


@pytest.mark.unit
def test_initial_state_reports_not_ready():
    state = readiness.current_state()

    assert state.ready is False
    assert state.stage == readiness.STAGE_PENDING


@pytest.mark.unit
def test_as_dict_exposes_every_field_the_api_contract_promises():
    state = readiness.ReadinessState(
        ready=True,
        stage="complete",
        detail="Ready",
        started_at="2026-03-08T10:00:00+00:00",
        completed_at="2026-03-08T10:00:04+00:00",
        error="model failed: boom",
    )

    assert state.as_dict() == {
        "ready": True,
        "stage": "complete",
        "detail": "Ready",
        "started_at": "2026-03-08T10:00:00+00:00",
        "completed_at": "2026-03-08T10:00:04+00:00",
        "error": "model failed: boom",
    }


@pytest.mark.unit
def test_now_is_timezone_aware_iso8601():
    stamp = readiness._now()

    # A naive timestamp here would make two containers' readiness incomparable.
    assert stamp.endswith("+00:00")


@pytest.mark.unit
def test_set_state_replaces_the_snapshot_rather_than_mutating_it():
    original = readiness.current_state()
    replacement = readiness.ReadinessState(ready=True, stage="complete", detail="Ready")

    readiness._set_state(replacement)

    assert readiness.current_state() is replacement
    assert original.ready is False, "the previously published snapshot must be untouched"


@pytest.mark.unit
def test_warm_database_delegates_to_ensure_db(monkeypatch):
    from app.data import f1db_source

    calls: list[int] = []
    monkeypatch.setattr(f1db_source, "ensure_db", lambda: calls.append(1))

    readiness._warm_database()

    assert len(calls) == 1


@pytest.mark.unit
def test_warm_model_pulls_the_finish_model_into_cache(monkeypatch):
    from app.data import predictions as predictions_package

    calls: list[int] = []
    # Patched on the package the step imports from, so no real joblib artifact
    # is read off disk.
    monkeypatch.setattr(predictions_package, "warm_model_cache", lambda: calls.append(1) or True)

    readiness._warm_model()

    assert len(calls) == 1


@pytest.mark.unit
def test_warm_season_runs_a_real_schedule_query(fake_f1db):
    # No mock: the point of this step is that the SQLite handle really opens.
    readiness._warm_season()


@pytest.mark.unit
def test_warm_store_succeeds_when_snapshots_load(monkeypatch):
    from app.services import prediction_cache

    monkeypatch.setattr(prediction_cache.prediction_snapshot_cache, "load", lambda: True)

    readiness._warm_store()


@pytest.mark.unit
def test_warm_store_raises_when_the_document_store_is_unreachable(monkeypatch):
    from app.services import prediction_cache

    monkeypatch.setattr(prediction_cache.prediction_snapshot_cache, "load", lambda: False)

    with pytest.raises(RuntimeError, match="prediction snapshot store unreachable"):
        readiness._warm_store()


@pytest.mark.unit
def test_registered_steps_cover_every_deferred_startup_cost():
    assert [step.stage for step in readiness.WARMUP_STEPS] == ["database", "model", "season", "store"]


@pytest.mark.unit
async def test_run_warmup_runs_every_step_in_order_and_finishes_ready():
    ran: list[str] = []
    steps = (
        _step("database", lambda: ran.append("database")),
        _step("model", lambda: ran.append("model")),
    )

    final = await readiness.run_warmup(steps)

    assert ran == ["database", "model"]
    assert (final.ready, final.error) == (True, None)
    assert final.started_at is not None
    assert final.completed_at is not None
    assert readiness.current_state() is final


@pytest.mark.unit
async def test_run_warmup_with_no_steps_reports_complete_immediately():
    final = await readiness.run_warmup(())

    assert (final.ready, final.stage, final.detail) == (True, readiness.STAGE_COMPLETE, "Ready")


@pytest.mark.unit
async def test_a_failing_step_does_not_abort_the_remaining_steps():
    ran: list[str] = []

    def explode() -> None:
        raise RuntimeError("disk full")

    steps = (_step("database", explode), _step("model", lambda: ran.append("model")))

    final = await readiness.run_warmup(steps)

    assert ran == ["model"], "a later step must still run after an earlier one fails"
    assert final.ready is True
    assert final.error == "database failed: disk full"


@pytest.mark.unit
async def test_only_the_first_failure_is_reported():
    def explode_with(message: str):
        def run() -> None:
            raise RuntimeError(message)

        return run

    steps = (_step("database", explode_with("first")), _step("model", explode_with("second")))

    final = await readiness.run_warmup(steps)

    assert final.error == "database failed: first"


@pytest.mark.unit
async def test_a_step_that_exceeds_its_budget_is_reported_as_a_timeout(monkeypatch):
    # A zero budget cancels the worker before it starts — the timeout branch
    # without any real waiting.
    monkeypatch.setattr(readiness, "WARMUP_STEP_TIMEOUT_SECONDS", 0)
    ran: list[str] = []

    final = await readiness.run_warmup((_step("database", lambda: ran.append("database")),))

    assert ran == [], "the step must have been abandoned, not merely reported slow"
    assert final.error == "database timed out"
    assert final.ready is True
