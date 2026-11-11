"""Tests for app.data.open_meteo: the hourly series behind per-session weather.

Two properties matter. A gap in the feed must stay a gap — a missing rain
probability read as 0 % is a dry call nobody made. And the request must never
ask for days Open-Meteo refuses to serve, which it answers with a 400 rather
than a partial series.

Since the production outage of 6 Nov 2026 (P0b.1a), the call is retried once on
a 429, a 5xx or a timeout, every failed attempt logs its status or exception
type, and a call that still fails serves the venue's last good series, marked
stored with when it was fetched, never as a fresh one. After a failure the same
request is not sent again for a cooldown, so a feed that is down does not make
every page view wait up to 17 s for it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import time

import httpx
import pytest
import structlog

from app.data import open_meteo as module, open_meteo_store
from app.data.open_meteo import HourlyReading, HourlySeries, fetch_hourly, forecast_window, parse_hourly
from app.data.open_meteo_store import ForecastStore
from app.data.store_types import ReadResult, WriteResult

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 1)

PAYLOAD = {
    "hourly": {
        "time": ["2026-11-08T17:00", "2026-11-08T18:00", "not-a-time", 7],
        "temperature_2m": [24.5, 23.0, 1.0, 1.0],
        "relative_humidity_2m": [60, None, 1, 1],
        "precipitation_probability": [35, 70],
        "precipitation": [0.0, 1.2, 0, 0],
        "weather_code": [3, 61, 0, 0],
        "cloud_cover": [80, 100, 0, 0],
        "wind_speed_10m": [12.4, "fast", 0, 0],
        "wind_direction_10m": [270, 290, 0, 0],
        "is_day": [1, 0, 1, 1],
    }
}


def test_hours_are_read_in_utc_and_gaps_stay_none():
    readings = parse_hourly(PAYLOAD)

    assert readings == (
        HourlyReading(
            time=datetime(2026, 11, 8, 17, tzinfo=UTC),
            temperature_c=24.5,
            humidity_pct=60.0,
            rain_probability_pct=35.0,
            precipitation_mm=0.0,
            weather_code=3,
            cloud_cover_pct=80.0,
            wind_kph=12.4,
            wind_direction_deg=270.0,
            is_day=True,
        ),
        HourlyReading(
            time=datetime(2026, 11, 8, 18, tzinfo=UTC),
            temperature_c=23.0,
            humidity_pct=None,
            rain_probability_pct=70.0,
            precipitation_mm=1.2,
            weather_code=61,
            cloud_cover_pct=100.0,
            wind_kph=None,
            wind_direction_deg=290.0,
            is_day=False,
        ),
    )


def test_a_boolean_is_not_mistaken_for_a_reading():
    readings = parse_hourly({"hourly": {"time": ["2026-11-08T17:00"], "temperature_2m": [True], "is_day": [None]}})

    assert readings[0].temperature_c is None
    assert readings[0].is_day is None
    assert readings[0].weather_code is None


@pytest.mark.parametrize(
    "payload",
    [None, [], {"hourly": None}, {"hourly": {"time": "x"}}, {"hourly": {"time": []}}],
    ids=["null", "list", "no-hourly", "times-not-list", "no-hours"],
)
def test_an_unusable_payload_has_no_hours(payload):
    assert parse_hourly(payload) == ()


# -- forecast window -------------------------------------------------------------


def test_a_weekend_inside_the_horizon_is_requested_whole():
    assert forecast_window(date(2026, 11, 6), date(2026, 11, 8), TODAY) == (date(2026, 11, 6), date(2026, 11, 8))


def test_a_weekend_straddling_the_horizon_is_cut_at_its_edge():
    assert forecast_window(date(2026, 11, 14), date(2026, 11, 18), TODAY) == (date(2026, 11, 14), date(2026, 11, 16))


def test_a_weekend_straddling_the_archive_edge_is_cut_at_its_edge():
    assert forecast_window(date(2026, 7, 30), date(2026, 8, 2), TODAY) == (date(2026, 8, 1), date(2026, 8, 2))


@pytest.mark.parametrize(
    ("first", "last"),
    [(date(2026, 11, 20), date(2026, 11, 22)), (date(2026, 3, 6), date(2026, 3, 8))],
    ids=["beyond-horizon", "beyond-archive"],
)
def test_a_weekend_entirely_out_of_range_is_not_requested(first, last):
    assert forecast_window(first, last, TODAY) is None


# -- fetch -----------------------------------------------------------------------

FETCHED_AT = datetime(2026, 11, 7, 14, 5, tzinfo=UTC)


class FakeDocuments:
    """The document store behind the last-good copy, in memory."""

    def __init__(self, payload=None, readable=True):
        self.payload = payload
        self.readable = readable
        self.writes: list[dict] = []

    def read(self, name):
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append(payload)
        self.payload = payload
        return WriteResult()


@pytest.fixture
def documents(monkeypatch):
    """A fresh last-good store over an in-memory document, so no test writes to disk."""
    fake = FakeDocuments()
    monkeypatch.setattr(open_meteo_store, "document_store", fake)
    monkeypatch.setattr(module, "forecast_store", ForecastStore())
    return fake


@pytest.fixture
def sleeps(monkeypatch):
    waited: list[float] = []
    monkeypatch.setattr(module, "_sleep", waited.append)
    return waited


class FakeClock:
    """The module's monotonic clock, moved by hand."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(module, "_clock", fake)
    return fake


