"""Readiness probe.

Distinct from ``/api/health``, which answers "is the process alive?" and returns
instantly because it touches nothing. This answers "can the process actually serve
a data request?" — false until the startup warm-up has paid the deferred import,
database, and model-loading costs.

Always responds 200, even when not ready. The consumer is the frontend's warming
banner, and a 200 carrying ``ready: false`` is simpler to read than a 503 that has
to be caught. It also keeps this endpoint safe to point a platform health check at
by mistake without triggering a restart loop mid-warm-up.
"""

from fastapi import APIRouter

from app.services.readiness import current_state

router = APIRouter()


@router.get("/ready")
async def readiness_probe() -> dict:
    """Report whether startup warm-up has finished, and which stage it is on."""
    return current_state().as_dict()
