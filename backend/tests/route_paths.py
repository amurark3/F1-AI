"""Route introspection helpers shared by the router-wiring tests.

FastAPI 0.139 (Starlette 1.x) stopped flattening ``include_router`` calls into
the parent's ``routes`` list. A router is now held as a single opaque
``_IncludedRouter`` entry that resolves its children lazily, so the old
``{route.path for route in router.routes}`` idiom raises ``AttributeError``.

``fastapi.routing.iter_route_contexts`` is the supported replacement: it walks
those containers and yields one ``RouteContext`` per real route, with the
prefixes already applied. Both helpers below take a raw ``routes`` list so they
work on an assembled app *and* on a bare ``APIRouter``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.routing import iter_route_contexts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.routing import BaseRoute


def _effective_path(context: Any) -> str:
    """Return the fully prefixed path a route is reachable at.

    WebSocket contexts leave ``path`` empty and carry the resolved route on
    ``starlette_route`` instead, so the bare ``path`` is not enough on its own.
    """
    resolved = getattr(context, "starlette_route", None)
    return context.path or getattr(resolved, "path", "")


def mounted_paths(routes: Sequence[BaseRoute]) -> set[str]:
    """Every path the routes are reachable at, HTTP and WebSocket alike."""
    return {_effective_path(context) for context in iter_route_contexts(routes)}


def mounted_http_methods(routes: Sequence[BaseRoute]) -> list[tuple[str, str]]:
    """Every ``(path, method)`` pair, one entry per registration.

    Duplicates are preserved on purpose: a repeated pair is what "two routers
    claim the same endpoint" looks like, and a set would hide it.
    """
    return [
        (_effective_path(context), method)
        for context in iter_route_contexts(routes)
        for method in (context.methods or ())
    ]
