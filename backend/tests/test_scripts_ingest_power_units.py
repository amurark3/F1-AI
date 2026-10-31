"""Tests for ``scripts.ingest_power_units`` — the scheduled FIA collection job.

What is pinned is the job's contract with its scheduler: the exit status says
whether to look (0 fine, 1 some documents unread, 2 nothing written at all,
3 no usable database),
and the printed report says what to look at.
"""

from __future__ import annotations

import os

import pytest

# `load_dotenv()` at the script's module scope repopulates the credentials
# conftest cleared. Restore the environment the moment the import returns.
_ENV_BEFORE_IMPORT = dict(os.environ)
from scripts import ingest_power_units as script  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_IMPORT)

from app.data.power_units.fia_site import FetchError  # noqa: E402
from app.data.power_units.ingest import IngestError, IngestReport  # noqa: E402
from app.data.power_units.sources import SourcesUnavailableError  # noqa: E402
from app.data.power_units.status import (  # noqa: E402
    OUTCOME_ABORTED,
    OUTCOME_DOCUMENT_FAILURES,
    OUTCOME_OK,
    OUTCOME_WRITE_FAILED,
)
from app.data.store import (  # noqa: E402
    BACKEND_FILE,
    BACKEND_POSTGRES,
    HOST_OTHER,
    HOST_SUPABASE_DIRECT,
    HOST_SUPABASE_POOLER,
)
from app.data.store_types import StoreHealth, WriteResult  # noqa: E402


def report(**overrides) -> IngestReport:
    fields = {
        "year": 2026,
        "events_checked": ("United States Grand Prix",),
        "added": ("Doc 15 - Infringement - Car 5 - PU elements",),
        "failed": (),
        "written": True,
    }
    return IngestReport(**{**fields, **overrides})


@pytest.fixture(autouse=True)
def recorded(monkeypatch):
    """Every status the script records, as ``(status, changed)``."""
    statuses: list[tuple] = []

    def record(status, *, changed):
        statuses.append((status, changed))
        return WriteResult()

    monkeypatch.setattr(script, "record_status", record)
    return statuses


@pytest.fixture
def calls(monkeypatch):
    seen: list[dict] = []

    def install(result):
        def fake(year, fetcher, *, all_events):
            seen.append({"year": year, "fetcher": fetcher, "all_events": all_events})
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(script, "ingest_season", fake)
        return seen

    return install


def test_a_clean_run_exits_zero_and_lists_what_it_added(calls, capsys, recorded):
    seen = calls(report(withdrawn=("Doc 44 - Infringement",), allowances_changed=("ICE",)))
    assert script.main(["--year", "2026"]) == script.EXIT_OK

    out = capsys.readouterr().out
    assert "2026: checked 1 event(s): United States Grand Prix" in out
    assert "+ Doc 15 - Infringement - Car 5 - PU elements" in out
    assert "store updated" in out
    assert "- withdrawn by the FIA: Doc 44 - Infringement" in out
    assert "allowances updated from the FIA's reports: ICE" in out
    assert "0 request(s) to fia.com" in out
    assert seen[0]["year"] == 2026
    assert seen[0]["all_events"] is False
    status, changed = recorded[0]
    assert (status.outcome, status.added, status.withdrawn, changed) == (OUTCOME_OK, 1, 1, True)


def test_options_reach_the_job(calls, tmp_path):
    seen = calls(report(added=(), written=False))
    script.main(["--year", "2025", "--all-events", "--cache-dir", str(tmp_path)])
    assert seen[0]["year"] == 2025
    assert seen[0]["all_events"] is True
    assert seen[0]["fetcher"]._cache_dir == tmp_path


def test_the_year_defaults_to_this_season(calls):
    seen = calls(report())
    script.main([])
    assert seen[0]["year"] >= 2026


