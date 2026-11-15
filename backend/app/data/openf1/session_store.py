"""Kept OpenF1 answers: one whole answer per (endpoint, session), plus the sessions themselves.

OpenF1 refuses every request while an F1 session is live and answers bursts with
429, so a finished session read once should not need OpenF1 again. A stored
entry is one whole response (a JSONB array, or one file), written in one
statement or one ``os.replace``: a partial answer is never stored. Rows come
back verbatim, quirks included; the readers keep handling those.

Two Postgres tables, no foreign key, no migration framework: each store creates
its tables on first use and ``ensure_schema(conn)`` is the same DDL for a
deploy script. Without ``DATABASE_URL`` the files under ``OPENF1_STORE_DIR`` are
used. Any failure here is a logged miss, never an error: the caller fetches.

This module imports neither ``client`` nor ``sessions``; the read-through lives there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import threading
from typing import TYPE_CHECKING

import structlog

from app.config import OPENF1_STORE_DIR, OPENF1_STORE_PROVISIONAL_TTL_MINUTES

if TYPE_CHECKING:
    import psycopg

logger = structlog.get_logger()

# position, intervals and overtakes are held back until the Oracle VM has the room.
STORED_ENDPOINTS = frozenset(
    {"drivers", "session_result", "laps", "pit", "stints", "race_control", "weather", "team_radio"}
)
SOURCE = "openf1"
# OpenF1Session's fields, in column order.
SESSION_FIELDS = ("session_key", "meeting_key", "circuit_key", "code", "name", "date_start", "date_end")
_DATETIME_FIELDS = ("date_start", "date_end")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS openf1_sessions (
    session_key INTEGER PRIMARY KEY, year SMALLINT NOT NULL, round SMALLINT NOT NULL,
    meeting_key INTEGER NOT NULL, circuit_key INTEGER, code TEXT NOT NULL, name TEXT NOT NULL,
    date_start TIMESTAMPTZ, date_end TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL, fetched_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS openf1_sessions_round ON openf1_sessions (year, round);
CREATE TABLE IF NOT EXISTS openf1_rows (
    endpoint TEXT NOT NULL, session_key INTEGER NOT NULL, payload JSONB NOT NULL,
    source TEXT NOT NULL, fetched_at TIMESTAMPTZ NOT NULL, provisional BOOLEAN NOT NULL,
    PRIMARY KEY (endpoint, session_key));
-- Supabase publishes every public table over PostgREST; RLS with no policies
-- denies that API while this backend, connecting as the owner, is unaffected.
ALTER TABLE openf1_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE openf1_rows ENABLE ROW LEVEL SECURITY;
"""
_LOOKUP_SQL = (
    "SELECT s.date_end, r.payload, r.fetched_at, r.provisional FROM openf1_sessions s "
    "LEFT JOIN openf1_rows r ON r.session_key = s.session_key AND r.endpoint = %s WHERE s.session_key = %s"
)
_SAVE_ROWS_SQL = (
    "INSERT INTO openf1_rows (endpoint, session_key, payload, source, fetched_at, provisional) "
    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (endpoint, session_key) DO UPDATE SET "
    "payload = EXCLUDED.payload, source = EXCLUDED.source, "
    "fetched_at = EXCLUDED.fetched_at, provisional = EXCLUDED.provisional"
)
_SAVE_SESSIONS_SQL = (
    "INSERT INTO openf1_sessions (session_key, year, round, meeting_key, circuit_key, code, name, "
    "date_start, date_end, source, fetched_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (session_key) DO UPDATE SET year = EXCLUDED.year, round = EXCLUDED.round, "
    "meeting_key = EXCLUDED.meeting_key, circuit_key = EXCLUDED.circuit_key, code = EXCLUDED.code, "
    "name = EXCLUDED.name, date_start = EXCLUDED.date_start, date_end = EXCLUDED.date_end, "
    "source = EXCLUDED.source, fetched_at = EXCLUDED.fetched_at"
)
_WEEKEND_SQL = (
    "SELECT session_key, meeting_key, circuit_key, code, name, date_start, date_end "
    "FROM openf1_sessions WHERE year = %s AND round = %s ORDER BY date_start"
)


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class KeptRows:
    """One whole OpenF1 answer and when it was fetched."""

    rows: list[dict]
    fetched_at: datetime
    provisional: bool

    def fresh(self, at: datetime) -> bool:
        """Final rows are always fresh; provisional ones only within the TTL."""
        return not self.provisional or at - self.fetched_at < timedelta(minutes=OPENF1_STORE_PROVISIONAL_TTL_MINUTES)


# The session's date_end when it is registered, and the kept rows when there are any.
Lookup = tuple[datetime | None, KeptRows | None]


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(_SCHEMA_SQL)


def _session_values(year: int, round_num: int, record: dict, fetched_at: datetime) -> tuple:
    fields = {name: record[name] for name in SESSION_FIELDS}
    return (
        fields["session_key"], year, round_num, fields["meeting_key"], fields["circuit_key"], fields["code"],
        fields["name"], fields["date_start"], fields["date_end"], SOURCE, fetched_at,
    )  # fmt: skip


