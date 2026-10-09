"""Tests for app.utils.fastf1_cache — corrupted-cache recovery around FastF1.

FastF1 caches HTTP responses in SQLite. A process killed mid-write leaves a
malformed database that then crashes *unrelated* requests, so this module
quarantines the bad file and lets FastF1 rebuild it. The cache is disposable —
losing it costs a re-download, keeping it costs an outage.

The module patches ``fastf1.get_session`` / ``fastf1.get_event_schedule`` at
import-installed-hook time and tracks that with process globals, so every test
here restores both the globals and the FastF1 attributes.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import fastf1
import pytest

from app.utils import fastf1_cache


@pytest.fixture(autouse=True)
def _restore_globals_and_fastf1():
    """Undo the module's global monkeypatching of the fastf1 package."""
    saved = (
        fastf1_cache._PATCHED,
        fastf1_cache._ACTIVE_CACHE_DIR,
        fastf1_cache._ORIGINAL_GET_SESSION,
        fastf1_cache._ORIGINAL_GET_EVENT_SCHEDULE,
        fastf1.get_session,
        fastf1.get_event_schedule,
    )
    fastf1_cache._PATCHED = False
    fastf1_cache._ORIGINAL_GET_SESSION = None
    fastf1_cache._ORIGINAL_GET_EVENT_SCHEDULE = None
    yield
    (
        fastf1_cache._PATCHED,
        fastf1_cache._ACTIVE_CACHE_DIR,
        fastf1_cache._ORIGINAL_GET_SESSION,
        fastf1_cache._ORIGINAL_GET_EVENT_SCHEDULE,
        fastf1.get_session,
        fastf1.get_event_schedule,
    ) = saved


@pytest.fixture
def stub_cache(monkeypatch):
    """Record calls to ``fastf1.Cache.enable_cache`` instead of touching disk."""
    calls: list[str] = []

    def enable_cache(path, *args, **kwargs):
        calls.append(str(path))

    monkeypatch.setattr(fastf1.Cache, "enable_cache", enable_cache)
    return calls


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    """Context-managed stand-in for ``sqlite3.Connection``."""

    def __init__(self, row=None, error=None):
        self._row = row
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _sql):
        if self._error is not None:
            raise self._error
        return _FakeCursor(self._row)


def _stub_quick_check(monkeypatch, *, row=None, error=None):
    monkeypatch.setattr(sqlite3, "connect", lambda *_a, **_k: _FakeConnection(row=row, error=error))


# ---------------------------------------------------------------------------
# enable_fastf1_cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enable_creates_the_cache_directory(tmp_path, stub_cache):
    target = tmp_path / "nested" / "f1_cache"

    result = fastf1_cache.enable_fastf1_cache(target)

    assert result == target
    assert target.is_dir()
    assert stub_cache == [str(target)]


@pytest.mark.unit
def test_enable_accepts_a_string_path(tmp_path, stub_cache):
    result = fastf1_cache.enable_fastf1_cache(str(tmp_path / "cache"))

    assert isinstance(result, Path)


