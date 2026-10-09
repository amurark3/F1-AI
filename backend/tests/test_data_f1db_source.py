"""Tests for app.data.f1db_source — acquisition of the local f1db SQLite dump.

Every F1 history query in the backend funnels through ``connect()``. If this
module resolves the wrong release, writes something that is not a database, or
hands out a *writable* connection, every downstream feature is silently wrong
and the on-disk dataset can be mutated by a stray query.

The risks covered here: the REST API fallback for release lookup degrading to
"unknown" rather than raising, the zip extraction refusing an archive with no
``.db`` member instead of writing garbage, download-on-first-use, and the
connection genuinely being read-only. Release selection, the redirect lookup,
throttling and the sync outcome are covered in ``test_f1db_source.py``.
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile

import pytest

from app.data import f1db_source


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    """Build an in-memory zip archive with the given member name -> payload."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class _StubResponse:
    """Stand-in for ``requests.Response`` covering only what the module uses."""

    def __init__(self, *, content: bytes = b"", payload: object = None, error: Exception | None = None):
        self.content = content
        self._payload = payload
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> object:
        return self._payload


def _stub_get(monkeypatch, response: _StubResponse) -> list[tuple[str, dict]]:
    """Replace ``requests.get`` and record ``(url, kwargs)`` for each call."""
    calls: list[tuple[str, dict]] = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(f1db_source.requests, "get", fake_get)
    return calls


# ---------------------------------------------------------------------------
# sqlite_url_for
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("version", ["v2026.10.0", "v2024.1.2"])
def test_sqlite_url_for_targets_the_release_zip_asset(version):
    assert f1db_source.sqlite_url_for(version) == (
        f"https://github.com/f1db/f1db/releases/download/{version}/f1db-sqlite.zip"
    )


# ---------------------------------------------------------------------------
# _latest_from_api — the backup release lookup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_api_lookup_returns_the_tag_reported_by_github(monkeypatch):
    calls = _stub_get(monkeypatch, _StubResponse(payload={"tag_name": "v2027.1.0"}))

    assert f1db_source._latest_from_api() == "v2027.1.0"
    url, kwargs = calls[0]
    assert url == f1db_source.F1DB_RELEASES_API
    assert kwargs["timeout"] == f1db_source.DOWNLOAD_TIMEOUT_SECONDS


