"""Readiness and deep-health probes.

Three endpoints, three questions, deliberately kept separate:

``/api/health``
    Is the process alive? Touches nothing, always 200. This is what Render's
    platform health check points at, so it must never fail for a reason that a
    restart cannot fix.

``/api/ready``
    Can the process serve a data request? False until the startup warm-up has
    paid the deferred import, database, and model-loading costs. Always 200,
    even when not ready: the consumer is the frontend's warming banner, and a
    200 carrying ``ready: false`` is simpler to read than a 503 that has to be
    caught. It reports the *last known* store health without opening a
    connection, so the frontend can poll it freely.

``/api/health/deep``
    Are the process **and its database** healthy? This one round-trips
    Postgres, and answers 503 when it cannot. It exists because a keepalive
    that pings ``/api/health`` is structurally blind to the database: it
    reported success every hour while the Supabase project idled out from under
    it and paused, taking every stored prediction offline. An uptime monitor
    pointed here both alerts on that failure and generates the database
    activity that prevents it.
"""

import asyncio

from fastapi import APIRouter, Response

from app.data.f1db_source import installed_version
from app.data.store import document_store
from app.services.readiness import current_state

router = APIRouter()

# Reuse a health verdict this fresh instead of reconnecting. Comfortably below
# any sane monitor interval, so every scheduled ping still does a real
# round-trip, while a burst of requests cannot open a connection each.
DEEP_HEALTH_MAX_AGE_SECONDS = 15.0


@router.get("/ready")
async def readiness_probe() -> dict:
    """Report whether startup warm-up has finished, and which stage it is on.

    Also reports document-store health and the f1db release currently on disk. A
    reachable process backed by an unreachable store still answers requests, but
    serves no stored predictions — a degraded state that is otherwise invisible
    from the outside. The dataset version is here for the same reason: a server
    happily serving last month's standings looks identical to a healthy one
    unless it says out loud which snapshot it is reading.
    """
    return {
        **current_state().as_dict(),
        "store": document_store.health().as_dict(),
        "f1db_version": installed_version(),
    }


@router.get("/health/deep")
async def deep_health_check(response: Response) -> dict:
    """Verify the database is actually reachable. 200 healthy, 503 degraded.

    Runs in a worker thread: the driver is blocking, and a stalled connection
    must not take the event loop with it.
    """
    health = await asyncio.to_thread(document_store.ping, DEEP_HEALTH_MAX_AGE_SECONDS)

    if not health.ok:
        response.status_code = 503

    return {
        "status": "ok" if health.ok else "degraded",
        "ready": current_state().ready,
        "store": health.as_dict(),
    }
