"""Create every table the app owns, with the app's own schema code.

    cd backend
    DATABASE_URL=<target> python -m scripts.ensure_schema                  # that database
    DATABASE_URL=<target> python -m scripts.ensure_schema --dbname <name>  # another one on that server

The API creates ``app_documents`` when it boots; ``analysis_cache``,
``user_profile`` + ``chat_message`` and ``rulebook_chunk`` (with the ``vector``
extension) are created by their modules on first use. A database that is about
to receive data, as in the Supabase → VM migration
(``deploy/oracle/bin/migrate-from-supabase.sh``), needs all of them first, made
by the statements the app itself runs rather than a copy that could drift.

On the VM it runs in the jobs container, which carries the stack's
``DATABASE_URL``; ``--dbname`` aims that URL at another database on the same
server (the migration's dry run uses a scratch one), so no second URL holding
the password is ever needed:

    bin/compose.sh --profile jobs run --rm -T jobs python -m scripts.ensure_schema

Every statement is idempotent (``IF NOT EXISTS``), so a second run changes
nothing. Prints the database, one line per module, then
``embedding dimension <n>``: the width the vector columns are created with,
which the migration checks the source against. Like
``backfill_chat_embeddings`` it never reads ``backend/.env``, which points at
production.

Exit status: 0 done; 1 a statement failed; 2 no ``DATABASE_URL``.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

from app.data import analysis_cache, memory, store
from app.rag import pgvector_store
from app.utils.embeddings import EMBEDDING_DIM

if TYPE_CHECKING:
    from collections.abc import Callable

    import psycopg

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_DATABASE = 2

NO_DATABASE = (
    "DATABASE_URL is not set. Export the URL of the target database; "
    "this script never reads backend/.env, which points at production."
)

# The tables each module creates, and the module's own schema function. The
# order is the app's: nothing here depends on another table.
SCHEMAS: tuple[tuple[str, Callable[[psycopg.Connection], None]], ...] = (
    ("app_documents", store.ensure_schema),
    ("analysis_cache", analysis_cache.ensure_schema),
    ("user_profile, chat_message", memory.ensure_schema),
    ("rulebook_chunk", pgvector_store.ensure_schema_conn),
)


def _database_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise argparse.ArgumentTypeError("must be a database name")
    return name


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create every table the app owns.")
    parser.add_argument(
        "--dbname",
        type=_database_name,
        help="a database on DATABASE_URL's server other than the one it names",
    )
    return parser.parse_args(argv)


def _connect(url: str, dbname: str | None) -> psycopg.Connection:
    import psycopg

    if dbname is None:
        return psycopg.connect(url, autocommit=True)
    return psycopg.connect(url, autocommit=True, dbname=dbname)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print(f"Schema not created: {NO_DATABASE}")
        return EXIT_NO_DATABASE
    try:
        with _connect(url, args.dbname) as conn:
            print(f"database {conn.info.dbname}")
            for tables, ensure in SCHEMAS:
                ensure(conn)
                print(f"  ready: {tables}")
    except Exception as exc:
        print(f"Schema not created: {exc}")
        return EXIT_FAILED
    print(f"embedding dimension {EMBEDDING_DIM}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