class FileSessionStore:
    """One directory per session: ``session.json`` and one ``<endpoint>.json`` per kept answer."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _write(self, path: Path, document: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # One temp name per thread, so concurrent writers never share a partial file.
        temp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
        temp.write_text(json.dumps(document), encoding="utf-8")
        os.replace(temp, path)

    def _read(self, path: Path) -> dict | None:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def lookup(self, endpoint: str, session_key: int) -> Lookup:
        session = self._read(self._root / str(session_key) / "session.json")
        if session is None:
            return None, None
        date_end = datetime.fromisoformat(session["date_end"])
        document = self._read(self._root / str(session_key) / f"{endpoint}.json")
        if document is None:
            return date_end, None
        kept = KeptRows(document["rows"], datetime.fromisoformat(document["fetched_at"]), document["provisional"])
        return date_end, kept

    def save_rows(self, endpoint: str, session_key: int, kept: KeptRows) -> None:
        document = {
            "source": SOURCE,
            "fetched_at": kept.fetched_at.isoformat(),
            "provisional": kept.provisional,
            "rows": kept.rows,
        }
        self._write(self._root / str(session_key) / f"{endpoint}.json", document)

    def weekend(self, year: int, round_num: int) -> list[dict]:
        found = []
        for path in sorted(self._root.glob("*/session.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if (document["year"], document["round"]) == (year, round_num):
                found.append({name: _revive(name, document[name]) for name in SESSION_FIELDS})
        return sorted(found, key=lambda record: record["date_start"] or record["date_end"])

    def save_sessions(self, year: int, round_num: int, records: list[dict]) -> None:
        fetched_at = now().isoformat()
        for record in records:
            document = {name: _dump(name, record[name]) for name in SESSION_FIELDS}
            document.update(year=year, round=round_num, source=SOURCE, fetched_at=fetched_at)
            self._write(self._root / str(record["session_key"]) / "session.json", document)


def _dump(name: str, value: object) -> object:
    return value.isoformat() if name in _DATETIME_FIELDS and isinstance(value, datetime) else value


def _revive(name: str, value: object) -> object:
    return datetime.fromisoformat(value) if name in _DATETIME_FIELDS and isinstance(value, str) else value


class PostgresSessionStore:
    """The two ``openf1_*`` tables, one short connection per call."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._schema_ready = False

    def _connect(self) -> psycopg.Connection:
        import psycopg

        conn = psycopg.connect(self._dsn, autocommit=True, connect_timeout=5)
        if not self._schema_ready:
            ensure_schema(conn)
            self._schema_ready = True
        return conn

    def lookup(self, endpoint: str, session_key: int) -> Lookup:
        with self._connect() as conn:
            row = conn.execute(_LOOKUP_SQL, (endpoint, session_key)).fetchone()
        if row is None:
            return None, None
        date_end, payload, fetched_at, provisional = row
        if payload is None:
            return date_end, None
        return date_end, KeptRows(payload, fetched_at, provisional)

    def save_rows(self, endpoint: str, session_key: int, kept: KeptRows) -> None:
        from psycopg.types.json import Jsonb

        values = (endpoint, session_key, Jsonb(kept.rows), SOURCE, kept.fetched_at, kept.provisional)
        with self._connect() as conn:
            conn.execute(_SAVE_ROWS_SQL, values)

    def weekend(self, year: int, round_num: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(_WEEKEND_SQL, (year, round_num)).fetchall()
        return [dict(zip(SESSION_FIELDS, row, strict=True)) for row in rows]

    def save_sessions(self, year: int, round_num: int, records: list[dict]) -> None:
        fetched_at = now()
        values = [_session_values(year, round_num, record, fetched_at) for record in records]
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.executemany(_SAVE_SESSIONS_SQL, values)


def _build(dsn: str) -> FileSessionStore | PostgresSessionStore:
    return PostgresSessionStore(dsn) if dsn else FileSessionStore(Path(OPENF1_STORE_DIR))


STORE = _build(os.getenv("DATABASE_URL", "").strip())


def lookup(endpoint: str, session_key: int) -> Lookup:
    """The session's end and any kept rows; ``(None, None)`` means fetch from OpenF1."""
    try:
        return STORE.lookup(endpoint, session_key)
    except Exception as exc:
        logger.warning("openf1_store.read_failed", endpoint=endpoint, session_key=session_key, error=str(exc))
        return None, None


def save_rows(endpoint: str, session_key: int, kept: KeptRows) -> None:
    try:
        STORE.save_rows(endpoint, session_key, kept)
    except Exception as exc:
        logger.warning("openf1_store.write_failed", endpoint=endpoint, session_key=session_key, error=str(exc))


def weekend(year: int, round_num: int) -> list[dict]:
    """The kept sessions of a weekend (``SESSION_FIELDS`` only), or [] when none or on failure."""
    try:
        return STORE.weekend(year, round_num)
    except Exception as exc:
        logger.warning("openf1_store.read_failed", year=year, round=round_num, error=str(exc))
        return []


def save_sessions(year: int, round_num: int, records: list[dict]) -> None:
    if not records:
        return
    try:
        STORE.save_sessions(year, round_num, records)
    except Exception as exc:
        logger.warning("openf1_store.write_failed", year=year, round=round_num, error=str(exc))
