"""libpq's environment variables for a connection URL that is itself in the environment.

    python -m scripts.libpq_env SOURCE_DATABASE_URL    # the variable's name, never its value

Prints one ``PGNAME=value`` line per connection parameter in the URL (PGHOST,
PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE …), sorted, on stdout.
``deploy/oracle/bin/migrate-from-supabase.sh`` hands them to pg_dump and psql by
name (``docker run -e PGPASSWORD``), so the Supabase URL, password included,
never appears on a command line, where ``ps`` shows it to every user of the
machine.

libpq parses the URL itself (``psycopg.conninfo.conninfo_to_dict``), so
percent-encoding, IPv6 hosts and query parameters mean exactly what they mean
to pg_dump. Refused, on stderr: an unset variable, a URL libpq cannot read, a
parameter libpq has no environment variable for, a value with a line break, and
a URL with no host (the clients run in a container, where libpq's default Unix
socket is nobody's server). A refusal never repeats the URL, and libpq's own
parse errors are withheld because they quote it, password included.

Exit status: 0 printed; 2 refused.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

EXIT_OK = 0
EXIT_REFUSED = 2

# libpq connection keywords and the environment variable each reads
# (PostgreSQL 17 documentation, "Environment Variables").
ENVIRONMENT_VARIABLES = {
    "application_name": "PGAPPNAME",
    "channel_binding": "PGCHANNELBINDING",
    "client_encoding": "PGCLIENTENCODING",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "dbname": "PGDATABASE",
    "gssencmode": "PGGSSENCMODE",
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "load_balance_hosts": "PGLOADBALANCEHOSTS",
    "options": "PGOPTIONS",
    "password": "PGPASSWORD",
    "port": "PGPORT",
    "require_auth": "PGREQUIREAUTH",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "user": "PGUSER",
}

_VARIABLE_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


class RefusedError(ValueError):
    """The URL cannot be turned into libpq variables; the message never quotes it."""


def _variable_name(value: str) -> str:
    if not _VARIABLE_NAME.fullmatch(value):
        raise argparse.ArgumentTypeError("must be the NAME of an environment variable, such as SOURCE_DATABASE_URL")
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print libpq's environment variables for a connection URL.")
    parser.add_argument("name", type=_variable_name, help="the environment variable that holds the URL")
    return parser.parse_args(argv)


def libpq_environment(name: str, url: str) -> dict[str, str]:
    """``{PGNAME: value}`` for the connection URL ``url``, held in variable ``name``."""
    from psycopg import ProgrammingError
    from psycopg.conninfo import conninfo_to_dict

    if not url.strip():
        raise RefusedError(f"{name} is not set")
    try:
        params = conninfo_to_dict(url)
    except ProgrammingError:
        raise RefusedError(
            f"{name} is not a connection URL libpq can read (its message is withheld: it quotes the URL)"
        ) from None
    if "host" not in params and "hostaddr" not in params:
        raise RefusedError(f"{name} names no host")
    environment: dict[str, str] = {}
    for keyword, value in params.items():
        variable = ENVIRONMENT_VARIABLES.get(keyword)
        if variable is None:
            raise RefusedError(f"{name} sets {keyword!r}, which libpq reads from no environment variable")
        text = str(value)
        if any(char in text for char in "\r\n\0"):
            raise RefusedError(f"{name}'s {keyword} contains a line break")
        environment[variable] = text
    return dict(sorted(environment.items()))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        environment = libpq_environment(args.name, os.getenv(args.name, ""))
    except RefusedError as exc:
        print(f"libpq_env: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    for variable, value in environment.items():
        print(f"{variable}={value}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
