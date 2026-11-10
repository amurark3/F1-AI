"""Tests for ``scripts.libpq_env`` — a connection URL turned into libpq's environment.

The migration (deploy/oracle/bin/migrate-from-supabase.sh) hands the Supabase
URL to pg_dump and psql through these variables, so the password never reaches
a command line. What is pinned:

* **libpq's parse, exactly.** Percent-encoding, IPv6 hosts and query parameters
  come out as pg_dump would read them.
* **The value never leaks.** The script takes the variable's *name*; a refusal
  names the problem, never the URL, even where libpq's own message quotes it.
* **Line-safe output.** One ``PGNAME=value`` per line on stdout, everything else
  on stderr, and a value that would break a line is refused.
"""

from __future__ import annotations

import pytest

from scripts import libpq_env as script

pytestmark = pytest.mark.unit

ESCAPED_LOGIN = "s3cr%23t-pw"  # percent-encoded "s3cr#t-pw"


def _run(monkeypatch, capsys, url: str | None, name: str = "SOURCE_DATABASE_URL") -> tuple[int, str, str]:
    if url is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, url)
    status = script.main([name])
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def test_a_session_pooler_url_becomes_libpq_variables(monkeypatch, capsys):
    url = f"postgresql://postgres.abcdef:{ESCAPED_LOGIN}@aws-0-eu-west-2.pooler.supabase.com:5432/postgres?sslmode=require"

    status, out, err = _run(monkeypatch, capsys, url)

    assert status == script.EXIT_OK
    assert err == ""
    assert out.splitlines() == [
        "PGDATABASE=postgres",
        "PGHOST=aws-0-eu-west-2.pooler.supabase.com",
        "PGPASSWORD=s3cr#t-pw",
        "PGPORT=5432",
        "PGSSLMODE=require",
        "PGUSER=postgres.abcdef",
    ]


def test_percent_encoding_and_an_ipv6_host_mean_what_they_mean_to_libpq(monkeypatch, capsys):
    url = "postgres://u%40x:p%40ss%3Aw%2Frd@[::1]:5433/db?connect_timeout=10&application_name=f1ai-migrate"

    status, out, _ = _run(monkeypatch, capsys, url)

    assert status == script.EXIT_OK
    assert set(out.splitlines()) == {
        "PGAPPNAME=f1ai-migrate",
        "PGCONNECT_TIMEOUT=10",
        "PGDATABASE=db",
        "PGHOST=::1",
        "PGPASSWORD=p@ss:w/rd",
        "PGPORT=5433",
        "PGUSER=u@x",
    }


def test_a_key_value_connection_string_works_too(monkeypatch, capsys):
    status, out, _ = _run(monkeypatch, capsys, "host=db.internal user=f1ai password=pw dbname=f1ai")

    assert status == script.EXIT_OK
    assert out.splitlines() == ["PGDATABASE=f1ai", "PGHOST=db.internal", "PGPASSWORD=pw", "PGUSER=f1ai"]


@pytest.mark.parametrize("url", [None, "", "   "])
def test_an_unset_or_empty_variable_is_refused(monkeypatch, capsys, url):
    status, out, err = _run(monkeypatch, capsys, url)

    assert status == script.EXIT_REFUSED
    assert out == ""
    assert "SOURCE_DATABASE_URL is not set" in err


def test_a_url_libpq_cannot_parse_is_refused_without_quoting_it(monkeypatch, capsys):
    """libpq's message here would be: unexpected spaces found in "pa ss" …"""
    status, out, err = _run(monkeypatch, capsys, "postgresql://u:pa ss@host/db")

    assert status == script.EXIT_REFUSED
    assert out == ""
    assert "not a connection URL libpq can read" in err
    assert "pa ss" not in err


def test_a_parameter_without_an_environment_variable_is_refused_by_name(monkeypatch, capsys):
    status, out, err = _run(monkeypatch, capsys, f"postgresql://u:{ESCAPED_LOGIN}@host/db?keepalives=1")

    assert status == script.EXIT_REFUSED
    assert out == ""
    assert "keepalives" in err
    assert "s3cr" not in err


def test_a_value_with_a_line_break_is_refused(monkeypatch, capsys):
    status, out, err = _run(monkeypatch, capsys, "postgresql://u:a%0Ab@host/db")

    assert status == script.EXIT_REFUSED
    assert out == ""
    assert "password" in err
    assert "line break" in err


def test_a_url_without_a_host_is_refused(monkeypatch, capsys):
    """pg_dump runs in a container, where libpq's default Unix socket is nobody's server."""
    status, out, err = _run(monkeypatch, capsys, "postgresql:///postgres")

    assert status == script.EXIT_REFUSED
    assert out == ""
    assert "names no host" in err


@pytest.mark.parametrize("name", ["postgresql://u:pw@host/db", "lower_case", "1STARTS_WITH_DIGIT", "HAS-DASH"])
def test_the_argument_must_be_a_variable_name_not_a_url(capsys, name):
    with pytest.raises(SystemExit) as exc:
        script.main([name])

    assert exc.value.code == 2
    assert "pw" not in capsys.readouterr().err
