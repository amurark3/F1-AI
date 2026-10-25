"""Tests for the power-unit screen's payload, end to end over real FIA text.

The corpus is the real 2026 documents in ``fixtures/power_units`` and the f1db
view is the real grid with the real Monza swap (see ``power_units_support``).
What is pinned is what the screen claims:

* **Usage follows the car** — Lawson's Monza elements land on Red Bull #6, not
  on his own Racing Bulls car (Article B8.2.7).
* **Every penalty is a stewards' decision** — places, pit-lane starts and the
  places a pit-lane start made redundant are kept apart.
* **What is not known is said** — a breach the stewards have not ruled on yet is
  ``pending`` at the latest round and ``not_found`` before it; a document that
  cannot be read is listed, not dropped.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.data.f1db_grid import GridSlot
from app.data.power_units.allowances import SOURCE_MANUAL, AllowanceEntry
from app.data.power_units.status import OUTCOME_OK, IngestStatus
from app.data.power_units.text import clean
from app.services.power_units import clear_cache, provenance, report
from app.services.power_units.evidence import gather_evidence
from tests.power_units_support import allowance_entries, corpus, fixture, season_context, source

CHECKED = IngestStatus(2026, "2026-10-24T08:17:00+00:00", OUTCOME_OK, added=2, changed_at="2026-10-23T21:40:00+00:00")


def slot(code: str, position: int | None, qualified: int, penalty: int | None = None, *, pit_lane: bool = False):
    return GridSlot(code, code, "Team", position, qualified, penalty, False, pit_lane)


GRIDS = {
    13: (slot("LAW", None, 14, 35, pit_lane=True), slot("VER", 1, 1)),
    17: (slot("RUS", 22, 6, 60), slot("ALO", None, 17, pit_lane=True)),
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def wired(monkeypatch):
    """Point the report at the fixture corpus, f1db view and grids."""

    def install(sources=None, context=None, allowances=None, checked=CHECKED):
        monkeypatch.setattr(report, "load_season", lambda year: sources or corpus())
        monkeypatch.setattr(report, "load_season_context", lambda year: context or season_context())
        monkeypatch.setattr(report, "starting_grid", lambda year, round_num: GRIDS.get(round_num, ()))
        monkeypatch.setattr(report, "load_allowances", lambda year: allowances or allowance_entries())
        monkeypatch.setattr(provenance, "load_status", lambda year: checked)

    install()
    return install


def car(payload: dict, seat_id: str) -> dict:
    return next(item for item in payload["cars"] if item["seat_id"] == seat_id)


def element(car_payload: dict, code: str) -> dict:
    return next(item for item in car_payload["elements"] if item["code"] == code)


def event(car_payload: dict, round_num: int) -> dict:
    return next(item for item in car_payload["events"] if item["round"] == round_num)


def test_payload_shape_and_provenance(wired):
    # A collected document about something else entirely is read and set aside.
    parc_ferme = source("Italian Grand Prix", "Doc 57 - Infringement - Car 30", "decision_italy_car30_parc_ferme.txt")
    wired(sources=corpus(parc_ferme))
    payload = report.build_power_units(2026)

    assert payload["available"]
    assert payload["as_of"]["round"] == 18
    assert payload["as_of"]["title"] == "Doc 15 - Infringement - Car 5 - PU elements"
    assert [item["code"] for item in payload["elements"]] == ["ICE", "TC", "EXH", "MGU-K", "ES", "PU-CE", "PU-ANC"]
    assert payload["elements"][0]["allowance"] == 4
    assert payload["elements"][0]["allowance_source"]["kind"] == "fia_report"
    assert payload["freshness"]["checked_at"] == CHECKED.checked_at
    assert payload["freshness"]["changed_at"] == CHECKED.changed_at
    assert payload["freshness"]["outcome"] == OUTCOME_OK
    assert payload["withdrawn"] == []
    assert [item["round"] for item in payload["rounds"] if item["has_documents"]] == [13, 17, 18]
    assert len(payload["cars"]) == 22
    assert payload["unread"] == []
    assert payload["warnings"] == []
    assert len(payload["notes"]) == 4


def test_a_stand_in_adds_to_the_car_he_drives(wired):
    payload = report.build_power_units(2026)
    red_bull = car(payload, "red-bull-6")

    assert red_bull["car_number"] == 6
    assert red_bull["driver"]["name"] == "Isack Hadjar"
    assert {driver["name"]: driver["rounds"] for driver in red_bull["drivers"]} == {
        "Isack Hadjar": [1, 17],
        "Liam Lawson": [13],
    }
    assert element(red_bull, "ICE")["used"] == 7
    assert element(red_bull, "ICE")["over_by"] == 3

    monza = event(red_bull, 13)
    assert monza["stand_in"]
    assert monza["driver"]["name"] == "Liam Lawson"
    assert {(part["code"], part["number"]) for part in monza["new_parts"]} == {
        ("ICE", 6),
        ("TC", 6),
        ("EXH", 6),
        ("MGU-K", 4),
        ("PU-ANC", 7),
    }
    assert all(part["beyond_allowance"] and part["source"] == "report" for part in monza["new_parts"])
    assert monza["penalty_status"] == "decided"
    assert monza["decisions"][0]["places"] == 35
    assert monza["decisions"][0]["session"] == "Free Practice 3"
    assert monza["grid"] == {
        "status": "official",
        "qualified": 14,
        "started": None,
        "pit_lane": True,
        "back_of_grid": False,
        "penalty_positions": 35,
    }
    assert red_bull["penalties"]["grid_places"] == 35

    lawsons_own = car(payload, "racing-bulls-30")
    assert element(lawsons_own, "ICE")["used"] == 4
    assert all(not item["decisions"] for item in lawsons_own["events"])


def test_units_without_a_named_round_are_placed_between_reports(wired):
    hadjar = car(report.build_power_units(2026), "red-bull-6")
    ice = {part["number"]: part for part in element(hadjar, "ICE")["parts"]}
    # Counted going into Singapore, named by no report: arrived somewhere in rounds 1–16.
    assert ice[7]["round"] is None
    assert ice[7]["window"] == [1, 16]
    assert ice[7]["source"] == "derived"
    assert ice[6]["round"] == 13


def test_pit_lane_decision_counts_no_places(wired):
    alonso = car(report.build_power_units(2026), "aston-martin-14")
    singapore = event(alonso, 17)

    assert singapore["decisions"][0]["outcome"] == "pit_lane"
    assert singapore["decisions"][0]["nominal_places"] == 5
    assert singapore["grid"]["pit_lane"]
    assert alonso["penalties"]["pit_lane_starts"] == 1
    assert alonso["penalties"]["grid_places"] == 0


def test_an_unruled_breach_is_pending_at_the_latest_round(wired):
    payload = report.build_power_units(2026)
    lindblad = car(payload, "racing-bulls-41")
    austin = event(lindblad, 18)

    assert austin["penalty_status"] == "pending"
    assert austin["grid"] == {"status": "pending"}
    assert lindblad["penalties"]["pending"] == 1

    bortoleto = event(car(payload, "audi-5"), 18)
    assert bortoleto["penalty_status"] == "decided"
    assert bortoleto["decisions"][0]["places"] == 20


def test_an_unruled_breach_at_an_earlier_round_is_not_found(wired):
    antonelli = car(report.build_power_units(2026), "mercedes-12")
    monza = event(antonelli, 13)

    assert monza["penalty_status"] == "not_found"
    assert monza["grid"] == {"status": "not_listed"}
    assert antonelli["penalties"]["not_found"] == 1


def test_unreadable_and_withdrawn_documents(wired):
    broken = source("Singapore Grand Prix", "Doc 99 - PU elements", "usage_singapore.txt", url="u-broken", text=None)
    gone = source(
        "Italian Grand Prix", "Doc 41", "decision_italy_car30.txt", url="u-gone", withdrawn="no longer listed"
    )
    wired(sources=replace(corpus(), documents=(*corpus().documents, broken, gone)))
    payload = report.build_power_units(2026)

    assert payload["unread"] == [
        {
            "title": "Doc 99 - PU elements",
            "url": "u-broken",
            "event": "Singapore Grand Prix",
            "reason": "no text was extracted",
        },
    ]
    assert car(payload, "red-bull-6")["penalties"]["decisions"] == 1
    assert payload["withdrawn"] == [{"title": "Doc 41", "url": "u-gone", "reason": "no longer listed"}]


def test_a_notice_rescinding_a_decision_removes_its_penalty(wired):
    notice = source(
        "Italian Grand Prix",
        "Doc 90 - Withdrawal of Document 41",
        "decision_italy_car30.txt",
        url="u-notice",
        text="2026 ITALIAN GRAND PRIX\n04 - 06 September 2026\nFrom The Stewards\nDocument 90\n"
        "The decision in Document 41 is rescinded following a right of review.\n",
    )
    wired(sources=corpus(notice))
    payload = report.build_power_units(2026)
    red_bull = car(payload, "red-bull-6")

    assert red_bull["penalties"]["grid_places"] == 0
    assert event(red_bull, 13)["decisions"] == []
    assert payload["withdrawn"] == [
        {
            "title": "Doc 41 - Infringement - Car 30 - Change to PU elements",
            "url": "https://www.fia.com/docs/decision_italy_car30.txt",
            "reason": "withdrawn by Doc 90 - Withdrawal of Document 41",
        },
    ]


def test_a_corrected_decision_replaces_the_original(wired):
    corrected = fixture("decision_usa_car43.txt").replace("Document 14", "Document 16")
    extra = source(
        "United States Grand Prix",
        "Doc 16 - Corrected Infringement - Car 43 - PU element",
        "decision_usa_car43.txt",
        url="u-corrected",
        text=corrected,
    )
    wired(sources=corpus(extra))
    colapinto = car(report.build_power_units(2026), "alpine-43")
    decisions = event(colapinto, 18)["decisions"]

    assert [item["title"] for item in decisions] == ["Doc 16 - Corrected Infringement - Car 43 - PU element"]
    assert colapinto["penalties"]["grid_places"] == 10
    assert report.build_power_units(2026)["withdrawn"] == [
        {
            "title": "Doc 14 - Infringement - Car 43 - PU element",
            "url": "https://www.fia.com/docs/decision_usa_car43.txt",
            "reason": "replaced by Doc 16 - Corrected Infringement - Car 43 - PU element",
        },
    ]


def test_a_round_before_f1db_names_anyone_has_no_driver(wired):
    wired(context=season_context(entry_rounds=(17,)))
    antonelli = car(report.build_power_units(2026), "mercedes-12")
    monza = event(antonelli, 13)

    assert antonelli["driver"]["name"] == "Kimi Antonelli"
    assert monza["driver"] is None
    assert not monza["stand_in"]
    assert monza["grid"] == {"status": "not_listed"}


def test_a_pinned_allowance_the_fia_contradicts_is_a_warning(wired):
    pinned = AllowanceEntry("ICE", 5, SOURCE_MANUAL, None, None, None, "t", "first-year bonus")
    wired(allowances=allowance_entries(ICE=pinned))
    payload = report.build_power_units(2026)

    assert payload["warnings"] == [
        "ICE is pinned at 5 by hand, while the FIA's latest report "
        "(Doc 13 - New PU Elements for this Competition) states 4.",
    ]
    assert payload["elements"][0]["allowance"] == 5
    assert payload["elements"][0]["allowance_source"]["kind"] == SOURCE_MANUAL
    # Measured against the pinned five, Lindblad's sixth engine is still one too many.
    assert event(car(payload, "racing-bulls-41"), 18)["penalty_status"] == "pending"


def test_without_a_stored_allowance_nothing_is_marked_beyond_it(wired):
    wired(allowances={"TC": allowance_entries()["TC"]})
    payload = report.build_power_units(2026)
    ice = element(car(payload, "red-bull-6"), "ICE")

    assert ice["allowance"] is None
    assert ice["over_by"] == 0
    assert not any(part["beyond_allowance"] for part in ice["parts"])
    assert any(warning.startswith("No ICE allowance is stored yet") for warning in payload["warnings"])


def test_a_stale_check_is_flagged(wired):
    wired(checked=IngestStatus(2026, "2026-01-01T00:00:00+00:00", OUTCOME_OK))
    assert report.build_power_units(2026)["freshness"]["stale"] is True


@pytest.mark.parametrize(
    ("year", "sources", "context", "reason"),
    [
        (2025, None, None, "Power-unit elements for 2025 have not been read"),
        (2026, "empty", None, "No FIA power-unit documents have been collected for 2026 yet"),
        (2026, "usage-free", "empty", "No 2026 line-up is known yet"),
    ],
)
def test_unavailable_states_say_why(wired, year, sources, context, reason):
    if sources == "empty":
        wired(sources=replace(corpus(), documents=()))
    if sources == "usage-free":
        only_decision = source("Italian Grand Prix", "Doc 41", "decision_italy_car30.txt")
        wired(sources=replace(corpus(), documents=(only_decision,)), context=season_context(entry_rounds=()))
    payload = report.build_power_units(year)
    assert not payload["available"]
    assert reason in payload["reason"]
    assert payload["cars"] == []


def test_no_readable_document_still_shows_the_cars(wired):
    unreadable = source("Italian Grand Prix", "Doc 1", "decision_usa_car5.txt", text=None, error="download failed: 503")
    wired(sources=replace(corpus(), documents=(unreadable,)))
    payload = report.build_power_units(2026)

    assert payload["available"]
    assert payload["as_of"] is None
    assert payload["unread"][0]["reason"] == "download failed: 503"
    assert all(not item["events"] for item in payload["cars"])


def test_payloads_are_cached_until_the_ttl_passes(wired, monkeypatch):
    builds = []
    monkeypatch.setattr(report, "_build", lambda year: builds.append(year) or {"available": False, "cars": []})
    clock = {"now": 1000.0}
    monkeypatch.setattr(report.time, "monotonic", lambda: clock["now"])

    report.build_power_units(2026)
    report.build_power_units(2026)
    assert builds == [2026]

    clock["now"] += report.CACHE_TTL_SECONDS + 1
    report.build_power_units(2026)
    assert builds == [2026, 2026]

    clear_cache()
    report.build_power_units(2026)
    assert len(builds) == 3


def test_evidence_records_why_a_document_is_unread():
    context = season_context()
    other_season = source("Abu Dhabi Grand Prix", "Doc 5", "usage_abu_dhabi_2025.txt")
    mgu_h = (
        clean(fixture("usage_abu_dhabi_2025.txt"))
        .replace("2025 ABU DHABI", "2026 SINGAPORE")
        .replace("05 - 07 December 2025", "09 - 11 October 2026")
    )
    unknown_code = source("Singapore Grand Prix", "Doc 6", "usage_abu_dhabi_2025.txt", text=mgu_h)
    moved = clean(fixture("decision_usa_car5.txt")).replace("23 - 25 October 2026", "01 - 03 January 2026")
    nowhere = source("Moon Grand Prix", "Doc 7", "decision_usa_car5.txt", text=moved)
    garbled = source(
        "Singapore Grand Prix",
        "Doc 8",
        "usage_singapore.txt",
        text="From The FIA Formula 1 Technical Delegate\nPU Elements used per Driver up to now\n",
    )
    evidence = gather_evidence(replace(corpus(), documents=(other_season, unknown_code, nowhere, garbled)), context)

    reasons = {item.title: item.reason for item in evidence.unread}
    assert reasons["Doc 5"] == "document is for the 2025 season"
    assert reasons["Doc 6"].startswith("unknown element code(s) MGU-H")
    assert reasons["Doc 7"] == "its event could not be matched to the season calendar"
    assert reasons["Doc 8"] == "usage report has no table heading"
    assert evidence.latest is None


def test_a_document_without_a_cover_date_is_placed_by_its_event_name():
    text = fixture("decision_italy_car30.txt").replace("04 - 06 September 2026", "")
    dated_by_name = source("Italian Grand Prix", "Doc 41", "decision_italy_car30.txt", text=text)
    evidence = gather_evidence(replace(corpus(), documents=(dated_by_name,)), season_context())
    assert [item.round for item in evidence.decisions] == [13]
