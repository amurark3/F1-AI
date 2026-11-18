"""The general FIA document ingest, end to end against a fake fia.com.

The season page is written here (Las Vegas current, Mexico City and São Paulo
past); Mexico City's event page is the real one, all 85 documents. The store
is the file backend in a temporary directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.fia_documents import listing, store
from app.data.fia_documents.ingest import ingest_season
from app.data.fia_documents.listing import WITHDRAWN_UNLISTED
from app.data.fia_documents.site import DOCUMENTS_INDEX_URL, FetchError
from app.data.fia_documents.store import FiaStoreError, FileFiaStore

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
SEASON_PATH = "/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072"
SEASON_URL = f"https://www.fia.com{SEASON_PATH}"
VEGAS, MEXICO, SAO_PAULO = "Las Vegas Grand Prix", "Mexico City Grand Prix", "São Paulo Grand Prix"
VEGAS_URL = f"{SEASON_URL}/event/Las%20Vegas%20Grand%20Prix"
MEXICO_URL = f"{SEASON_URL}/event/Mexico%20City%20Grand%20Prix"
SAO_PAULO_URL = f"{SEASON_URL}/event/S%C3%A3o%20Paulo%20Grand%20Prix"
SEASON_HTML = f"""
<a class="event-title active" href="{SEASON_PATH}/event/Las%20Vegas%20Grand%20Prix">Las Vegas Grand Prix</a>
<a href="{SEASON_PATH}/event/Mexico%20City%20Grand%20Prix">Mexico City Grand Prix</a>
<a href="{SEASON_PATH}/event/S%C3%A3o%20Paulo%20Grand%20Prix">São Paulo Grand Prix</a>
"""
PDF = "https://www.fia.com/system/files/decision-document/2026_mexico_city_grand_prix_-_{}.pdf"
FINAL_CLASSIFICATION = PDF.format("final_race_classification")
DOC_79 = PDF.format("infringement_-_car_81_-_causing_a_collision")


class FakeFetcher:
    """fia.com as the fixtures show it; every PDF's "bytes" are its own URL."""

    def __init__(self, pages: dict[str, str] | None = None, failing: frozenset[str] = frozenset()) -> None:
        self.pages = {
            DOCUMENTS_INDEX_URL: (FIXTURES / "power_units" / "documents_index.html").read_text(),
            SEASON_URL: SEASON_HTML,
            VEGAS_URL: "<html>no documents yet</html>",
            MEXICO_URL: (FIXTURES / "fia_documents" / "event_page_mexico_2026.html").read_text(),
            **(pages or {}),
        }
        self.failing = failing
        self.visited: list[str] = []

    def page(self, url: str) -> str:
        self.visited.append(url)
        if url not in self.pages:
            raise FetchError(f"GET {url} failed: 404")
        return self.pages[url]

    def document(self, url: str) -> bytes:
        self.visited.append(url)
        if url in self.failing:
            raise FetchError(f"GET {url} failed: 503")
        return url.encode()


@pytest.fixture(autouse=True)
def files(tmp_path, monkeypatch) -> FileFiaStore:
    monkeypatch.setattr(listing, "pdf_text", lambda data: f"text of {data.decode()}")
    files = FileFiaStore(tmp_path / "fia")
    monkeypatch.setattr(store, "STORE", files)
    return files


def stored(event: str = MEXICO) -> dict:
    return {document.url: document for document in store.load_event(2026, event)}


def test_the_first_run_collects_every_document_of_every_event(files):
    report = ingest_season(2026, FakeFetcher())

    assert report.events_checked == (VEGAS, MEXICO, SAO_PAULO)
    assert len(report.added) == 85
    assert report.failed == (f"{SAO_PAULO} event page: GET {SAO_PAULO_URL} failed: 404",)
    assert not report.ok
    documents = stored()
    assert len(documents) == 85
    final = documents[FINAL_CLASSIFICATION]
    assert final.title == "Doc 86 - Final Race Classification"
    assert final.published == "02.11.26 02:50"
    assert final.text == f"text of {FINAL_CLASSIFICATION}"
    assert final.sha256
    assert store.events(2026) == frozenset({MEXICO})


def test_a_quiet_run_reads_only_the_current_event_and_events_still_empty():
    ingest_season(2026, FakeFetcher())
    fetcher = FakeFetcher()

    report = ingest_season(2026, fetcher)

    assert report.events_checked == (VEGAS, SAO_PAULO)
    assert report.added == ()
    assert fetcher.visited == [DOCUMENTS_INDEX_URL, SEASON_URL, VEGAS_URL, SAO_PAULO_URL]


def test_all_events_rereads_every_page_but_downloads_nothing_held():
    ingest_season(2026, FakeFetcher())
    fetcher = FakeFetcher()

    report = ingest_season(2026, fetcher, all_events=True)

    assert report.events_checked == (VEGAS, MEXICO, SAO_PAULO)
    assert report.added == ()
    assert not any(url.endswith(".pdf") for url in fetcher.visited)


@pytest.mark.parametrize(
    ("limit", "checked", "deferred"), [(0, (VEGAS,), (MEXICO, SAO_PAULO)), (1, (VEGAS, MEXICO), (SAO_PAULO,))]
)
def test_a_run_starts_at_most_max_new_events_empty_events(limit, checked, deferred):
    report = ingest_season(2026, FakeFetcher(), max_new_events=limit)

    assert report.events_checked == checked
    assert report.deferred == deferred


def test_a_failed_download_is_kept_without_text_and_tried_again():
    report = ingest_season(2026, FakeFetcher(failing=frozenset({DOC_79})))

    title = "Doc 79 - Infringement - Car 81 - Causing a collision"
    assert f"{title}: download failed: GET {DOC_79} failed: 503" in report.failed
    assert stored()[DOC_79].text is None
    assert stored()[DOC_79].error

    again = ingest_season(2026, FakeFetcher(), all_events=True)

    assert again.added == (title,)
    assert stored()[DOC_79].text == f"text of {DOC_79}"
    assert stored()[DOC_79].error is None


def test_a_document_the_fia_takes_off_its_page_is_kept_and_marked_withdrawn():
    ingest_season(2026, FakeFetcher())
    page = (FIXTURES / "fia_documents" / "event_page_mexico_2026.html").read_text()
    without_79 = page.replace(DOC_79.removeprefix("https://www.fia.com"), "/elsewhere.html")

    report = ingest_season(2026, FakeFetcher(pages={MEXICO_URL: without_79}), all_events=True)
    repeat = ingest_season(2026, FakeFetcher(pages={MEXICO_URL: without_79}), all_events=True)

    assert report.withdrawn == ("Doc 79 - Infringement - Car 81 - Causing a collision",)
    assert stored()[DOC_79].withdrawn == WITHDRAWN_UNLISTED
    assert stored()[DOC_79].text  # kept, never deleted
    assert repeat.withdrawn == ()


def test_unchanged_documents_are_not_written_again(files, monkeypatch):
    ingest_season(2026, FakeFetcher())
    saves: list[int] = []
    monkeypatch.setattr(files, "save", lambda year, documents: saves.append(len(documents)))

    ingest_season(2026, FakeFetcher(), all_events=True)

    assert saves == []


def test_an_unreadable_store_stops_the_run_before_any_download(monkeypatch):
    def down(_year):
        raise OSError("disk gone")

    monkeypatch.setattr(store.STORE, "events", down)
    fetcher = FakeFetcher()

    with pytest.raises(FiaStoreError, match="disk gone"):
        ingest_season(2026, fetcher)
    assert fetcher.visited == [DOCUMENTS_INDEX_URL, SEASON_URL]
