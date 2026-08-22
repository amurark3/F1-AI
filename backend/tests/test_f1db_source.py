"""Tests for f1db dataset freshness (app.data.f1db_source).

The behaviour under test: the serving path tracks the newest f1db release on its
own. The regression that motivated this module left production on a release cut
before the Hungarian GP — the standings page served round-10 points for four
weeks while every cold start faithfully re-downloaded the same stale snapshot,
because the only code that ever asked GitHub for a newer release lived in the
weekly model-retraining job and threw its download away on a CI runner.
"""

import io
import zipfile

import pytest

from app.data import f1db_source


def zip_bytes(payload: bytes = b"sqlite-dataset") -> bytes:
    """Build a zip archive shaped like an f1db release asset."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("f1db.db", payload)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes = b"", payload: dict | None = None):
        self.content = content
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Point the module at a scratch dataset path with no throttle carry-over."""
    db_path = tmp_path / "f1db.db"
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    monkeypatch.setattr(f1db_source, "VERSION_PATH", tmp_path / "f1db.db.version")
    monkeypatch.setattr(f1db_source, "F1DB_VERSION", "")
    monkeypatch.setattr(f1db_source, "_last_check_at", None)
    return db_path


def install(dataset_path, version: str, payload: bytes = b"old-dataset") -> None:
    """Put a dataset of ``version`` on disk, as a previous refresh would leave it."""
    dataset_path.write_bytes(payload)
    f1db_source.VERSION_PATH.write_text(version)


def fake_github(monkeypatch, *, latest: str | None = None, asset: bytes | None = None):
    """Stub requests.get for both the releases API and the asset download.

    ``latest=None`` makes the API call fail, standing in for GitHub being
    unreachable or rate-limited.
    """
    calls: list[str] = []

    def _get(url, **_kwargs):
        calls.append(url)
        if url == f1db_source.F1DB_RELEASES_API:
            if latest is None:
                raise RuntimeError("github unreachable")
            return FakeResponse(payload={"tag_name": latest})
        if asset is None:
            raise RuntimeError("download failed")
        return FakeResponse(content=asset)

    monkeypatch.setattr(f1db_source.requests, "get", _get)
    return calls


# ---------------------------------------------------------------------------
# Which release should we be on?
# ---------------------------------------------------------------------------


def test_installed_version_is_none_without_a_dataset(dataset):
    assert f1db_source.installed_version() is None


def test_installed_version_is_none_when_the_stamp_is_missing(dataset):
    dataset.write_bytes(b"dataset from before version stamps existed")

    assert f1db_source.installed_version() is None


def test_installed_version_reads_the_stamp(dataset):
    install(dataset, "v2026.11.0")

    assert f1db_source.installed_version() == "v2026.11.0"


def test_target_is_the_newest_release_by_default(dataset, monkeypatch):
    fake_github(monkeypatch, latest="v2026.12.0")

    assert f1db_source.target_version() == "v2026.12.0"


def test_pin_overrides_the_newest_release(dataset, monkeypatch):
    monkeypatch.setattr(f1db_source, "F1DB_VERSION", "v2026.9.0")
    calls = fake_github(monkeypatch, latest="v2026.12.0")

    assert f1db_source.target_version() == "v2026.9.0"
    assert calls == [], "a pinned dataset has no reason to ask GitHub anything"


def test_unreachable_github_keeps_the_installed_release(dataset, monkeypatch):
    install(dataset, "v2026.11.0")
    fake_github(monkeypatch, latest=None)

    assert f1db_source.target_version() == "v2026.11.0"


def test_unreachable_github_with_no_dataset_uses_the_fallback(dataset, monkeypatch):
    fake_github(monkeypatch, latest=None)

    assert f1db_source.target_version() == f1db_source.FALLBACK_F1DB_VERSION


# ---------------------------------------------------------------------------
# Syncing
# ---------------------------------------------------------------------------


def test_sync_downloads_when_there_is_no_dataset(dataset, monkeypatch):
    fake_github(monkeypatch, latest="v2026.12.0", asset=zip_bytes(b"fresh"))

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is True
    assert outcome.version == "v2026.12.0"
    assert dataset.read_bytes() == b"fresh"
    assert f1db_source.installed_version() == "v2026.12.0"


def test_sync_replaces_a_dataset_from_an_older_release(dataset, monkeypatch):
    install(dataset, "v2026.10.0")
    fake_github(monkeypatch, latest="v2026.11.0", asset=zip_bytes(b"with-hungary"))

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is True
    assert dataset.read_bytes() == b"with-hungary"
    assert f1db_source.installed_version() == "v2026.11.0"


def test_sync_is_a_no_op_when_already_on_the_newest_release(dataset, monkeypatch):
    install(dataset, "v2026.11.0", payload=b"untouched")
    fake_github(monkeypatch, latest="v2026.11.0")  # no asset — must not download

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is False
    assert dataset.read_bytes() == b"untouched"


