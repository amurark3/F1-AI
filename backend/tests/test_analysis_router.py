"""Tests for the Telemetry Lab router and its single-flight registry.

* A slow OpenF1 load is one run however many requests ask: a request that stops
  waiting gets ``pending`` and the next one joins the same run. A worker thread
  cannot be stopped, so starting another per retry is how Render ran out of
  memory on 2026-10-30.
* Every failure is a 200 with a reason the page shows: OpenF1's live lockout,
  OpenF1 down, nothing published, or a client-safe error id.
* Inputs are validated before any OpenF1 request is made.
"""

from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import single_flight as single_flight_module
from app.api.routers import analysis as router_module
from app.api.single_flight import SingleFlight
from app.data.openf1.client import OpenF1LiveLockoutError, OpenF1UnavailableError
from app.services.analysis.common import AnalysisUnavailableError, DriverLap, SessionRef

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Single flight
# ---------------------------------------------------------------------------


async def test_requests_for_the_same_key_share_one_run():
    flight: SingleFlight[int] = SingleFlight("test")
    release = threading.Event()
    calls: list[int] = []

    def work() -> int:
        calls.append(1)
        release.wait(timeout=5)
        return 7

    first = await flight.run("k", work, wait_seconds=0.01)
    joined = flight.start("k", work)
    release.set()

    assert first is None
    assert await joined == 7
    assert calls == [1]


async def test_a_finished_run_is_forgotten_so_the_next_request_starts_afresh():
    flight: SingleFlight[int] = SingleFlight("test")
    answers = iter([1, 2])

    assert await flight.run("k", lambda: next(answers), wait_seconds=1) == 1
    await asyncio.sleep(0)
    assert await flight.run("k", lambda: next(answers), wait_seconds=1) == 2


async def test_a_failure_reaches_the_waiting_request_and_is_logged(monkeypatch):
    flight: SingleFlight[int] = SingleFlight("test")
    logged: list[str] = []
    monkeypatch.setattr(single_flight_module.logger, "warning", lambda event, **_kw: logged.append(event))

    def broken() -> int:
        raise OpenF1UnavailableError("down")

    with pytest.raises(OpenF1UnavailableError):
        await flight.run("k", broken, wait_seconds=1)
    await asyncio.sleep(0)

    assert logged == ["single_flight.failed"]


async def test_a_run_that_itself_timed_out_is_an_error_not_pending():
    flight: SingleFlight[int] = SingleFlight("test")

    def timed_out() -> int:
        raise TimeoutError("socket timed out")

    with pytest.raises(TimeoutError):
        await flight.run("k", timed_out, wait_seconds=1)


async def test_a_cancelled_run_is_forgotten_quietly():
    flight: SingleFlight[int] = SingleFlight("test")
    release = threading.Event()
    run = flight.start("k", lambda: release.wait(timeout=5) and 1)
    run.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await run
    await asyncio.sleep(0)
    assert flight.start("k", lambda: 2) is not run


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(router_module, "flights", SingleFlight("test"))
    app = FastAPI()
    app.include_router(router_module.router)
    return TestClient(app)


def _answer(**fields) -> dict:
    return {"available": True, "pending": False, **fields}


def test_each_endpoint_hands_the_builder_what_was_asked_for(client, monkeypatch):
    seen: dict[str, tuple] = {}

    def recorder(name):
        def build(*args):
            seen[name] = args
            return _answer(name=name)

        return build

    for name in ("build_weekend", "build_lap_list", "build_track_map", "build_comparison", "build_degradation"):
        monkeypatch.setattr(router_module, name, recorder(name))

    assert client.get("/analysis/2026/18/sessions").json()["name"] == "build_weekend"
    assert client.get("/analysis/2026/18/laps?session=SQ").json()["name"] == "build_lap_list"
    client.get("/analysis/2026/18/track-map?driver=nor&lap=8")
    client.get("/analysis/2026/18/compare?a=NOR&b=ver&lap_b=12&session=FP2")
    client.get("/analysis/2023/4/tyre-degradation?session=S")

    assert seen["build_weekend"] == (2026, 18)
    assert seen["build_lap_list"] == (SessionRef(2026, 18, "SQ"),)
    assert seen["build_track_map"] == (SessionRef(2026, 18, "Q"), DriverLap("NOR", 8))
    assert seen["build_comparison"] == (SessionRef(2026, 18, "FP2"), DriverLap("NOR", None), DriverLap("VER", 12))
    assert seen["build_degradation"] == (SessionRef(2023, 4, "S"),)


@pytest.mark.parametrize(
    "path",
    [
        "/analysis/2022/1/sessions",
        "/analysis/2026/0/sessions",
        "/analysis/2026/18/laps?session=FP4",
        "/analysis/2026/18/track-map",
        "/analysis/2026/18/track-map?driver=NORRIS",
        "/analysis/2026/18/track-map?driver=NOR&lap=0",
        "/analysis/2026/18/compare?a=NOR",
        "/analysis/2026/18/tyre-degradation?session=Q",
    ],
)
def test_bad_inputs_are_refused_before_openf1_is_asked(client, path):
    assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (AnalysisUnavailableError("no_lap"), "no_lap"),
        (OpenF1LiveLockoutError("live"), "openf1_live"),
        (OpenF1UnavailableError("HTTP 503"), "openf1_unavailable"),
    ],
)
def test_a_failure_is_a_200_with_the_reason(client, monkeypatch, error, reason):
    def fail(*_args):
        raise error

    monkeypatch.setattr(router_module, "build_track_map", fail)

    response = client.get("/analysis/2026/18/track-map?driver=NOR")

    assert response.status_code == 200
    assert response.json()["reason"] == reason
    assert response.json()["available"] is False


def test_an_unexpected_failure_carries_an_error_id_not_the_exception(client, monkeypatch):
    def fail(*_args):
        raise RuntimeError("postgres://secret@host")

    monkeypatch.setattr(router_module, "build_degradation", fail)

    body = client.get("/analysis/2026/18/tyre-degradation").json()

    assert body["reason"] == "error"
    assert "error_id" in body
    assert "secret" not in str(body)


def test_a_load_that_outlives_the_wait_answers_pending(client, monkeypatch):
    release = threading.Event()

    def slow(*_args):
        release.wait(timeout=5)
        return _answer()

    monkeypatch.setattr(router_module, "ANALYSIS_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(router_module, "build_lap_list", slow)
    # TestClient waits for the run before returning, so it is let go shortly
    # after the request has stopped waiting on it.
    threading.Timer(0.2, release.set).start()

    body = client.get("/analysis/2026/18/laps").json()

    assert (body["pending"], body["reason"]) == (True, "loading")