@pytest.fixture
def open_meteo(monkeypatch, documents, sleeps, clock):
    monkeypatch.setattr(module, "_cache", {})
    monkeypatch.setattr(module, "_failures", {})
    monkeypatch.setattr(module, "_utcnow", lambda: FETCHED_AT)
    calls: list[httpx.Request] = []

    def install(handler):
        def recorded(request):
            calls.append(request)
            return handler(request)

        monkeypatch.setattr(module, "new_client", lambda: httpx.Client(transport=httpx.MockTransport(recorded)))
        return calls

    return install


def answers(*responses):
    """A handler that gives each response in turn: an httpx.Response, or an exception to raise."""
    queue = list(responses)

    def handler(request):
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return handler


WEEKEND = (date(2026, 11, 6), date(2026, 11, 8))


def test_the_series_is_requested_in_utc_for_the_weekend_and_kept(open_meteo):
    calls = open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))

    first = fetch_hourly(-23.7036, -46.6997, *WEEKEND)

    assert first == HourlySeries(readings=parse_hourly(PAYLOAD), fetched_at=FETCHED_AT, stored=False)
    assert fetch_hourly(-23.7036, -46.6997, *WEEKEND) == first
    assert len(calls) == 1
    params = calls[0].url.params
    assert str(calls[0].url).startswith(module.OPEN_METEO_FORECAST_URL)
    assert params["timezone"] == "GMT"
    assert params["wind_speed_unit"] == "kmh"
    assert (params["start_date"], params["end_date"]) == ("2026-11-06", "2026-11-08")
    assert params["hourly"] == ",".join(module.HOURLY_VARIABLES)


def test_a_good_series_is_stored_for_its_venue_as_open_meteo_sent_it(open_meteo, documents):
    open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))

    fetch_hourly(-23.7036, -46.6997, *WEEKEND)

    assert documents.writes == [
        {
            "version": open_meteo_store.SCHEMA_VERSION,
            "venues": {"-23.7036,-46.6997": {"fetched_at": "2026-11-07T14:05:00Z", "hourly": PAYLOAD["hourly"]}},
        }
    ]


def test_a_series_served_from_memory_is_not_stored_again(open_meteo, documents):
    open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))

    fetch_hourly(1.0, 2.0, *WEEKEND)
    fetch_hourly(1.0, 2.0, *WEEKEND)

    assert len(documents.writes) == 1


def test_an_expired_series_is_fetched_again_and_old_entries_pruned(open_meteo, clock):
    calls = open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))

    fetch_hourly(1.0, 2.0, *WEEKEND)
    clock.now += module.WEATHER_CACHE_TTL + 1
    fetch_hourly(1.0, 2.0, *WEEKEND)

    assert len(calls) == 2
    assert len(module._cache) == 1


# -- retry -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "first",
    [
        httpx.Response(429, json={"error": True, "reason": "Minutely API request limit exceeded"}),
        httpx.Response(503, text="upstream down"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectTimeout("connect timed out"),
    ],
    ids=["rate-limited", "server-error", "read-timeout", "connect-timeout"],
)
def test_a_transient_failure_is_retried_once_after_a_short_backoff(open_meteo, sleeps, first):
    calls = open_meteo(answers(first, httpx.Response(200, json=PAYLOAD)))

    series = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert series is not None
    assert series.readings == parse_hourly(PAYLOAD)
    assert series.stored is False
    assert len(calls) == 2
    assert sleeps == [module.RETRY_BACKOFF_SECONDS]


