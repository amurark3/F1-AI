"""Tests for app.api.routers.profiles — the Teams & Drivers HTTP surface.

* ids are f1db slugs; anything else is rejected with 422 before the service runs;
* seasons run from 1950 to next year;
* a service failure answers 200 with a client-safe error and the shape the
  page destructures (``team: None`` / ``driver: None``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import profiles as router_module

NEXT_YEAR = datetime.now(UTC).year + 1


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router_module.router)
    return TestClient(app, raise_server_exceptions=False)


def _boom(*_args):
    raise RuntimeError("sqlite3.OperationalError: no such table: race_data")


@pytest.mark.unit
def test_directory_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(router_module, "build_directory", lambda year: {"year": year, "status": "ok"})

    assert client.get("/profiles/2026/directory").json() == {"year": 2026, "status": "ok"}


@pytest.mark.unit
def test_team_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(router_module, "build_team_profile", lambda year, team_id: {"team": {"id": team_id}})

    assert client.get("/profiles/2026/teams/red-bull").json() == {"team": {"id": "red-bull"}}


@pytest.mark.unit
def test_driver_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(router_module, "build_driver_profile", lambda year, driver_id: {"driver": {"id": driver_id}})

    assert client.get("/profiles/2026/drivers/max-verstappen").json() == {"driver": {"id": "max-verstappen"}}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "service", "key"),
    [
        ("/profiles/2026/directory", "build_directory", "teams"),
        ("/profiles/2026/teams/red-bull", "build_team_profile", "team"),
        ("/profiles/2026/drivers/max-verstappen", "build_driver_profile", "driver"),
    ],
    ids=["directory", "team", "driver"],
)
def test_a_service_failure_answers_200_with_a_safe_error(client, monkeypatch, path, service, key):
    monkeypatch.setattr(router_module, service, _boom)

    response = client.get(path)
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "error"
    assert body[key] in (None, [])
    assert "error_id" in body
    assert "race_data" not in body["error"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/profiles/2026/teams/Red%20Bull",
        "/profiles/2026/teams/red_bull",
        "/profiles/2026/drivers/MAX",
        f"/profiles/2026/drivers/{'a' * 65}",
    ],
    ids=["space", "underscore", "upper-case", "too-long"],
)
def test_ids_that_are_not_f1db_slugs_are_rejected(client, monkeypatch, path):
    monkeypatch.setattr(router_module, "build_team_profile", _boom)
    monkeypatch.setattr(router_module, "build_driver_profile", _boom)

    assert client.get(path).status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize("year", [1949, NEXT_YEAR + 1], ids=["before-1950", "beyond-next-season"])
def test_seasons_outside_the_championship_are_rejected(client, monkeypatch, year):
    monkeypatch.setattr(router_module, "build_directory", _boom)

    assert client.get(f"/profiles/{year}/directory").status_code == 422


@pytest.mark.unit
def test_next_season_is_allowed_for_its_entry_list(client, monkeypatch):
    monkeypatch.setattr(router_module, "build_directory", lambda year: {"year": year})

    assert client.get(f"/profiles/{NEXT_YEAR}/directory").json() == {"year": NEXT_YEAR}