def test_unread_documents_exit_one_and_are_listed(calls, capsys, recorded):
    calls(report(failed=("Doc 9 - PU elements: download failed: 503",)))
    assert script.main([]) == script.EXIT_DOCUMENT_FAILURES
    assert "! Doc 9 - PU elements: download failed: 503" in capsys.readouterr().out
    assert recorded[0][0].outcome == OUTCOME_DOCUMENT_FAILURES
    assert recorded[0][0].failed == 1


def test_a_failed_write_exits_one_and_says_so(calls, capsys, recorded):
    calls(report(written=False, write_error="disk full"))
    assert script.main([]) == script.EXIT_DOCUMENT_FAILURES
    assert "store write FAILED: disk full" in capsys.readouterr().out
    assert recorded[0][0].outcome == OUTCOME_WRITE_FAILED
    assert recorded[0][1] is False


def test_a_status_that_cannot_be_recorded_is_reported(calls, capsys, monkeypatch):
    calls(report())
    monkeypatch.setattr(script, "record_status", lambda status, *, changed: WriteResult(ok=False, error="db down"))
    assert script.main([]) == script.EXIT_OK
    assert "WARNING: the run's status could not be recorded: db down" in capsys.readouterr().out


def test_a_quiet_run_says_nothing_changed(calls, capsys):
    calls(report(events_checked=(), added=(), written=False))
    assert script.main([]) == script.EXIT_OK
    out = capsys.readouterr().out
    assert "checked 0 event(s): -" in out
    assert "nothing new — store unchanged" in out


@pytest.mark.parametrize("failure", [IngestError("no 2026 season"), FetchError("GET index failed")])
def test_an_unreachable_site_exits_two_and_records_why(calls, capsys, recorded, failure):
    calls(failure)
    assert script.main([]) == script.EXIT_UNREACHABLE
    assert "Ingest aborted, nothing written" in capsys.readouterr().out
    status, changed = recorded[0]
    assert status.outcome == OUTCOME_ABORTED
    assert status.error == f"fia.com could not be read: {failure}"
    assert changed is False


def test_an_unreachable_store_exits_two_without_recording(calls, capsys, recorded):
    calls(SourcesUnavailableError("store down"))
    assert script.main([]) == script.EXIT_UNREACHABLE
    assert "store down" in capsys.readouterr().out
    assert recorded == []


# ---------------------------------------------------------------------------
# --require-database: the scheduled job must never write to a throwaway disk
# ---------------------------------------------------------------------------


def store_health(monkeypatch, health: StoreHealth) -> None:
    monkeypatch.setattr(script.document_store, "health", lambda: health)


@pytest.mark.parametrize(
    ("health", "message"),
    [
        (StoreHealth(backend=BACKEND_FILE), "DATABASE_URL is not set"),
        (StoreHealth(backend=BACKEND_POSTGRES, host_kind=HOST_SUPABASE_DIRECT), "IPv6-only"),
    ],
)
def test_require_database_refuses_a_store_the_job_would_lose(calls, capsys, monkeypatch, recorded, health, message):
    seen = calls(report())
    store_health(monkeypatch, health)
    assert script.main(["--require-database"]) == script.EXIT_NO_DATABASE

    assert message in capsys.readouterr().out
    assert seen == []  # fia.com was never asked
    assert recorded == []


@pytest.mark.parametrize("host_kind", [HOST_SUPABASE_POOLER, HOST_OTHER])
def test_require_database_lets_a_reachable_postgres_run(calls, monkeypatch, host_kind):
    seen = calls(report())
    store_health(monkeypatch, StoreHealth(backend=BACKEND_POSTGRES, host_kind=host_kind))
    assert script.main(["--require-database"]) == script.EXIT_OK
    assert len(seen) == 1


def test_without_the_flag_a_local_file_run_is_allowed(calls, monkeypatch):
    seen = calls(report())
    store_health(monkeypatch, StoreHealth(backend=BACKEND_FILE))
    assert script.main([]) == script.EXIT_OK
    assert len(seen) == 1
