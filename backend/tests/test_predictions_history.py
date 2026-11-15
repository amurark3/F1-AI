"""Tests for durable prediction history (app.data.predictions.history).

This module is the only writer of the document every accuracy number is later
computed from, and every write is a read-modify-write of one shared document.
The failure this file exists to prevent is the expensive one: a *failed read*
being treated as an empty history, so the next save replaces an entire season of
accumulated predictions with the single race in hand. That is exactly the outage
``ReadResult.ok`` was introduced for, and ``save_prediction`` must refuse to
write when it cannot see what is already there.

The rest is the same theme at smaller scale: a race that has not been published
yet answers nothing, so the retry must be rate-limited rather than paid on every
page view; and a result is graded on the published classification (the order
after post-race penalties, Mexico City 2026's real captures), stored with its
source and provisional until a later read confirms it.

The document store and the classification are both replaced at the module
boundary — the namespace these functions resolve the names in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from app.data.predictions import history as history_module
from app.data.predictions.history import (
    ACTUAL_RESULT_RETRY_SECONDS,
    CONFIRM_AFTER,
    _classify_results,
    _load_prediction_history,
    _read_prediction_history,
    _save_prediction_history,
    _should_attempt_actual_load,
    actuals_pending,
    prediction_call,
    record_actual_result,
    save_prediction,
)
from app.data.race_classification import (
    JOLPICA_SOURCE,
    OPENF1_SOURCE,
    ClassifiedDriver,
    RaceClassification,
    classification_from_jolpica,
    classification_from_openf1,
)
from app.data.store_types import ReadResult, WriteResult

YEAR = 2026
ROUND = 4
KEY = f"({YEAR},{ROUND})"
R19 = Path(__file__).parent / "fixtures" / "mexico_2026_r19"


@dataclass
class _FakeStore:
    """A document store scripted per test: readable/writable, and what it holds."""

    document: object = field(default_factory=dict)
    read_ok: bool = True
    write_ok: bool = True
    writes: list[dict] = field(default_factory=list)

    def read(self, name: str) -> ReadResult:
        if not self.read_ok:
            return ReadResult(ok=False, error="backend unreachable")
        return ReadResult(payload=self.document)

    def write(self, name: str, payload: dict) -> WriteResult:
        self.writes.append(payload)
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="backend unreachable")
        self.document = payload
        return WriteResult()


@pytest.fixture
def store(monkeypatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(history_module, "document_store", fake)
    return fake


@pytest.fixture(autouse=True)
def _clear_retry_deadlines():
    """Retry deadlines are module-global and would leak across tests."""
    history_module._actual_result_attempts.clear()
    yield
    history_module._actual_result_attempts.clear()


def _predictions(**overrides: object) -> dict:
    """A compute_race_predictions-shaped payload, minimally populated."""
    payload = {
        "generated_at": "2026-05-24T10:00:00+00:00",
        "prediction_phase": "post_qualifying",
        "data_sources": ["qualifying"],
        "predictions": [
            {"driver_code": "VER", "position": 1},
            {"driver_code": "NOR", "position": 2},
        ],
        "risk_predictions": [
            {
                "driver_code": "NOR",
                "dnf_risk_pct": 22,
                "crash_risk_pct": 11,
                "mechanical_risk_pct": 14,
                "risk_level": "high",
            }
        ],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Reading and writing the document
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_successful_read_reports_the_document_and_that_it_was_readable(store):
    store.document = {KEY: {"predicted_positions": {"VER": 1}}}

    assert _read_prediction_history() == (store.document, True)


@pytest.mark.unit
def test_a_failed_read_is_distinguishable_from_an_empty_history(store):
    store.read_ok = False

    history, readable = _read_prediction_history()

    # The pair is the whole point: {} alone cannot tell a caller whether it is
    # safe to write.
    assert history == {}
    assert readable is False


@pytest.mark.unit
def test_a_payload_of_the_wrong_shape_is_treated_as_no_history(store):
    store.document = ["not", "a", "document"]

    assert _read_prediction_history() == ({}, True)


@pytest.mark.unit
def test_loading_history_hides_the_readability_flag_from_read_only_callers(store):
    store.read_ok = False

    assert _load_prediction_history() == {}


@pytest.mark.unit
def test_a_failed_write_is_reported_rather_than_raised(store):
    store.write_ok = False

    _save_prediction_history({"a": 1})

    assert store.writes == [{"a": 1}]


# ---------------------------------------------------------------------------
# Saving a prediction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_saved_prediction_records_positions_risks_and_provenance(store):
    save_prediction(YEAR, ROUND, _predictions())

    entry = store.document[KEY]
    assert entry["predicted_positions"] == {"VER": 1, "NOR": 2}
    assert entry["risk_predictions"]["NOR"]["dnf_risk_pct"] == 22
    assert entry["prediction_phase"] == "post_qualifying"
    assert entry["data_sources"] == ["qualifying"]
    assert len(entry["snapshots"]) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "predictions",
    [
        pytest.param([], id="no_predictions"),
        pytest.param([{"driver_code": "", "position": 1}], id="no_driver_code"),
        pytest.param([{"driver_code": "VER", "position": None}], id="no_position"),
    ],
)
def test_a_prediction_with_no_usable_finishing_order_is_not_stored(store, predictions):
    save_prediction(YEAR, ROUND, _predictions(predictions=predictions))

    assert store.writes == []


@pytest.mark.unit
def test_a_risk_row_without_a_driver_code_is_dropped(store):
    save_prediction(YEAR, ROUND, _predictions(risk_predictions=[{"dnf_risk_pct": 30}]))

    assert store.document[KEY]["risk_predictions"] == {}


@pytest.mark.unit
def test_saving_is_skipped_entirely_when_the_existing_history_cannot_be_read(store):
    store.read_ok = False

    save_prediction(YEAR, ROUND, _predictions())

    # Losing one race's snapshot is recoverable; overwriting a season is not.
    assert store.writes == []


@pytest.mark.unit
def test_a_second_prediction_for_the_same_race_appends_a_snapshot(store):
    save_prediction(YEAR, ROUND, _predictions(prediction_phase="pre_qualifying"))
    save_prediction(YEAR, ROUND, _predictions(prediction_phase="post_qualifying"))

    entry = store.document[KEY]
    phases = [snapshot["prediction_phase"] for snapshot in entry["snapshots"]]
    assert phases == ["pre_qualifying", "post_qualifying"]
    # The top-level fields hold the graded call: the post-qualifying one.
    assert entry["prediction_phase"] == "post_qualifying"


@pytest.mark.unit
def test_a_pre_qualifying_call_after_the_post_qualifying_one_does_not_become_the_graded_call(store):
    # R20 São Paulo: a pre-qualifying recompute 16 s after the post-qualifying
    # call took over the top-level fields, so the race was graded on VER P2.
    post = _predictions(generated_at="2026-11-08T00:45:43+00:00", prediction_phase="post_qualifying")
    pre = _predictions(
        generated_at="2026-11-08T00:45:59+00:00",
        prediction_phase="pre_qualifying",
        predictions=[{"driver_code": "VER", "position": 2}, {"driver_code": "NOR", "position": 1}],
    )
    save_prediction(YEAR, ROUND, post)
    save_prediction(YEAR, ROUND, pre)

    entry = store.document[KEY]
    assert [snapshot["prediction_phase"] for snapshot in entry["snapshots"]] == ["post_qualifying", "pre_qualifying"]
    assert entry["prediction_phase"] == "post_qualifying"
    assert entry["generated_at"] == "2026-11-08T00:45:43+00:00"
    assert entry["predicted_positions"] == {"VER": 1, "NOR": 2}
    assert entry["risk_predictions"]["NOR"]["dnf_risk_pct"] == 22


@pytest.mark.unit
def test_a_call_with_no_phase_is_graded_when_it_is_the_only_one(store):
    save_prediction(YEAR, ROUND, _predictions(prediction_phase=None))

    entry = store.document[KEY]
    assert entry["prediction_phase"] is None
    assert entry["predicted_positions"] == {"VER": 1, "NOR": 2}


@pytest.mark.unit
def test_the_call_extracted_from_a_compute_is_what_history_stores(store):
    call = prediction_call(_predictions())

    assert call == {
        "generated_at": "2026-05-24T10:00:00+00:00",
        "prediction_phase": "post_qualifying",
        "data_sources": ["qualifying"],
        "predicted_positions": {"VER": 1, "NOR": 2},
        "risk_predictions": {
            "NOR": {"dnf_risk_pct": 22, "crash_risk_pct": 11, "mechanical_risk_pct": 14, "risk_level": "high"}
        },
    }
    save_prediction(YEAR, ROUND, _predictions())
    assert store.document[KEY]["snapshots"] == [call]


@pytest.mark.unit
def test_a_compute_with_no_finishing_order_has_no_call():
    assert prediction_call(_predictions(predictions=[])) is None


@pytest.mark.unit
def test_only_the_eight_most_recent_snapshots_are_retained(store):
    for run in range(10):
        save_prediction(YEAR, ROUND, _predictions(generated_at=f"2026-05-24T{run:02d}:00:00+00:00"))

    snapshots = store.document[KEY]["snapshots"]
    assert len(snapshots) == 8
    assert snapshots[0]["generated_at"] == "2026-05-24T02:00:00+00:00"
    assert snapshots[-1]["generated_at"] == "2026-05-24T09:00:00+00:00"


@pytest.mark.unit
def test_re_saving_a_prediction_does_not_discard_the_recorded_result(store):
    save_prediction(YEAR, ROUND, _predictions())
    store.document[KEY]["actual_positions"] = {"VER": 1, "NOR": 5}
    store.document[KEY]["actual_statuses"] = {"NOR": "Engine"}
    store.document[KEY]["actual_incidents"] = {"NOR": {"dnf": True}}

    save_prediction(YEAR, ROUND, _predictions())

    entry = store.document[KEY]
    assert entry["actual_positions"] == {"VER": 1, "NOR": 5}
    assert entry["actual_statuses"] == {"NOR": "Engine"}
    assert entry["actual_incidents"] == {"NOR": {"dnf": True}}


@pytest.mark.unit
def test_a_generated_at_is_stamped_when_the_payload_carries_none(store):
    payload = _predictions()
    del payload["generated_at"]

    save_prediction(YEAR, ROUND, payload)

    assert store.document[KEY]["generated_at"].startswith("20")


# ---------------------------------------------------------------------------
# Retry back-off
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_result_load_is_attempted_once_then_backed_off():
    assert _should_attempt_actual_load(YEAR, ROUND) is True
    # A race that has not run yet fails every load, so an unguarded retry would
    # cost a slow FastF1 round trip on every request.
    assert _should_attempt_actual_load(YEAR, ROUND) is False


@pytest.mark.unit
def test_the_back_off_expires_so_a_finished_race_is_eventually_picked_up(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(history_module.time, "monotonic", lambda: clock[0])

    assert _should_attempt_actual_load(YEAR, ROUND) is True
    clock[0] += ACTUAL_RESULT_RETRY_SECONDS + 1

    assert _should_attempt_actual_load(YEAR, ROUND) is True


@pytest.mark.unit
def test_back_off_is_tracked_per_race():
    _should_attempt_actual_load(YEAR, ROUND)

    assert _should_attempt_actual_load(YEAR, ROUND + 1) is True


# ---------------------------------------------------------------------------
# Grading from the published classification
# ---------------------------------------------------------------------------


def _r19(name: str) -> list | dict:
    return json.loads((R19 / name).read_text())


def _r19_openf1() -> RaceClassification:
    """Mexico City 2026 as OpenF1 published it: the final order, post-penalty."""
    codes = {row["driver_number"]: row["name_acronym"] for row in _r19("openf1_drivers.json")}
    drivers = classification_from_openf1(_r19("openf1_session_result.json"), codes)
    return RaceClassification(source=OPENF1_SOURCE, drivers=drivers)


def _r19_jolpica() -> RaceClassification:
    """The same race as Jolpica showed it the morning after: before the penalties."""
    rows = [
        {
            "driverCode": row["Driver"]["code"],
            "position": row["position"],
            "positionText": row["positionText"],
            "status": row["status"],
            "laps": row["laps"],
        }
        for row in _r19("jolpica_results.json")["Results"]
    ]
    return RaceClassification(source=JOLPICA_SOURCE, drivers=classification_from_jolpica(rows))


class _Feed:
    """A scripted ``race_classification`` that counts its reads."""

    def __init__(self, answer: RaceClassification) -> None:
        self.answer = answer
        self.calls: list[tuple[int, int]] = []

    def __call__(self, year: int, round_num: int) -> RaceClassification:
        self.calls.append((year, round_num))
        return self.answer


@pytest.fixture
def feed(monkeypatch):
    """Install a scripted classification feed and hand the test the double back."""

    def _install(answer: RaceClassification) -> _Feed:
        fake = _Feed(answer)
        monkeypatch.setattr(history_module, "race_classification", fake)
        return fake

    return _install


def _recorded_hours_ago(hours: float, **fields: object) -> dict:
    stamp = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    return {
        "actual_positions": {"VER": 1},
        "actual_statuses": {"VER": "Finished"},
        "actual_provisional": True,
        "actual_recorded_at": stamp,
        **fields,
    }


@pytest.mark.unit
def test_jolpicas_morning_after_order_is_not_the_final_order():
    """The finding behind D1.8: the stored review's Mexico City actuals followed Jolpica, not the FIA."""
    jolpica = {driver.driver_code: driver.position for driver in _r19_jolpica().drivers}
    final = {driver.driver_code: driver.position for driver in _r19_openf1().drivers}

    # What the stored review held (fixtures/mexico_2026_r19/prediction_history_entry.json) is Jolpica's.
    stored = _r19("prediction_history_entry.json")["entry"]["actual_positions"]
    assert (
        (stored["PIA"], stored["COL"], stored["GAS"]) == (jolpica["PIA"], jolpica["COL"], jolpica["GAS"]) == (7, 8, 10)
    )
    assert (final["PIA"], final["COL"], final["GAS"]) == (13, 15, 17)


