"""Tests for app.api.routers.readiness — the three health probes.

The three endpoints answer three different questions and must not collapse into
one another:

* ``/ready`` always answers 200, carrying ``ready: false`` while warming. The
  consumer is the frontend's warming banner, and a 503 there would be caught as
  an error rather than rendered as a state.
* ``/health/deep`` round-trips the database and answers **503** when it cannot.
  It exists because an hourly keepalive against the shallow probe reported
  success the whole time Supabase idled out and paused, taking every stored
  prediction offline. If this probe stops failing on an unreachable database it
  has lost its only reason to exist.
* Neither may leak the driver's error text — it names host, port and user.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import readiness as readiness_router
from app.data.store_types import StoreHealth


class _FakeState:
    """Stand-in for `app.services.readiness.current_state()`."""

    def __init__(self, ready: bool, stage: str = "idle") -> None:
        self.ready = ready
        self._stage = stage

    def as_dict(self) -> dict:
        return {"ready": self.ready, "stage": self._stage}


@pytest.fixture
def client(monkeypatch):
    """Mount only the readiness router, with the store and warm-up state faked."""

    def _build(*, state: _FakeState, health: StoreHealth, ping: StoreHealth | None = None):
        monkeypatch.setattr(readiness_router, "current_state", lambda: state)
        monkeypatch.setattr(readiness_router.document_store, "health", lambda: health)
        monkeypatch.setattr(
            readiness_router.document_store,
            "ping",
            lambda max_age_seconds=0.0: ping if ping is not None else health,
        )
        app = FastAPI()
        app.include_router(readiness_router.router)
        return TestClient(app)

    return _build


@pytest.mark.unit
def test_ready_reports_warm_up_state_alongside_store_health(client):
    test_client = client(
        state=_FakeState(ready=True, stage="complete"),
        health=StoreHealth(backend="postgres", ok=True),
    )

    response = test_client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["stage"] == "complete"
    assert body["store"]["backend"] == "postgres"


@pytest.mark.unit
def test_ready_answers_200_while_still_warming(client):
    """A warming process is a state to render, not an error to catch."""
    test_client = client(
        state=_FakeState(ready=False, stage="loading_model"),
        health=StoreHealth(backend="json", ok=None),
    )

    response = test_client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is False


@pytest.mark.unit
def test_ready_surfaces_a_degraded_store_on_a_healthy_process(client):
    """Reachable process + unreachable store is invisible from the outside otherwise."""
    test_client = client(
        state=_FakeState(ready=True),
        health=StoreHealth(
            backend="postgres",
            ok=False,
            error='connection to server at "db.abcdefgh.supabase.co", port 5432 failed',
            error_id="deadbeef",
            reason="connection_refused",
            host_kind="managed",
        ),
    )

    body = test_client.get("/ready").json()

    assert body["ready"] is True
    assert body["store"]["ok"] is False
    assert body["store"]["reason"] == "connection_refused"


@pytest.mark.unit
def test_ready_never_leaks_the_driver_error_text(client):
    leaky = 'connection to server at "db.abcdefgh.supabase.co" (11.22.33.44), port 5432 failed: FATAL: password authentication failed for user "postgres"'
    test_client = client(
        state=_FakeState(ready=True),
        health=StoreHealth(backend="postgres", ok=False, error=leaky, error_id="abc123"),
    )

    serialized = test_client.get("/ready").text

    # "postgres" alone is not a secret — `backend` is a deliberate part of the
    # payload. The connection detail is what must never reach a client.
    for fragment in ("supabase.co", "5432", "password", 'user "postgres"', "11.22.33.44"):
        assert fragment not in serialized


@pytest.mark.unit
def test_deep_health_answers_200_when_the_database_round_trips(client):
    test_client = client(
        state=_FakeState(ready=True),
        health=StoreHealth(backend="postgres", ok=True),
    )

    response = test_client.get("/health/deep")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.unit
def test_deep_health_answers_503_when_the_database_is_unreachable(client):
    """The regression this endpoint was built for: a paused Supabase project."""
    test_client = client(
        state=_FakeState(ready=True),
        health=StoreHealth(backend="postgres", ok=True),
        ping=StoreHealth(backend="postgres", ok=False, reason="connection_refused", error_id="f00d"),
    )

    response = test_client.get("/health/deep")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    # Readiness is reported independently: the process is up, the database is not.
    assert body["ready"] is True


@pytest.mark.unit
def test_deep_health_reuses_a_recent_verdict_instead_of_reconnecting(client, monkeypatch):
    """A burst of monitor requests must not open a connection each."""
    seen: list[float] = []

    def record_ping(max_age_seconds=0.0):
        seen.append(max_age_seconds)
        return StoreHealth(backend="postgres", ok=True)

    monkeypatch.setattr(
        readiness_router.current_state.__module__ and readiness_router, "current_state", lambda: _FakeState(True)
    )
    monkeypatch.setattr(readiness_router.document_store, "ping", record_ping)
    monkeypatch.setattr(readiness_router.document_store, "health", lambda: StoreHealth(backend="postgres", ok=True))

    app = FastAPI()
    app.include_router(readiness_router.router)
    TestClient(app).get("/health/deep")

    assert seen == [readiness_router.DEEP_HEALTH_MAX_AGE_SECONDS]


@pytest.mark.unit
def test_deep_health_max_age_stays_below_a_sane_monitor_interval():
    # Above ~60s a scheduled ping would reuse a cached verdict and stop
    # generating the database activity that keeps the project from idling out.
    assert 0 < readiness_router.DEEP_HEALTH_MAX_AGE_SECONDS <= 60
