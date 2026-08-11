"""Tests for app.api.routers.champions — the /champions endpoints.

Three thin handlers over `app.data.champions`. The property worth pinning is
the failure shape: each one catches broadly and returns a **200 with a
client-safe error**, never a 500 and never the raw exception. The champions
screen renders 1950-present, so a single bad season must degrade to an empty
list with an error id rather than blanking the page.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import champions as champions_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(champions_router.router)
    return TestClient(app)


@pytest.mark.unit
def test_list_returns_the_seasons_from_the_data_layer(client, monkeypatch):
    seasons = [{"season": 2026, "driver_champion": None}, {"season": 2025}]
    monkeypatch.setattr(champions_router, "list_champions", lambda: seasons)

    response = client.get("/champions")

    assert response.status_code == 200
    assert response.json() == {"seasons": seasons}


@pytest.mark.unit
def test_list_degrades_to_an_empty_season_list_on_failure(client, monkeypatch):
    def explode():
        raise RuntimeError("f1db.db is missing")

    monkeypatch.setattr(champions_router, "list_champions", explode)

    response = client.get("/champions")
    body = response.json()

    assert response.status_code == 200, "a data failure must not 500 the page"
    assert body["seasons"] == []
    assert "error_id" in body


@pytest.mark.unit
def test_stats_returns_the_leaderboards(client, monkeypatch):
    stats = {"most_driver_titles": [{"name": "Max Verstappen", "titles": 4}]}
    monkeypatch.setattr(champions_router, "get_champion_stats", lambda: stats)

    assert client.get("/champions/stats").json() == stats


@pytest.mark.unit
def test_stats_returns_a_client_safe_error_on_failure(client, monkeypatch):
    def explode():
        raise ValueError("no such table: season_driver_standing")

    monkeypatch.setattr(champions_router, "get_champion_stats", explode)

    body = client.get("/champions/stats").json()

    assert "error_id" in body
    # The SQLite message names internal schema and must not reach the client.
    assert "season_driver_standing" not in str(body)


@pytest.mark.unit
def test_season_detail_is_returned_for_a_known_year(client, monkeypatch):
    detail = {"season": 1994, "race_winners": []}
    monkeypatch.setattr(champions_router, "get_season_detail", lambda year: detail)

    assert client.get("/champions/1994").json() == detail


@pytest.mark.unit
def test_season_detail_passes_the_requested_year_through(client, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(champions_router, "get_season_detail", lambda year: seen.append(year) or {"season": year})

    client.get("/champions/1950")

    assert seen == [1950]


@pytest.mark.unit
def test_season_detail_error_still_reports_which_year_failed(client, monkeypatch):
    def explode(year):
        raise RuntimeError("db locked")

    monkeypatch.setattr(champions_router, "get_season_detail", explode)

    body = client.get("/champions/2026").json()

    # The year is echoed so the client can keep rendering the route it asked for.
    assert body["year"] == 2026
    assert "error_id" in body


@pytest.mark.unit
def test_a_non_numeric_year_is_rejected_by_validation(client):
    # `/champions/stats` must keep winning over `/champions/{year}`; anything
    # else non-numeric is a 422 rather than reaching the data layer.
    assert client.get("/champions/not-a-year").status_code == 422
