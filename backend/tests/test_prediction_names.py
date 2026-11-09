"""Tests for the canonical-name overlay on stored prediction snapshots.

A snapshot froze the names its compute saw: FastF1's "Andrea Kimi Antonelli",
"Carlos Sainz" and "RB F1 Team". What a read must guarantee:

* every served row prints f1db's names ("Kimi Antonelli", "Carlos Sainz Jr.",
  "Racing Bulls"), found by the row's code (and car number when stored), under
  the keys the row already had;
* the stored document is never rewritten: the overlay is on the copy a read
  serves, so the record of what the model saw stays as it was;
* a row nobody resolves keeps its stored name, display-cased, and an
  unreadable f1db serves the stored names with a warning.

The snapshot is the real R19 entry (``fixtures/mexico_2026_r19/``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3

import pytest
import structlog

from app.data import f1db_source
from app.data.predictions import PREDICTION_LOGIC_VERSION
from app.data.store_types import DocumentChange, ReadResult, UpdateResult
from app.services import prediction_cache, predictions as service
from app.services.prediction_cache import PredictionSnapshotCache
from app.services.prediction_names import with_canonical_names

SNAPSHOT = Path(__file__).parent / "fixtures" / "mexico_2026_r19" / "prediction_snapshot_entry.json"
ROW_LISTS = ("predictions", "risk_predictions")


class _Store:
    """A document store holding one prediction-cache document, recording writes."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.writes: list[dict] = []

    def read(self, _name: str) -> ReadResult:
        return ReadResult(payload=self.payload)

    def update(self, _name: str, change: DocumentChange) -> UpdateResult:
        payload = change(self.payload)
        self.writes.append(copy.deepcopy(payload))
        return UpdateResult(durable=True, payload=payload)


def _r19_entry() -> dict:
    """The stored R19 entry, its logic version kept current so a read serves it rather than recomputing."""
    entry = json.loads(SNAPSHOT.read_text())["entry"]
    for snapshot in entry["snapshots"]:
        snapshot["result"]["logic_version"] = PREDICTION_LOGIC_VERSION
    return entry


def _stored_rows(entry: dict, key: str = "predictions") -> list[dict]:
    return entry["snapshots"][-1]["result"][key]


@pytest.fixture
def store(monkeypatch) -> _Store:
    holder = _Store({"schema_version": 2, "entries": {"2026:19": _r19_entry()}})
    monkeypatch.setattr(prediction_cache, "document_store", holder)
    return holder


def _by_code(rows: list[dict]) -> dict[str, dict]:
    return {row["driver_code"]: row for row in rows}


def _break_f1db(monkeypatch) -> None:
    def connect() -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(f1db_source, "connect", connect)


# --- Through the snapshot cache: what /predictions serves ------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("key", ROW_LISTS)
def test_a_read_snapshot_prints_f1dbs_names(identity_f1db, store, key):
    rows = _by_code(PredictionSnapshotCache().get(2026, 19)[key])

    assert rows["ANT"]["driver_name"] == "Kimi Antonelli"
    assert rows["SAI"]["driver_name"] == "Carlos Sainz Jr."
    assert rows["NAN"]["driver_name"] == "Ryō Hirakawa", "stored without a code, he resolves by name"
    assert rows["PER"]["driver_name"] == "Sergio Pérez"
    assert {code: rows[code]["team"] for code in ("LAW", "LIN", "BEA", "NAN", "GAS", "BOT", "HAD")} == {
        "LAW": "Racing Bulls",
        "LIN": "Racing Bulls",
        "BEA": "Haas",
        "NAN": "Haas",
        "GAS": "Alpine",
        "BOT": "Cadillac",
        "HAD": "Red Bull",
    }


@pytest.mark.integration
def test_only_names_change_every_key_code_and_number_stays(identity_f1db, store):
    stored = _r19_entry()["snapshots"][-1]["result"]
    served = PredictionSnapshotCache().get(2026, 19)

    for key in ROW_LISTS:
        for before, after in zip(stored[key], served[key], strict=True):
            assert set(after) == set(before)
            assert {k: v for k, v in after.items() if k not in {"driver_name", "team"}} == {
                k: v for k, v in before.items() if k not in {"driver_name", "team"}
            }


