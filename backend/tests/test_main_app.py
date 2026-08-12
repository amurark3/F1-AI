"""Tests for ``main`` — the ASGI entry point, its wiring and its prefetch loop.

Nothing in this module has business logic, which is exactly why it is risky: a
router that is not mounted, a CORS origin list that does not match the deployed
frontend, or a background task that is never cancelled are all silent in
development and total in production.

Two hazards shape how these tests are written:

* **Importing ``main`` calls ``load_dotenv()``.** The repo has a real ``.env``
  holding ``GROQ_API_KEY`` and ``DATABASE_URL``, which ``tests/conftest.py``
  deliberately clears so no test can reach a live service. The import below is
  therefore bracketed by an exact ``os.environ`` snapshot/restore, and every
  reload goes through ``reloaded_main`` which does the same. Without that, this
  file would hand real credentials to the entire suite.
* **The lifespan starts an endless prefetch loop.** It is never allowed to run:
  ``_prefetch_race_details`` is stubbed wherever the lifespan is exercised, and
  where the loop itself is under test ``asyncio.sleep`` is replaced with a stub
  that escapes it after a fixed number of turns.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
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

from app.api import race_detail  # noqa: E402


class _LoopEscape(BaseException):
    """Breaks out of the endless prefetch loop.

    Derived from ``BaseException`` on purpose: the loop body catches
    ``Exception`` around everything, so an ordinary error would be swallowed and
    the loop would spin forever.
    """


def _naive_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


def _schedule_row(round_number: int, race_date: pd.Timestamp | None) -> dict:
    """One schedule row with the Race in session slot 3, as FastF1 lays it out."""
    row = {"RoundNumber": round_number}
    for index in range(1, 6):
        row[f"Session{index}"] = "Race" if index == 3 and race_date is not None else f"Practice {index}"
        row[f"Session{index}DateUtc"] = race_date if index == 3 else _naive_now()
    return row


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
def detail_cache(monkeypatch) -> dict:
    """Swap the process-wide race-detail cache for a throwaway dict."""
    cache: dict = {}
    monkeypatch.setattr(race_detail, "race_detail_cache", cache)
    return cache


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
# Schedule row parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_race_session_date_reads_the_slot_the_race_actually_occupies():
    race_date = _naive_now() - timedelta(days=2)
    row = pd.Series(_schedule_row(4, race_date))

    assert main._race_session_date(row) == race_date.to_pydatetime()


@pytest.mark.unit
def test_a_weekend_with_no_race_session_has_no_date():
    row = pd.Series(_schedule_row(4, race_date=None))

    assert main._race_session_date(row) is None


@pytest.mark.unit
def test_an_undated_race_session_has_no_date():
    # A future round on the calendar before its timings are published.
    row = pd.Series(_schedule_row(4, race_date=pd.NaT))

    assert main._race_session_date(row) is None


# ---------------------------------------------------------------------------
# Single-round prefetch
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_prefetch_round_caches_a_detail_that_resolved_a_circuit(monkeypatch, detail_cache):
    detail = {"circuit": {"name": "Suzuka"}, "results": []}
    monkeypatch.setattr(race_detail, "build_race_detail", lambda year, rnd: detail)

    await main._prefetch_round(2026, 5)

    assert detail_cache == {(2026, 5): detail}


@pytest.mark.integration
async def test_prefetch_round_refuses_to_cache_a_detail_with_no_circuit(monkeypatch, detail_cache):
    # A circuit-less detail is a failed build, and caching it would pin that
    # failure in memory until the process restarts.
    monkeypatch.setattr(race_detail, "build_race_detail", lambda year, rnd: {"circuit": None})

    await main._prefetch_round(2026, 5)

    assert detail_cache == {}


@pytest.mark.integration
async def test_prefetch_round_gives_up_on_a_slow_race_without_raising(monkeypatch, detail_cache):
    monkeypatch.setattr(main, "PREFETCH_RACE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(race_detail, "build_race_detail", lambda year, rnd: time.sleep(0.5))

    with structlog.testing.capture_logs() as logs:
        await main._prefetch_round(2026, 5)

    assert detail_cache == {}
    assert [entry["event"] for entry in logs] == ["prefetch.starting", "prefetch.timeout"]


@pytest.mark.integration
async def test_prefetch_round_logs_a_broken_race_and_lets_the_sweep_continue(monkeypatch, detail_cache):
    def _explode(year: int, rnd: int) -> dict:
        raise RuntimeError("upstream 503")

    monkeypatch.setattr(race_detail, "build_race_detail", _explode)

    with structlog.testing.capture_logs() as logs:
        await main._prefetch_round(2026, 5)

    assert detail_cache == {}
    failure = next(entry for entry in logs if entry["event"] == "prefetch.failed")
    assert failure["error"] == "upstream 503"


# ---------------------------------------------------------------------------
# The background sweep
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_the_sweep_only_prefetches_completed_uncached_rounds(monkeypatch, sleep_stub, detail_cache):
    finished = _naive_now() - timedelta(days=1)
    schedule = pd.DataFrame(
        [
            _schedule_row(1, finished),  # completed, but already cached
            _schedule_row(2, race_date=None),  # no race session at all
            _schedule_row(3, _naive_now() + timedelta(days=1)),  # still upcoming
            _schedule_row(4, finished),  # completed and missing
        ]
    )
    detail_cache[(_naive_now().year, 1)] = {"circuit": {}}
    prefetched: list[tuple[int, int]] = []

    monkeypatch.setattr(main.fastf1, "get_event_schedule", lambda year, include_testing: schedule)
    monkeypatch.setattr(main, "_prefetch_round", lambda year, rnd: _record(prefetched, year, rnd))
    _stub_self_improvement(monkeypatch, lambda year: {"reviewed": 0})
    delays = sleep_stub(3)

    with pytest.raises(_LoopEscape):
        await main._prefetch_race_details()

    assert prefetched == [(_naive_now().year, 4)]
    # Startup delay, then the inter-race pause. Zero-length sleeps from the
    # `to_thread` stub are incidental; the loop escapes before the sweep gap.
    assert [delay for delay in delays if delay] == [
        main.PREFETCH_STARTUP_DELAY,
        main.PREFETCH_INTER_RACE_DELAY,
    ]


@pytest.mark.integration
async def test_a_race_completed_within_the_three_hour_buffer_is_left_alone(monkeypatch, sleep_stub, detail_cache):
    just_finished = _naive_now() - timedelta(hours=2)
    schedule = pd.DataFrame([_schedule_row(1, just_finished)])
    prefetched: list[tuple[int, int]] = []

    monkeypatch.setattr(main.fastf1, "get_event_schedule", lambda year, include_testing: schedule)
    monkeypatch.setattr(main, "_prefetch_round", lambda year, rnd: _record(prefetched, year, rnd))
    _stub_self_improvement(monkeypatch, lambda year: {})
    sleep_stub(2)

    with pytest.raises(_LoopEscape):
        await main._prefetch_race_details()

    assert prefetched == [], "results are not final until the buffer has passed"


@pytest.mark.integration
async def test_an_unreachable_schedule_is_logged_and_the_sweep_is_rescheduled(monkeypatch, sleep_stub):
    def _explode(year: int, include_testing: bool):
        raise ConnectionError("fastf1 unreachable")

    monkeypatch.setattr(main.fastf1, "get_event_schedule", _explode)
    _stub_self_improvement(monkeypatch, lambda year: {})
    delays = sleep_stub(2)

    with structlog.testing.capture_logs() as logs, pytest.raises(_LoopEscape):
        await main._prefetch_race_details()

    assert [entry["event"] for entry in logs] == ["prefetch.loop_error"]
    # The loop survives and still queues the next sweep rather than dying.
    assert delays == [main.PREFETCH_STARTUP_DELAY, main.PREFETCH_INTERVAL]


@pytest.mark.integration
async def test_a_failing_self_improvement_pass_does_not_break_prefetching(monkeypatch, sleep_stub):
    def _explode(year: int) -> dict:
        raise RuntimeError("groq quota exhausted")

    monkeypatch.setattr(main.fastf1, "get_event_schedule", lambda year, include_testing: pd.DataFrame([]))
    _stub_self_improvement(monkeypatch, _explode)
    delays = sleep_stub(2)

    with structlog.testing.capture_logs() as logs, pytest.raises(_LoopEscape):
        await main._prefetch_race_details()

    assert [entry["event"] for entry in logs] == ["self_improvement.loop_error"]
    assert delays == [main.PREFETCH_STARTUP_DELAY, main.PREFETCH_INTERVAL]


def _record(sink: list[tuple[int, int]], year: int, round_num: int):
    """Stand in for ``_prefetch_round``; the loop awaits whatever it returns."""
    sink.append((year, round_num))
    return asyncio.sleep(0)


def _stub_self_improvement(monkeypatch, replacement) -> None:
    from app.services import self_improvement

    monkeypatch.setattr(self_improvement, "run_self_improvement_pass", replacement)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_lifespan_runs_both_background_tasks_and_cancels_them_on_shutdown(monkeypatch):
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
    monkeypatch.setattr(main, "_prefetch_race_details", _make("prefetch"))

    async with main.lifespan(main.app):
        await asyncio.sleep(0)  # hand control to the freshly created tasks
        assert events == ["logging.configured", "warmup.started", "prefetch.started"]

    # Shutdown must reach both: a surviving prefetch loop keeps the worker busy
    # long after the server has stopped answering.
    assert events[-2:] == ["warmup.cancelled", "prefetch.cancelled"]


@pytest.mark.integration
def test_serving_through_the_asgi_lifespan_does_not_start_the_real_prefetch(monkeypatch):
    started: list[str] = []

    async def _noop() -> None:
        started.append("called")

    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "run_warmup", _noop)
    monkeypatch.setattr(main, "_prefetch_race_details", _noop)

    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200

    assert started == ["called", "called"]


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
