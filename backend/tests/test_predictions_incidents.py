"""Tests for retirement/incident history (app.data.predictions.incidents).

This module is what turns a free-text retirement reason ("Engine", "Collision
damage", "+1 Lap") into the DNF/crash/mechanical flags that drive the published
risk percentages. Two failure modes matter:

* **Misclassification.** A lapped-but-classified finisher counted as a DNF
  would inflate every driver's retirement rate, and a driver who genuinely
  retired every race must not come out looking more reliable than one who
  finished them all.
* **Leaking the current round.** The profile is built to score an *upcoming*
  race, so it may only see rounds strictly before it — otherwise the model is
  scoring with the result it is trying to predict.

f1db is a real seeded SQLite file here, so the retirement SQL runs rather than
being stubbed.
"""

from __future__ import annotations

import pytest

from app.data import f1db_results
from app.data.predictions import incidents as incidents_module
from app.data.predictions.incidents import _classify_status, _load_recent_incidents, _season_retirements

# In the seeded database NOR retires with "Engine" in every round of both
# seasons; VER and LEC are classified finishers (reason NULL).
RETIRING_DRIVER = "NOR"
FINISHING_DRIVER = "VER"


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both caches live for the process, so they must not cross tests."""
    incidents_module._season_retirements_cache.clear()
    incidents_module._incident_cache.clear()
    yield
    incidents_module._season_retirements_cache.clear()
    incidents_module._incident_cache.clear()


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "dnf", "crash", "mechanical"),
    [
        # A classified finish is never a retirement, however it is spelled.
        ("Finished", False, False, False),
        ("+1 Lap", False, False, False),
        ("+2 Laps", False, False, False),
        ("", False, False, False),
        ("Accident", True, True, False),
        ("Collision damage", True, True, False),
        ("Spun off", True, True, False),
        ("Engine", True, False, True),
        ("Gearbox", True, False, True),
        ("Power unit", True, False, True),
        ("Hydraulics", True, False, True),
        ("Suspension", True, False, True),
        ("Withdrew", True, False, False),
        # Contact that broke something is both — the risk table reports each
        # separately, so neither flag may swallow the other.
        ("Collision damage - suspension", True, True, True),
    ],
)
def test_status_is_classified_into_the_flags_the_risk_table_reports(status, dnf, crash, mechanical):
    assert _classify_status(status) == {"dnf": dnf, "crash": crash, "mechanical": mechanical}


@pytest.mark.unit
def test_status_classification_is_case_insensitive():
    assert _classify_status("ACCIDENT") == _classify_status("accident")


# ---------------------------------------------------------------------------
# Season retirement loading
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_season_retirements_maps_each_round_to_its_entrants(fake_f1db):
    retirements = _season_retirements(2026)

    # Round 3 is on the calendar but has no results yet, so it contributes no
    # entry at all rather than an empty round that would count as a start.
    assert sorted(retirements) == [1, 2]
    assert retirements[1][RETIRING_DRIVER] == "Engine"
    assert retirements[1][FINISHING_DRIVER] is None


@pytest.mark.integration
def test_season_retirements_are_loaded_once_per_season(fake_f1db, monkeypatch):
    first = _season_retirements(2026)

    def _explode(year):
        raise AssertionError("f1db was queried a second time for a cached season")

    monkeypatch.setattr(f1db_results, "race_schedule", _explode)

    assert _season_retirements(2026) is first


@pytest.mark.unit
def test_a_failing_f1db_read_yields_an_empty_season_rather_than_raising(monkeypatch):
    def _fail(year):
        raise RuntimeError("f1db unavailable")

    monkeypatch.setattr(f1db_results, "race_schedule", _fail)

    # Reliability history is a nice-to-have signal; losing it must degrade the
    # risk profile to its defaults, not fail the whole prediction.
    assert _season_retirements(2026) == {}


# ---------------------------------------------------------------------------
# Per-driver incident profile
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_profile_counts_this_season_before_the_round_plus_all_of_the_previous_one(fake_f1db):
    profile = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)

    # 2026 rounds 1-2 (both before round 3) + 2025 rounds 1-2 = four starts.
    assert profile["starts"] == 4
    assert profile["dnfs"] == 4
    assert profile["mechanical"] == 4
    assert profile["crashes"] == 0
    assert profile["dnf_rate"] == 1.0
    assert profile["mechanical_rate"] == 1.0
    assert profile["crash_rate"] == 0.0


@pytest.mark.integration
def test_the_current_round_is_never_counted_into_the_profile_that_scores_it(fake_f1db):
    before_round_two = _load_recent_incidents(RETIRING_DRIVER, 2026, 2)
    before_round_three = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)

    # Predicting round 2 may see round 1 only; predicting round 3 gains round 2.
    assert before_round_two["starts"] == 3
    assert before_round_three["starts"] == 4


@pytest.mark.integration
def test_a_driver_who_finished_every_race_carries_no_retirement_risk(fake_f1db):
    profile = _load_recent_incidents(FINISHING_DRIVER, 2026, 3)

    assert profile["starts"] == 4
    assert profile["dnfs"] == 0
    assert profile["dnf_rate"] == 0.0
    assert profile["recent_statuses"] == []


@pytest.mark.integration
def test_a_retirement_prone_driver_outscores_a_clean_one_on_every_rate(fake_f1db):
    fragile = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)
    clean = _load_recent_incidents(FINISHING_DRIVER, 2026, 3)

    assert fragile["dnf_rate"] > clean["dnf_rate"]
    assert fragile["mechanical_rate"] > clean["mechanical_rate"]


@pytest.mark.integration
def test_only_the_three_most_recent_retirement_reasons_are_kept(fake_f1db):
    profile = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)

    assert profile["recent_statuses"] == ["Engine", "Engine", "Engine"]


@pytest.mark.integration
def test_a_driver_with_no_history_falls_back_to_grid_average_rates(fake_f1db):
    profile = _load_recent_incidents("ZZZ", 2026, 3)

    # A rookie must not be scored as perfectly reliable — the fallbacks are the
    # rough field-wide rates instead of zero.
    assert profile["starts"] == 0
    assert profile["dnf_rate"] == 0.08
    assert profile["crash_rate"] == 0.03
    assert profile["mechanical_rate"] == 0.04


@pytest.mark.integration
def test_a_profile_is_computed_once_per_driver_round(fake_f1db):
    first = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)

    assert _load_recent_incidents(RETIRING_DRIVER, 2026, 3) is first


@pytest.mark.unit
def test_a_failure_mid_accumulation_still_returns_a_usable_profile(monkeypatch):
    def _fail(year):
        raise RuntimeError("season load exploded")

    monkeypatch.setattr(incidents_module, "_season_retirements", _fail)

    profile = _load_recent_incidents(RETIRING_DRIVER, 2026, 3)

    assert profile["starts"] == 0
    assert profile["dnf_rate"] == 0.08


@pytest.mark.unit
def test_contact_retirements_are_counted_as_crashes_separately_from_mechanical_ones(monkeypatch):
    # The seeded database retires NOR with "Engine" every round, so the crash
    # tally is exercised here with a season of contact retirements instead.
    # Crash and mechanical counts feed two published percentages, and a driver
    # who keeps being taken out must not be reported as unreliable machinery.
    seasons = {
        2026: {1: {"NOR": "Collision"}, 2: {"NOR": "Accident"}},
        2025: {1: {"NOR": "Collision damage - suspension"}},
    }
    monkeypatch.setattr(incidents_module, "_season_retirements", lambda year: seasons.get(year, {}))

    profile = _load_recent_incidents("NOR", 2026, 3)

    assert profile["starts"] == 3
    assert profile["dnfs"] == 3
    assert profile["crashes"] == 3
    # Only the third retirement broke a component as well as involving contact.
    assert profile["mechanical"] == 1
    assert profile["crash_rate"] == 1.0
    assert profile["mechanical_rate"] == pytest.approx(1 / 3)


@pytest.mark.unit
def test_a_crash_prone_driver_carries_more_crash_risk_than_a_mechanically_fragile_one(monkeypatch):
    seasons = {
        2026: {
            1: {"CRASHER": "Accident", "BREAKER": "Gearbox"},
            2: {"CRASHER": "Collision", "BREAKER": "Engine"},
        }
    }
    monkeypatch.setattr(incidents_module, "_season_retirements", lambda year: seasons.get(year, {}))

    crasher = _load_recent_incidents("CRASHER", 2026, 3)
    breaker = _load_recent_incidents("BREAKER", 2026, 3)

    # Identical DNF counts: only the *cause* differs, so only the cause-specific
    # rates may diverge.
    assert crasher["dnf_rate"] == breaker["dnf_rate"]
    assert crasher["crash_rate"] > breaker["crash_rate"]
    assert breaker["mechanical_rate"] > crasher["mechanical_rate"]