@pytest.mark.parametrize(
    "first",
    [
        httpx.Response(400, json={"error": True, "reason": "out of allowed range"}),
        httpx.Response(404),
        httpx.Response(301, headers={"location": "https://elsewhere.example"}),
        httpx.ConnectError("refused"),
        httpx.Response(200, content=b"<html>"),
    ],
    ids=["bad-request", "not-found", "redirect", "connect-error", "not-json"],
)
def test_a_failure_a_retry_cannot_fix_is_not_retried(open_meteo, sleeps, first):
    calls = open_meteo(answers(first, httpx.Response(200, json=PAYLOAD)))

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert len(calls) == 1
    assert sleeps == []


def test_a_second_transient_failure_gives_up(open_meteo, sleeps):
    calls = open_meteo(answers(httpx.Response(429), httpx.Response(502)))

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert len(calls) == 2
    assert sleeps == [module.RETRY_BACKOFF_SECONDS]


# -- failure logs ----------------------------------------------------------------


def _failures(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["event"] == "open_meteo.fetch_failed"]


def test_every_failed_attempt_logs_its_status_and_the_feeds_reason(open_meteo):
    open_meteo(
        answers(
            httpx.Response(429, json={"error": True, "reason": "Minutely API request limit exceeded"}),
            httpx.Response(503, text="<html>bad gateway</html>"),
        )
    )

    with structlog.testing.capture_logs() as logs:
        fetch_hourly(1.0, 2.0, *WEEKEND)

    failures = _failures(logs)
    assert [(entry["attempt"], entry["status"], entry["retrying"]) for entry in failures] == [
        (1, 429, True),
        (2, 503, False),
    ]
    assert failures[0]["reason"] == "Minutely API request limit exceeded"
    assert failures[1]["reason"] is None
    assert all(entry["log_level"] == "warning" for entry in failures)


@pytest.mark.parametrize(
    ("raised", "error_type"),
    [(httpx.ReadTimeout("slow"), "ReadTimeout"), (httpx.ConnectError("refused"), "ConnectError")],
    ids=["timeout", "transport"],
)
def test_a_failed_attempt_with_no_answer_logs_the_exception_type(open_meteo, raised, error_type):
    open_meteo(answers(raised, raised))

    with structlog.testing.capture_logs() as logs:
        fetch_hourly(1.0, 2.0, *WEEKEND)

    assert {entry["error_type"] for entry in _failures(logs)} == {error_type}
    assert "status" not in _failures(logs)[0]


def test_an_answer_that_is_not_json_logs_its_status_and_the_decode_error(open_meteo):
    open_meteo(lambda request: httpx.Response(200, content=b"<html>"))

    with structlog.testing.capture_logs() as logs:
        fetch_hourly(1.0, 2.0, *WEEKEND)

    [failure] = _failures(logs)
    assert (failure["status"], failure["error_type"], failure["retrying"]) == (200, "JSONDecodeError", False)


def test_an_answer_with_no_hours_is_logged_as_empty(open_meteo):
    open_meteo(lambda request: httpx.Response(200, json={"hourly": {"time": []}}))

    with structlog.testing.capture_logs() as logs:
        assert fetch_hourly(1.0, 2.0, *WEEKEND) is None

    assert [entry["event"] for entry in logs] == ["open_meteo.empty_series"]


# -- the last good copy ----------------------------------------------------------


def _stored(fetched_at: str = "2026-11-07T08:00:00Z", hourly: dict = PAYLOAD["hourly"]) -> dict:
    return {
        "version": open_meteo_store.SCHEMA_VERSION,
        "venues": {"1.0000,2.0000": {"fetched_at": fetched_at, "hourly": hourly}},
    }


def test_a_failed_call_serves_the_venues_last_good_series_with_when_it_was_fetched(open_meteo, documents):
    documents.payload = _stored()
    open_meteo(lambda request: httpx.Response(429))

    with structlog.testing.capture_logs() as logs:
        series = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert series == HourlySeries(
        readings=parse_hourly(PAYLOAD), fetched_at=datetime(2026, 11, 7, 8, tzinfo=UTC), stored=True
    )
    assert logs[-1]["event"] == "open_meteo.serving_stored"
    assert logs[-1]["fetched_at"] == "2026-11-07T08:00:00Z"


def test_the_stored_copy_is_cut_to_the_days_asked_for(open_meteo, documents):
    hourly = {"time": ["2026-11-05T23:00", "2026-11-06T00:00", "2026-11-08T23:00", "2026-11-09T00:00"]}
    documents.payload = _stored(hourly=hourly)
    open_meteo(lambda request: httpx.Response(503))

    series = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert series is not None
    assert [reading.time.isoformat() for reading in series.readings] == [
        "2026-11-06T00:00:00+00:00",
        "2026-11-08T23:00:00+00:00",
    ]