@pytest.mark.unit
def test_the_api_lookup_omits_authorization_when_no_token_is_set(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = _stub_get(monkeypatch, _StubResponse(payload={"tag_name": "v2027.1.0"}))

    f1db_source._latest_from_api()

    assert "Authorization" not in calls[0][1]["headers"]


@pytest.mark.unit
def test_the_api_lookup_authenticates_when_a_github_token_is_set(monkeypatch):
    """CI sets GITHUB_TOKEN purely to lift the anonymous API rate limit."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    calls = _stub_get(monkeypatch, _StubResponse(payload={"tag_name": "v2027.1.0"}))

    f1db_source._latest_from_api()

    assert calls[0][1]["headers"]["Authorization"] == "Bearer ghp_secret"


@pytest.mark.unit
def test_a_failed_api_lookup_reports_unknown_rather_than_raising(monkeypatch, capsys):
    """Unknown is not the pinned version: the caller decides what to keep."""
    _stub_get(
        monkeypatch,
        _StubResponse(error=f1db_source.requests.HTTPError("503 Service Unavailable")),
    )

    assert f1db_source._latest_from_api() == ""
    assert "f1db.latest_api_failed" in capsys.readouterr().out


@pytest.mark.unit
def test_a_payload_with_no_tag_reports_unknown(monkeypatch):
    """A schema change on GitHub's side must degrade, not raise."""
    _stub_get(monkeypatch, _StubResponse(payload={}))

    assert f1db_source._latest_from_api() == ""


# ---------------------------------------------------------------------------
# refresh_f1db
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_refresh_f1db_extracts_the_database_member_and_creates_its_directory(tmp_path, monkeypatch):
    archive = _zip_bytes({"README.txt": b"notes", "f1db-sqlite/f1db.db": b"SQLite payload"})
    calls = _stub_get(monkeypatch, _StubResponse(content=archive))
    dest = tmp_path / "nested" / "f1db.db"

    result = f1db_source.refresh_f1db("v2027.1.0", dest=dest)

    assert result == dest
    assert dest.read_bytes() == b"SQLite payload"
    assert calls[0][0] == f1db_source.sqlite_url_for("v2027.1.0")
    # The release is stamped beside the database, so the next check can compare.
    assert (tmp_path / "nested" / "f1db.db.version").read_text().strip() == "v2027.1.0"


@pytest.mark.integration
def test_refresh_f1db_overwrites_an_existing_database(tmp_path, monkeypatch):
    dest = tmp_path / "f1db.db"
    dest.write_bytes(b"stale release")
    _stub_get(monkeypatch, _StubResponse(content=_zip_bytes({"f1db.db": b"fresh release"})))

    f1db_source.refresh_f1db("v2027.1.0", dest=dest)

    assert dest.read_bytes() == b"fresh release"


@pytest.mark.integration
def test_refresh_f1db_rejects_an_archive_with_no_database_member(tmp_path, monkeypatch):
    """Better a loud failure than leaving a half-written, non-SQLite file behind."""
    _stub_get(monkeypatch, _StubResponse(content=_zip_bytes({"LICENSE": b"MIT"})))
    dest = tmp_path / "f1db.db"

    with pytest.raises(ValueError, match=re.escape("No .db file found")):
        f1db_source.refresh_f1db("v2027.1.0", dest=dest)

    assert not dest.exists()


@pytest.mark.integration
def test_refresh_f1db_propagates_a_download_failure(tmp_path, monkeypatch):
    _stub_get(monkeypatch, _StubResponse(error=RuntimeError("404 Not Found")))

    dest = tmp_path / "f1db.db"

    with pytest.raises(RuntimeError, match="404 Not Found"):
        f1db_source.refresh_f1db("v2027.1.0", dest=dest)

    assert not (tmp_path / "f1db.db.version").exists(), "a failed download must not claim a release"


# ---------------------------------------------------------------------------
# ensure_db
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ensure_db_downloads_when_the_database_is_missing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "absent.db"
    monkeypatch.setattr(f1db_source, "DB_PATH", target)
    monkeypatch.setattr(f1db_source, "target_version", lambda: "v2027.1.0")
    downloads: list[str] = []
    monkeypatch.setattr(f1db_source, "refresh_f1db", lambda version, *a, **k: downloads.append(version))

    assert f1db_source.ensure_db() == target
    assert downloads == ["v2027.1.0"]
    assert "f1db.missing_downloading" in capsys.readouterr().out


@pytest.mark.unit
def test_ensure_db_does_not_re_download_an_existing_database(fake_f1db, monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("an existing f1db must never be re-downloaded")

    monkeypatch.setattr(f1db_source, "refresh_f1db", fail)

    assert f1db_source.ensure_db() == fake_f1db


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_connect_returns_rows_addressable_by_column_name(fake_f1db):
    with f1db_source.connect() as conn:
        row = conn.execute("SELECT id, full_name FROM driver WHERE id = 'max-verstappen'").fetchone()

    assert row["full_name"] == "Max Verstappen"


@pytest.mark.integration
def test_connect_opens_the_database_read_only(fake_f1db):
    """The dataset is a downloaded artefact — no code path may mutate it."""
    with f1db_source.connect() as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO season (year) VALUES (1899)")


@pytest.mark.unit
def test_db_path_honours_the_f1db_path_environment_variable(monkeypatch, reload_module):
    monkeypatch.setenv("F1DB_PATH", "/srv/data/custom-f1db.db")
    monkeypatch.setenv("F1DB_DOWNLOAD_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("F1DB_VERSION", "v2030.1.0")

    reloaded = reload_module("app.data.f1db_source")

    assert str(reloaded.DB_PATH) == "/srv/data/custom-f1db.db"
    assert str(reloaded.VERSION_PATH) == "/srv/data/custom-f1db.db.version", "the stamp lives beside the database"
    assert reloaded.DOWNLOAD_TIMEOUT_SECONDS == 7
    assert reloaded.F1DB_VERSION == "v2030.1.0"