def test_sync_adopts_an_unstamped_dataset_once(dataset, monkeypatch):
    dataset.write_bytes(b"dataset from before version stamps existed")
    fake_github(monkeypatch, latest="v2026.11.0", asset=zip_bytes(b"stamped"))

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is True
    assert f1db_source.installed_version() == "v2026.11.0"


def test_a_failed_download_keeps_the_previous_dataset_serving(dataset, monkeypatch):
    install(dataset, "v2026.10.0", payload=b"stale-but-usable")
    fake_github(monkeypatch, latest="v2026.11.0", asset=None)

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is False
    assert dataset.read_bytes() == b"stale-but-usable"
    assert f1db_source.installed_version() == "v2026.10.0"
    assert "download failed" in outcome.reason


def test_a_failed_download_with_no_dataset_raises(dataset, monkeypatch):
    fake_github(monkeypatch, latest="v2026.11.0", asset=None)

    with pytest.raises(RuntimeError):
        f1db_source.sync_to_latest()


def test_repeat_syncs_are_throttled(dataset, monkeypatch):
    install(dataset, "v2026.11.0")
    calls = fake_github(monkeypatch, latest="v2026.11.0")

    f1db_source.sync_to_latest()
    f1db_source.sync_to_latest()

    assert len(calls) == 1, "the second call is inside the check interval"


def test_forcing_a_sync_bypasses_the_throttle(dataset, monkeypatch):
    install(dataset, "v2026.11.0")
    calls = fake_github(monkeypatch, latest="v2026.11.0")

    f1db_source.sync_to_latest()
    f1db_source.sync_to_latest(force=True)

    assert len(calls) == 2


def test_the_first_sync_of_a_process_is_never_throttled(dataset, monkeypatch):
    """Uptime is not a release check.

    ``time.monotonic()`` counts from system boot, so on a machine that booted
    less than the check interval ago every reading is small. A throttle that
    treats "no check yet" as a timestamp of zero therefore concludes the process
    just checked and skips the boot sync — silently, and for the first hour of
    the container's life. CI runners boot seconds before the suite runs, which is
    where this first showed up; a Render container restarting onto a persistent
    disk that already holds a dataset is the same shape, and there it serves a
    stale release instead.
    """
    monkeypatch.setattr(f1db_source.time, "monotonic", lambda: 5.0)
    install(dataset, "v2026.10.0")
    calls = fake_github(
        monkeypatch, latest="v2026.11.0", asset=zip_bytes(b"with-hungary")
    )

    outcome = f1db_source.sync_to_latest()

    assert outcome.updated is True, "a fresh process must check before it throttles"
    assert f1db_source.F1DB_RELEASES_API in calls


def test_a_missing_dataset_is_never_throttled(dataset, monkeypatch):
    """Throttling a server that has no data at all would strand it."""
    fake_github(monkeypatch, latest="v2026.11.0", asset=zip_bytes())
    monkeypatch.setattr(f1db_source, "_last_check_at", 1e9)

    assert f1db_source.sync_to_latest().updated is True


# ---------------------------------------------------------------------------
# Refresh mechanics
# ---------------------------------------------------------------------------


def test_refresh_leaves_no_temporary_files_behind(dataset, monkeypatch):
    fake_github(monkeypatch, latest="v2026.11.0", asset=zip_bytes())

    f1db_source.sync_to_latest()

    assert sorted(path.name for path in dataset.parent.iterdir()) == [
        "f1db.db",
        "f1db.db.version",
    ]


def test_a_failed_refresh_leaves_no_temporary_files_behind(dataset, monkeypatch):
    install(dataset, "v2026.10.0")
    fake_github(monkeypatch, latest="v2026.11.0", asset=None)

    f1db_source.sync_to_latest()

    assert sorted(path.name for path in dataset.parent.iterdir()) == [
        "f1db.db",
        "f1db.db.version",
    ]


def test_refresh_rejects_an_archive_with_no_database(dataset, monkeypatch):
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("README.md", "no database here")
    fake_github(monkeypatch, latest="v2026.11.0", asset=empty.getvalue())

    with pytest.raises(ValueError):
        f1db_source.refresh_f1db("v2026.11.0")

    assert not dataset.exists()


def test_ensure_db_downloads_only_when_the_file_is_missing(dataset, monkeypatch):
    install(dataset, "v2026.10.0")
    calls = fake_github(monkeypatch, latest="v2026.12.0")

    assert f1db_source.ensure_db() == dataset
    assert calls == [], "ensure_db is on the connect() hot path — no network there"


def test_ensure_db_fetches_a_missing_dataset(dataset, monkeypatch):
    fake_github(monkeypatch, latest="v2026.11.0", asset=zip_bytes(b"fetched"))

    assert f1db_source.ensure_db().read_bytes() == b"fetched"