def test_a_stored_copy_from_other_days_is_no_forecast(open_meteo, documents):
    documents.payload = _stored(hourly={"time": ["2025-11-08T17:00"]})
    open_meteo(lambda request: httpx.Response(503))

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None


def test_a_stored_copy_is_never_written_back_as_a_fresh_one(open_meteo, documents, clock):
    documents.payload = _stored()
    calls = open_meteo(lambda request: httpx.Response(400))

    first = fetch_hourly(1.0, 2.0, *WEEKEND)
    clock.now += module.FAILURE_COOLDOWN_SECONDS
    second = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert first == second
    assert first is not None
    assert first.stored is True
    assert len(calls) == 2, "a failure is not kept as an answer: once the cooldown ends the feed is asked again"
    assert documents.writes == []


@pytest.mark.parametrize(
    "respond",
    [
        lambda: httpx.Response(400, json={"error": True, "reason": "out of allowed range"}),
        lambda: httpx.Response(200, content=b"<html>"),
        lambda: httpx.Response(200, json={"hourly": {"time": []}}),
    ],
    ids=["refused", "not-json", "empty"],
)
def test_a_venue_that_never_had_a_good_answer_gets_none(open_meteo, respond, capsys):
    calls = open_meteo(lambda request: respond())

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert len(calls) == 1, "the second view falls in the cooldown"
    assert "open_meteo." in capsys.readouterr().out


def test_an_unreadable_store_with_a_failing_feed_gets_none(open_meteo, documents):
    documents.readable = False

    def boom(request):
        raise httpx.ConnectError("down", request=request)

    open_meteo(boom)

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None


# -- cooldown after a failure ------------------------------------------------------

VIEWS = 5

