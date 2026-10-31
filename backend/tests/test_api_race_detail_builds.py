"""Tests for the race-detail build registry: one FastF1 build per race, however many ask.

A build runs ``build_race_detail`` on a worker thread, and Python cannot stop a
thread. A request that stops waiting at its deadline therefore leaves the build
running. Before the registry, every retry, and the startup prefetch, started
another full build beside it: the pattern that ran the 512 MB Render instance
out of memory through the predictions route on 2026-10-30. These tests pin the
replacement:

* **Later requests join the build in flight** instead of starting another.
* **A build caches its own result**, so a detail that arrives after every
  request gave up still lands in the cache for the next one.
* **A finished build is forgotten**, so a failure is retried, never pinned.

FastF1 is replaced by a stand-in whose thread blocks until the test releases it.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
import structlog

from app.api import race_detail as rd

DETAIL = {"round": 1, "circuit": {"circuit_name": "Bahrain International Circuit"}}
# Generous next to the 0.05 s request deadline, so a slow runner cannot leave a
# test waiting on a thread nobody released.
RELEASE_TIMEOUT_SECONDS = 5


class _GatedBuild:
    """A ``build_race_detail`` stand-in that blocks until released, counting calls."""

    def __init__(self, outcome: dict | Exception) -> None:
        self.calls = 0
        self.release = threading.Event()
        self._outcome = outcome

    def __call__(self, year: int, round_num: int) -> dict:
        self.calls += 1
        self.release.wait(timeout=RELEASE_TIMEOUT_SECONDS)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    """The cache and the registry are module-global; each test gets its own."""
    monkeypatch.setattr(rd, "race_detail_cache", {})
    monkeypatch.setattr(rd, "race_detail_builds", {})
    monkeypatch.setattr(rd, "FASTF1_TIMEOUT", 0.05)


def _install(monkeypatch, outcome: dict | Exception = DETAIL) -> _GatedBuild:
    build = _GatedBuild(outcome)
    monkeypatch.setattr(rd, "build_race_detail", build)
    return build


@pytest.mark.unit
async def test_requests_that_outlive_their_wait_share_one_build(monkeypatch):
    gated = _install(monkeypatch)

    first = await rd.get_race_detail(2026, 1)
    second = await rd.get_race_detail(2026, 1)

    assert first == second == {"error": rd.STILL_LOADING_MESSAGE, "timeout": True}
    assert gated.calls == 1, "a retry must join the build in flight, not start another"

    gated.release.set()
    await rd.race_detail_builds[(2026, 1)]


@pytest.mark.unit
async def test_a_build_that_finishes_after_every_request_gave_up_is_still_cached(monkeypatch):
    gated = _install(monkeypatch)
    await rd.get_race_detail(2026, 1)
    build = rd.race_detail_builds[(2026, 1)]

    gated.release.set()
    await build

    assert rd.race_detail_cache == {(2026, 1): DETAIL}
    assert await rd.get_race_detail(2026, 1) == DETAIL
    assert gated.calls == 1


@pytest.mark.unit
async def test_a_finished_build_is_forgotten_so_a_failure_is_retried(monkeypatch):
    calls: list[int] = []

    def flaky(year: int, round_num: int) -> dict:
        calls.append(round_num)
        if len(calls) == 1:
            raise RuntimeError("upstream 503")
        return DETAIL

    monkeypatch.setattr(rd, "build_race_detail", flaky)

    failed = await rd.get_race_detail(2026, 1)
    retried = await rd.get_race_detail(2026, 1)

    assert "error_id" in failed
    assert retried == DETAIL
    assert calls == [1, 1]
    assert rd.race_detail_builds == {}


@pytest.mark.unit
async def test_a_failure_no_request_stayed_to_see_is_logged(monkeypatch):
    gated = _install(monkeypatch, RuntimeError("upstream 503"))
    await rd.get_race_detail(2026, 1)
    build = rd.race_detail_builds[(2026, 1)]

    with structlog.testing.capture_logs() as logs:
        gated.release.set()
        await asyncio.wait([build])
        await asyncio.sleep(0)  # the registry's done callback runs on the next turn

    assert rd.race_detail_builds == {}
    assert rd.race_detail_cache == {}
    failure = next(entry for entry in logs if entry["event"] == "api.race_detail.build_failed")
    assert failure["error"] == "upstream 503"
