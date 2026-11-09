"""Shared fixtures and process-wide isolation for the backend suite.

Two invariants this file exists to guarantee:

1. **Hermetic environment.** Every credential and path the app reads from the
   environment is cleared or redirected *before* the first ``app.*`` import.
   ``app.config`` snapshots ``os.getenv`` at import time, so anything set after
   that import is invisible — the scrubbing has to happen at conftest module
   level, which pytest imports ahead of any test module.

2. **No real network, filesystem or model loads.** LLM engines, Supabase, FastF1,
   OpenF1, Tavily and sentence-transformers are all reached through mocked
   boundaries. A test that would open a socket fails loudly instead.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# Re-exported so any test module can request the shared f1db fixtures by name
# without importing them itself. `pytest_plugins` is only honoured in the
# rootdir conftest, which this is not, so a plain import is the supported route.
from tests.f1db_fixture import build_f1db, empty_f1db, fake_f1db  # noqa: F401
from tests.identity_support import identity_f1db  # noqa: F401
from tests.profiles_support import profiles_f1db  # noqa: F401

# ---------------------------------------------------------------------------
# Environment scrubbing — must run before `app.*` is imported anywhere.
# ---------------------------------------------------------------------------

# Credentials: cleared so no test can accidentally reach a live service, and so
# the "missing key" branches are the default path under test.
_CLEARED_ENV = (
    "DATABASE_URL",
    "TOKENLAB_API_KEY",
    "GOOGLE_API_KEY",
    "OPENWEATHERMAP_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_OUTPUT",
    "F1DB_PATH",
    # Importing the API enables the FastF1 cache; a developer's override must not
    # send the suite's cache directory somewhere else.
    "FASTF1_CACHE_DIR",
    "RACE_PREDICTOR_MODEL_PATH",
    # Clearable since `app/api/tools/external.py` builds its Tavily client
    # lazily. While it built the client at import time, clearing this made
    # `app.api.tools` — and therefore `app.api.routes` and `main` — unimportable,
    # so the suite had to set a placeholder instead.
    "TAVILY_API_KEY",
)

for _key in _CLEARED_ENV:
    os.environ.pop(_key, None)

# Blanked rather than popped: `main` calls `load_dotenv()` on import, which
# refills any *absent* variable from a developer's `.env` but never overrides a
# present one. A real DSN there would ship every deliberately raised test error
# to the live Sentry project.
os.environ["SENTRY_DSN"] = ""

# Deterministic settings the suite asserts against.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ENABLE_LOCAL_MODELS", "false")
# OpenF1 requests are paced in production; against a mock transport the pause
# is only wall-clock time. The pacer's own tests inject a gap and a clock.
os.environ["OPENF1_MIN_REQUEST_GAP_SECONDS"] = "0"

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def reload_module():
    """Re-import a module so import-time ``os.getenv`` reads patched values.

    ``app.config`` and friends bind their constants at import time. A test that
    needs a different value patches the environment and then asks for a reload::

        cfg = reload_module("app.config")

    The module is restored to its original state on teardown so the reload
    cannot leak into the next test.
    """

    reloaded: list[str] = []

    def _reload(name: str):
        module = importlib.import_module(name)
        reloaded.append(name)
        return importlib.reload(module)

    yield _reload

    # Restore every reloaded module to the ambient environment's version.
    for name in reversed(reloaded):
        if name in sys.modules:
            importlib.reload(sys.modules[name])


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the JSON document-store fallback at a throwaway directory."""

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("PREDICTION_HISTORY_PATH", str(data_dir / "history.json"))
    monkeypatch.setenv("PREDICTION_CACHE_PATH", str(data_dir / "cache.json"))
    monkeypatch.chdir(tmp_path)
    return data_dir


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that opens a real socket instead of mocking the boundary.

    Autouse so the guard is opt-out (``@pytest.mark.integration``) rather than
    opt-in — an unmocked HTTP call otherwise shows up as a slow, flaky test
    rather than the boundary bug it is.
    """

    import socket

    real_socket = socket.socket

    class _BlockedSocket(real_socket):  # type: ignore[misc,valid-type]
        def connect(self, *args: Any, **kwargs: Any):
            raise RuntimeError(
                "network access is blocked in unit tests — mock the boundary (httpx/requests/urllib) instead"
            )

        connect_ex = connect

    monkeypatch.setattr(socket, "socket", _BlockedSocket)
    return


@pytest.fixture(autouse=True)
def _no_local_f1db(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A test that builds no f1db reads an empty one, never the developer's download.

    ``DB_PATH`` defaults to ``data/f1db.db``, which exists on a developer's machine
    and not in CI. Every emit point now prints names through ``app.data.identity``,
    so a test that silently read the local file would pass here and fail there.
    An empty file fails every query with ``sqlite3.OperationalError``, which the
    emit points answer with the feed's own words. Tests that need data build an
    f1db and point ``DB_PATH`` at it, which overrides this.
    """
    from app.data import f1db_source, identity

    empty = tmp_path_factory.getbasetemp() / "f1db-empty.db"
    empty.touch()
    monkeypatch.setattr(f1db_source, "DB_PATH", empty)
    identity.clear_cache()
    yield
    identity.clear_cache()
