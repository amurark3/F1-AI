"""The weekend live feed over the 2026 Mexico City GP's real documents."""

from __future__ import annotations

import dataclasses

import pytest

from app.data.fia_documents import feed, store
from app.data.fia_documents.document import SourceDocument
from app.data.fia_documents.feed import FEED_TTL_SECONDS, document_event, fia_event, weekend_feed
from app.data.fia_documents.kinds import KIND_CLASSIFICATION, KIND_GRID, KIND_PENALTY
from app.data.fia_documents.store import FiaStoreError, FileFiaStore
from app.utils.ttl_cache import TtlCache
from tests.fia_documents_support import MEXICO_2026

pytestmark = pytest.mark.unit

MEXICO = "Mexico City Grand Prix"
SCHEDULE = [
    {"round": 19, "name": "Mexico City Grand Prix", "location": "rodriguez"},
    {"round": 21, "name": "Las Vegas Grand Prix", "location": "vegas"},
]


def held(title: str) -> SourceDocument:
    entry = MEXICO_2026[title]
    return SourceDocument(
        url=entry["url"],
        event=MEXICO,
        title=title,
        published=entry["published"],
        sha256="0" * 64,
        fetched_at="2026-11-18T09:00:00+00:00",
        text=entry["text"],
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    tick = Clock()
    monkeypatch.setattr(feed, "_CACHE", TtlCache(clock=tick))
    return tick


@pytest.fixture(autouse=True)
def mexico_held(tmp_path, monkeypatch, clock) -> FileFiaStore:
    files = FileFiaStore(tmp_path / "fia")
    files.save(2026, [held(title) for title in MEXICO_2026])
    monkeypatch.setattr(store, "STORE", files)
    monkeypatch.setattr(feed, "race_schedule", lambda year: SCHEDULE)
    return files


def by_number(payload: dict) -> dict[int, dict]:
    return {item["number"]: item for item in payload["events"]}


def test_the_feed_lists_the_weekend_newest_first_with_what_each_document_says():
    payload = weekend_feed(2026, 19)

    assert (payload["year"], payload["round"], payload["event"], payload["latest"]) == (2026, 19, MEXICO, 86)
    numbers = [item["number"] for item in payload["events"]]
    assert len(numbers) == 58
    assert numbers == sorted(numbers, reverse=True)
    events = by_number(payload)
    piastri = events[79]
    assert (piastri["kind"], piastri["published"], piastri["unread"]) == (
        KIND_PENALTY,
        MEXICO_2026[piastri["title"]]["published"],
        None,
    )
    assert piastri["data"]["car"] == 81
    assert piastri["data"]["outcomes"] == ({"kind": "time_penalty", "value": 10},)
    assert events[67]["data"]["final"] is True
    assert len(events[80]["data"]["laps"]) == 13
    assert events[86]["kind"] == KIND_CLASSIFICATION
    assert [entry["car"] for entry in events[86]["data"]["entries"][:3]] == [3, 44, 12]
    assert (events[36]["data"]["outgoing"], events[36]["data"]["incoming"]) == ("Esteban Ocon", "Ryo Hirakawa")
    assert events[37]["data"]["revised"] is True
    assert (events[2]["data"]["hard"], events[2]["data"]["soft"]) == ("C3", "C5")
    # A permission to start is in the grid kind but is not a grid: listed, data empty.
    assert (events[58]["kind"], events[58]["data"], events[58]["unread"]) == (KIND_GRID, None, None)
    # Every parsed kind reads: no document of the weekend is unread.
    assert [item["title"] for item in payload["events"] if item["unread"]] == []


def test_after_returns_only_the_documents_newer_than_the_client_holds():
    payload = weekend_feed(2026, 19, after=80)

    assert [item["number"] for item in payload["events"]] == [86, 85, 84, 83, 82]
    assert payload["latest"] == 86


def test_an_unread_document_says_why_and_never_breaks_the_feed():
    failed = dataclasses.replace(
        held("Doc 79 - Infringement - Car 81 - Causing a collision"), text=None, error="download failed: 503"
    )
    garbled = dataclasses.replace(held("Doc 80 - Infringement - Race Deleted Lap Times"), text="nothing to read")

    assert (document_event(failed)["data"], document_event(failed)["unread"]) == (None, "download failed: 503")
    assert document_event(garbled)["data"] is None
    assert "deleted-lap sheet" in document_event(garbled)["unread"]


def test_a_document_without_a_number_sorts_last():
    stray = dataclasses.replace(held("Doc 2 - Competition Notes - Pirelli Preview"), title="Pirelli Preview")

    assert document_event(stray)["number"] is None


@pytest.mark.parametrize("round_number", [21, 30])
def test_a_round_with_no_documents_or_not_on_the_calendar_has_an_empty_feed(round_number):
    assert weekend_feed(2026, round_number) == {
        "year": 2026,
        "round": round_number,
        "event": None,
        "latest": None,
        "events": [],
    }


def test_the_event_name_matches_the_calendar_whatever_its_accents_and_spacing(monkeypatch):
    monkeypatch.setattr(
        feed, "race_schedule", lambda year: [{"round": 19, "name": "Mexico  City Grand Prix", "location": "x"}]
    )

    assert fia_event(2026, 19) == MEXICO


def test_the_feed_is_reused_for_a_minute_then_read_again(mexico_held, clock, monkeypatch):
    reads: list[str] = []
    load = mexico_held.load_event
    monkeypatch.setattr(mexico_held, "load_event", lambda year, event: reads.append(event) or load(year, event))

    weekend_feed(2026, 19)
    weekend_feed(2026, 19, after=85)
    clock.now = FEED_TTL_SECONDS + 1
    weekend_feed(2026, 19)

    assert reads == [MEXICO, MEXICO]


def test_a_store_outage_is_raised_not_shown_as_an_empty_weekend(monkeypatch, mexico_held):
    def down(year):
        raise OSError("disk gone")

    monkeypatch.setattr(mexico_held, "events", down)

    with pytest.raises(FiaStoreError, match="disk gone"):
        weekend_feed(2026, 19)
