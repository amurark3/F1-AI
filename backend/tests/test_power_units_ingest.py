"""Tests for the stored corpus and the ingest job.

The store runs on its JSON-file backend in a temporary directory, and the FIA
site is a fake fetcher serving the real HTML fixtures, so every rule is tested
end to end: what gets fetched, what gets kept, and what a failure leaves
behind.
"""

from pathlib import Path

import pytest

from app.data.power_units import ingest, sources
from app.data.power_units.allowances import load_allowances
from app.data.power_units.fia_site import DOCUMENTS_INDEX_URL, FetchError
from app.data.power_units.ingest import WITHDRAWN_UNLISTED, IngestError, ingest_season
from app.data.power_units.sources import (
    SeasonSources,
    SourceDocument,
    SourcesUnavailableError,
    load_season,
    save_season,
)
from app.data.power_units.text import DocumentParseError
from app.data.store import DOCUMENT_POWER_UNIT_SOURCES, document_store
from app.data.store_types import ReadResult, WriteResult

FIXTURES = Path(__file__).parent / "fixtures" / "power_units"
SEASON_URL = f"{DOCUMENTS_INDEX_URL}/season/season-2026-2072"
EVENT_URL = SEASON_URL + "/event/{}"
PDF_BASE = "https://www.fia.com/system/files/decision-document/"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def doc(url: str = "u", **overrides) -> SourceDocument:
    fields = {
        "url": url,
        "event": "Singapore Grand Prix",
        "title": "Doc 1",
        "published": "",
        "sha256": "",
        "fetched_at": "",
        "text": "t",
    }
    return SourceDocument(**{**fields, **overrides})


@pytest.fixture
def store_dir(isolated_data_dir):
    return isolated_data_dir


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------


def test_an_empty_store_is_a_season_with_no_documents(store_dir):
    season = load_season(2026)
    assert season == SeasonSources(year=2026, documents=(), updated_at=None)


def test_a_season_round_trips_and_other_seasons_survive(store_dir):
    save_season(SeasonSources(year=2025, documents=(doc("old"),), updated_at="a"))
    failed = doc("bad", text=None, error="download failed", withdrawn=WITHDRAWN_UNLISTED)
    save_season(SeasonSources(year=2026, documents=(doc("new"), failed), updated_at="b"))

    assert load_season(2025).documents == (doc("old"),)
    season = load_season(2026)
    assert season.updated_at == "b"
    assert season.documents == (doc("new"), failed)


def test_malformed_entries_are_skipped_not_fatal(store_dir):
    document_store.write(
        DOCUMENT_POWER_UNIT_SOURCES,
        {"seasons": {"2026": {"documents": [{"url": "only-a-url"}, "junk", doc("ok").as_dict()], "updated_at": 7}}},
    )
    season = load_season(2026)
    assert season.documents == (doc("ok"),)
    assert season.updated_at is None


def test_a_payload_without_seasons_reads_as_empty(store_dir):
    document_store.write(DOCUMENT_POWER_UNIT_SOURCES, {"seasons": ["not", "a", "dict"]})
    assert load_season(2026).documents == ()
    save_season(SeasonSources(year=2026, documents=(doc(),)))
    assert load_season(2026).documents == (doc(),)


def test_an_unreadable_store_is_an_error_and_is_never_overwritten(store_dir, monkeypatch):
    monkeypatch.setattr(sources.document_store, "read", lambda name: ReadResult(ok=False, error="down"))
    with pytest.raises(SourcesUnavailableError, match="down"):
        load_season(2026)
    with pytest.raises(SourcesUnavailableError):
        save_season(SeasonSources(year=2026, documents=()))
    monkeypatch.setattr(sources.document_store, "read", lambda name: ReadResult(ok=False))
    with pytest.raises(SourcesUnavailableError, match="could not be read"):
        load_season(2026)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

SINGAPORE_USAGE = PDF_BASE + "2026_singapore_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf"
SINGAPORE_DECISION = PDF_BASE + "2026_singapore_grand_prix_-_infringement_-_car_63_-_changes_to_pu_elements.pdf"
AZERBAIJAN_NEW = PDF_BASE + "2026_azerbaijan_grand_prix_-_new_pu_elements_for_this_competition.pdf"
AZERBAIJAN_DECISION = PDF_BASE + "2026_azerbaijan_grand_prix_-_infringement_-_car_14_-_pu_element.pdf"


