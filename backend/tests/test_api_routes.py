"""Tests for app.api.routes — the module that wires every feature router together.

It holds almost no logic of its own, and that is the point: the risk here is a
router silently not being mounted. A missing ``include_router`` line is not a
crash, it is a 404 on one feature that nothing else notices, so the assertions
below are about the *set* of paths the assembled router exposes.

Importing this module also enables the FastF1 cache as a side effect, which is
asserted rather than left implicit — it is the only place that happens for the
web process.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import routes

# Every feature the frontend depends on, keyed by a representative path. A
# router dropped from the assembly makes exactly one of these disappear.
EXPECTED_PATHS = {
    "/chat",
    "/profile/{user_id}",
    "/threads/{user_id}/recall",
    "/predictions/{year}/{round_num}",
    "/predictions/{year}/{round_num}/snapshot",
    "/predictions/{year}/{round_num}/compute",
    "/race-control/overview/{year}",
    "/race-control/rulebook/search",
    "/schedule/{year}",
    "/standings/drivers/{year}",
    "/standings/constructors/{year}",
    "/champions",
    "/champions/stats",
    "/champions/{year}",
    "/ready",
    "/health/deep",
    "/health",
    "/compare/{year}/{driver1}/{driver2}",
}


def _mounted_paths() -> set[str]:
    return {route.path for route in routes.router.routes}


@pytest.mark.unit
@pytest.mark.parametrize("path", sorted(EXPECTED_PATHS))
def test_every_feature_router_is_mounted(path):
    assert path in _mounted_paths(), f"{path} is not reachable — a router was not included"


@pytest.mark.unit
def test_the_live_timing_websocket_is_mounted():
    # WebSocket routes do not appear alongside HTTP ones in every FastAPI
    # version, so this is matched by prefix rather than exact path.
    assert any(route.path.startswith("/live") for route in routes.router.routes)


@pytest.mark.unit
def test_health_reports_ok_with_a_utc_timestamp():
    app = FastAPI()
    app.include_router(routes.router)

    body = TestClient(app).get("/health").json()

    assert body["status"] == "ok"
    # Serialised with an explicit UTC designator — a naive stamp would be
    # ambiguous to a client. (`fromisoformat` only accepts "Z" from 3.11.)
    assert body["timestamp"].endswith("Z")
    assert datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00")).tzinfo is not None


@pytest.mark.unit
async def test_health_check_is_callable_directly():
    result = await routes.health_check()

    assert result["status"] == "ok"
    assert result["timestamp"].tzinfo == timezone.utc


@pytest.mark.unit
def test_importing_the_app_does_not_require_a_tavily_key(monkeypatch):
    """A missing TAVILY_API_KEY must not take the service down at boot.

    `app/api/tools/external.py` is reached from `app.api.tools` →
    `app.api.routers.chat` → `app.api.routes` → `main.py`. It used to build
    ``TavilyClient(api_key=os.getenv(...))`` at module scope, and that client
    raises ``MissingAPIKeyError`` without a key — so an unset key meant the
    process could not start at all and *every* endpoint was down, not just web
    search. The client is now built lazily inside the tool, matching how the
    rest of the codebase treats optional third-party credentials:
    `build_chat_llm()` raises only when a chat request actually needs Groq, and
    the embedder degrades to ``None``.

    This asserts the import stays credential-free, which is the property that
    keeps the boot path alive.
    """
    import importlib

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    external = importlib.reload(importlib.import_module("app.api.tools.external"))

    assert external._tavily_client is None, "the client was built during import"


@pytest.mark.unit
def test_a_missing_tavily_key_fails_only_the_web_search_tool(monkeypatch):
    """The cost of an absent key is scoped to the one tool that needs it.

    `perform_web_search` catches the construction failure and reports it, so a
    key-less deployment loses web search and keeps everything else.
    """
    import importlib

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    external = importlib.reload(importlib.import_module("app.api.tools.external"))

    result = external.perform_web_search.invoke({"query": "who leads the championship"})

    assert result.startswith("Search failed:")


@pytest.mark.unit
def test_importing_the_module_enables_the_fastf1_cache():
    """The web process gets its cache from this import and nowhere else."""
    from app.utils import fastf1_cache

    assert fastf1_cache._PATCHED is True, "FastF1 loaders were never wrapped for cache recovery"


@pytest.mark.unit
def test_no_duplicate_paths_are_mounted():
    # Two routers claiming one path means the second is unreachable.
    http_paths = [route.path for route in routes.router.routes if hasattr(route, "methods")]
    duplicates = {
        path
        for path in http_paths
        if sum(1 for route in routes.router.routes if hasattr(route, "methods") and route.path == path)
        > len({m for route in routes.router.routes if getattr(route, "path", None) == path for m in route.methods})
    }

    assert duplicates == set(), f"paths mounted more than once for the same method: {duplicates}"
