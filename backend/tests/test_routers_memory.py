"""Tests for app.api.routers.memory — profile and semantic-recall endpoints.

Thin handlers over `app.data.memory`. Two properties matter:

* every response reports ``enabled``, so a client can tell "you have no saved
  preferences" from "memory is switched off in this deployment" — without it,
  a disabled backend looks identical to an empty profile;
* a partial ``PUT`` must send ``None`` for the fields the caller omitted, so
  the data layer can distinguish "leave unchanged" from "clear this".
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import memory as memory_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(memory_router.router)
    return TestClient(app)


@pytest.mark.unit
def test_get_profile_returns_the_stored_profile_with_the_enabled_flag(client, monkeypatch):
    monkeypatch.setattr(memory_router.memory, "get_profile", lambda user_id: {"favorite_driver": "VER"})
    monkeypatch.setattr(memory_router.memory, "MEMORY_ENABLED", True)

    body = client.get("/profile/user-1").json()

    assert body == {"user_id": "user-1", "profile": {"favorite_driver": "VER"}, "enabled": True}


@pytest.mark.unit
def test_get_profile_distinguishes_disabled_memory_from_an_empty_profile(client, monkeypatch):
    monkeypatch.setattr(memory_router.memory, "get_profile", lambda user_id: {})
    monkeypatch.setattr(memory_router.memory, "MEMORY_ENABLED", False)

    body = client.get("/profile/user-1").json()

    assert body["profile"] == {}
    assert body["enabled"] is False


@pytest.mark.unit
def test_update_profile_forwards_every_field_and_returns_the_merged_result(client, monkeypatch):
    captured: dict = {}

    def fake_set(user_id, **fields):
        captured.update({"user_id": user_id, **fields})
        return {"favorite_driver": "LEC", "favorite_team": "Ferrari"}

    monkeypatch.setattr(memory_router.memory, "set_profile", fake_set)
    monkeypatch.setattr(memory_router.memory, "MEMORY_ENABLED", True)

    body = client.put(
        "/profile/user-2",
        json={"favorite_driver": "LEC", "favorite_team": "Ferrari", "prefs": {"units": "metric"}},
    ).json()

    assert captured["user_id"] == "user-2"
    assert captured["favorite_driver"] == "LEC"
    assert captured["prefs"] == {"units": "metric"}
    assert body["profile"]["favorite_team"] == "Ferrari"


@pytest.mark.unit
def test_update_profile_sends_none_for_omitted_fields(client, monkeypatch):
    """A partial update must not invent values for fields the caller left out."""
    captured: dict = {}

    def fake_set(user_id, **fields):
        captured.update(fields)
        return {}

    monkeypatch.setattr(memory_router.memory, "set_profile", fake_set)

    client.put("/profile/user-3", json={"favorite_driver": "NOR"})

    assert captured["favorite_driver"] == "NOR"
    assert captured["favorite_team"] is None
    assert captured["prefs"] is None


@pytest.mark.unit
def test_update_profile_accepts_an_empty_body(client, monkeypatch):
    monkeypatch.setattr(memory_router.memory, "set_profile", lambda user_id, **fields: {})

    assert client.put("/profile/user-4", json={}).status_code == 200


@pytest.mark.unit
def test_update_profile_rejects_a_wrongly_typed_field(client):
    # `prefs` is a dict; a string would otherwise be persisted as-is.
    assert client.put("/profile/user-5", json={"prefs": "metric"}).status_code == 422


@pytest.mark.unit
def test_recall_returns_matches_for_the_query(client, monkeypatch):
    monkeypatch.setattr(
        memory_router.memory,
        "recall_relevant",
        lambda user_id, q, k=4: [{"content": "you asked about Monaco", "score": 0.91}],
    )

    body = client.get("/threads/user-6/recall", params={"q": "monaco"}).json()

    assert body["query"] == "monaco"
    assert body["matches"][0]["score"] == 0.91


@pytest.mark.unit
def test_recall_defaults_to_four_matches(client, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(
        memory_router.memory,
        "recall_relevant",
        lambda user_id, q, k=4: seen.append(k) or [],
    )

    client.get("/threads/user-7/recall", params={"q": "drs"})

    assert seen == [4]


@pytest.mark.unit
def test_recall_honours_an_explicit_k(client, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(
        memory_router.memory,
        "recall_relevant",
        lambda user_id, q, k=4: seen.append(k) or [],
    )

    client.get("/threads/user-8/recall", params={"q": "drs", "k": 10})

    assert seen == [10]


@pytest.mark.unit
def test_recall_requires_a_query(client):
    assert client.get("/threads/user-9/recall").status_code == 422
