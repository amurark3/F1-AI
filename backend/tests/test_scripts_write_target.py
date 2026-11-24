"""Tests for ``scripts.write_target`` — the guard before a script writes production.

Pinned properties:

* **Every run is logged**, dry run or apply, with its store and database.
* **A dry run and a file-store run always proceed**: nothing reaches production.
* **An apply against Postgres needs production's agreement**: it goes ahead only
  when production reports the same database, and is refused when production
  names another one or can't be asked.
"""

from __future__ import annotations

import pytest
import requests

from app.data.store import BACKEND_FILE, BACKEND_POSTGRES
from app.data.store_types import StoreHealth
from scripts import write_target

pytestmark = pytest.mark.unit


class _Store:
    def __init__(self, backend: str, database: str | None) -> None:
        self._health = StoreHealth(backend=backend, database=database)

    def health(self) -> StoreHealth:
        return self._health


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def run_log(monkeypatch, tmp_path):
    path = tmp_path / "logs" / "runs.log"
    monkeypatch.setattr(write_target, "RUN_LOG", path)
    return path


@pytest.fixture
def production(monkeypatch):
    """Answer production's /api/ready with ``state['payload']`` (an exception raises)."""
    state: dict = {"payload": {"store": {"database": "abc123"}}}

    def _get(url, timeout):
        state["url"] = url
        if isinstance(state["payload"], requests.RequestException):
            raise state["payload"]
        return _Response(state["payload"])

    monkeypatch.setattr(write_target.requests, "get", _get)
    return state


def _use(monkeypatch, backend: str, database: str | None) -> None:
    monkeypatch.setattr(write_target, "document_store", _Store(backend, database))


def test_an_apply_on_production_s_own_database_proceeds_and_is_logged(monkeypatch, run_log, production, capsys):
    _use(monkeypatch, BACKEND_POSTGRES, "abc123")

    assert write_target.check_write_target("regrade_actuals", apply=True) is True
    assert production["url"].endswith("/api/ready")
    line = run_log.read_text().strip()
    assert line.endswith("regrade_actuals apply store=postgres database=abc123")
    assert "target: postgres database abc123" in capsys.readouterr().out


def test_an_apply_on_another_database_is_refused(monkeypatch, run_log, production, capsys):
    _use(monkeypatch, BACKEND_POSTGRES, "other99")

    assert write_target.check_write_target("regrade_actuals", apply=True) is False
    assert "production uses abc123; refusing to write" in capsys.readouterr().out


@pytest.mark.parametrize(
    "payload",
    [
        requests.ConnectionError("down"),
        ValueError("not json"),
        {"store": {}},
        ["not", "a", "dict"],
    ],
)
def test_an_apply_is_refused_when_production_cannot_say_which_database_it_uses(
    monkeypatch, run_log, production, capsys, payload
):
    production["payload"] = payload
    _use(monkeypatch, BACKEND_POSTGRES, "abc123")

    assert write_target.check_write_target("backfill_predictions", apply=True) is False
    assert "did not report production's database" in capsys.readouterr().out


def test_a_dry_run_never_asks_production(monkeypatch, run_log, capsys):
    monkeypatch.setattr(write_target.requests, "get", lambda *_a, **_k: pytest.fail("a dry run must not ask"))
    _use(monkeypatch, BACKEND_POSTGRES, "other99")

    assert write_target.check_write_target("import_snapshots", apply=False) is True
    assert "import_snapshots dry-run store=postgres database=other99" in run_log.read_text()


def test_a_file_store_apply_writes_local_files_and_is_never_refused(monkeypatch, run_log):
    monkeypatch.setattr(write_target.requests, "get", lambda *_a, **_k: pytest.fail("files need no check"))
    _use(monkeypatch, BACKEND_FILE, None)

    assert write_target.check_write_target("backfill_logic_version", apply=True) is True
    assert "store=file database=-" in run_log.read_text()


def test_runs_append_to_the_log(monkeypatch, run_log, production):
    _use(monkeypatch, BACKEND_POSTGRES, "abc123")

    write_target.check_write_target("regrade_actuals", apply=False)
    write_target.check_write_target("regrade_actuals", apply=True)

    assert len(run_log.read_text().splitlines()) == 2


# ---------------------------------------------------------------------------
# Every guarded script stops when the guard refuses
# ---------------------------------------------------------------------------


def _refusing_guard(monkeypatch, module) -> list[tuple]:
    asked: list[tuple] = []

    def _refuse(script, *, apply):
        asked.append((script, apply))
        return False

    monkeypatch.setattr(module, "check_write_target", _refuse)
    monkeypatch.setattr(module.document_store, "write", lambda *_a, **_k: pytest.fail("a refused run must not write"))
    return asked


@pytest.mark.parametrize(
    ("module_name", "argv", "exit_code"),
    [
        ("backfill_predictions", ["--apply"], 1),
        ("backfill_logic_version", ["--apply"], 1),
        ("import_snapshots", ["harvested.json", "--apply"], 1),
    ],
)
def test_a_cli_script_stops_before_any_work_when_the_guard_refuses(monkeypatch, module_name, argv, exit_code):
    import importlib
    import sys

    module = importlib.import_module(f"scripts.{module_name}")
    asked = _refusing_guard(monkeypatch, module)
    monkeypatch.setattr(sys, "argv", [module_name, *argv])

    assert module.main() == exit_code
    assert asked == [(module_name, True)]


@pytest.mark.parametrize("module_name", ["regrade_actuals", "repair_graded_predictions"])
def test_a_history_script_stops_with_its_wrong_database_code_when_the_guard_refuses(monkeypatch, module_name):
    import importlib

    from scripts.repair_graded_predictions import EXIT_WRONG_DATABASE

    module = importlib.import_module(f"scripts.{module_name}")
    asked = _refusing_guard(monkeypatch, module)
    monkeypatch.setattr(module, "_target_problem", lambda _local: None)

    assert module.main(["--apply"]) == EXIT_WRONG_DATABASE
    assert asked == [(module_name, True)]
