"""The OpenF1 read-through store's storage layer: files and Postgres (faked), provenance, failures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import psycopg
import pytest

from app.data.openf1 import session_store
from app.data.openf1.session_store import FileSessionStore, KeptRows, PostgresSessionStore

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
DSN = "postgresql://user:secret@db.example.supabase.co:5432/postgres"
AT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
RACE_KEY = 11404


def _sessions() -> list[dict]:
    raw = json.loads((FIXTURES / "openf1_sessions.json").read_text())
    return [
        {
            "session_key": row["session_key"],
            "meeting_key": row["meeting_key"],
            "circuit_key": row["circuit_key"],
            "code": row["session_name"][:2].upper(),
            "name": row["session_name"],
            "date_start": datetime.fromisoformat(row["date_start"]),
            "date_end": datetime.fromisoformat(row["date_end"]),
        }
        for row in raw
    ]


def _stints() -> list[dict]:
    return json.loads((FIXTURES / "openf1_stints.json").read_text())


def _race() -> dict:
    return next(record for record in _sessions() if record["session_key"] == RACE_KEY)


@pytest.fixture
def files(tmp_path) -> FileSessionStore:
    return FileSessionStore(tmp_path / "store")


def test_a_saved_answer_reads_back_with_its_provenance(files, monkeypatch):
    monkeypatch.setattr(session_store, "STORE", files)
    session_store.save_sessions(2026, 19, [_race()])
    rows = _stints()

    session_store.save_rows("stints", RACE_KEY, KeptRows(rows, AT, provisional=True))
    date_end, kept = session_store.lookup("stints", RACE_KEY)

    assert date_end == _race()["date_end"]
    assert kept == KeptRows(rows, AT, True)
    document = json.loads((files._root / str(RACE_KEY) / "stints.json").read_text())
    assert document["source"] == "openf1"


def test_saving_the_same_answer_twice_keeps_one_copy(files):
    files.save_sessions(2026, 19, [_race()])
    files.save_sessions(2026, 19, [_race()])
    kept = KeptRows(_stints(), AT, provisional=False)
    files.save_rows("stints", RACE_KEY, kept)
    files.save_rows("stints", RACE_KEY, kept)

    assert sorted(path.name for path in (files._root / str(RACE_KEY)).iterdir()) == ["session.json", "stints.json"]
    assert len(files.weekend(2026, 19)) == 1


def test_an_unregistered_session_is_unknown(files, monkeypatch):
    monkeypatch.setattr(session_store, "STORE", files)

    assert session_store.lookup("stints", RACE_KEY) == (None, None)


def test_a_registered_session_without_rows_has_no_kept_rows(files):
    files.save_sessions(2026, 19, [_race()])

    assert files.lookup("stints", RACE_KEY) == (_race()["date_end"], None)


def test_a_weekend_reads_back_its_own_sessions_only(files):
    records = _sessions()
    files.save_sessions(2026, 19, records)
    other = {**records[0], "session_key": 1}
    files.save_sessions(2026, 20, [other])

    weekend = files.weekend(2026, 19)

    assert weekend == sorted(records, key=lambda record: record["date_start"])
    assert files.weekend(2026, 20) == [other]
    assert files.weekend(2026, 21) == []


def test_a_weekend_session_without_a_start_sorts_by_its_end(files):
    undated = {**_race(), "session_key": 2, "date_start": None}
    files.save_sessions(2026, 19, [_race(), undated])

    assert [record["session_key"] for record in files.weekend(2026, 19)][-1] == undated["session_key"]


def test_registering_nothing_writes_nothing(files, monkeypatch):
    monkeypatch.setattr(session_store, "STORE", files)

    session_store.save_sessions(2026, 19, [])

    assert not files._root.exists()


def test_an_unreadable_file_is_a_logged_miss(files, monkeypatch):
    monkeypatch.setattr(session_store, "STORE", files)
    files.save_sessions(2026, 19, [_race()])
    (files._root / str(RACE_KEY) / "stints.json").write_text("{not json")
    (files._root / str(RACE_KEY) / "session.json").write_text("{not json")

    assert session_store.lookup("stints", RACE_KEY) == (None, None)
    assert session_store.weekend(2026, 19) == []


def test_a_failed_file_write_is_logged_not_raised(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the store directory should be")
    monkeypatch.setattr(session_store, "STORE", FileSessionStore(blocker))

    session_store.save_sessions(2026, 19, [_race()])
    session_store.save_rows("stints", RACE_KEY, KeptRows(_stints(), AT, provisional=False))


def test_provisional_rows_are_fresh_only_within_the_ttl():
    final = KeptRows([], AT, provisional=False)
    provisional = KeptRows([], AT, provisional=True)
    ttl = timedelta(minutes=session_store.OPENF1_STORE_PROVISIONAL_TTL_MINUTES)

    assert final.fresh(AT + timedelta(days=30))
    assert provisional.fresh(AT + ttl - timedelta(seconds=1))
    assert not provisional.fresh(AT + ttl)


class FakeConnection:
    def __init__(self, row: tuple | None = None, rows: list[tuple] | None = None, fail_on: str | None = None) -> None:
        self.row = row
        self.rows = rows or []
        self.fail_on = fail_on
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self.fail_on is not None and self.fail_on in sql:
            raise psycopg.OperationalError("connection to server failed")
        return self

    def executemany(self, sql, params):
        self.statements.append((sql, list(params)))

    def cursor(self):
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


@pytest.fixture
def connect(monkeypatch):
    def install(connection: FakeConnection) -> FakeConnection:
        monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: connection)
        return connection

    return install


def _queries(connection: FakeConnection) -> list[tuple[str, object]]:
    return [statement for statement in connection.statements if "CREATE TABLE" not in statement[0]]


def test_postgres_lookup_is_one_joined_query(connect):
    rows = _stints()
    connection = connect(FakeConnection(row=(_race()["date_end"], rows, AT, True)))

    result = PostgresSessionStore(DSN).lookup("stints", RACE_KEY)

    assert result == (_race()["date_end"], KeptRows(rows, AT, True))
    [(sql, params)] = _queries(connection)
    assert "LEFT JOIN openf1_rows" in sql
    assert params == ("stints", RACE_KEY)


def test_postgres_lookup_of_a_registered_session_without_rows(connect):
    connect(FakeConnection(row=(_race()["date_end"], None, None, None)))

    assert PostgresSessionStore(DSN).lookup("stints", RACE_KEY) == (_race()["date_end"], None)


def test_postgres_lookup_of_an_unknown_session(connect):
    connect(FakeConnection(row=None))

    assert PostgresSessionStore(DSN).lookup("stints", RACE_KEY) == (None, None)


def test_postgres_rows_upsert_on_endpoint_and_session(connect):
    connection = connect(FakeConnection())

    PostgresSessionStore(DSN).save_rows("stints", RACE_KEY, KeptRows(_stints(), AT, provisional=True))

    [(sql, params)] = _queries(connection)
    assert "ON CONFLICT (endpoint, session_key) DO UPDATE" in sql
    assert params[:2] == ("stints", RACE_KEY)
    assert params[2].obj == _stints()
    assert params[3:] == ("openf1", AT, True)


def test_postgres_sessions_upsert_on_session_key(connect, monkeypatch):
    monkeypatch.setattr(session_store, "now", lambda: AT)
    connection = connect(FakeConnection())

    PostgresSessionStore(DSN).save_sessions(2026, 19, [_race()])

    [(sql, params)] = _queries(connection)
    race = _race()
    assert "ON CONFLICT (session_key) DO UPDATE" in sql
    assert params == [
        (RACE_KEY, 2026, 19, race["meeting_key"], race["circuit_key"], race["code"], race["name"],
         race["date_start"], race["date_end"], "openf1", AT),
    ]  # fmt: skip


def test_postgres_weekend_selects_by_year_and_round(connect):
    race = _race()
    connection = connect(FakeConnection(rows=[tuple(race[name] for name in session_store.SESSION_FIELDS)]))

    assert PostgresSessionStore(DSN).weekend(2026, 19) == [race]
    [(sql, params)] = _queries(connection)
    assert "WHERE year = %s AND round = %s" in sql
    assert params == (2026, 19)


def test_the_schema_is_created_once_per_store(connect):
    connection = connect(FakeConnection(row=None))
    store = PostgresSessionStore(DSN)

    store.lookup("stints", 1)
    store.lookup("stints", 2)

    assert sum("CREATE TABLE" in sql for sql, _ in connection.statements) == 1


def test_a_database_failure_is_a_logged_miss(connect, monkeypatch):
    connect(FakeConnection(fail_on="SELECT"))
    monkeypatch.setattr(session_store, "STORE", PostgresSessionStore(DSN))

    assert session_store.lookup("stints", RACE_KEY) == (None, None)
    assert session_store.weekend(2026, 19) == []


def test_a_failed_database_write_is_logged_not_raised(connect, monkeypatch):
    connect(FakeConnection(fail_on="INSERT"))
    monkeypatch.setattr(session_store, "STORE", PostgresSessionStore(DSN))

    session_store.save_rows("stints", RACE_KEY, KeptRows(_stints(), AT, provisional=False))
    session_store.save_sessions(2026, 19, [_race()])


def test_ensure_schema_is_idempotent_ddl_with_rls():
    connection = FakeConnection()

    session_store.ensure_schema(connection)

    [(sql, _)] = connection.statements
    assert sql.count("CREATE TABLE IF NOT EXISTS") == 2
    assert sql.count("ENABLE ROW LEVEL SECURITY") == 2


def test_the_database_url_picks_postgres_and_its_absence_the_files():
    assert isinstance(session_store._build(DSN), PostgresSessionStore)
    assert isinstance(session_store._build(""), FileSessionStore)