@pytest.mark.unit
def test_enable_quarantines_and_retries_when_enable_cache_rejects_the_db(tmp_path, monkeypatch):
    """A malformed DB that only surfaces inside ``enable_cache`` still recovers."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    db = cache_dir / fastf1_cache.FASTF1_HTTP_CACHE
    db.write_bytes(b"not a database")
    _stub_quick_check(monkeypatch, row=("ok",))

    attempts: list[str] = []

    def flaky_enable(path, *args, **kwargs):
        attempts.append(str(path))
        if len(attempts) == 1:
            raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(fastf1.Cache, "enable_cache", flaky_enable)

    fastf1_cache.enable_fastf1_cache(cache_dir)

    assert len(attempts) == 2, "must retry after quarantining the bad file"
    assert not db.exists(), "the malformed db must be moved aside"
    assert list(cache_dir.glob("*.corrupt-*"))


# ---------------------------------------------------------------------------
# _repair_if_malformed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_repair_is_a_no_op_when_no_cache_db_exists(tmp_path):
    fastf1_cache._repair_if_malformed(tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_repair_keeps_a_healthy_database(tmp_path, monkeypatch):
    db = tmp_path / fastf1_cache.FASTF1_HTTP_CACHE
    db.write_bytes(b"healthy")
    _stub_quick_check(monkeypatch, row=("ok",))

    fastf1_cache._repair_if_malformed(tmp_path)

    assert db.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "row",
    [("*** in database main ***\nPage 3 is never used",), None],
    ids=["quick_check-reports-damage", "quick_check-returns-nothing"],
)
def test_repair_quarantines_when_quick_check_does_not_say_ok(tmp_path, monkeypatch, row):
    db = tmp_path / fastf1_cache.FASTF1_HTTP_CACHE
    db.write_bytes(b"damaged")
    _stub_quick_check(monkeypatch, row=row)

    fastf1_cache._repair_if_malformed(tmp_path)

    assert not db.exists()
    assert len(list(tmp_path.glob("*.corrupt-*"))) == 1


@pytest.mark.unit
def test_repair_quarantines_a_genuinely_corrupt_sqlite_file(tmp_path):
    """End-to-end against real sqlite3 — no stubbing of the driver."""
    db = tmp_path / fastf1_cache.FASTF1_HTTP_CACHE
    # A valid SQLite header followed by garbage: opens fine, fails quick_check.
    db.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)

    fastf1_cache._repair_if_malformed(tmp_path)

    assert not db.exists()


# ---------------------------------------------------------------------------
# _quarantine_cache_files
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_quarantine_moves_every_cache_sidecar_file(tmp_path):
    base = tmp_path / fastf1_cache.FASTF1_HTTP_CACHE
    base.write_text("main")
    (tmp_path / f"{fastf1_cache.FASTF1_HTTP_CACHE}-wal").write_text("wal")
    (tmp_path / f"{fastf1_cache.FASTF1_HTTP_CACHE}-shm").write_text("shm")

    fastf1_cache._quarantine_cache_files(tmp_path)

    assert len(list(tmp_path.glob("*.corrupt-*"))) == 3
    assert not base.exists()


@pytest.mark.unit
def test_quarantine_skips_directories_matching_the_glob(tmp_path):
    directory = tmp_path / f"{fastf1_cache.FASTF1_HTTP_CACHE}-dir"
    directory.mkdir()

    fastf1_cache._quarantine_cache_files(tmp_path)

    assert directory.is_dir(), "a directory must not be renamed as a corrupt file"


@pytest.mark.unit
def test_quarantine_survives_an_unrenameable_file(tmp_path, monkeypatch):
    """A read-only volume must not turn cache recovery into a hard failure."""
    stuck = tmp_path / fastf1_cache.FASTF1_HTTP_CACHE
    stuck.write_text("locked")

    def refuse(self, _target):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(Path, "replace", refuse)

    fastf1_cache._quarantine_cache_files(tmp_path)  # must not raise

    assert stuck.exists()


# ---------------------------------------------------------------------------
# _with_cache_repair
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_cache_repair_passes_results_straight_through(stub_cache):
    assert fastf1_cache._with_cache_repair(lambda: "schedule", "label") == "schedule"
    assert stub_cache == [], "a healthy call must not touch the cache"


@pytest.mark.unit
def test_with_cache_repair_retries_once_after_quarantining(tmp_path, stub_cache, monkeypatch):
    monkeypatch.setattr(fastf1_cache, "_ACTIVE_CACHE_DIR", tmp_path)
    calls: list[int] = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.DatabaseError("database disk image is malformed")
        return "recovered"

    assert fastf1_cache._with_cache_repair(flaky, "get_session") == "recovered"
    assert len(calls) == 2
    assert stub_cache == [str(tmp_path)]


@pytest.mark.unit
def test_with_cache_repair_propagates_a_second_failure(tmp_path, stub_cache, monkeypatch):
    """If the retry fails too, the error is real — it must not be swallowed."""
    monkeypatch.setattr(fastf1_cache, "_ACTIVE_CACHE_DIR", tmp_path)

    def always_broken():
        raise sqlite3.DatabaseError("still malformed")

    with pytest.raises(sqlite3.DatabaseError):
        fastf1_cache._with_cache_repair(always_broken, "get_session")


@pytest.mark.unit
def test_with_cache_repair_does_not_catch_unrelated_errors(stub_cache):
    def network_down():
        raise ConnectionError("ergast unreachable")

    with pytest.raises(ConnectionError):
        fastf1_cache._with_cache_repair(network_down, "get_session")


# ---------------------------------------------------------------------------
# _install_recovery_hooks and the patched loaders
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, name="session"):
        self.name = name
        self.loaded_with: list[tuple] = []

    def load(self, *args, **kwargs):
        self.loaded_with.append((args, kwargs))
        return f"{self.name}-loaded"


@pytest.mark.unit
def test_hooks_wrap_the_public_fastf1_loaders(tmp_path, monkeypatch):
    original_schedule = lambda year: f"schedule-{year}"  # noqa: E731
    monkeypatch.setattr(fastf1, "get_event_schedule", original_schedule)
    monkeypatch.setattr(fastf1, "get_session", lambda *a, **k: _FakeSession())

    fastf1_cache._install_recovery_hooks(tmp_path)

    assert fastf1.get_event_schedule is not original_schedule
    assert fastf1_cache._PATCHED is True
    assert tmp_path == fastf1_cache._ACTIVE_CACHE_DIR
    assert fastf1.get_event_schedule(2026) == "schedule-2026"


@pytest.mark.unit
def test_hooks_are_installed_once_but_retarget_the_cache_dir(tmp_path, monkeypatch):
    """Re-enabling with a new directory must not double-wrap the loaders."""
    monkeypatch.setattr(fastf1, "get_event_schedule", lambda *a, **k: "first")
    monkeypatch.setattr(fastf1, "get_session", lambda *a, **k: _FakeSession())

    fastf1_cache._install_recovery_hooks(tmp_path)
    wrapper = fastf1.get_event_schedule

    second_dir = tmp_path / "other"
    fastf1_cache._install_recovery_hooks(second_dir)

    assert fastf1.get_event_schedule is wrapper, "must not wrap the wrapper"
    assert second_dir == fastf1_cache._ACTIVE_CACHE_DIR


@pytest.mark.unit
def test_patched_get_session_returns_a_session_with_a_guarded_load(tmp_path, monkeypatch):
    monkeypatch.setattr(fastf1, "get_event_schedule", lambda *a, **k: "schedule")
    monkeypatch.setattr(fastf1, "get_session", lambda *a, **k: _FakeSession())

    fastf1_cache._install_recovery_hooks(tmp_path)
    session = fastf1.get_session(2026, 1, "R")

    assert session.load(telemetry=False) == "session-loaded"


@pytest.mark.unit
def test_patched_get_event_schedule_recovers_from_a_malformed_cache(tmp_path, stub_cache, monkeypatch):
    calls: list[int] = []

    def flaky_schedule(year):
        calls.append(year)
        if len(calls) == 1:
            raise sqlite3.DatabaseError("database disk image is malformed")
        return f"schedule-{year}"

    monkeypatch.setattr(fastf1, "get_event_schedule", flaky_schedule)
    monkeypatch.setattr(fastf1, "get_session", lambda *a, **k: _FakeSession())

    fastf1_cache._install_recovery_hooks(tmp_path)

    assert fastf1.get_event_schedule(2026) == "schedule-2026"
    assert stub_cache == [str(tmp_path)]


# ---------------------------------------------------------------------------
# _patch_session_load
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_session_load_passes_arguments_through(tmp_path):
    session = _FakeSession()

    fastf1_cache._patch_session_load(session, (2026, 1, "R"), {})

    assert session.load(laps=True, telemetry=False) == "session-loaded"
    assert session.loaded_with == [((), {"laps": True, "telemetry": False})]


@pytest.mark.unit
def test_session_load_rebuilds_the_session_after_cache_corruption(tmp_path, stub_cache, monkeypatch):
    """The recovered session's state is copied onto the object the caller holds."""
    monkeypatch.setattr(fastf1_cache, "_ACTIVE_CACHE_DIR", tmp_path)
    replacement = _FakeSession("replacement")
    replacement.laps = "fresh laps"
    monkeypatch.setattr(fastf1_cache, "_ORIGINAL_GET_SESSION", lambda *a, **k: replacement)

    broken = _FakeSession("broken")

    def corrupt_load(*_args, **_kwargs):
        raise sqlite3.DatabaseError("database disk image is malformed")

    broken.load = corrupt_load

    fastf1_cache._patch_session_load(broken, (2026, 1, "R"), {})
    result = broken.load(laps=True)

    assert result == "replacement-loaded"
    assert broken.laps == "fresh laps", "caller's handle must see the recovered data"
    assert stub_cache == [str(tmp_path)]


