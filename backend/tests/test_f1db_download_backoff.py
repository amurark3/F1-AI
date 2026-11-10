"""Tests for the f1db download backoff (app.data.f1db_source).

The regression: with no dataset on disk, every f1db read retried the GitHub
release download at once. During GitHub's 504s the API started 637 downloads in
about four minutes (2026-11-08) and 66 in a minute (2026-11-09), hammering
GitHub from our address while every attempt failed the same way.

The contract under test: after a failed download, no download starts until a
backoff window passes (60 s, doubling per consecutive failure, capped at 15
minutes, reset by a success), and a reader inside the window takes the
"f1db unavailable" path at once, with no network and no waiting.
"""

from __future__ import annotations

import io
import zipfile

import pytest
import requests

from app.data import canonical_names, f1db_source, identity
from app.services import readiness

RELEASE = "v2026.19.0"
DOWNLOAD_MARKER = "/releases/download/"


def _archive() -> bytes:
    """A zip shaped like an f1db release asset."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("f1db.db", b"sqlite-dataset")
    return buffer.getvalue()


class Clock:
    """A ``time.monotonic`` stand-in that moves only when the test says so."""

    def __init__(self, start: float = 10_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Response:
    def __init__(self, *, status_code: int = 200, content: bytes = b"", headers: dict | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Gateway Timeout")

    def json(self) -> dict:
        return {}


class GitHub:
    """The release page, the releases API and the asset download.

    ``down`` answers every request with a 504, as on 2026-11-08 and 2026-11-09.
    Every URL asked for is recorded, so a test can prove a read made no request.
    """

    def __init__(self) -> None:
        self.down = True
        self.requests: list[str] = []

    @property
    def downloads(self) -> int:
        return sum(DOWNLOAD_MARKER in url for url in self.requests)

    def head(self, url: str, **_kwargs) -> Response:
        self.requests.append(url)
        if self.down:
            return Response(status_code=504)
        return Response(status_code=302, headers={"Location": f"https://github.com/f1db/f1db/releases/tag/{RELEASE}"})

    def get(self, url: str, **_kwargs) -> Response:
        self.requests.append(url)
        if self.down:
            return Response(status_code=504)
        return Response(content=_archive())


@pytest.fixture
def github(tmp_path, monkeypatch) -> GitHub:
    """No dataset on disk, nothing pinned, and a GitHub that is down."""
    monkeypatch.setattr(f1db_source, "DB_PATH", tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "VERSION_PATH", tmp_path / "f1db.db.version")
    monkeypatch.setattr(f1db_source, "F1DB_VERSION", "")
    monkeypatch.setattr(f1db_source, "_last_check_at", None)
    monkeypatch.setattr(f1db_source, "_last_outcome", None)
    fake = GitHub()
    monkeypatch.setattr(f1db_source.requests, "head", fake.head)
    monkeypatch.setattr(f1db_source.requests, "get", fake.get)
    return fake


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(f1db_source.time, "monotonic", fake)
    return fake


def attempt_fails() -> None:
    """A read that downloads, and the download fails."""
    with pytest.raises(requests.HTTPError):
        f1db_source.ensure_db()


def read_is_refused() -> f1db_source.F1dbUnavailableError:
    """A read inside a window: refused without trying."""
    with pytest.raises(f1db_source.F1dbUnavailableError) as refused:
        f1db_source.ensure_db()
    return refused.value


# ---------------------------------------------------------------------------
# One attempt per window
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rapid_reads_after_a_failure_make_one_download_attempt_in_the_window(github, clock):
    attempt_fails()
    asked = list(github.requests)

    for _ in range(50):
        read_is_refused()
        clock.advance(1)

    assert github.downloads == 1
    assert github.requests == asked, "a refused read makes no request, release lookups included"


@pytest.mark.unit
def test_another_attempt_runs_once_the_window_passes(github, clock):
    attempt_fails()

    clock.advance(59.9)
    read_is_refused()
    clock.advance(0.1)
    attempt_fails()

    assert github.downloads == 2


@pytest.mark.unit
def test_consecutive_failures_double_the_window_up_to_15_minutes(github, clock):
    attempt_fails()

    for window in (60, 120, 240, 480, 900, 900):
        clock.advance(window - 1)
        read_is_refused()
        clock.advance(1)
        attempt_fails()

    assert github.downloads == 7


@pytest.mark.unit
def test_a_successful_download_resets_the_window_to_60_seconds(github, clock):
    attempt_fails()
    clock.advance(60)
    attempt_fails()
    clock.advance(120)
    github.down = False
    assert f1db_source.ensure_db().read_bytes() == b"sqlite-dataset"

    # The volume is lost, and GitHub is down again: the window starts over.
    f1db_source.DB_PATH.unlink()
    github.down = True
    attempt_fails()
    clock.advance(59)
    read_is_refused()
    clock.advance(1)
    attempt_fails()

    assert github.downloads == 5


# ---------------------------------------------------------------------------
# What a refused caller sees
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_reader_inside_the_window_takes_the_unavailable_path_without_network(github, clock):
    attempt_fails()
    github.requests.clear()
    clock.advance(15)

    with pytest.raises(f1db_source.F1dbUnavailableError, match=r"after 1 failed download; next attempt in 45 s"):
        f1db_source.connect()
    driver = canonical_names.driver_identity(2026, code="VER", number=3, name="Max VERSTAPPEN")

    assert driver == identity.feed_driver(code="VER", number=3, name="Max VERSTAPPEN"), (
        "a refusal is an OSError, which readers already answer with the feed's own words"
    )
    assert github.requests == []


@pytest.mark.unit
def test_a_refusal_is_logged_once_per_window(github, clock, capsys):
    attempt_fails()
    capsys.readouterr()

    for _ in range(5):
        read_is_refused()
    first_window = capsys.readouterr().out
    clock.advance(60)
    attempt_fails()
    for _ in range(5):
        read_is_refused()
    second_window = capsys.readouterr().out

    assert first_window.count("f1db.download.refused") == 1
    assert second_window.count("f1db.download.refused") == 1
    assert "f1db.download.backoff" in second_window, "the failure that opens a window says how long it is"


@pytest.mark.unit
def test_a_reader_that_waited_out_another_download_does_not_repeat_it(github, monkeypatch):
    """Readers queue on the lock while one download runs; their turn finds the file."""

    class DownloadedWhileWaiting:
        def __enter__(self) -> None:
            f1db_source.DB_PATH.write_bytes(b"fetched by the warm-up")

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(f1db_source, "_sync_lock", DownloadedWhileWaiting())

    assert f1db_source.ensure_db().read_bytes() == b"fetched by the warm-up"
    assert github.requests == []


@pytest.mark.unit
def test_a_sync_with_no_dataset_inside_the_window_raises_without_network(github, clock):
    attempt_fails()
    github.requests.clear()

    with pytest.raises(f1db_source.F1dbUnavailableError):
        f1db_source.sync_to_latest()

    assert github.requests == []
    assert f1db_source.last_sync_outcome() is None, "a refusal is not a release check"


@pytest.mark.unit
def test_a_sync_inside_the_window_keeps_the_dataset_it_has(github, clock, monkeypatch):
    f1db_source.DB_PATH.write_bytes(b"round-18")
    f1db_source.VERSION_PATH.write_text("v2026.18.0")
    monkeypatch.setattr(f1db_source, "F1DB_VERSION", RELEASE)
    f1db_source.sync_to_latest()
    assert github.downloads == 1

    outcome = f1db_source.sync_to_latest(force=True)

    assert github.downloads == 1
    assert outcome.version == "v2026.18.0"
    assert "next attempt in 60 s" in outcome.reason
    assert f1db_source.DB_PATH.read_bytes() == b"round-18"


@pytest.mark.unit
async def test_the_warm_up_inside_the_window_reports_the_reason_at_once(github, monkeypatch):
    monkeypatch.setattr(readiness, "_state", readiness._INITIAL_STATE)
    attempt_fails()
    github.requests.clear()

    final = await readiness.run_warmup(readiness.WARMUP_STEPS[:1])

    assert final.error is not None
    assert final.error.startswith("database failed: f1db download paused after 1 failed download")
    assert github.requests == []
