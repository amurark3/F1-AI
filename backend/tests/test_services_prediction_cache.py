"""Tests for app.services.prediction_cache — the stored-snapshot cache.

This cache is the reason a prediction shown before a race is still the same
prediction after it. The failure this module was written to prevent is a
read-modify-write hazard: the cache holds the whole document in memory and
rewrites all of it on every ``set``, so persisting on top of a *failed* load
would upload only the entries this process happened to hold and destroy every
snapshot it could not read. A paused Supabase project caused exactly that.

So the properties under test are:

* a failed read is never recorded as "loaded and empty", and blocks the write;
* the failure is retried after a backoff rather than pinned for the process;
* a snapshot computed by superseded logic is a miss, not a stale answer;
* a non-durable write still returns the prediction, with ``durable=False`` said
  out loud rather than hidden.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.predictions import PREDICTION_LOGIC_VERSION
from app.data.store import DOCUMENT_PREDICTION_CACHE
from app.data.store_types import ReadResult, WriteResult
from app.services import prediction_cache as module
from app.services.prediction_cache import (
    CACHE_SCHEMA_VERSION,
    PredictionCacheUnavailableError,
    PredictionSnapshotCache,
)


class FakeStore:
    """In-memory ``DocumentStore`` whose read/write outcomes are scriptable."""

    def __init__(self, payload=None, *, read_ok=True, write_ok=True, durable=True):
        self.payload = payload
        self.read_ok = read_ok
        self.write_ok = write_ok
        self.durable = durable
        self.reads: list[str] = []
        self.writes: list[tuple[str, dict]] = []

    def read(self, name):
        self.reads.append(name)
        if not self.read_ok:
            return ReadResult(ok=False, error="connection to server failed")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append((name, payload))
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="write failed")
        self.payload = payload
        return WriteResult(durable=self.durable)


def _result(driver="VER", *, logic_version=PREDICTION_LOGIC_VERSION):
    return {
        "year": 2026,
        "round": 1,
        "logic_version": logic_version,
        "predictions": [{"driver_code": driver, "position": 1}],
    }


@pytest.fixture
def cache(monkeypatch):
    """A cold cache wired to a fake store holding nothing."""
    store = FakeStore()
    monkeypatch.setattr(module, "document_store", store)
    instance = PredictionSnapshotCache()
    instance.store = store  # test handle, not used by the implementation
    return instance


# ---------------------------------------------------------------------------
# datetime coercion helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_iso_renders_utc_and_passes_none_through():
    aware = datetime(2026, 3, 8, 14, 0, tzinfo=timezone(timedelta(hours=2)))

    assert module._iso(aware) == "2026-03-08T12:00:00+00:00"
    assert module._iso(None) is None


@pytest.mark.unit
def test_utc_now_is_timezone_aware():
    assert module._utc_now().tzinfo == timezone.utc


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [None, pd.NaT, "2026-03-08", 42],
    ids=["none", "pandas-nat", "string", "number"],
)
def test_coerce_utc_rejects_non_datetimes(value):
    assert module._coerce_utc(value) is None


@pytest.mark.unit
def test_coerce_utc_assumes_utc_for_a_naive_datetime():
    """FastF1's ``*DateUtc`` columns are naive but already UTC."""
    coerced = module._coerce_utc(datetime(2026, 3, 8, 15, 0))

    assert coerced == datetime(2026, 3, 8, 15, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_coerce_utc_converts_an_offset_aware_datetime():
    local = datetime(2026, 3, 8, 15, 0, tzinfo=timezone(timedelta(hours=3)))

    assert module._coerce_utc(local) == datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_coerce_utc_unwraps_a_pandas_timestamp():
    coerced = module._coerce_utc(pd.Timestamp("2026-03-08 15:00"))

    assert coerced == datetime(2026, 3, 8, 15, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _race_datetime — picking the race session out of a schedule row
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_race_datetime_prefers_the_session_named_race():
    row = {
        "Session1": "Practice 1",
        "Session1DateUtc": datetime(2026, 3, 6, 11, 0),
        "Session4": "Race",
        "Session4DateUtc": datetime(2026, 3, 8, 15, 0),
        "Session5": "Post-race",
        "Session5DateUtc": datetime(2026, 3, 8, 18, 0),
        "EventDate": datetime(2026, 3, 8),
    }

    assert module._race_datetime(row) == datetime(2026, 3, 8, 15, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_race_datetime_falls_back_to_the_last_dated_session():
    """A calendar without a session labelled "Race" still has a final session."""
    row = {
        "Session1": "Practice 1",
        "Session1DateUtc": datetime(2026, 3, 6, 11, 0),
        "Session3": "Qualifying",
        "Session3DateUtc": datetime(2026, 3, 7, 15, 0),
        "EventDate": datetime(2026, 3, 8),
    }

    assert module._race_datetime(row) == datetime(2026, 3, 7, 15, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_race_datetime_ignores_a_race_session_with_no_date():
    row = {"Session2": "Race", "Session2DateUtc": None, "EventDate": datetime(2026, 3, 8)}

    assert module._race_datetime(row) == datetime(2026, 3, 8, tzinfo=timezone.utc)


@pytest.mark.unit
def test_race_datetime_returns_none_when_the_row_is_undated():
    assert module._race_datetime({"Session1": "Race"}) is None


# ---------------------------------------------------------------------------
# next_race_start
# ---------------------------------------------------------------------------


def _schedule(rows):
    return pd.DataFrame(rows)


@pytest.mark.unit
def test_next_race_start_returns_the_earliest_future_race(monkeypatch):
    now = module._utc_now()
    schedule = _schedule(
        [
            {"Session5": "Race", "Session5DateUtc": now - timedelta(days=7)},
            {"Session5": "Race", "Session5DateUtc": now + timedelta(days=30)},
            {"Session5": "Race", "Session5DateUtc": now + timedelta(days=3)},
        ]
    )
    monkeypatch.setattr(module.fastf1, "get_event_schedule", lambda **_kwargs: schedule)

    result = module.next_race_start(2026)

    assert result == module._coerce_utc(now + timedelta(days=3))


@pytest.mark.unit
def test_next_race_start_is_none_once_the_season_is_over(monkeypatch):
    past = module._utc_now() - timedelta(days=1)
    monkeypatch.setattr(
        module.fastf1,
        "get_event_schedule",
        lambda **_kwargs: _schedule([{"Session5": "Race", "Session5DateUtc": past}]),
    )

    assert module.next_race_start(2026) is None


@pytest.mark.unit
def test_next_race_start_degrades_when_the_calendar_is_unavailable(monkeypatch, capsys):
    def unavailable(**_kwargs):
        raise ConnectionError("ergast unreachable")

    monkeypatch.setattr(module.fastf1, "get_event_schedule", unavailable)

    assert module.next_race_start(2026) is None
    assert "prediction_cache.schedule_unavailable" in capsys.readouterr().out


@pytest.mark.unit
def test_next_race_start_excludes_pre_season_testing(monkeypatch):
    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return _schedule([])

    monkeypatch.setattr(module.fastf1, "get_event_schedule", capture)

    module.next_race_start(2026)

    assert captured == {"year": 2026, "include_testing": False}


# ---------------------------------------------------------------------------
# load — the failed-read boundary
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_of_a_missing_document_is_a_real_empty_cache(cache):
    assert cache.load() is True
    assert cache._loaded is True
    assert cache._entries == {}


@pytest.mark.unit
def test_failed_load_is_not_recorded_as_loaded(monkeypatch, capsys):
    monkeypatch.setattr(module, "document_store", FakeStore(read_ok=False))
    cache = PredictionSnapshotCache()

    assert cache.load() is False
    assert cache._loaded is False, "an outage must not latch as an empty cache"
    assert "prediction_cache.load_failed" in capsys.readouterr().out


@pytest.mark.unit
def test_load_normalises_stored_entries(cache, capsys):
    cache.store.payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "entries": {
            "2026:1": {
                "schema_version": CACHE_SCHEMA_VERSION,
                "active_snapshot_id": "v1",
                "snapshots": [{"id": "v1", "result": _result()}],
            },
            "2026:2": "not a dict",
        },
    }

    assert cache.load() is True
    assert set(cache._entries) == {"2026:1"}, "non-dict entries are dropped"
    assert "prediction_cache.loaded" in capsys.readouterr().out


@pytest.mark.unit
def test_load_accepts_the_legacy_schema_version(cache):
    cache.store.payload = {
        "schema_version": 1,
        "entries": {"2026:1": {"result": _result(), "stored_at": "2026-03-01T00:00:00+00:00"}},
    }

    assert cache.load() is True
    assert cache._entries["2026:1"]["snapshots"][0]["reason"] == "legacy_cache"


@pytest.mark.unit
def test_load_discards_a_document_written_by_a_future_schema(cache, capsys):
    cache.store.payload = {"schema_version": 99, "entries": {"2026:1": {}}}

    assert cache.load() is True
    assert cache._entries == {}
    assert "prediction_cache.unsupported_schema" in capsys.readouterr().out


@pytest.mark.unit
def test_load_tolerates_a_document_with_no_entries_key(cache):
    cache.store.payload = {"schema_version": CACHE_SCHEMA_VERSION}

    assert cache.load() is True
    assert cache._entries == {}


# ---------------------------------------------------------------------------
# _ensure_loaded — backoff after a failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ensure_loaded_backs_off_before_retrying_a_failed_read(monkeypatch):
    store = FakeStore(read_ok=False)
    monkeypatch.setattr(module, "document_store", store)
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    cache = PredictionSnapshotCache()

    assert cache._ensure_loaded() is False
    assert cache._ensure_loaded() is False, "a second immediate attempt must be suppressed"
    assert len(store.reads) == 1


@pytest.mark.unit
def test_ensure_loaded_retries_once_the_backoff_expires(monkeypatch):
    """The bug this fixes: a recovered database still served "no prediction"."""
    store = FakeStore(read_ok=False)
    monkeypatch.setattr(module, "document_store", store)
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    cache = PredictionSnapshotCache()

    assert cache._ensure_loaded() is False
    clock[0] += module.RELOAD_BACKOFF_SECONDS + 1
    store.read_ok = True  # the database came back

    assert cache._ensure_loaded() is True
    assert len(store.reads) == 2


@pytest.mark.unit
def test_ensure_loaded_short_circuits_once_loaded(cache):
    cache.load()

    assert cache._ensure_loaded() is True
    assert len(cache.store.reads) == 1, "a warm cache must not re-read the store"


# ---------------------------------------------------------------------------
# set / get round trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_set_then_get_returns_the_stored_prediction(cache):
    cache.set(2026, 1, _result())

    stored = cache.get(2026, 1)

    assert stored["predictions"] == [{"driver_code": "VER", "position": 1}]
    assert stored["cache"]["status"] == "hit"
    assert stored["cache"]["policy"] == module.CACHE_POLICY
    assert stored["cache"]["snapshot_count"] == 1
    assert stored["cache"]["recompute_count"] == 0


@pytest.mark.unit
def test_set_persists_the_whole_document_to_the_store(cache):
    cache.set(2026, 1, _result())

    (name, payload) = cache.store.writes[-1]
    assert name == DOCUMENT_PREDICTION_CACHE
    assert payload["schema_version"] == CACHE_SCHEMA_VERSION
    assert set(payload["entries"]) == {"2026:1"}


@pytest.mark.unit
def test_set_appends_a_snapshot_and_keeps_the_original_stored_at(cache):
    first = cache.set(2026, 1, _result("VER"))
    second = cache.set(2026, 1, _result("NOR"), reason="qualifying_recompute")

    assert second["cache"]["snapshot_count"] == 2
    assert second["cache"]["recompute_count"] == 1
    assert second["cache"]["reason"] == "qualifying_recompute"
    assert second["predictions"][0]["driver_code"] == "NOR"
    # The entry records when the race was first predicted, not last.
    assert second["cache"]["updated_at"] >= first["cache"]["updated_at"]
    assert cache._entries["2026:1"]["stored_at"] == first["cache"]["stored_at"]


@pytest.mark.unit
def test_set_strips_the_caller_supplied_cache_block(cache):
    """Round-tripping an enriched result must not persist its own metadata."""
    payload = _result()
    payload["cache"] = {"status": "hit", "snapshot_id": "stale"}

    cache.set(2026, 1, payload)

    snapshot = cache._entries["2026:1"]["snapshots"][0]
    assert "cache" not in snapshot["result"]


@pytest.mark.unit
def test_set_does_not_mutate_the_caller_result(cache):
    original = _result()

    cache.set(2026, 1, original)
    cache._entries["2026:1"]["snapshots"][0]["result"]["predictions"].append({"driver_code": "LEC"})

    assert original["predictions"] == [{"driver_code": "VER", "position": 1}]


@pytest.mark.unit
def test_set_refuses_to_write_on_top_of_a_failed_read(monkeypatch):
    """The data-loss guard: no truncated document may reach the store."""
    store = FakeStore(read_ok=False)
    monkeypatch.setattr(module, "document_store", store)
    cache = PredictionSnapshotCache()

    with pytest.raises(PredictionCacheUnavailableError, match="refusing to overwrite"):
        cache.set(2026, 1, _result())

    assert store.writes == [], "nothing may be persisted while the store is unreadable"


@pytest.mark.unit
def test_set_reports_a_non_durable_write_without_losing_the_prediction(cache, capsys):
    cache.store.write_ok = False

    stored = cache.set(2026, 1, _result())

    assert stored["cache"]["durable"] is False
    assert stored["predictions"], "the caller still gets its prediction"
    assert cache.get(2026, 1)["predictions"], "and it is live in memory"
    assert "prediction_cache.stored" in capsys.readouterr().out


@pytest.mark.unit
def test_get_returns_none_for_an_unknown_race(cache):
    assert cache.get(2026, 7) is None


@pytest.mark.unit
def test_get_returns_none_while_the_store_is_unreadable(monkeypatch):
    monkeypatch.setattr(module, "document_store", FakeStore(read_ok=False))
    cache = PredictionSnapshotCache()

    assert cache.get(2026, 1) is None


@pytest.mark.unit
def test_get_treats_a_snapshot_without_predictions_as_a_miss(cache):
    cache.load()
    cache._entries["2026:1"] = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "active_snapshot_id": "v1",
        "snapshots": [{"id": "v1", "result": {"predictions": [], "logic_version": PREDICTION_LOGIC_VERSION}}],
    }

    assert cache.get(2026, 1) is None


@pytest.mark.unit
def test_get_treats_a_superseded_logic_version_as_a_miss(cache, capsys):
    cache.set(2026, 1, _result(logic_version=PREDICTION_LOGIC_VERSION - 1))

    assert cache.get(2026, 1) is None
    assert "prediction_cache.stale" in capsys.readouterr().out


@pytest.mark.unit
def test_get_treats_a_pre_versioning_snapshot_as_stale(cache):
    """Snapshots stored before logic versioning carry no version at all."""
    result = _result()
    del result["logic_version"]
    cache.set(2026, 1, result)

    assert cache.get(2026, 1) is None


@pytest.mark.unit
def test_get_logs_a_hit(cache, capsys):
    cache.set(2026, 1, _result())
    capsys.readouterr()

    cache.get(2026, 1)

    assert "prediction_cache.hit" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# snapshot selection and entry normalisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_active_snapshot_prefers_the_recorded_active_id(cache):
    entry = {
        "active_snapshot_id": "v1",
        "snapshots": [{"id": "v1", "result": _result("VER")}, {"id": "v2", "result": _result("NOR")}],
    }

    assert cache._active_snapshot(entry)["id"] == "v1"


@pytest.mark.unit
def test_active_snapshot_falls_back_to_the_newest_when_the_id_is_dangling(cache):
    entry = {
        "active_snapshot_id": "deleted",
        "snapshots": [{"id": "v1", "result": _result()}, {"id": "v2", "result": _result()}],
    }

    assert cache._active_snapshot(entry)["id"] == "v2"


@pytest.mark.unit
def test_active_snapshot_is_none_for_an_empty_history(cache):
    assert cache._active_snapshot({"snapshots": []}) is None


@pytest.mark.unit
@pytest.mark.parametrize("entry", [None, "corrupt", 7], ids=["missing", "string", "number"])
def test_normalise_entry_replaces_a_non_dict_with_an_empty_record(cache, entry):
    normalised = cache._normalise_entry(entry)

    assert normalised == {
        "schema_version": CACHE_SCHEMA_VERSION,
        "policy": module.CACHE_POLICY,
        "snapshots": [],
    }


@pytest.mark.unit
def test_normalise_entry_drops_snapshots_without_a_result_dict(cache):
    entry = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "snapshots": [{"id": "v1", "result": _result()}, {"id": "v2"}, "junk"],
    }

    assert [s["id"] for s in cache._normalise_entry(entry)["snapshots"]] == ["v1"]


@pytest.mark.unit
def test_normalise_entry_supplies_the_default_policy(cache):
    entry = {"schema_version": CACHE_SCHEMA_VERSION, "policy": None, "snapshots": []}

    assert cache._normalise_entry(entry)["policy"] == module.CACHE_POLICY


@pytest.mark.unit
def test_normalise_entry_upgrades_a_legacy_record(cache):
    legacy = {"result": _result(), "stored_at": "2026-03-01T10:00:00+00:00"}

    normalised = cache._normalise_entry(legacy)

    assert normalised["schema_version"] == CACHE_SCHEMA_VERSION
    assert normalised["active_snapshot_id"] == "v1-2026-03-01T10:00:00+00:00"
    assert normalised["snapshots"][0]["result"]["predictions"]


@pytest.mark.unit
def test_normalise_entry_dates_a_legacy_record_from_its_result(cache):
    legacy = {"result": {**_result(), "generated_at": "2026-02-02T00:00:00+00:00"}}

    assert cache._normalise_entry(legacy)["stored_at"] == "2026-02-02T00:00:00+00:00"


@pytest.mark.unit
def test_normalise_entry_stamps_an_undated_legacy_record(cache):
    normalised = cache._normalise_entry({"result": _result()})

    assert normalised["stored_at"].endswith("+00:00")


@pytest.mark.unit
def test_normalise_entry_discards_a_legacy_record_with_no_result(cache):
    assert cache._normalise_entry({"stored_at": "2026-01-01"})["snapshots"] == []


@pytest.mark.unit
def test_with_metadata_handles_an_entry_holding_no_snapshot(cache):
    enriched = cache._with_metadata({"stored_at": "2026-01-01T00:00:00+00:00"}, status="hit")

    assert enriched["cache"]["snapshot_id"] is None
    assert enriched["cache"]["snapshot_count"] == 0
    assert enriched["cache"]["valid_until"] is None


@pytest.mark.unit
def test_key_is_year_and_round(cache):
    assert cache._key(2026, 12) == "2026:12"


@pytest.mark.unit
def test_module_exposes_a_shared_cache_instance():
    assert isinstance(module.prediction_snapshot_cache, PredictionSnapshotCache)


# ---------------------------------------------------------------------------
# Against the real Postgres backend, with only psycopg faked
# ---------------------------------------------------------------------------


class _FakePgConnection:
    """Enough of ``psycopg.Connection`` for the document store's two statements."""

    def __init__(self, rows: dict, *, fail_on):
        self._rows = rows
        self._fail_on = fail_on
        self._pending = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        if self._fail_on and self._fail_on in sql:
            raise RuntimeError("connection to server failed: the database is paused")
        if sql.strip().startswith("SELECT payload"):
            self._pending = self._rows.get(params[0])
        elif "INSERT INTO app_documents" in sql:
            self._rows[params[0]] = params[1].obj
        return self

    def fetchone(self):
        return (self._pending,) if self._pending is not None else None


@pytest.fixture
def postgres_store(monkeypatch):
    """A ``PostgresDocumentStore`` over a fake psycopg driver (no network)."""
    rows: dict[str, dict] = {}
    state = SimpleNamespace(rows=rows, fail_on=None)

    def connect(_dsn, **_kwargs):
        return _FakePgConnection(state.rows, fail_on=state.fail_on)

    fake_psycopg = SimpleNamespace(
        connect=connect,
        Connection=_FakePgConnection,
        types=SimpleNamespace(json=SimpleNamespace(Jsonb=lambda obj, **_kw: SimpleNamespace(obj=obj))),
    )
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.types", fake_psycopg.types)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", fake_psycopg.types.json)

    from app.data.store import PostgresDocumentStore

    store = PostgresDocumentStore("postgresql://user:pw@aws-0-eu-west-1.pooler.supabase.com:5432/postgres")
    monkeypatch.setattr(module, "document_store", store)
    return state


