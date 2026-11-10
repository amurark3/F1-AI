"""Conversation memory and user personalization (Postgres + pgvector).

Gives the assistant a memory across sessions:

  * ``user_profile`` — favourite driver/team and free-form preferences, so the
    engineer can tailor briefings to the person on the pit wall.
  * ``chat_message`` — every user/assistant turn, embedded with the shared
    sentence-transformers model in ``app.utils.embeddings`` (the instance the
    rulebook uses), so past conversation can be recalled semantically (pgvector
    cosine search) rather than just by recency. A turn saved while local models
    are off keeps a NULL embedding; ``scripts/backfill_chat_embeddings.py``
    fills those in later.

Everything here is a no-op when ``DATABASE_URL`` is unset, so local development
without a database keeps working exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

import os
import threading
from typing import Any

import structlog

from app.utils.embeddings import EMBEDDING_DIM, embed, to_pgvector_literal

logger = structlog.get_logger()

MEMORY_ENABLED = bool(os.getenv("DATABASE_URL", "").strip())

_SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS user_profile (
    user_id         TEXT PRIMARY KEY,
    favorite_driver TEXT,
    favorite_team   TEXT,
    prefs           JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_message (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    thread_id  TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    embedding  vector({EMBEDDING_DIM}),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_message_thread_idx
    ON chat_message (user_id, thread_id, created_at);

-- Both tables hold per-user data and Supabase exposes every public table over
-- PostgREST, so RLS with no policies is what keeps the anon/authenticated API
-- from reading other people's profiles and chat history.  This module connects
-- as the owning role over plain Postgres and so bypasses RLS.  Idempotent.
ALTER TABLE user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_message ENABLE ROW LEVEL SECURITY;
"""

# ---------------------------------------------------------------------------
# Lazy singleton: DB schema
# ---------------------------------------------------------------------------
_schema_ready = False
_schema_lock = threading.Lock()


def _connect() -> psycopg.Connection:
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create ``user_profile`` and ``chat_message`` on ``conn``'s database. Idempotent.

    Runs every time it is called (``scripts.ensure_schema`` may aim it at another
    database); the request path goes through ``_ensure_schema``, once per process.
    """
    conn.execute(_SCHEMA_SQL)


def _ensure_schema(conn: psycopg.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        ensure_schema(conn)
        _schema_ready = True


# ---------------------------------------------------------------------------
# Public API — all no-op safe when memory is disabled or the DB is down
# ---------------------------------------------------------------------------
def save_message(user_id: str, thread_id: str, role: str, content: str) -> None:
    """Persist a chat turn (embedded when possible). Never raises."""
    if not MEMORY_ENABLED or not user_id or not content:
        return
    embedding = embed(content) if role in ("user", "assistant") else None
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            if embedding is not None:
                conn.execute(
                    "INSERT INTO chat_message (user_id, thread_id, role, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::vector)",
                    (user_id, thread_id, role, content, to_pgvector_literal(embedding)),
                )
            else:
                conn.execute(
                    "INSERT INTO chat_message (user_id, thread_id, role, content) VALUES (%s, %s, %s, %s)",
                    (user_id, thread_id, role, content),
                )
    except Exception as exc:
        logger.warning("memory.save_message_failed", error=str(exc))


# Both recall statements, written out rather than assembled from a WHERE
# fragment, so no SQL is built at runtime. The only difference is the extra
# thread-exclusion predicate.
_RECALL_ALL_THREADS = """
    SELECT role, content, thread_id, created_at,
           1 - (embedding <=> %s::vector) AS similarity
    FROM chat_message
    WHERE user_id = %s AND embedding IS NOT NULL
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""

_RECALL_EXCLUDING_THREAD = """
    SELECT role, content, thread_id, created_at,
           1 - (embedding <=> %s::vector) AS similarity
    FROM chat_message
    WHERE user_id = %s AND embedding IS NOT NULL AND thread_id <> %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""


def recall_relevant(user_id: str, query: str, *, k: int = 4, exclude_thread: str | None = None) -> list[dict]:
    """Return the user's most semantically-similar past messages to ``query``.

    Empty list when memory is off, the query can't be embedded, or on error.
    """
    if not MEMORY_ENABLED or not user_id or not query:
        return []
    embedding = embed(query)
    if embedding is None:
        return []
    literal = to_pgvector_literal(embedding)
    if exclude_thread:
        statement = _RECALL_EXCLUDING_THREAD
        # Order: sim-select vec, user_id, excluded thread, order vec, k.
        params: list[Any] = [literal, user_id, exclude_thread, literal, k]
    else:
        statement = _RECALL_ALL_THREADS
        params = [literal, user_id, literal, k]
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            rows = conn.execute(statement, params).fetchall()
        return [
            {
                "role": r[0],
                "content": r[1],
                "thread_id": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "similarity": round(float(r[4]), 3),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("memory.recall_failed", error=str(exc))
        return []


def get_profile(user_id: str) -> dict:
    """Return the stored profile for ``user_id`` (empty dict if none)."""
    if not MEMORY_ENABLED or not user_id:
        return {}
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT favorite_driver, favorite_team, prefs FROM user_profile WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if not row:
            return {}
        return {"favorite_driver": row[0], "favorite_team": row[1], "prefs": row[2] or {}}
    except Exception as exc:
        logger.warning("memory.get_profile_failed", error=str(exc))
        return {}


def set_profile(
    user_id: str,
    *,
    favorite_driver: str | None = None,
    favorite_team: str | None = None,
    prefs: dict | None = None,
) -> dict:
    """Upsert profile fields for ``user_id`` and return the merged profile."""
    if not MEMORY_ENABLED or not user_id:
        return {}
    from psycopg.types.json import Jsonb

    try:
        with _connect() as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO user_profile (user_id, favorite_driver, favorite_team, prefs, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    favorite_driver = COALESCE(EXCLUDED.favorite_driver, user_profile.favorite_driver),
                    favorite_team   = COALESCE(EXCLUDED.favorite_team, user_profile.favorite_team),
                    prefs           = user_profile.prefs || EXCLUDED.prefs,
                    updated_at      = now()
                """,
                (user_id, favorite_driver, favorite_team, Jsonb(prefs or {})),
            )
    except Exception as exc:
        logger.warning("memory.set_profile_failed", error=str(exc))
    return get_profile(user_id)


def build_memory_context(user_id: str, query: str, thread_id: str | None = None) -> str:
    """Assemble a system-prompt fragment from profile + recalled messages.

    Returns an empty string when there is nothing personalised to add.
    """
    if not MEMORY_ENABLED or not user_id:
        return ""

    parts: list[str] = []
    profile = get_profile(user_id)
    prefs_bits = []
    if profile.get("favorite_driver"):
        prefs_bits.append(f"favourite driver is {profile['favorite_driver']}")
    if profile.get("favorite_team"):
        prefs_bits.append(f"supports {profile['favorite_team']}")
    if prefs_bits:
        parts.append("ABOUT THIS USER: " + "; ".join(prefs_bits) + ".")

    recalled = recall_relevant(user_id, query, k=3, exclude_thread=thread_id)
    strong = [r for r in recalled if r["similarity"] >= 0.35]
    if strong:
        lines = [f"- ({r['role']}) {r['content'][:200]}" for r in strong]
        parts.append("RELEVANT PAST CONVERSATION:\n" + "\n".join(lines))

    return "\n\n".join(parts)
