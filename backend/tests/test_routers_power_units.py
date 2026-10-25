"""Tests for the power-unit HTTP route."""

from app.api.errors import GENERIC_ERROR_MESSAGE
from app.api.routers import power_units


async def test_the_route_returns_the_service_payload(monkeypatch):
    monkeypatch.setattr(power_units, "build_power_units", lambda year: {"year": year, "available": True, "cars": [1]})
    assert await power_units.get_power_units(2026) == {"year": 2026, "available": True, "cars": [1]}


async def test_a_failure_returns_the_client_safe_envelope(monkeypatch):
    def explode(year):
        raise RuntimeError("postgres://secret-host:5432 refused")

    monkeypatch.setattr(power_units, "build_power_units", explode)
    payload = await power_units.get_power_units(2026)

    assert payload["available"] is False
    assert payload["cars"] == []
    assert payload["error"] == GENERIC_ERROR_MESSAGE
    assert "secret-host" not in str(payload)
    assert payload["error_id"]