@pytest.mark.unit
def test_session_load_reraises_when_no_original_loader_is_recorded(tmp_path, stub_cache, monkeypatch):
    """Without the original ``get_session`` there is nothing to rebuild from."""
    monkeypatch.setattr(fastf1_cache, "_ACTIVE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(fastf1_cache, "_ORIGINAL_GET_SESSION", None)

    session = _FakeSession()

    def corrupt_load(*_args, **_kwargs):
        raise sqlite3.DatabaseError("database disk image is malformed")

    session.load = corrupt_load
    fastf1_cache._patch_session_load(session, (2026, 1, "R"), {})

    with pytest.raises(sqlite3.DatabaseError):
        session.load()


@pytest.mark.unit
def test_session_load_patch_failure_is_logged_not_raised(capsys):
    """Some FastF1 objects use ``__slots__``; failing to patch must not break the load."""

    class _SlottedSession:
        __slots__ = ()

        def load(self, *_args, **_kwargs):
            return "loaded"

    session = _SlottedSession()

    fastf1_cache._patch_session_load(session, (2026,), {})  # must not raise

    assert "session_load_patch_failed" in capsys.readouterr().out


@pytest.mark.unit
def test_default_cache_dir_sits_under_the_backend_root():
    assert fastf1_cache.DEFAULT_CACHE_DIR.name == "f1_cache"
    assert fastf1_cache.DEFAULT_CACHE_DIR.parent == fastf1_cache.BACKEND_ROOT