@pytest.mark.unit
def test_snapshot_survives_a_round_trip_through_postgres(postgres_store):
    writer = PredictionSnapshotCache()
    writer.set(2026, 1, _result("VER"))

    # A fresh process reading the same table must see the same snapshot.
    reader = PredictionSnapshotCache()

    assert reader.get(2026, 1)["predictions"][0]["driver_code"] == "VER"


@pytest.mark.unit
def test_a_paused_database_never_truncates_the_stored_snapshots(postgres_store):
    """The production incident, reproduced: read fails, write must not proceed."""
    seeded = PredictionSnapshotCache()
    seeded.set(2026, 1, _result("VER"))
    seeded.set(2026, 2, _result("NOR"))
    persisted_before = dict(postgres_store.rows[DOCUMENT_PREDICTION_CACHE]["entries"])

    postgres_store.fail_on = "SELECT payload"
    cold = PredictionSnapshotCache()

    with pytest.raises(PredictionCacheUnavailableError):
        cold.set(2026, 3, _result("LEC"))

    assert postgres_store.rows[DOCUMENT_PREDICTION_CACHE]["entries"] == persisted_before


@pytest.mark.unit
def test_a_failed_postgres_write_is_reported_as_not_durable(postgres_store):
    cache = PredictionSnapshotCache()
    cache.load()
    postgres_store.fail_on = "INSERT INTO app_documents"

    stored = cache.set(2026, 1, _result())

    assert stored["cache"]["durable"] is False
    assert DOCUMENT_PREDICTION_CACHE not in postgres_store.rows
