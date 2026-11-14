"""Tests for ``main`` — the ASGI entry point, its wiring and its background loops.

Nothing in this module has business logic, which is exactly why it is risky: a
router that is not mounted, a CORS origin list that does not match the deployed
frontend, or a background task that is never cancelled are all silent in
development and total in production.

Two hazards shape how these tests are written:

* **Importing ``main`` calls ``load_dotenv()``.** The repo has a real ``.env``
  holding engine keys and ``DATABASE_URL``, which ``tests/conftest.py``
  deliberately clears so no test can reach a live service. The import below is
  therefore bracketed by an exact ``os.environ`` snapshot/restore, and every
  reload goes through ``reloaded_main`` which does the same. Without that, this
  file would hand real credentials to the entire suite.
* **The lifespan starts endless loops.** Where a loop itself is under test
  ``asyncio.sleep`` is replaced with a stub that escapes it after a fixed number
  of turns. Where the lifespan runs for real, the loops are cancelled on exit.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import importlib
import os
import time

from fastapi.testclient import TestClient
import pandas as pd
import pytest
import structlog

from tests.route_paths import mounted_paths

# `load_dotenv()` at main's module scope repopulates the credentials conftest
# cleared. Restore the environment byte for byte the moment the import returns.
_ENV_BEFORE_IMPORT = dict(os.environ)
import main  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_IMPORT)


class _LoopEscape(BaseException):
    """Breaks out of an endless background loop.

    Derived from ``BaseException`` on purpose: the loop body catches
    ``Exception`` around everything, so an ordinary error would be swallowed and
    the loop would spin forever.
    """


@pytest.fixture
def sleep_stub(monkeypatch):
    """Replace ``asyncio.sleep`` with a recorder that escapes after N calls."""

    def _install(stop_after: int) -> list[float]:
        delays: list[float] = []

        async def _sleep(delay, *_args, **_kwargs):
            delays.append(delay)
            if len(delays) >= stop_after:
                raise _LoopEscape

        monkeypatch.setattr(asyncio, "sleep", _sleep)
        return delays

    return _install


@pytest.fixture
def reloaded_main(monkeypatch):
    """Re-import ``main`` so its module-scope ``os.getenv`` reads run again.

    Restores both the environment ``load_dotenv`` would repopulate and the
    module itself, so a reloaded ``main.app`` cannot leak into another test.
    """

    def _reload():
        before = dict(os.environ)
        module = importlib.reload(main)
        os.environ.clear()
        os.environ.update(before)
        return module

    yield _reload

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    _reload()


# ---------------------------------------------------------------------------
# The self-improvement loop
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_the_loop_waits_out_warm_up_then_runs_one_pass_per_interval(monkeypatch, sleep_stub):
    passes: list[int] = []
    _stub_self_improvement(monkeypatch, passes.append)
    delays = sleep_stub(2)

    with pytest.raises(_LoopEscape):
        await main._self_improvement_loop()

    assert passes == [datetime.now(UTC).year]
    # Zero-length sleeps from the `to_thread` stub are incidental.
    assert [delay for delay in delays if delay] == [main.PREFETCH_STARTUP_DELAY, main.PREFETCH_INTERVAL]


@pytest.mark.integration
async def test_a_failing_self_improvement_pass_does_not_end_the_loop(monkeypatch, sleep_stub):
    def _explode(year: int) -> dict:
        raise RuntimeError("engine quota exhausted")

    _stub_self_improvement(monkeypatch, _explode)
    delays = sleep_stub(2)

    with structlog.testing.capture_logs() as logs, pytest.raises(_LoopEscape):
        await main._self_improvement_loop()

    assert [entry["event"] for entry in logs] == ["self_improvement.loop_error"]
    assert delays == [main.PREFETCH_STARTUP_DELAY, main.PREFETCH_INTERVAL]


@pytest.mark.integration
async def test_a_fresh_boot_and_one_loop_pass_load_no_fastf1_session(monkeypatch):
    """D1.2: boot used to sweep race detail for every finished round.

    That sweep cost about 358 FastF1 requests per start, 72 % of FastF1's 500/h
    cap. The real lifespan and warm-up steps run here; only the f1db download and
    the model load are stubbed, at their boundaries. Grading's own FastF1 read
    (``record_actual_result``) moves in D1.8, so the pass is a recorder.
    """
    import fastf1

    from app.data import f1db_source, predictions
    from app.services import prediction_cache, readiness

    fastf1_calls: list[str] = []
    for entry_point in ("get_session", "get_event_schedule"):
        monkeypatch.setattr(fastf1, entry_point, _fastf1_spy(fastf1_calls, entry_point))
    passes: list[int] = []
    _stub_self_improvement(monkeypatch, passes.append)
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "PREFETCH_STARTUP_DELAY", 0)
    monkeypatch.setattr(f1db_source, "sync_to_latest", lambda: None)
    monkeypatch.setattr(predictions, "warm_model_cache", lambda: None)
    monkeypatch.setattr(prediction_cache, "prediction_snapshot_cache", prediction_cache.PredictionSnapshotCache())
    monkeypatch.setattr(readiness, "_state", readiness._INITIAL_STATE)

    async with main.lifespan(main.app):
        deadline = time.monotonic() + 10
        while not (readiness.current_state().ready and passes):
            assert time.monotonic() < deadline, "warm-up or the first pass never finished"
            await asyncio.sleep(0.01)

    assert passes == [datetime.now(UTC).year]
    assert fastf1_calls == [], "boot or the loop reached FastF1"


def _fastf1_spy(sink: list[str], entry_point: str):
    """Record a call to a FastF1 entry point and refuse it."""

    def _spy(*_args, **_kwargs):
        sink.append(entry_point)
        raise RuntimeError(f"fastf1.{entry_point} called")

    return _spy


def _stub_self_improvement(monkeypatch, replacement) -> None:
    from app.services import self_improvement

    monkeypatch.setattr(self_improvement, "run_self_improvement_pass", replacement)


# ---------------------------------------------------------------------------
# f1db refresh loop
# ---------------------------------------------------------------------------


def _stub_sync(monkeypatch, outcome) -> list[int]:
    """Serve ``outcome`` (or raise it) from the f1db sync; count the calls."""
    calls: list[int] = []

    def _sync():
        calls.append(1)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(main, "sync_to_latest", _sync)
    return calls


@pytest.mark.unit
async def test_the_refresh_loop_sleeps_before_its_first_check(monkeypatch, sleep_stub):
    """Warm-up has just synced; checking again at boot would only spend the API quota."""
    calls = _stub_sync(monkeypatch, AssertionError("must not sync before the first interval"))
    delays = sleep_stub(stop_after=1)

    with pytest.raises(_LoopEscape):
        await main._refresh_f1db_dataset()

    assert delays == [main.F1DB_REFRESH_INTERVAL_SECONDS]
    assert calls == []


@pytest.mark.unit
async def test_a_new_release_is_logged_and_the_loop_carries_on(monkeypatch, sleep_stub, capsys):
    from app.data.f1db_source import SyncOutcome

    calls = _stub_sync(monkeypatch, SyncOutcome(version="v2026.17.0", updated=True, reason="downloaded"))
    sleep_stub(stop_after=2)

    with pytest.raises(_LoopEscape):
        await main._refresh_f1db_dataset()

    assert calls == [1]
    assert "f1db.refresh_loop.updated" in capsys.readouterr().out


@pytest.mark.unit
async def test_an_unchanged_dataset_is_not_reported_as_an_update(monkeypatch, sleep_stub, capsys):
    from app.data.f1db_source import SyncOutcome

    _stub_sync(monkeypatch, SyncOutcome(version="v2026.17.0", updated=False, reason="current"))
    sleep_stub(stop_after=2)

    with pytest.raises(_LoopEscape):
        await main._refresh_f1db_dataset()

    assert "f1db.refresh_loop.updated" not in capsys.readouterr().out


@pytest.mark.unit
async def test_a_failed_refresh_is_logged_and_retried_next_interval(monkeypatch, sleep_stub, capsys):
    """A long-lived container must not lose its refresh loop to one bad check."""
    calls = _stub_sync(monkeypatch, RuntimeError("github unreachable"))
    sleep_stub(stop_after=3)

    with pytest.raises(_LoopEscape):
        await main._refresh_f1db_dataset()

    assert calls == [1, 1]
    assert "f1db.refresh_loop_error" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_lifespan_runs_every_background_task_and_cancels_them_on_shutdown(monkeypatch):
    events: list[str] = []

    def _make(name: str):
        async def _task() -> None:
            events.append(f"{name}.started")
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                events.append(f"{name}.cancelled")
                raise

        return _task

    monkeypatch.setattr(main, "setup_logging", lambda: events.append("logging.configured"))
    monkeypatch.setattr(main, "run_warmup", _make("warmup"))
    monkeypatch.setattr(main, "_self_improvement_loop", _make("self_improvement"))
    monkeypatch.setattr(main, "_refresh_f1db_dataset", _make("f1db_refresh"))

    async with main.lifespan(main.app):
        await asyncio.sleep(0)  # hand control to the freshly created tasks
        assert events == ["logging.configured", "warmup.started", "self_improvement.started", "f1db_refresh.started"]

    # Shutdown must reach every task: a surviving loop keeps the worker busy
    # long after the server has stopped answering.
    assert events[-3:] == ["warmup.cancelled", "self_improvement.cancelled", "f1db_refresh.cancelled"]


@pytest.mark.integration
def test_serving_through_the_asgi_lifespan_does_not_start_the_real_loops(monkeypatch):
    started: list[str] = []

    async def _noop() -> None:
        started.append("called")

    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "run_warmup", _noop)
    monkeypatch.setattr(main, "_self_improvement_loop", _noop)
    monkeypatch.setattr(main, "_refresh_f1db_dataset", _noop)

    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200

    assert started == ["called", "called", "called"]


# ---------------------------------------------------------------------------
# Wiring: routes, CORS, probes
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """A client that never enters the lifespan, so no background task starts."""
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.unit
def test_root_answers_a_health_probe():
    assert main.read_root() == {"status": "Backend is running", "service": "F1 Race Engineer"}


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    [
        "/api/chat",
        "/api/health",
        "/api/ready",
        "/api/champions",
        "/api/predictions/{year}/{round_num}",
        "/api/race-control/overview/{year}",
        "/api/compare/{year}/{driver1}/{driver2}",
    ],
)
def test_the_api_router_is_mounted_under_the_api_prefix(path):
    # An unprefixed mount would 404 every frontend call while the app booted fine.
    assert path in mounted_paths(main.app.routes)


@pytest.mark.integration
def test_health_answers_through_the_assembled_app(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["timestamp"].endswith("Z")


@pytest.mark.integration
def test_readiness_reports_warmup_progress_and_store_health(client):
    body = client.get("/api/ready").json()

    assert body["ready"] is False, "nothing has warmed up in a test process"
    # The file fallback is what a deployment without DATABASE_URL actually uses.
    assert body["store"]["backend"] == "file"


@pytest.mark.integration
def test_the_schedule_endpoint_serialises_its_list_through_the_assembled_app(client, monkeypatch):
    """Regression, end to end through ``main.app``.

    ``app/api/routers/season.py`` once annotated this handler ``-> dict`` while
    returning a list, so FastAPI's response validation rejected every body it
    was given. The route was mounted and the handler ran — the failure was in
    serialisation, which is why it took the season schedule down for every
    client while looking healthy from the router's own return value. Pinned
    here because ``tests/test_routers_season.py`` covers it only at the router
    level, and the response model is applied by the app that mounts the route.

    An empty schedule is enough: the handler returns ``[]``, and ``[]`` is
    exactly what a ``-> dict`` response model rejects.
    """
    from app.api.routers import season as season_router

    monkeypatch.setattr(season_router.fastf1, "get_event_schedule", lambda year, include_testing: pd.DataFrame())

    response = client.get("/api/schedule/2024")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_cors_defaults_to_the_local_frontend_origin(client):
    assert main.ALLOWED_ORIGINS == ["http://localhost:3000"]

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    stranger = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in stranger.headers


@pytest.mark.integration
def test_cors_preflight_is_refused_for_an_unlisted_origin(client):
    response = client.options(
        "/api/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400


@pytest.mark.integration
def test_allowed_origins_is_a_comma_separated_environment_list(monkeypatch, reloaded_main):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://f1.example,https://staging.f1.example")

    module = reloaded_main()

    assert module.ALLOWED_ORIGINS == ["https://f1.example", "https://staging.f1.example"]
    response = TestClient(module.app).get("/api/health", headers={"Origin": "https://staging.f1.example"})
    assert response.headers["access-control-allow-origin"] == "https://staging.f1.example"