class FakeFetcher:
    """Serves fixture pages; PDFs are served as their extracted text."""

    def __init__(self, pages: dict[str, str] | None = None, documents: dict[str, object] | None = None):
        self.pages = {
            DOCUMENTS_INDEX_URL: fixture("documents_index.html"),
            SEASON_URL: fixture("season_page.html"),
            EVENT_URL.format("Azerbaijan%20Grand%20Prix"): fixture("event_page_drupal.html"),
            EVENT_URL.format("Singapore%20Grand%20Prix"): fixture("event_page_flat.html"),
            EVENT_URL.format("United%20States%20Grand%20Prix"): "<html>no rows yet</html>",
            **(pages or {}),
        }
        self.documents = {
            SINGAPORE_USAGE: fixture("usage_singapore.txt").encode(),
            SINGAPORE_DECISION: fixture("decision_singapore_car63.txt").encode(),
            AZERBAIJAN_NEW: fixture("new_elements_usa.txt").encode(),
            AZERBAIJAN_DECISION: fixture("decision_usa_car43.txt").encode(),
            **(documents or {}),
        }
        self.visited: list[str] = []

    def page(self, url):
        self.visited.append(url)
        if url not in self.pages:
            raise FetchError(f"GET {url} failed: 404")
        return self.pages[url]

    def document(self, url):
        self.visited.append(url)
        result = self.documents[url]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def text_pdfs(monkeypatch):
    """The fake fetcher's "PDFs" are already text."""

    def extract(data):
        if data == b"corrupt":
            raise DocumentParseError("PDF text could not be extracted: broken")
        return data.decode()

    monkeypatch.setattr(ingest, "pdf_text", extract)


def test_the_first_run_collects_every_event(store_dir, text_pdfs):
    fetcher = FakeFetcher()
    report = ingest_season(2026, fetcher)

    assert set(report.events_checked) == {"Azerbaijan Grand Prix", "Singapore Grand Prix", "United States Grand Prix"}
    assert len(report.added) == 4  # the "Power Unit Information" and summons rows are not collected
    assert report.ok
    assert report.written
    stored = {document.url: document for document in load_season(2026).documents}
    assert set(stored) == {SINGAPORE_USAGE, SINGAPORE_DECISION, AZERBAIJAN_NEW, AZERBAIJAN_DECISION}
    assert stored[SINGAPORE_USAGE].sha256
    assert stored[SINGAPORE_USAGE].published == "09.10.26 10:08"
    # The run also records the allowances the reports state, with their source.
    assert report.allowances_changed == ("ES", "EXH", "ICE", "PU-ANC", "PU-CE", "TC")
    ice = load_allowances(2026)["ICE"]
    assert ice.allowance == 4
    assert ice.document_url == AZERBAIJAN_NEW


