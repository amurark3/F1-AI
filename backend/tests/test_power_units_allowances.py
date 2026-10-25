"""Tests for the stored allowances, the ingest status record, and what the screen says about both.

Allowances are data, not code: the ingest job keeps them at the latest figure
the FIA's reports state, a hand-pinned value overrides it, and the screen
reports any disagreement. The status record is the screen's "last checked".
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.data.power_units import allowances, status
from app.data.power_units.allowances import (
    SOURCE_FIA,
    SOURCE_MANUAL,
    AllowanceEntry,
    StatedAllowance,
    latest_statements,
    load_allowances,
    pin,
    refresh_from_reports,
    save_allowances,
    statements_in,
    unpin,
)
from app.data.power_units.sources import SeasonSources, SourcesUnavailableError
from app.data.power_units.status import (
    OUTCOME_ABORTED,
    OUTCOME_OK,
    IngestStatus,
    load_status,
    record_status,
)
from app.data.store import DOCUMENT_POWER_UNIT_ALLOWANCES, DOCUMENT_POWER_UNIT_STATUS, document_store
from app.data.store_types import ReadResult
from app.services.power_units import provenance
from app.services.power_units.evidence import AllowanceStatement, DocumentRef, Evidence
from tests.power_units_support import allowance_entries, fixture, source

NOW = "2026-10-24T09:00:00+00:00"


@pytest.fixture
def store_dir(isolated_data_dir):
    return isolated_data_dir


def corpus(*documents) -> SeasonSources:
    return SeasonSources(year=2026, documents=documents)


# ---------------------------------------------------------------------------
# statements
# ---------------------------------------------------------------------------


def test_statements_come_from_current_new_element_reports_only():
    found = statements_in(
        corpus(
            source("United States Grand Prix", "Doc 13", "new_elements_usa.txt"),
            source("Italian Grand Prix", "Doc 13", "new_elements_italy.txt", withdrawn="replaced"),
            source("Singapore Grand Prix", "Doc 10", "usage_singapore.txt"),
            source("Singapore Grand Prix", "Doc 11", "usage_singapore.txt", text=None),
            source(
                "Singapore Grand Prix",
                "Doc 12",
                "usage_singapore.txt",
                text="From The FIA Formula 1 Technical Delegate\\nPU Elements used per Driver\\n",
            ),
        ),
    )
    assert {item.code: item.allowance for item in found} == {
        "ICE": 4,
        "TC": 4,
        "EXH": 4,
        "ES": 3,
        "PU-CE": 3,
        "PU-ANC": 6,
    }
    assert all(item.race_day == date(2026, 10, 25) for item in found)


def test_the_latest_statement_wins_over_an_earlier_base_figure():
    early = StatedAllowance("PU-CE", 2, date(2026, 3, 8), 34, "Doc 34", "u-aus")
    later = StatedAllowance("PU-CE", 3, date(2026, 9, 6), 13, "Doc 13", "u-ita")
    undated = StatedAllowance("ICE", 4, None, None, "Doc ?", "u-x")
    assert latest_statements([later, early, undated]) == {"PU-CE": later, "ICE": undated}


# ---------------------------------------------------------------------------
# the stored document
# ---------------------------------------------------------------------------


def test_allowances_round_trip_and_other_seasons_survive(store_dir):
    save_allowances(2025, {"ICE": AllowanceEntry("ICE", 4, SOURCE_FIA, None, None, None, NOW)})
    save_allowances(2026, allowance_entries())

    assert load_allowances(2025)["ICE"].allowance == 4
    assert load_allowances(2026) == allowance_entries()


def test_malformed_entries_are_dropped_and_odd_fields_cleaned(store_dir):
    document_store.write(
        DOCUMENT_POWER_UNIT_ALLOWANCES,
        {
            "seasons": {
                "2026": {
                    "elements": {
                        "ICE": {"allowance": 4, "source": "rumour", "note": 7},
                        "TC": {"allowance": -1},
                        "EXH": "four",
                        "ES": {"allowance": "3"},
                    },
                },
            },
        },
    )
    assert load_allowances(2026) == {"ICE": AllowanceEntry("ICE", 4, SOURCE_FIA, None, None, None, "", None)}
    document_store.write(DOCUMENT_POWER_UNIT_ALLOWANCES, {"seasons": {"2026": {"elements": ["no"]}}})
    assert load_allowances(2026) == {}
    document_store.write(DOCUMENT_POWER_UNIT_ALLOWANCES, {"seasons": []})
    assert load_allowances(2026) == {}


def test_an_unreadable_allowance_document_is_an_error(store_dir, monkeypatch):
    monkeypatch.setattr(allowances.document_store, "read", lambda name: ReadResult(ok=False, error="down"))
    with pytest.raises(SourcesUnavailableError, match="down"):
        load_allowances(2026)
    monkeypatch.setattr(allowances.document_store, "read", lambda name: ReadResult(ok=False))
    with pytest.raises(SourcesUnavailableError, match="could not be read"):
        load_allowances(2026)


# ---------------------------------------------------------------------------
# keeping them current
# ---------------------------------------------------------------------------

USA = source("United States Grand Prix", "Doc 13", "new_elements_usa.txt")


def test_a_first_refresh_records_every_stated_allowance_with_its_document(store_dir):
    changed = refresh_from_reports(corpus(USA), NOW)
    stored = load_allowances(2026)

    assert changed == ("ES", "EXH", "ICE", "PU-ANC", "PU-CE", "TC")
    assert stored["ICE"].allowance == 4
    assert stored["ICE"].source == SOURCE_FIA
    assert stored["ICE"].document_url == USA.url
    assert stored["ICE"].stated_on == "2026-10-25"
    assert "MGU-K" not in stored  # the Austin report fitted no MGU-K, so stated none


def test_a_refresh_with_nothing_new_writes_nothing(store_dir, monkeypatch):
    refresh_from_reports(corpus(USA), NOW)
    writes = []
    monkeypatch.setattr(allowances, "save_allowances", lambda year, entries: writes.append(entries))
    assert refresh_from_reports(corpus(USA), "later") == ()
    assert writes == []


def test_a_changed_figure_is_taken_and_a_newer_same_figure_moves_the_pointer(store_dir):
    italy = source("Italian Grand Prix", "Doc 13", "new_elements_italy.txt")
    refresh_from_reports(corpus(italy), NOW)
    raised = fixture("new_elements_usa.txt").replace("of the four (4) new", "of the five (5) new", 1)
    changed = refresh_from_reports(corpus(italy, replace(USA, text=raised)), "later")

    stored = load_allowances(2026)
    assert changed == ("ICE",)
    assert (stored["ICE"].allowance, stored["ICE"].updated_at) == (5, "later")
    # Same figure, newer report: the source moves on, the change date does not.
    assert (stored["TC"].document_url, stored["TC"].updated_at) == (USA.url, NOW)


def test_a_pinned_allowance_is_never_overwritten(store_dir):
    pin(2026, "ICE", 5, "first-year manufacturer bonus, B8.2.3b")
    assert refresh_from_reports(corpus(USA), NOW) == ("ES", "EXH", "PU-ANC", "PU-CE", "TC")
    ice = load_allowances(2026)["ICE"]
    assert (ice.allowance, ice.source, ice.note) == (5, SOURCE_MANUAL, "first-year manufacturer bonus, B8.2.3b")

    unpin(2026, "ICE")
    assert "ICE" not in load_allowances(2026)
    assert refresh_from_reports(corpus(USA), NOW) == ("ICE",)


# ---------------------------------------------------------------------------
# ingest status
# ---------------------------------------------------------------------------


def test_status_records_runs_and_carries_the_last_change(store_dir):
    assert load_status(2026) is None
    record_status(IngestStatus(2026, "t1", OUTCOME_OK, added=3), changed=True)
    record_status(IngestStatus(2026, "t2", OUTCOME_ABORTED, error="fia.com could not be read"), changed=False)
    record_status(IngestStatus(2025, "t0", OUTCOME_OK), changed=False)

    latest = load_status(2026)
    assert latest == IngestStatus(2026, "t2", OUTCOME_ABORTED, error="fia.com could not be read", changed_at="t1")
    assert load_status(2025).changed_at is None


def test_an_unreadable_or_malformed_status_reads_as_none(store_dir, monkeypatch):
    document_store.write(DOCUMENT_POWER_UNIT_STATUS, {"seasons": {"2026": {"checked_at": 5}}})
    assert load_status(2026) is None
    document_store.write(
        DOCUMENT_POWER_UNIT_STATUS, {"seasons": {"2026": {"checked_at": "t", "outcome": "ok", "added": "x"}}}
    )
    assert load_status(2026).added == 0
    monkeypatch.setattr(status.document_store, "read", lambda name: ReadResult(ok=False, error="down"))
    assert load_status(2026) is None


# ---------------------------------------------------------------------------
# what the screen says
# ---------------------------------------------------------------------------

MOMENT = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("recorded", "stale"),
    [
        (IngestStatus(2026, "2026-10-24T08:17:00+00:00", OUTCOME_OK, changed_at="2026-10-23T21:40:00+00:00"), False),
        (IngestStatus(2026, (MOMENT - timedelta(hours=30)).isoformat(), OUTCOME_OK), True),
        (IngestStatus(2026, "2026-10-24T08:17:00", OUTCOME_OK), False),
        (IngestStatus(2026, "not a time", OUTCOME_OK), True),
        (None, True),
    ],
)
def test_freshness_flags_a_check_more_than_a_day_old(monkeypatch, recorded, stale):
    monkeypatch.setattr(provenance, "load_status", lambda year: recorded)
    fresh = provenance.freshness(2026, "corpus-time", MOMENT)
    assert fresh["stale"] is stale
    assert fresh["checked_at"] == (recorded.checked_at if recorded else None)
    assert fresh["changed_at"] == ((recorded and recorded.changed_at) or "corpus-time")


def test_element_payload_carries_each_allowance_and_its_source():
    payload = provenance.element_payload(2026, allowance_entries())
    ice = payload[0]
    assert (ice["code"], ice["allowance"]) == ("ICE", 4)
    assert ice["allowance_source"]["kind"] == SOURCE_FIA
    assert ice["allowance_source"]["title"] == "Doc 13 - New PU Elements for this Competition"
    unknown = provenance.element_payload(2026, {})[0]
    assert (unknown["allowance"], unknown["allowance_source"]) == (None, None)


def statement(code: str, count: int) -> AllowanceStatement:
    return AllowanceStatement(18, code, count, DocumentRef("Doc 13 - New PU Elements", "u", "", 13))


def evidence(*statements: AllowanceStatement) -> Evidence:
    return Evidence((), (), statements, (), (), (), None)


def test_allowance_warnings_name_every_disagreement():
    pinned = AllowanceEntry("ICE", 5, SOURCE_MANUAL, None, None, None, NOW, "why")
    entries = allowance_entries(ICE=pinned, TC=replace(allowance_entries()["TC"], allowance=3))
    del entries["ES"]
    warnings = provenance.allowance_warnings(
        evidence(statement("ICE", 4), statement("TC", 4), statement("ES", 3), statement("EXH", 4)),
        entries,
    )
    assert warnings == [
        "ICE is pinned at 5 by hand, while the FIA's latest report (Doc 13 - New PU Elements) states 4.",
        "The stored TC allowance is 3, while the FIA's latest report (Doc 13 - New PU Elements) states 4; "
        "it updates on the next collection run.",
        "No ES allowance is stored yet, so no ES unit is marked as beyond it; "
        "the FIA's latest report (Doc 13 - New PU Elements) states 3.",
    ]