@pytest.mark.integration
def test_the_stored_document_is_never_rewritten(identity_f1db, store):
    PredictionSnapshotCache().get(2026, 19)

    assert store.writes == []
    assert _by_code(_stored_rows(store.payload["entries"]["2026:19"]))["ANT"]["driver_name"] == "Andrea Kimi Antonelli"


@pytest.mark.integration
def test_a_new_snapshot_is_stored_as_computed_and_served_canonical(identity_f1db, store):
    computed = _r19_entry()["snapshots"][-1]["result"]

    served = PredictionSnapshotCache().set(2026, 19, computed, reason="manual_compute")

    written = store.writes[-1]["entries"]["2026:19"]["snapshots"][-1]["result"]
    assert _by_code(written["predictions"])["SAI"]["driver_name"] == "Carlos Sainz"
    assert _by_code(served["predictions"])["SAI"]["driver_name"] == "Carlos Sainz Jr."


@pytest.mark.integration
def test_the_served_leader_is_named_by_f1db(identity_f1db, store, monkeypatch):
    """The model summary reads the leader's name from the served rows, overlay included."""
    cache = PredictionSnapshotCache()
    monkeypatch.setattr(service, "prediction_snapshot_cache", cache)
    monkeypatch.setattr(service, "build_prediction_review", lambda *_args, **_kwargs: {"evaluated": False})
    rows = _stored_rows(store.payload["entries"]["2026:19"])
    store.payload["entries"]["2026:19"]["snapshots"][-1]["result"]["predictions"] = [rows[3], *rows[:3], *rows[4:]]

    summary = service.get_cached_race_prediction(2026, 19)["model_summary"]

    assert (summary["leader"], summary["leader_code"]) == ("Kimi Antonelli", "ANT")


@pytest.mark.integration
def test_a_driver_f1db_has_no_record_of_keeps_the_stored_name_display_cased(identity_f1db, store):
    """Mick Schumacher drove no 2026 session: his name is recased, never swapped for someone else's."""
    rows = _stored_rows(store.payload["entries"]["2026:19"])
    rows.append({**rows[-1], "driver_code": "MSC", "driver_name": "Mick SCHUMACHER", "team": "Haas F1 Team"})

    served = _by_code(PredictionSnapshotCache().get(2026, 19)["predictions"])

    assert (served["MSC"]["driver_name"], served["MSC"]["team"]) == ("Mick Schumacher", "Haas")


@pytest.mark.integration
def test_an_unreadable_f1db_serves_the_stored_names_and_logs_why(store, monkeypatch):
    _break_f1db(monkeypatch)

    with structlog.testing.capture_logs() as logs:
        rows = _by_code(PredictionSnapshotCache().get(2026, 19)["predictions"])

    assert (rows["ANT"]["driver_name"], rows["LAW"]["team"]) == ("Andrea Kimi Antonelli", "RB F1 Team")
    warnings = {log["event"] for log in logs if log["log_level"] == "warning"}
    assert warnings == {"canonical_names.f1db_unreadable"}


# --- The overlay on its own ----------------------------------------------------------------


@pytest.mark.unit
def test_a_result_without_a_season_is_served_as_stored(monkeypatch):
    _break_f1db(monkeypatch)
    result = {"predictions": [{"driver_code": "ANT", "driver_name": "Andrea Kimi Antonelli", "team": "Mercedes"}]}

    assert with_canonical_names(result) is result


@pytest.mark.unit
def test_rows_without_names_gain_no_keys_and_read_nothing(monkeypatch):
    _break_f1db(monkeypatch)
    result = {"year": 2026, "predictions": [{"driver_code": "VER", "position": 1}, "not-a-row"], "warnings": []}

    assert with_canonical_names(result) == result


@pytest.mark.integration
def test_a_blank_stored_name_or_team_stays_blank(identity_f1db):
    result = {"year": 2026, "risk_predictions": [{"driver_code": "", "driver_name": "", "team": None}]}

    assert with_canonical_names(result)["risk_predictions"] == [{"driver_code": "", "driver_name": "", "team": None}]


@pytest.mark.integration
def test_a_stored_car_number_is_a_key_too(identity_f1db):
    result = {"year": 2026, "predictions": [{"driver_code": "NAN", "driver_number": 50, "driver_name": "", "team": ""}]}

    assert with_canonical_names(result)["predictions"][0]["driver_name"] == "Ryō Hirakawa"