def test_a_quiet_run_only_reads_the_current_event(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    fetcher = FakeFetcher()
    report = ingest_season(2026, fetcher)

    assert report.events_checked == ("United States Grand Prix",)
    assert report.added == ()
    assert not report.written
    assert report.allowances_changed == ()
    assert fetcher.visited == [DOCUMENTS_INDEX_URL, SEASON_URL, EVENT_URL.format("United%20States%20Grand%20Prix")]


def test_all_events_rereads_every_event_page(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    report = ingest_season(2026, FakeFetcher(), all_events=True)
    assert len(report.events_checked) == 3
    assert report.added == ()


def test_failures_are_kept_reported_and_retried(store_dir, text_pdfs):
    broken = FakeFetcher(
        documents={
            SINGAPORE_DECISION: FetchError("GET … failed: 503"),
            AZERBAIJAN_NEW: b"corrupt",
            AZERBAIJAN_DECISION: b"From The Stewards\nThe following Power Unit elements have been used:\n",
        },
    )
    report = ingest_season(2026, broken)

    assert not report.ok
    assert len(report.failed) == 3
    stored = {document.url: document for document in load_season(2026).documents}
    assert stored[SINGAPORE_DECISION].text is None
    assert "download failed" in stored[SINGAPORE_DECISION].error
    assert stored[AZERBAIJAN_NEW].error.startswith("PDF text could not be extracted")
    # A parse failure keeps the text and no stored error: the parser runs again at read time.
    assert stored[AZERBAIJAN_DECISION].text is not None
    assert stored[AZERBAIJAN_DECISION].error is None

    retry = ingest_season(2026, FakeFetcher(), all_events=True)
    assert set(retry.added) == {
        "Doc 20 - Infringement - Car 63 - Changes to PU elements",
        "Doc 14 - New PU Elements for this Competition",
    }


def test_a_document_the_fia_takes_down_is_marked_withdrawn(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    rows = fixture("event_page_flat.html").split('<li class="document-row')
    without_decision = '<li class="document-row'.join(row for row in rows if "car_63_-_changes" not in row)
    report = ingest_season(
        2026,
        FakeFetcher(pages={EVENT_URL.format("Singapore%20Grand%20Prix"): without_decision}),
        all_events=True,
    )

    assert report.withdrawn == ("Doc 20 - Infringement - Car 63 - Changes to PU elements",)
    stored = {document.url: document for document in load_season(2026).documents}
    assert stored[SINGAPORE_DECISION].withdrawn == WITHDRAWN_UNLISTED
    assert stored[SINGAPORE_USAGE].withdrawn is None


def test_a_document_the_page_marks_withdrawn_is_withdrawn(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    marked = fixture("event_page_flat.html").replace(
        "Doc 20 - Infringement - Car 63 - Changes to PU elements", "Doc 20 - Infringement - Car 63 (Withdrawn)"
    )
    ingest_season(2026, FakeFetcher(pages={EVENT_URL.format("Singapore%20Grand%20Prix"): marked}), all_events=True)

    decision = next(document for document in load_season(2026).documents if document.url == SINGAPORE_DECISION)
    assert decision.title == "Doc 20 - Infringement - Car 63 (Withdrawn)"
    assert decision.withdrawn == "marked on the FIA event page: Doc 20 - Infringement - Car 63 (Withdrawn)"


def test_a_page_cut_short_does_not_withdraw_what_it_no_longer_reaches(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    rows = fixture("event_page_flat.html").split('<li class="document-row')
    # Only documents 20 and 22 remain: document 10 is below everything listed.
    later_only = '<li class="document-row'.join(
        row for row in rows if "used_per_driver" not in row and "power_unit_information" not in row
    )
    report = ingest_season(
        2026, FakeFetcher(pages={EVENT_URL.format("Singapore%20Grand%20Prix"): later_only}), all_events=True
    )
    assert report.withdrawn == ()
    usage = next(document for document in load_season(2026).documents if document.url == SINGAPORE_USAGE)
    assert usage.withdrawn is None


def test_a_withdrawal_notice_is_collected_even_without_pu_in_its_title(store_dir, text_pdfs):
    notice_url = PDF_BASE + "2026_singapore_grand_prix_-_withdrawal_of_document_20.pdf"
    notice_row = (
        f'<li class="document-row key-99"><a href="{notice_url.removeprefix("https://www.fia.com")}">'
        '<div class="title">Doc 99 - Withdrawal of Document 20</div>'
        '<div class="published"><span class="date-display-single">12.10.26 09:00</span></div></a></li>'
    )
    page = fixture("event_page_flat.html").replace("<ul>", "<ul>" + notice_row, 1)
    notice = (
        b"2026 SINGAPORE GRAND PRIX\n09 - 11 October 2026\nFrom The Stewards\nDocument 99\nDocument 20 is withdrawn."
    )
    report = ingest_season(
        2026,
        FakeFetcher(pages={EVENT_URL.format("Singapore%20Grand%20Prix"): page}, documents={notice_url: notice}),
    )
    assert "Doc 99 - Withdrawal of Document 20" in report.added


def test_an_event_page_that_lists_nothing_withdraws_nothing(store_dir, text_pdfs):
    ingest_season(2026, FakeFetcher())
    blank = {EVENT_URL.format("Singapore%20Grand%20Prix"): "<html>maintenance</html>"}
    report = ingest_season(2026, FakeFetcher(pages=blank), all_events=True)
    assert report.withdrawn == ()
    assert all(document.withdrawn is None for document in load_season(2026).documents)


def test_a_season_the_index_does_not_list_is_an_error(store_dir, text_pdfs):
    with pytest.raises(IngestError, match="lists no 2031 season"):
        ingest_season(2031, FakeFetcher())


def test_a_season_page_without_events_is_an_error(store_dir, text_pdfs):
    with pytest.raises(IngestError, match="links no events"):
        ingest_season(2026, FakeFetcher(pages={SEASON_URL: "<html></html>"}))


def test_an_unreachable_event_page_aborts_without_writing(store_dir, text_pdfs):
    fetcher = FakeFetcher()
    del fetcher.pages[EVENT_URL.format("Singapore%20Grand%20Prix")]
    with pytest.raises(FetchError):
        ingest_season(2026, fetcher)
    assert load_season(2026).documents == ()


def test_a_failed_store_write_is_reported(store_dir, text_pdfs, monkeypatch):
    monkeypatch.setattr(
        sources.document_store,
        "write",
        lambda name, payload: WriteResult(ok=False, durable=False, error="disk full"),
    )
    report = ingest_season(2026, FakeFetcher())
    assert not report.written
    assert report.write_error == "disk full"
    assert not report.ok
