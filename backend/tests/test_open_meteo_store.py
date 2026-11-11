"""Tests for app.data.open_meteo_store: the last good forecast per venue.

The store is what lets the weekend forecast stand through an Open-Meteo outage
instead of the race-day card falling back on a number that is not race day.
The risks it carries:

* **A write after a failed read destroys data.** It would upload a document
  holding only this venue and drop every other one. Writes wait for a read.
* **A stored copy is not trusted blindly.** An entry of the wrong shape, or a
  document from another schema, is a miss rather than a crash or a forecast.
* **The document must not grow for ever.** A series too old to overlap any
  window Open-Meteo serves is pruned on the next write.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import structlog

from app.data import open_meteo, open_meteo_store as module
from app.data.open_meteo_store import ForecastStore, StoredSeries, venue_key
from app.data.store import DOCUMENT_OPEN_METEO_FORECASTS
from app.data.store_types import ReadResult, WriteResult

pytestmark = pytest.mark.unit

FETCHED_AT = datetime(2026, 11, 7, 14, 5, tzinfo=UTC)
HOURLY = {"time": ["2026-11-08T17:00"], "precipitation_probability": [92]}
INTERLAGOS = "-23.7036,-46.6997"


class FakeStore:
    """In-memory document store that can be told to fail."""

    def __init__(self, payload=None, readable=True, writable=True):
        self.payload = payload
        self.readable = readable
        self.writable = writable
        self.reads = 0
        self.writes: list[tuple[str, dict]] = []

    def read(self, name):
        self.reads += 1
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append((name, payload))
        if not self.writable:
            return WriteResult(ok=False, durable=False, error="read-only")
        self.payload = payload
        return WriteResult()


@pytest.fixture
def store(monkeypatch):
    def install(**kwargs) -> FakeStore:
        fake = FakeStore(**kwargs)
        monkeypatch.setattr(module, "document_store", fake)
        return fake

    return install


def _document(venues: dict, version: int = module.SCHEMA_VERSION) -> dict:
    return {"version": version, "venues": venues}


def _entry(fetched_at: str = "2026-11-07T14:05:00Z", hourly: object = HOURLY) -> dict:
    return {"fetched_at": fetched_at, "hourly": hourly}


def test_a_venue_is_keyed_by_its_coordinates_to_four_places():
    assert venue_key(-23.70361, -46.69972) == INTERLAGOS


def test_a_kept_series_round_trips_with_when_it_was_fetched(store):
    fake = store(payload=None)
    kept = ForecastStore()

    kept.keep(INTERLAGOS, FETCHED_AT, HOURLY)

    assert fake.writes == [(DOCUMENT_OPEN_METEO_FORECASTS, _document({INTERLAGOS: _entry()}))]
    assert kept.last_good(INTERLAGOS) == StoredSeries(fetched_at=FETCHED_AT, hourly=HOURLY)
    assert ForecastStore().last_good(INTERLAGOS) == StoredSeries(fetched_at=FETCHED_AT, hourly=HOURLY), (
        "a fresh process reads it back"
    )


def test_a_newer_series_replaces_the_venues_copy_and_keeps_the_others(store):
    other = {"time": ["2026-11-21T04:00"]}
    fake = store(payload=_document({"36.1147,-115.1728": _entry(hourly=other), INTERLAGOS: _entry()}))
    later = FETCHED_AT + timedelta(minutes=10)

    ForecastStore().keep(INTERLAGOS, later, {"time": []})

    assert fake.payload == _document(
        {"36.1147,-115.1728": _entry(hourly=other), INTERLAGOS: _entry("2026-11-07T14:15:00Z", {"time": []})}
    )


def test_an_unknown_venue_has_no_copy(store):
    store(payload=_document({INTERLAGOS: _entry()}))

    assert ForecastStore().last_good("0.0000,0.0000") is None


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "2026-11-07",
        {"hourly": HOURLY},
        _entry(fetched_at=1_762_524_300),
        _entry(fetched_at="yesterday"),
        _entry(hourly=[1, 2]),
    ],
    ids=["null", "not-a-dict", "no-stamp", "stamp-not-text", "stamp-unparseable", "hourly-not-a-dict"],
)
def test_an_entry_of_the_wrong_shape_is_a_miss_not_a_forecast(store, entry):
    store(payload=_document({INTERLAGOS: entry}))

    assert ForecastStore().last_good(INTERLAGOS) is None


def test_a_naive_stamp_is_read_as_utc(store):
    store(payload=_document({INTERLAGOS: _entry(fetched_at="2026-11-07T14:05:00")}))

    stored = ForecastStore().last_good(INTERLAGOS)

    assert stored is not None
    assert stored.fetched_at == FETCHED_AT


@pytest.mark.parametrize(
    "payload",
    [_document({INTERLAGOS: _entry()}, version=0), {"version": module.SCHEMA_VERSION, "venues": ["x"]}],
    ids=["other-schema", "venues-not-a-dict"],
)
def test_a_document_this_schema_cannot_read_is_treated_as_empty(store, payload):
    fake = store(payload=payload)
    kept = ForecastStore()

    assert kept.last_good(INTERLAGOS) is None
    kept.keep(INTERLAGOS, FETCHED_AT, HOURLY)
    assert fake.payload == _document({INTERLAGOS: _entry()})


def test_a_series_too_old_to_serve_any_window_is_pruned_on_the_next_write(store):
    stale = FETCHED_AT - timedelta(days=module.KEEP_DAYS + 1)
    recent = FETCHED_AT - timedelta(days=module.KEEP_DAYS - 1)
    fake = store(
        payload=_document(
            {
                "1.0000,1.0000": _entry(fetched_at=stale.isoformat()),
                "2.0000,2.0000": _entry(fetched_at=recent.isoformat()),
                "3.0000,3.0000": _entry(fetched_at="garbage"),
            }
        )
    )

    ForecastStore().keep(INTERLAGOS, FETCHED_AT, HOURLY)

    assert set(fake.payload["venues"]) == {"2.0000,2.0000", INTERLAGOS}


def test_the_store_keeps_every_series_open_meteo_could_still_serve():
    """A series fetched at T covers at most T-92 days to T+15; a request today can reach that far back."""
    assert module.KEEP_DAYS >= open_meteo.PAST_DAYS_LIMIT + open_meteo.FORECAST_HORIZON_DAYS


def test_nothing_is_written_after_a_failed_read(store):
    fake = store(readable=False)
    kept = ForecastStore()

    with structlog.testing.capture_logs() as logs:
        assert kept.last_good(INTERLAGOS) is None
        kept.keep(INTERLAGOS, FETCHED_AT, HOURLY)

    assert fake.writes == [], "writing now would upload only this venue and drop every other"
    assert [entry["event"] for entry in logs] == ["open_meteo_store.read_failed", "open_meteo_store.write_skipped"]


def test_a_failed_read_is_retried_after_a_backoff(store, monkeypatch):
    clock = iter([100.0, 110.0, 200.0])
    monkeypatch.setattr(module, "_clock", lambda: next(clock))
    fake = store(readable=False)
    kept = ForecastStore()

    kept.last_good(INTERLAGOS)  # reads, fails, backs off until 130
    kept.last_good(INTERLAGOS)  # 110: still backing off, no read
    fake.readable = True
    fake.payload = _document({INTERLAGOS: _entry()})

    assert kept.last_good(INTERLAGOS) == StoredSeries(fetched_at=FETCHED_AT, hourly=HOURLY)  # 200: tries again
    assert fake.reads == 2


def test_a_failed_write_is_logged_and_kept_in_memory(store):
    store(payload=None, writable=False)
    kept = ForecastStore()

    with structlog.testing.capture_logs() as logs:
        kept.keep(INTERLAGOS, FETCHED_AT, HOURLY)

    assert [entry["event"] for entry in logs] == ["open_meteo_store.write_failed"]
    assert logs[0]["error"] == "read-only"
    assert kept.last_good(INTERLAGOS) == StoredSeries(fetched_at=FETCHED_AT, hourly=HOURLY)
