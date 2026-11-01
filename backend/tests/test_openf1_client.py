"""Tests for app.data.openf1.client: one request to OpenF1, read the way OpenF1 means it.

* 404 is "no rows", never an outage.
* 429 is retried after the advertised wait, within bounds, then given up.
* 401 is the live-session lockout, its own error so a page can say "try later".
* Request starts are spaced across the process, and the spacing never holds a
  lock while a request is in flight.

HTTP is served by ``httpx.MockTransport``; the network is blocked.
"""

from __future__ import annotations

import threading

import httpx
import pytest

from app.data.openf1 import client as module
from app.data.openf1.client import (
    OpenF1LiveLockoutError,
    OpenF1UnavailableError,
    RequestPacer,
    get_json,
    new_client,
    retry_after,
)


def _get(handler) -> list[dict]:
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return get_json(client, "stints", {"session_key": 1})


@pytest.mark.unit
def test_rows_are_returned_as_served():
    rows = [{"driver_number": 1}]

    assert _get(lambda request: httpx.Response(200, json=rows)) == rows


@pytest.mark.unit
def test_the_query_reaches_openf1_on_the_named_path():
    seen: list[httpx.Request] = []

    def record(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    _get(record)

    assert str(seen[0].url) == f"{module.OPENF1_BASE}/stints?session_key=1"


@pytest.mark.unit
def test_no_results_found_is_an_empty_answer():
    assert _get(lambda request: httpx.Response(404, json={"detail": "No results found."})) == []


@pytest.mark.unit
def test_a_live_session_refusal_is_the_lockout_error():
    refusal = httpx.Response(401, json={"detail": "Live F1 session in progress, restricted to authenticated users"})

    with pytest.raises(OpenF1LiveLockoutError, match="live"):
        _get(lambda request: refusal)


@pytest.mark.unit
def test_the_lockout_is_still_an_unavailable_openf1():
    assert issubclass(OpenF1LiveLockoutError, OpenF1UnavailableError)


@pytest.mark.unit
def test_a_rate_limited_request_is_retried_after_the_advertised_wait(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", waits.append)
    answers = iter([httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, json=[{"a": 1}])])

    assert _get(lambda request: next(answers)) == [{"a": 1}]
    assert waits == [3.0]


@pytest.mark.unit
def test_a_request_that_stays_rate_limited_gives_up(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", waits.append)

    with pytest.raises(OpenF1UnavailableError, match="rate limited"):
        _get(lambda request: httpx.Response(429))

    assert waits == [module.DEFAULT_RETRY_AFTER_SECONDS] * module.RATE_LIMIT_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize(("header", "expected"), [("120", 10.0), ("soon", 2.0), ("-4", 0.0)])
def test_the_advertised_wait_is_bounded(header, expected):
    assert retry_after(httpx.Response(429, headers={"retry-after": header})) == expected


@pytest.mark.unit
def test_an_unreachable_openf1_is_unavailable():
    def refuse(request):
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(OpenF1UnavailableError, match="unreachable"):
        _get(refuse)


@pytest.mark.unit
def test_a_server_error_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="HTTP 503"):
        _get(lambda request: httpx.Response(503))


@pytest.mark.unit
def test_a_page_that_is_not_json_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="not JSON"):
        _get(lambda request: httpx.Response(200, content=b"<html>maintenance</html>"))


@pytest.mark.unit
def test_an_object_where_a_list_belongs_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="detail"):
        _get(lambda request: httpx.Response(200, json={"detail": "restricted"}))


@pytest.mark.unit
def test_the_default_client_carries_the_configured_timeout():
    with new_client() as client:
        assert client.timeout.read == module.OPENF1_HTTP_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


@pytest.mark.unit
def test_requests_in_a_burst_are_spaced_by_the_gap():
    clock = FakeClock()
    pacer = RequestPacer(0.5, clock=clock, sleep=clock.sleep)

    for _ in range(3):
        pacer.wait()

    assert clock.sleeps == [0.5, 1.0]


@pytest.mark.unit
def test_a_request_after_a_quiet_spell_starts_at_once():
    clock = FakeClock()
    pacer = RequestPacer(0.5, clock=clock, sleep=clock.sleep)

    pacer.wait()
    clock.now += 5
    pacer.wait()

    assert clock.sleeps == []


@pytest.mark.unit
def test_the_pacer_does_not_hold_its_lock_while_a_caller_sleeps():
    clock = FakeClock()
    in_sleep = threading.Event()
    release = threading.Event()

    def blocking_sleep(seconds: float) -> None:
        clock.sleeps.append(seconds)
        in_sleep.set()
        release.wait(timeout=5)

    pacer = RequestPacer(0.5, clock=clock, sleep=blocking_sleep)
    pacer.wait()
    sleeper = threading.Thread(target=pacer.wait)
    sleeper.start()
    assert in_sleep.wait(timeout=5)

    # A third caller books its slot while the second is still asleep.
    booked = threading.Thread(target=pacer.wait)
    booked.start()
    booked_slot_taken = False
    for _ in range(100):
        if len(clock.sleeps) == 2:
            booked_slot_taken = True
            break
        threading.Event().wait(0.01)
    release.set()
    sleeper.join(timeout=5)
    booked.join(timeout=5)

    assert booked_slot_taken
    assert clock.sleeps == [0.5, 1.0]


@pytest.mark.unit
def test_every_request_waits_its_turn_with_the_process_pacer(monkeypatch):
    waits: list[str] = []
    monkeypatch.setattr(module.PACER, "wait", lambda: waits.append("wait"))

    _get(lambda request: httpx.Response(200, json=[]))

    assert waits == ["wait"]
