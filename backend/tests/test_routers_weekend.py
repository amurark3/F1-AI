"""Tests for the weekend live feed's HTTP route."""

from fastapi import FastAPI

from app.api import routes
from app.api.errors import GENERIC_ERROR_MESSAGE
from app.api.routers import weekend


async def test_the_route_returns_the_feed_and_passes_after_through(monkeypatch):
    calls = []
    monkeypatch.setattr(
        weekend,
        "weekend_feed",
        lambda year, round_num, after: calls.append(after) or {"year": year, "round": round_num},
    )

    assert await weekend.get_weekend_feed(2026, 19, after=80) == {"year": 2026, "round": 19}
    assert calls == [80]


async def test_a_failure_returns_the_client_safe_envelope(monkeypatch):
    def explode(year, round_num, after):
        raise RuntimeError("postgres://secret-host:5432 refused")

    monkeypatch.setattr(weekend, "weekend_feed", explode)
    payload = await weekend.get_weekend_feed(2026, 19, after=None)

    assert (payload["event"], payload["latest"], payload["events"]) == (None, None, [])
    assert payload["error"] == GENERIC_ERROR_MESSAGE
    assert "secret-host" not in str(payload)


def test_the_feed_is_served_under_the_api_router():
    app = FastAPI()
    app.include_router(routes.router)

    assert "/weekend/{year}/{round_num}/feed" in app.openapi()["paths"]