@pytest.mark.unit
def test_a_race_with_a_post_race_penalty_is_graded_on_the_post_penalty_order(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    entry = store.document[KEY]
    assert (entry["actual_positions"]["PIA"], entry["actual_positions"]["COL"], entry["actual_positions"]["GAS"]) == (
        13,
        15,
        17,
    )
    assert entry["actual_positions"]["VER"] == 1


@pytest.mark.unit
def test_a_retirement_is_stored_as_dnf_with_its_incident_flag_never_only_a_place(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    entry = store.document[KEY]
    retired = ("LIN", "BEA", "BOT", "STR", "ALO")
    assert {entry["actual_statuses"][code] for code in retired} == {"DNF"}
    assert all(entry["actual_incidents"][code]["dnf"] for code in retired)
    assert not entry["actual_incidents"]["PIA"]["dnf"]
    # Listed after the 17 classified cars, in the order they are published.
    assert sorted(entry["actual_positions"][code] for code in retired) == [18, 19, 20, 21, 22]


@pytest.mark.unit
def test_a_result_is_stored_with_its_source_and_provisional(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    entry = store.document[KEY]
    assert (entry["actual_source"], entry["actual_provisional"]) == (OPENF1_SOURCE, True)
    assert datetime.fromisoformat(entry["actual_recorded_at"]).tzinfo is not None


@pytest.mark.unit
def test_every_status_reads_as_its_label_and_a_car_without_a_place_follows_the_order():
    drivers = (
        ClassifiedDriver("VER", 1, "finished", 70),
        ClassifiedDriver("NOR", None, "dnf", 40),
        ClassifiedDriver("PIA", None, "not_classified", 10),
        ClassifiedDriver("LEC", None, "dns", None),
        ClassifiedDriver("HAM", None, "dsq", 70),
    )

    positions, statuses, incidents = _classify_results(RaceClassification(source=OPENF1_SOURCE, drivers=drivers))

    assert positions == {"VER": 1, "NOR": 2, "PIA": 3, "LEC": 4, "HAM": 5}
    assert statuses == {"VER": "Finished", "NOR": "DNF", "PIA": "NC", "LEC": "DNS", "HAM": "DSQ"}
    assert [incidents[code]["dnf"] for code in positions] == [False, True, True, True, True]


@pytest.mark.unit
def test_a_race_with_no_stored_prediction_is_never_fetched(store, feed):
    fake = feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    # Nothing to compare against, so reading the classification is pointless.
    assert fake.calls == []


@pytest.mark.unit
def test_an_unpublished_classification_records_nothing_and_is_retried_after_the_window(store, feed, monkeypatch):
    save_prediction(YEAR, ROUND, _predictions())
    fake = feed(RaceClassification(source=None, drivers=()))
    writes_before = len(store.writes)
    clock = [1000.0]
    monkeypatch.setattr(history_module.time, "monotonic", lambda: clock[0])

    record_actual_result(YEAR, ROUND)
    record_actual_result(YEAR, ROUND)
    assert (len(fake.calls), len(store.writes)) == (1, writes_before)

    clock[0] += ACTUAL_RESULT_RETRY_SECONDS + 1
    fake.answer = _r19_openf1()
    record_actual_result(YEAR, ROUND)

    assert (len(fake.calls), store.document[KEY]["actual_source"]) == (2, OPENF1_SOURCE)


@pytest.mark.unit
def test_a_result_for_a_race_removed_from_history_mid_flight_is_dropped(store, monkeypatch):
    save_prediction(YEAR, ROUND, _predictions())

    def _read_while_the_race_is_removed(year: int, round_num: int) -> RaceClassification:
        store.document = {}
        return _r19_openf1()

    monkeypatch.setattr(history_module, "race_classification", _read_while_the_race_is_removed)

    record_actual_result(YEAR, ROUND)

    assert store.document == {}


@pytest.mark.unit
def test_a_provisional_result_is_not_read_again_within_a_day(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    store.document[KEY].update(_recorded_hours_ago(2))
    fake = feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    assert fake.calls == []


@pytest.mark.unit
def test_a_read_a_day_later_that_agrees_makes_the_result_final(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    feed(_r19_openf1())
    record_actual_result(YEAR, ROUND)
    store.document[KEY]["actual_recorded_at"] = (datetime.now(UTC) - CONFIRM_AFTER).isoformat()
    history_module._actual_result_attempts.clear()

    record_actual_result(YEAR, ROUND)

    assert store.document[KEY]["actual_provisional"] is False
    assert actuals_pending(store.document[KEY]) is False


@pytest.mark.unit
def test_a_read_a_day_later_that_differs_replaces_the_result_and_it_stays_provisional(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    store.document[KEY].update(_recorded_hours_ago(25, actual_source=JOLPICA_SOURCE))
    graded_before = store.document[KEY]["predicted_positions"]
    feed(_r19_openf1())

    record_actual_result(YEAR, ROUND)

    entry = store.document[KEY]
    assert (entry["actual_positions"]["PIA"], entry["actual_source"], entry["actual_provisional"]) == (
        13,
        OPENF1_SOURCE,
        True,
    )
    assert entry["predicted_positions"] == graded_before


@pytest.mark.unit
def test_jolpicas_pre_penalty_order_never_confirms_itself(store, feed):
    save_prediction(YEAR, ROUND, _predictions())
    feed(_r19_jolpica())
    record_actual_result(YEAR, ROUND)
    store.document[KEY]["actual_recorded_at"] = (datetime.now(UTC) - CONFIRM_AFTER).isoformat()
    history_module._actual_result_attempts.clear()

    record_actual_result(YEAR, ROUND)

    assert (store.document[KEY]["actual_source"], store.document[KEY]["actual_provisional"]) == (JOLPICA_SOURCE, True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entry", "pending"),
    [
        pytest.param({}, True, id="nothing_recorded"),
        pytest.param({"actual_positions": {"VER": 1}}, False, id="recorded_before_sources_are_left_to_the_script"),
        pytest.param(_recorded_hours_ago(1, actual_provisional=False), False, id="final"),
        pytest.param(_recorded_hours_ago(1), False, id="provisional_and_recent"),
        pytest.param(_recorded_hours_ago(30), True, id="provisional_for_over_a_day"),
        pytest.param(_recorded_hours_ago(1, actual_recorded_at=None), True, id="provisional_with_no_stamp"),
    ],
)
def test_which_races_still_need_their_result_recorded_or_confirmed(entry, pending):
    assert actuals_pending(entry) is pending
