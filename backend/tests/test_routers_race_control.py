"""Tests for app.api.routers.race_control — the Race Control v2 HTTP surface.

Thin handlers over the race-control services, each running its blocking service
call in a worker thread. The properties pinned here:

* every guarded handler answers **200 with a client-safe error envelope** on
  failure, and keeps the shape the frontend destructures (``teams: []``,
  ``drivers: []``, ``podium: []``) so a failed panel renders empty rather than
  crashing the dashboard;
* ``/teams/{team_slug}/{year}`` returns ``team: None`` plus a plain message for
  an unknown slug — a miss is a normal outcome, not an error;
* two handlers (``/battle``, ``/intel``) are deliberately **unguarded**, so a
  service exception propagates. That asymmetry is easy to introduce by accident,
  so it is asserted rather than assumed.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import race_control as rc_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rc_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _boom(*_args, **_kwargs):
    raise RuntimeError("f1db unavailable")


@pytest.mark.unit
def test_overview_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_overview", lambda year: {"year": year, "flags": []})

    body = client.get("/race-control/overview/2026").json()

    assert body == {"year": 2026, "flags": []}


@pytest.mark.unit
def test_overview_failure_keeps_the_year_and_adds_an_error_id(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_overview", _boom)

    response = client.get("/race-control/overview/2026")
    body = response.json()

    assert response.status_code == 200
    assert body["year"] == 2026
    assert "error_id" in body


@pytest.mark.unit
def test_teams_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_teams", lambda year: {"teams": [{"slug": "ferrari"}]})

    assert client.get("/race-control/teams/2026").json()["teams"] == [{"slug": "ferrari"}]


@pytest.mark.unit
def test_teams_failure_degrades_to_an_empty_list(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_teams", _boom)

    body = client.get("/race-control/teams/2026").json()

    assert body["teams"] == [], "the dashboard destructures this array"
    assert "error_id" in body


@pytest.mark.unit
def test_single_team_is_selected_by_slug(client, monkeypatch):
    monkeypatch.setattr(
        rc_router,
        "build_teams",
        lambda year: {"teams": [{"slug": "ferrari", "name": "Ferrari"}, {"slug": "mclaren"}]},
    )

    body = client.get("/race-control/teams/ferrari/2026").json()

    assert body["team"]["name"] == "Ferrari"
    assert body["error"] is None


@pytest.mark.unit
def test_unknown_team_slug_is_a_normal_miss_not_an_error_id(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_teams", lambda year: {"teams": [{"slug": "ferrari"}]})

    body = client.get("/race-control/teams/haas/2026").json()

    assert body["team"] is None
    assert body["error"] == "Team 'haas' not found"
    # A miss is an expected outcome — it must not be logged as a server fault.
    assert "error_id" not in body


@pytest.mark.unit
def test_single_team_failure_returns_a_null_team_and_an_error_id(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_teams", _boom)

    body = client.get("/race-control/teams/ferrari/2026").json()

    assert body["team"] is None
    assert "error_id" in body


@pytest.mark.unit
def test_drivers_returns_the_option_list(client, monkeypatch):
    monkeypatch.setattr(rc_router, "get_driver_options", lambda year: {"drivers": ["VER", "LEC"]})

    assert client.get("/race-control/drivers/2026").json()["drivers"] == ["VER", "LEC"]


@pytest.mark.unit
def test_drivers_failure_degrades_to_an_empty_list(client, monkeypatch):
    monkeypatch.setattr(rc_router, "get_driver_options", _boom)

    body = client.get("/race-control/drivers/2026").json()

    assert body["drivers"] == []
    assert "error_id" in body


@pytest.mark.unit
def test_forecast_returns_both_championship_projections(client, monkeypatch):
    monkeypatch.setattr(
        rc_router,
        "build_championship_forecast",
        lambda year: {"drivers": [{"code": "VER"}], "constructors": [{"slug": "red-bull"}]},
    )

    body = client.get("/race-control/forecast/2026").json()

    assert body["drivers"]
    assert body["constructors"]


@pytest.mark.unit
def test_forecast_failure_degrades_both_arrays(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_championship_forecast", _boom)

    body = client.get("/race-control/forecast/2026").json()

    assert body["drivers"] == []
    assert body["constructors"] == []
    assert "error_id" in body


@pytest.mark.unit
def test_battle_passes_both_drivers_through(client, monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(
        rc_router,
        "build_driver_battle",
        lambda year, d1, d2: seen.append((year, d1, d2)) or {"winner": d1},
    )

    body = client.get("/race-control/battle/2026/VER/LEC").json()

    assert seen == [(2026, "VER", "LEC")]
    assert body["winner"] == "VER"


@pytest.mark.unit
def test_battle_is_unguarded_and_surfaces_a_service_failure(client, monkeypatch):
    """Unlike its neighbours this handler has no try/except — pinned deliberately."""
    monkeypatch.setattr(rc_router, "build_driver_battle", _boom)

    assert client.get("/race-control/battle/2026/VER/LEC").status_code == 500


@pytest.mark.unit
def test_debrief_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(
        rc_router,
        "build_race_debrief",
        lambda year, round_num: {"year": year, "round": round_num, "podium": ["VER"]},
    )

    body = client.get("/race-control/debrief/2026/1").json()

    assert body["podium"] == ["VER"]


@pytest.mark.unit
def test_debrief_failure_keeps_the_race_identity_and_empty_arrays(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_race_debrief", _boom)

    body = client.get("/race-control/debrief/2026/4").json()

    assert (body["year"], body["round"]) == (2026, 4)
    assert body["podium"] == []
    assert body["takeaways"] == []
    assert "error_id" in body


@pytest.mark.unit
def test_rulebook_search_echoes_the_request_alongside_the_results(client, monkeypatch):
    monkeypatch.setattr(
        rc_router.rulebook,
        "search_rulebook",
        lambda query, category, year: {"results": [{"text": "Article 26.1"}]},
    )

    body = client.post("/race-control/rulebook/search", json={"query": "parc ferme"}).json()

    assert body["query"] == "parc ferme"
    # Unset filters echo as "All" so the UI can render its filter chips.
    assert body["category"] == "All"
    assert body["year"] == "All"
    assert body["results"][0]["text"] == "Article 26.1"


@pytest.mark.unit
def test_rulebook_search_forwards_the_category_and_year_filters(client, monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(
        rc_router.rulebook,
        "search_rulebook",
        lambda query, category, year: seen.append((query, category, year)) or {"results": []},
    )

    body = client.post(
        "/race-control/rulebook/search",
        json={"query": "drs", "category": "Sporting", "year": 2026},
    ).json()

    assert seen == [("drs", "Sporting", 2026)]
    assert body["category"] == "Sporting"
    assert body["year"] == 2026


@pytest.mark.unit
def test_rulebook_search_requires_a_query(client):
    assert client.post("/race-control/rulebook/search", json={}).status_code == 422


@pytest.mark.unit
def test_intel_returns_the_service_payload(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_intel", lambda slug: {"slug": slug, "notes": []})

    assert client.get("/race-control/intel/ferrari").json()["slug"] == "ferrari"


@pytest.mark.unit
def test_intel_is_unguarded_and_surfaces_a_service_failure(client, monkeypatch):
    monkeypatch.setattr(rc_router, "build_intel", _boom)

    assert client.get("/race-control/intel/ferrari").status_code == 500


@pytest.mark.unit
def test_health_reports_the_service_name_and_a_utc_timestamp(client):
    body = client.get("/race-control/health").json()

    assert body["status"] == "ok"
    assert body["service"] == "race-control"
    # An offset-naive stamp would be ambiguous for a client in another zone.
    assert body["time"].endswith("+00:00")
