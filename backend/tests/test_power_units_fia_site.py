"""Tests for FIA site discovery and polite fetching (app.data.power_units.fia_site).

The HTML fixtures are trimmed from real fia.com pages in both markups the site
serves — the flat one and the Drupal ``field-item`` one — because a parser
written against only one of them silently found nothing on the other.
"""

from pathlib import Path

import pytest
import requests

from app.data.power_units import fia_site
from app.data.power_units.fia_site import (
    FetchError,
    PoliteFetcher,
    active_event,
    is_power_unit_title,
    listed_documents,
    pdf_text,
    season_events,
    season_page_url,
)
from app.data.power_units.text import DocumentParseError

FIXTURES = Path(__file__).parent / "fixtures" / "power_units"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def tiny_pdf(text: str) -> bytes:
    """A minimal one-page PDF whose only content is ``text``."""
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return body


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_season_page_url_is_read_from_the_index():
    url = season_page_url(fixture("documents_index.html"), 2026)
    assert url == f"{fia_site.DOCUMENTS_INDEX_URL}/season/season-2026-2072"
    assert season_page_url(fixture("documents_index.html"), 2031) is None


def test_season_events_and_the_active_one():
    html = fixture("season_page.html")
    events = season_events(html)
    assert [event.name for event in events] == [
        "Azerbaijan Grand Prix",
        "Singapore Grand Prix",
        "United States Grand Prix",
    ]
    assert events[2].url.endswith("/season/season-2026-2072/event/United%20States%20Grand%20Prix")
    assert active_event(html) == "United States Grand Prix"
    assert active_event("<html></html>") is None


def test_listed_documents_in_the_flat_markup():
    rows = listed_documents(fixture("event_page_flat.html"), "Singapore Grand Prix")
    titles = [row.title for row in rows]
    assert "Doc 20 - Infringement - Car 63 - Changes to PU elements" in titles
    assert "Doc 10 - PU Elements used per Driver up to now" in titles
    assert len(rows) == 4  # the row with no title is skipped
    decision = next(row for row in rows if "Car 63" in row.title)
    assert decision.url.startswith("https://www.fia.com/system/files/decision-document/")
    assert decision.published == "09.10.26 14:03"
    assert decision.event == "Singapore Grand Prix"


def test_listed_documents_in_the_drupal_markup():
    rows = listed_documents(fixture("event_page_drupal.html"), "Azerbaijan Grand Prix")
    assert [row.title for row in rows] == [
        "Doc 34 - Infringement - Car 14 - PU element",
        "Doc 14 - New PU Elements for this Competition",
    ]
    assert all(row.published for row in rows)


def test_listed_document_without_a_published_date_still_lists():
    html = '<li class="document-row"><a href="/a.pdf"><div class="title">Doc 1 - PU</div><div class="published"></div></a></li>'
    assert listed_documents(html, "E")[0].published == ""


@pytest.mark.parametrize(
    ("title", "wanted"),
    [
        ("Doc 20 - Infringement - Car 63 - Changes to PU elements", True),
        ("Doc 8 - PU elements used per driver up to now", True),
        ("Doc 1 - New Power Unit elements", True),
        ("Doc 8 - Power Unit Information", False),
        ("Doc 22 - Summons - Car 44 - Alleged Yellow Flag Infringement", False),
    ],
)
def test_is_power_unit_title(title, wanted):
    assert is_power_unit_title(title) is wanted


# ---------------------------------------------------------------------------
# PDF text
# ---------------------------------------------------------------------------


def test_pdf_text_extracts_every_page():
    assert "Doc 14 PU elements" in pdf_text(tiny_pdf("Doc 14 PU elements"))


def test_pdf_text_refuses_a_file_that_is_not_a_pdf():
    with pytest.raises(DocumentParseError, match="could not be extracted"):
        pdf_text(b"<html>not a pdf</html>")


# ---------------------------------------------------------------------------
# polite fetching
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, content: bytes, error: Exception | None = None):
        self.content = content
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error


def http_error(status: int, retry_after: str | None = None) -> FakeResponse:
    """A response whose ``raise_for_status`` raises an HTTPError carrying it, as requests does."""
    answer = requests.Response()
    answer.status_code = status
    if retry_after is not None:
        answer.headers["Retry-After"] = retry_after
    return FakeResponse(b"", requests.HTTPError(f"{status} error", response=answer))


