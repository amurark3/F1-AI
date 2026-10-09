"""Tests for app.data.session_entries — who is actually entered for a weekend.

The entry list decides which drivers a prediction scores, so the risks are all
about believing the right source for the right length of time:

* **Every entered driver counts.** A driver who set no lap, crashed or was
  disqualified was still entered; dropping them makes the grid incomplete.
* **The newest session wins.** A withdrawal after FP1 is already reflected in
  qualifying, so sessions are tried newest-first.
* **"Not yet known" is not cached like an answer.** Pinning an unavailable
  entry list would hide the real one for hours after the cars ran, so it is
  retried on a short interval while a resolved list lives longer.

FastF1 is replaced at ``fastf1.get_session``; the monotonic clock is patched to
drive cache expiry without sleeping.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data import session_entries as module
from app.data.session_entries import (
    UNAVAILABLE,
    EntryListDriver,
    WeekendEntryList,
    load_weekend_entry_list,
)

pytestmark = pytest.mark.unit

YEAR = 2026
ROUND = 14


def _results(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _driver(code: str, first: str = "", last: str = "", team: str = "Ferrari") -> dict:
    return {"Abbreviation": code, "FirstName": first, "LastName": last, "TeamName": team}


class _FakeSession:
    def __init__(self, results: pd.DataFrame | None, load_error: Exception | None = None):
        self.results = results
        self.load_error = load_error
        self.load_kwargs: dict | None = None

    def load(self, **kwargs):
        self.load_kwargs = kwargs
        if self.load_error is not None:
            raise self.load_error


@pytest.fixture(autouse=True)
def _fresh_cache():
    module.reset_cache()
    yield
    module.reset_cache()


@pytest.fixture
def sessions(monkeypatch):
    """Serve a results frame per session name; record which were asked for."""
    served: dict[str, _FakeSession] = {}
    requested: list[str] = []

    def _get_session(year, round_num, name):
        requested.append(name)
        if name not in served:
            raise ValueError(f"session {name} does not exist for this weekend")
        return served[name]

    monkeypatch.setattr(module.fastf1, "get_session", _get_session)
    return served, requested


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    return now


# ---------------------------------------------------------------------------
# _entries_from_results
# ---------------------------------------------------------------------------


def test_every_row_is_an_entry_whatever_its_classification():
    results = _results(
        _driver("LEC", "Charles", "Leclerc"),
        {**_driver("HAM", "Lewis", "Hamilton"), "Status": "Disqualified"},
    )

    entries = module._entries_from_results(results)

    assert [entry.code for entry in entries] == ["LEC", "HAM"]
    assert entries[0] == EntryListDriver(code="LEC", name="Charles Leclerc", team="Ferrari")


def test_codes_are_normalised_and_duplicates_kept_once():
    entries = module._entries_from_results(_results(_driver(" lec "), _driver("LEC")))

    assert [entry.code for entry in entries] == ["LEC"]


def test_a_row_without_a_code_cannot_be_an_entry():
    entries = module._entries_from_results(
        _results(_driver(""), {**_driver("LEC"), "Abbreviation": None}, _driver("ham"))
    )

    assert [entry.code for entry in entries] == ["HAM"]


def test_a_driver_with_no_name_is_named_by_code_and_a_blank_team_is_empty():
    [entry] = module._entries_from_results(_results({"Abbreviation": "LIN", "FirstName": None, "TeamName": None}))

    assert entry == EntryListDriver(code="LIN", name="LIN", team="")


@pytest.mark.parametrize("results", [None, pd.DataFrame()])
def test_no_results_means_no_entries(results):
    assert module._entries_from_results(results) == ()


# ---------------------------------------------------------------------------
# _load_from_session
# ---------------------------------------------------------------------------


def test_a_session_with_results_is_an_entry_list_named_after_it(sessions):
    served, _ = sessions
    served["Q"] = _FakeSession(_results(_driver("LEC")))

    entry_list = module._load_from_session(YEAR, ROUND, "Q")

    assert entry_list.session == "Q"
    assert entry_list.codes == {"LEC"}
    # Results only: laps, telemetry, weather and messages are never needed here.
    assert served["Q"].load_kwargs == {"laps": False, "telemetry": False, "weather": False, "messages": False}


def test_a_session_that_will_not_load_is_unavailable(sessions):
    served, _ = sessions
    served["FP1"] = _FakeSession(_results(_driver("LEC")), load_error=RuntimeError("no timing data"))

    assert module._load_from_session(YEAR, ROUND, "FP1") is UNAVAILABLE


def test_a_session_with_an_empty_classification_is_unavailable(sessions):
    served, _ = sessions
    served["FP1"] = _FakeSession(pd.DataFrame())

    assert module._load_from_session(YEAR, ROUND, "FP1") is UNAVAILABLE


# ---------------------------------------------------------------------------
# load_weekend_entry_list
# ---------------------------------------------------------------------------


def test_the_newest_session_that_has_run_supplies_the_lineup(sessions):
    """HAM withdrew after FP1; qualifying already knows, so qualifying wins."""
    served, requested = sessions
    served["FP1"] = _FakeSession(_results(_driver("LEC"), _driver("HAM")))
    served["Q"] = _FakeSession(_results(_driver("LEC"), _driver("BEA")))

    entry_list = load_weekend_entry_list(YEAR, ROUND)

    assert entry_list.session == "Q"
    assert entry_list.codes == {"LEC", "BEA"}
    assert requested == ["Q"], "nothing older is loaded once a newer session answers"


def test_sessions_that_have_not_run_are_skipped_in_order(sessions):
    served, requested = sessions
    served["FP2"] = _FakeSession(_results(_driver("LEC")))

    entry_list = load_weekend_entry_list(YEAR, ROUND)

    assert entry_list.session == "FP2"
    assert requested == ["Q", "S", "SQ", "FP3", "FP2"]


def test_a_weekend_with_no_session_data_is_unavailable(sessions):
    _, requested = sessions

    assert load_weekend_entry_list(YEAR, ROUND) is UNAVAILABLE
    assert requested == list(module.ENTRY_LIST_SESSIONS)


def test_a_resolved_entry_list_is_reused_until_its_ttl_passes(sessions, clock):
    served, requested = sessions
    served["Q"] = _FakeSession(_results(_driver("LEC")))
    first = load_weekend_entry_list(YEAR, ROUND)

    clock[0] += module.ENTRY_LIST_TTL_SECONDS - 1
    assert load_weekend_entry_list(YEAR, ROUND) is first
    assert requested == ["Q"]

    clock[0] += 2
    load_weekend_entry_list(YEAR, ROUND)
    assert requested == ["Q", "Q"], "a withdrawal between sessions must eventually be seen"


def test_an_unavailable_entry_list_is_retried_on_the_short_interval(sessions, clock):
    served, requested = sessions
    assert load_weekend_entry_list(YEAR, ROUND) is UNAVAILABLE
    calls_after_first = len(requested)

    clock[0] += module.ENTRY_LIST_RETRY_SECONDS - 1
    assert load_weekend_entry_list(YEAR, ROUND) is UNAVAILABLE
    assert len(requested) == calls_after_first, "inside the retry window nothing is reloaded"

    served["FP1"] = _FakeSession(_results(_driver("LEC")))
    clock[0] += 2

    assert load_weekend_entry_list(YEAR, ROUND).session == "FP1", "FP1 ran; the miss must not stick"
    assert module.ENTRY_LIST_RETRY_SECONDS < module.ENTRY_LIST_TTL_SECONDS


def test_each_weekend_is_cached_separately(sessions):
    served, _ = sessions
    served["Q"] = _FakeSession(_results(_driver("LEC")))

    load_weekend_entry_list(YEAR, ROUND)
    served["Q"] = _FakeSession(_results(_driver("VER")))

    assert load_weekend_entry_list(YEAR, ROUND + 1).codes == {"VER"}


def test_reset_cache_forces_a_fresh_read(sessions):
    served, requested = sessions
    served["Q"] = _FakeSession(_results(_driver("LEC")))
    load_weekend_entry_list(YEAR, ROUND)

    module.reset_cache()
    load_weekend_entry_list(YEAR, ROUND)

    assert requested == ["Q", "Q"]


def test_an_entry_list_with_entries_but_no_session_is_still_unknown():
    """``session`` is the provenance; without it the list is not trusted."""
    assert WeekendEntryList(entries=(EntryListDriver("LEC", "Charles Leclerc", "Ferrari"),)).available is False
