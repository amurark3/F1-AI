"""Tests for ``scripts.ingest_fia_documents``: its exit status and printed report."""

from __future__ import annotations

import os

import pytest

# `load_dotenv()` at the script's module scope repopulates the credentials
# conftest cleared. Restore the environment the moment the import returns.
_ENV_BEFORE_IMPORT = dict(os.environ)
from scripts import ingest_fia_documents as script  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_IMPORT)

from app.data.fia_documents.ingest import IngestReport  # noqa: E402
from app.data.fia_documents.listing import IngestError  # noqa: E402
from app.data.fia_documents.site import FetchError  # noqa: E402
from app.data.fia_documents.store import FiaStoreError  # noqa: E402

pytestmark = pytest.mark.unit


def report(**overrides) -> IngestReport:
    fields = {
        "year": 2026,
        "events_checked": ("Las Vegas Grand Prix",),
        "added": ("Doc 79 - Infringement - Car 81 - Causing a collision",),
        "failed": (),
    }
    return IngestReport(**{**fields, **overrides})


@pytest.fixture
def calls(monkeypatch):
    """Replace the ingest with one returning (or raising) ``outcome``; record its arguments."""

    def install(outcome):
        seen: list[tuple] = []

        def fake(year, fetcher, **kwargs):
            seen.append((year, kwargs))
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(script, "ingest_season", fake)
        return seen

    return install


def test_a_clean_run_prints_each_document_with_its_kind(calls, capsys):
    seen = calls(report(withdrawn=("Doc 13 - New PU Elements",), deferred=("Mexico City Grand Prix",)))

    assert script.main(["--year", "2026", "--all-events", "--max-new-events", "2"]) == script.EXIT_OK

    assert seen == [(2026, {"all_events": True, "max_new_events": 2})]
    out = capsys.readouterr().out
    assert "+ [penalty] Doc 79 - Infringement - Car 81 - Causing a collision" in out
    assert "- withdrawn by the FIA: Doc 13 - New PU Elements" in out
    assert "left for a later run (nothing collected yet): Mexico City Grand Prix" in out
    assert "0 request(s) to fia.com" in out


def test_unread_documents_exit_1_and_are_listed(calls, capsys):
    calls(report(events_checked=(), added=(), failed=("Doc 1: download failed",)))

    assert script.main([]) == script.EXIT_DOCUMENT_FAILURES

    out = capsys.readouterr().out
    assert "checked 0 event(s): -" in out
    assert "! Doc 1: download failed" in out


@pytest.mark.parametrize(
    "error", [FiaStoreError("store down"), IngestError("no 2026 season"), FetchError("GET index failed")]
)
def test_an_unreachable_store_or_site_exits_2(calls, capsys, error):
    calls(error)

    assert script.main([]) == script.EXIT_UNREACHABLE
    assert f"Ingest aborted: {error}" in capsys.readouterr().out


def test_require_database_refuses_before_fia_is_asked(calls, capsys, monkeypatch):
    seen = calls(report())
    monkeypatch.setattr(script, "database_problem", lambda: "DATABASE_URL is not set")

    assert script.main(["--require-database"]) == script.EXIT_NO_DATABASE

    assert "Ingest refused: DATABASE_URL is not set" in capsys.readouterr().out
    assert seen == []


def test_require_database_lets_a_usable_database_run(calls, monkeypatch):
    seen = calls(report())
    monkeypatch.setattr(script, "database_problem", lambda: None)

    assert script.main(["--require-database"]) == script.EXIT_OK
    assert len(seen) == 1