class FakeSession:
    """Serves each URL's result; a list is served one entry per request, in order."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[tuple[str, dict, int]] = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        result = self.responses[url]
        if isinstance(result, list):
            result = result.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def clock(monkeypatch):
    """A controllable monotonic clock; ``sleeps`` records every wait."""
    state = {"now": 100.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(fia_site.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(fia_site.time, "sleep", sleep)
    return state


def test_requests_identify_themselves_and_wait_the_crawl_delay(clock):
    session = FakeSession({"u1": FakeResponse(b"one"), "u2": FakeResponse("twö".encode())})
    fetcher = PoliteFetcher(session=session, delay_seconds=10)

    assert fetcher.page("u1") == "one"
    clock["now"] += 3  # three seconds pass before the next request
    assert fetcher.page("u2") == "twö"

    assert clock["sleeps"] == [7]
    assert fetcher.requests_made == 2
    url, headers, timeout = session.calls[0]
    assert url == "u1"
    assert "F1-AI" in headers["User-Agent"]
    assert timeout == fia_site.REQUEST_TIMEOUT_SECONDS


def test_no_wait_once_the_delay_has_already_passed(clock):
    session = FakeSession({"u": FakeResponse(b"x")})
    fetcher = PoliteFetcher(session=session, delay_seconds=10)
    fetcher.page("u")
    clock["now"] += 30
    fetcher.page("u")
    assert clock["sleeps"] == []


RESET = requests.ConnectionError(ConnectionResetError(104, "Connection reset by peer"))


@pytest.mark.parametrize(
    "transient",
    [RESET, requests.Timeout("read timed out"), requests.exceptions.ChunkedEncodingError("broken"), http_error(503)],
)
def test_a_transient_failure_is_tried_again_after_a_longer_pause(clock, transient):
    fetcher = PoliteFetcher(session=FakeSession({"u": [transient, FakeResponse(b"ok")]}), delay_seconds=10)
    assert fetcher.page("u") == "ok"
    assert fetcher.requests_made == 2
    assert clock["sleeps"] == [30.0]  # the backoff alone: it already outlasts the crawl delay


def test_a_failure_that_persists_gives_up_after_three_attempts(clock):
    fetcher = PoliteFetcher(session=FakeSession({"u": [RESET, RESET, RESET]}), delay_seconds=10)
    with pytest.raises(FetchError, match="GET u failed after 3 attempts"):
        fetcher.page("u")
    assert fetcher.requests_made == 3
    assert clock["sleeps"] == [30.0, 90.0]


@pytest.mark.parametrize("failure", [http_error(404), http_error(403), FakeResponse(b"", requests.HTTPError("bare"))])
def test_a_definite_answer_is_not_retried(clock, failure):
    fetcher = PoliteFetcher(session=FakeSession({"u": failure}), delay_seconds=10)
    with pytest.raises(FetchError, match="GET u failed: "):
        fetcher.page("u")
    assert fetcher.requests_made == 1
    assert clock["sleeps"] == []


def test_retry_after_is_honoured_when_sane(clock):
    asked = PoliteFetcher(session=FakeSession({"u": [http_error(429, "120"), FakeResponse(b"ok")]}))
    assert asked.page("u") == "ok"
    assert clock["sleeps"] == [120.0]

    clock["sleeps"].clear()
    short = PoliteFetcher(session=FakeSession({"u": [http_error(503, "5"), FakeResponse(b"ok")]}))
    assert short.page("u") == "ok"
    assert clock["sleeps"] == [30.0]

    clock["sleeps"].clear()
    unparseable = PoliteFetcher(session=FakeSession({"u": [http_error(503, "Fri, 30 Oct"), FakeResponse(b"ok")]}))
    assert unparseable.page("u") == "ok"
    assert clock["sleeps"] == [30.0]


def test_an_absurd_retry_after_fails_instead_of_stalling_the_job(clock):
    fetcher = PoliteFetcher(session=FakeSession({"u": http_error(429, "3600")}))
    with pytest.raises(FetchError, match="429 error"):
        fetcher.page("u")
    assert clock["sleeps"] == []


def test_documents_come_from_the_cache_when_it_holds_them(clock, tmp_path):
    cached = tmp_path / "cache" / "a doc.pdf"
    cached.parent.mkdir()
    cached.write_bytes(b"cached")
    session = FakeSession({"https://x/b.pdf": FakeResponse(b"fresh")})
    fetcher = PoliteFetcher(session=session, cache_dir=tmp_path / "cache")

    assert fetcher.document("https://x/a%20doc.pdf") == b"cached"
    assert fetcher.document("https://x/b.pdf") == b"fresh"
    assert (tmp_path / "cache" / "b.pdf").read_bytes() == b"fresh"
    assert fetcher.requests_made == 1


def test_documents_without_a_cache_are_always_downloaded(clock):
    fetcher = PoliteFetcher(session=FakeSession({"https://x/b.pdf": FakeResponse(b"pdf")}))
    assert fetcher.document("https://x/b.pdf") == b"pdf"


def test_a_fetcher_builds_its_own_session_by_default():
    assert PoliteFetcher().requests_made == 0
