"""Shared fixtures and process-wide isolation for the backend suite.

Two invariants this file exists to guarantee:

1. **Hermetic environment.** Every credential and path the app reads from the
   environment is cleared or redirected *before* the first ``app.*`` import.
   ``app.config`` snapshots ``os.getenv`` at import time, so anything set after
   that import is invisible — the scrubbing has to happen at conftest module
   level, which pytest imports ahead of any test module.

2. **No real network, filesystem or model loads.** Groq, Supabase, FastF1,
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

# ---------------------------------------------------------------------------
# Environment scrubbing — must run before `app.*` is imported anywhere.
# ---------------------------------------------------------------------------

# Credentials: cleared so no test can accidentally reach a live service, and so
# the "missing key" branches are the default path under test.
_CLEARED_ENV = (
    "DATABASE_URL",
    "GROQ_API_KEY",
    "OPENWEATHERMAP_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_OUTPUT",
    "F1DB_PATH",
    "RACE_PREDICTOR_MODEL_PATH",
    # Clearable since `app/api/tools/external.py` builds its Tavily client
    # lazily. While it built the client at import time, clearing this made
    # `app.api.tools` — and therefore `app.api.routes` and `main` — unimportable,
    # so the suite had to set a placeholder instead.
    "TAVILY_API_KEY",
)

for _key in _CLEARED_ENV:
    os.environ.pop(_key, None)

# Deterministic settings the suite asserts against.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ENABLE_LOCAL_MODELS", "false")

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
