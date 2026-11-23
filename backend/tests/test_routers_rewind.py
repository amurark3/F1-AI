"""Race Rewind's HTTP route."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.api.errors import GENERIC_ERROR_MESSAGE
from app.api.routers import rewind


async def test_the_route_passes_the_payload_through(monkeypatch):
    monkeypatch.setattr(rewind, "build_race_rewind", lambda year, round_num: {"year": year, "round": round_num})

    assert await rewind.get_race_rewind(2026, 19) == {"year": 2026, "round": 19}


async def test_a_failure_returns_the_client_safe_envelope(monkeypatch):
    def explode(year, round_num):
        raise RuntimeError("postgres://secret-host:5432 refused")

    monkeypatch.setattr(rewind, "build_race_rewind", explode)
    payload = await rewind.get_race_rewind(2026, 19)

    assert payload["available"] is False
    assert (payload["laps"], payload["final"], payload["grid"]) == ([], None, None)
    assert payload["error"] == GENERIC_ERROR_MESSAGE
    assert "secret-host" not in str(payload)


def test_the_route_is_served_under_the_api_router_and_rejects_years_before_openf1():
    app = FastAPI()
    app.include_router(routes.router)

    assert "/race-control/rewind/{year}/{round_num}" in app.openapi()["paths"]
    assert TestClient(app).get("/race-control/rewind/2022/1").status_code == 422