FAILED_CALLS = [
    pytest.param((httpx.Response(429), httpx.Response(502)), id="both-attempts-failed"),
    pytest.param((httpx.Response(400),), id="final-failure"),
    pytest.param((httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow")), id="both-timed-out"),
]


@pytest.mark.parametrize("failure", FAILED_CALLS)
def test_within_the_cooldown_the_feed_is_not_called_and_the_stored_copy_is_served(
    open_meteo, documents, clock, failure
):
    documents.payload = _stored()
    calls = open_meteo(answers(*failure))
    failed = fetch_hourly(1.0, 2.0, *WEEKEND)
    sent = len(calls)

    clock.now += module.FAILURE_COOLDOWN_SECONDS - 1
    views = [fetch_hourly(1.0, 2.0, *WEEKEND) for _ in range(VIEWS)]

    assert len(calls) == sent, "no request reaches the feed during the cooldown"
    assert failed is not None
    assert failed.stored is True
    assert views == [failed] * VIEWS


@pytest.mark.parametrize("failure", FAILED_CALLS)
def test_within_the_cooldown_a_venue_with_no_stored_copy_gets_none_without_a_call(open_meteo, failure):
    calls = open_meteo(answers(*failure))
    fetch_hourly(1.0, 2.0, *WEEKEND)
    sent = len(calls)

    views = [fetch_hourly(1.0, 2.0, *WEEKEND) for _ in range(VIEWS)]

    assert views == [None] * VIEWS
    assert len(calls) == sent


def test_the_cooldown_is_kept_per_request(open_meteo):
    calls = open_meteo(answers(httpx.Response(400), httpx.Response(200, json=PAYLOAD)))

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    other_venue = fetch_hourly(3.0, 4.0, *WEEKEND)

    assert other_venue is not None
    assert len(calls) == 2


def test_after_the_cooldown_one_live_attempt_is_made(open_meteo, clock):
    calls = open_meteo(lambda request: httpx.Response(400))
    fetch_hourly(1.0, 2.0, *WEEKEND)

    clock.now += module.FAILURE_COOLDOWN_SECONDS
    fetch_hourly(1.0, 2.0, *WEEKEND)
    fetch_hourly(1.0, 2.0, *WEEKEND)

    assert len(calls) == 2, "one attempt when the cooldown ends; its failure starts the next one"


def test_the_cooldown_starts_when_the_failure_is_known(open_meteo, clock):
    """A failing call can take 17 s; the cooldown is counted from its end, not its start."""

    def slow_failure(request):
        clock.now += 17
        return httpx.Response(400)

    calls = open_meteo(slow_failure)
    fetch_hourly(1.0, 2.0, *WEEKEND)

    clock.now += module.FAILURE_COOLDOWN_SECONDS - 1
    fetch_hourly(1.0, 2.0, *WEEKEND)

    assert len(calls) == 1


def test_a_good_answer_after_the_cooldown_clears_it(open_meteo, documents, clock):
    documents.payload = _stored()
    calls = open_meteo(answers(httpx.Response(400), httpx.Response(200, json=PAYLOAD)))
    fetch_hourly(1.0, 2.0, *WEEKEND)

    clock.now += module.FAILURE_COOLDOWN_SECONDS
    live = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert live == HourlySeries(readings=parse_hourly(PAYLOAD), fetched_at=FETCHED_AT, stored=False)
    assert fetch_hourly(1.0, 2.0, *WEEKEND) == live
    assert len(calls) == 2
    assert module._failures == {}


def test_a_good_answer_clears_a_failure_recorded_while_it_was_in_flight(open_meteo, monkeypatch, clock):
    """Two views ask at once; one fails, the other's good answer lands after it.

    With a memory TTL shorter than the cooldown, the next view after that answer
    expires must ask the feed again rather than sit out the other view's cooldown.
    """
    monkeypatch.setattr(module, "WEATHER_CACHE_TTL", 60)
    in_flight: list[httpx.Request] = []

    def handler(request):
        in_flight.append(request)
        if len(in_flight) == 1:
            assert fetch_hourly(1.0, 2.0, *WEEKEND) is None, "the concurrent view fails"
            return httpx.Response(200, json=PAYLOAD)
        if len(in_flight) == 2:
            return httpx.Response(400)
        return httpx.Response(200, json=PAYLOAD)

    calls = open_meteo(handler)
    first = fetch_hourly(1.0, 2.0, *WEEKEND)

    clock.now += 61
    later = fetch_hourly(1.0, 2.0, *WEEKEND)

    assert first is not None
    assert later is not None
    assert later.stored is False
    assert len(calls) == 3


def _skips(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["event"] == "open_meteo.fetch_skipped"]


def test_a_skipped_call_is_logged_once_per_cooldown_window(open_meteo, documents, clock):
    documents.payload = _stored()
    open_meteo(lambda request: httpx.Response(429))

    with structlog.testing.capture_logs() as logs:
        fetch_hourly(1.0, 2.0, *WEEKEND)
        clock.now += 60
        for _ in range(VIEWS):
            fetch_hourly(1.0, 2.0, *WEEKEND)
        clock.now += module.FAILURE_COOLDOWN_SECONDS
        for _ in range(VIEWS + 1):
            fetch_hourly(1.0, 2.0, *WEEKEND)

    skips = _skips(logs)
    assert len(skips) == 2, "one per window, not one per view"
    assert (skips[0]["lat"], skips[0]["lon"], skips[0]["log_level"]) == (1.0, 2.0, "info")
    assert skips[0]["retry_in_seconds"] == module.FAILURE_COOLDOWN_SECONDS - 60
    assert [entry["event"] for entry in logs].count("open_meteo.serving_stored") == 2, (
        "the stored copy is announced when a live call fails, not on every view it is served to"
    )


def test_failures_past_their_cooldown_are_pruned(open_meteo, clock):
    open_meteo(lambda request: httpx.Response(400))

    fetch_hourly(1.0, 2.0, *WEEKEND)
    clock.now += module.FAILURE_COOLDOWN_SECONDS
    fetch_hourly(3.0, 4.0, *WEEKEND)

    assert list(module._failures) == [(3.0, 4.0, "2026-11-06", "2026-11-08")]


def test_a_good_answer_prunes_failures_past_their_cooldown(open_meteo, clock):
    open_meteo(answers(httpx.Response(400), httpx.Response(200, json=PAYLOAD)))

    fetch_hourly(1.0, 2.0, *WEEKEND)
    clock.now += module.FAILURE_COOLDOWN_SECONDS
    fetch_hourly(3.0, 4.0, *WEEKEND)

    assert module._failures == {}


def test_the_default_clock_is_monotonic():
    assert module._clock is time.monotonic


def test_the_default_client_has_a_timeout():
    with module.new_client() as client:
        assert client.timeout.read == module.REQUEST_TIMEOUT_SECONDS


def test_fetched_at_defaults_to_the_wall_clock_in_utc():
    assert module._utcnow().tzinfo is UTC
