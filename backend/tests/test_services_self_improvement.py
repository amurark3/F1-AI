"""Tests for app.services.self_improvement — the prediction feedback loop.

Two risks dominate this module.

The first is **silent data loss**: post-mortems are stored as one merged
document, so a read-modify-write against a store that failed to answer would
overwrite every previously stored post-mortem with a single entry. The write
must be skipped when the merge base is unknown.

The second is **fabricated analysis**: the post-mortem text comes from an LLM.
With no key, or on any LLM error, the pass must record actuals and return
``None`` rather than store an empty or invented summary.

The document store and the LLM are both faked; ``GROQ_API_KEY`` is unset, so
no real client is ever constructed.
"""

from __future__ import annotations

import pytest

from app.data.store_types import ReadResult, WriteResult
from app.services import self_improvement as si


class _FakeStore:
    """In-memory document store that can fail reads or writes on demand."""

    def __init__(self, payload=None, *, read_ok: bool = True, write_ok: bool = True) -> None:
        self.payload = payload
        self.read_ok = read_ok
        self.write_ok = write_ok
        self.writes: list[tuple[str, dict]] = []

    def read(self, name: str) -> ReadResult:
        if not self.read_ok:
            return ReadResult(payload=None, ok=False, error="supabase unreachable")
        return ReadResult(payload=self.payload)

    def write(self, name: str, payload: dict) -> WriteResult:
        self.writes.append((name, payload))
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="disk full")
        self.payload = payload
        return WriteResult()


class _FakeLLM:
    def __init__(self, content: str = "Grid pace was overweighted.") -> None:
        self.content = content
        self.prompts: list[str] = []

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        return type("_Response", (), {"content": self.content})()


@pytest.fixture
def store(monkeypatch):
    fake = _FakeStore(payload={})
    monkeypatch.setattr(si, "document_store", fake)
    return fake


def _install_llm(monkeypatch, llm) -> None:
    """Patch the lazily-imported Groq factory the post-mortem reaches for."""
    from app.api import llm as llm_module

    monkeypatch.setattr(llm_module, "build_chat_llm", lambda: llm)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("(2026,3)", (2026, 3)),
        ("(2026, 12)", (2026, 12)),
        ("2026,1", (2026, 1)),
        ("(2026)", None),  # no round component
        ("()", None),  # not numeric
        ("(twenty,three)", None),
    ],
)
def test_parse_key_round_trips_stored_history_keys(key, expected):
    assert si._parse_key(key) == expected


@pytest.mark.unit
def test_biggest_misses_ignores_gaps_below_the_threshold():
    predicted = {"VER": 1, "LEC": 3, "NOR": 5}
    actual = {"VER": 2, "LEC": 9, "NOR": 12}

    misses = si._biggest_misses(predicted, actual)

    # VER moved one place; only gaps of MISS_THRESHOLD or more are worth explaining.
    assert [m["driver"] for m in misses] == ["NOR", "LEC"]
    assert misses[0] == {"driver": "NOR", "predicted": 5, "actual": 12, "delta": 7}


@pytest.mark.unit
def test_biggest_misses_ranks_by_magnitude_regardless_of_direction():
    predicted = {"A": 1, "B": 18}
    actual = {"A": 6, "B": 2}

    misses = si._biggest_misses(predicted, actual)

    # B over-performed by 16, A under-performed by 5 — magnitude wins.
    assert [(m["driver"], m["delta"]) for m in misses] == [("B", -16), ("A", 5)]


@pytest.mark.unit
def test_biggest_misses_only_scores_drivers_present_on_both_sides():
    misses = si._biggest_misses({"A": 1, "GONE": 2}, {"A": 20, "NEW": 1})

    assert [m["driver"] for m in misses] == ["A"]


@pytest.mark.unit
def test_biggest_misses_respects_the_limit():
    predicted = {f"D{i}": 1 for i in range(10)}
    actual = {f"D{i}": 20 - i for i in range(10)}

    assert len(si._biggest_misses(predicted, actual, limit=3)) == 3


@pytest.mark.unit
def test_a_failed_store_read_is_reported_as_unreadable_not_empty(monkeypatch):
    monkeypatch.setattr(si, "document_store", _FakeStore(read_ok=False))

    assert si._read_postmortems() == ({}, False)


@pytest.mark.unit
@pytest.mark.parametrize("payload", [None, [], "corrupt"])
def test_a_non_dict_document_reads_as_an_empty_but_readable_store(monkeypatch, payload):
    monkeypatch.setattr(si, "document_store", _FakeStore(payload=payload))

    assert si._read_postmortems() == ({}, True)


@pytest.mark.unit
def test_get_postmortem_returns_the_stored_entry(store):
    store.payload = {"(2026,2)": {"summary": "safety car"}}

    assert si.get_postmortem(2026, 2) == {"summary": "safety car"}
    assert si.get_postmortem(2026, 3) is None


@pytest.mark.unit
def test_write_merges_into_the_existing_document(store):
    store.payload = {"(2026,1)": {"summary": "old"}}

    si._write_postmortem("(2026,2)", {"summary": "new"})

    assert store.payload == {"(2026,1)": {"summary": "old"}, "(2026,2)": {"summary": "new"}}


@pytest.mark.unit
def test_write_is_skipped_when_the_merge_base_could_not_be_read(monkeypatch):
    fake = _FakeStore(read_ok=False)
    monkeypatch.setattr(si, "document_store", fake)

    si._write_postmortem("(2026,2)", {"summary": "new"})

    assert fake.writes == [], "writing blind would drop every post-mortem that failed to load"


@pytest.mark.unit
def test_a_failed_write_does_not_raise(store):
    store.write_ok = False

    si._write_postmortem("(2026,2)", {"summary": "new"})

    assert len(store.writes) == 1


@pytest.mark.unit
def test_prompt_reports_a_correct_winner_and_signs_the_deltas():
    review = {
        "winner_correct": True,
        "predicted_winner": "VER",
        "actual_winner": "VER",
        "avg_position_error": 2.4,
        "top3_correct": 2,
        "top3_possible": 3,
    }
    misses = [
        {"driver": "NOR", "predicted": 3, "actual": 12, "delta": 9},
        {"driver": "LEC", "predicted": 10, "actual": 4, "delta": -6},
    ]

    prompt = si._postmortem_prompt(2026, 4, review, misses)

    assert "winner correct" in prompt
    assert "- NOR: predicted P3, finished P12 (+9)" in prompt
    assert "- LEC: predicted P10, finished P4 (-6)" in prompt


@pytest.mark.unit
def test_prompt_says_so_when_nothing_crossed_the_threshold():
    prompt = si._postmortem_prompt(2026, 4, {"winner_correct": False}, [])

    assert "winner wrong" in prompt
    assert "- none beyond threshold" in prompt


@pytest.mark.unit
def test_an_unevaluated_race_produces_no_postmortem(store, monkeypatch):
    monkeypatch.setattr(si, "get_prediction_review", lambda year, round_num: {"evaluated": False})

    assert si.generate_miss_postmortem(2026, 9) is None
    assert store.writes == []


@pytest.mark.unit
def test_an_existing_postmortem_is_not_regenerated(store, monkeypatch):
    store.payload = {"(2026,2)": {"summary": "already explained"}}
    monkeypatch.setattr(si, "get_prediction_review", lambda *_: pytest.fail("must not re-review a stored race"))

    assert si.generate_miss_postmortem(2026, 2) == {"summary": "already explained"}


@pytest.mark.unit
def test_force_regenerates_over_a_stored_postmortem(store, monkeypatch):
    store.payload = {"(2026,2)": {"summary": "stale"}}
    monkeypatch.setattr(si, "get_prediction_review", lambda *_: {"evaluated": True, "winner_correct": True})
    monkeypatch.setattr(si, "_load_prediction_history", dict)
    monkeypatch.setattr(si, "_latest_prediction_snapshot", lambda entry: {})
    _install_llm(monkeypatch, _FakeLLM("fresh analysis"))

    payload = si.generate_miss_postmortem(2026, 2, force=True)

    assert payload["summary"] == "fresh analysis"
    assert store.payload["(2026,2)"]["summary"] == "fresh analysis"


@pytest.mark.unit
def test_an_llm_outage_yields_no_postmortem_rather_than_an_empty_one(store, monkeypatch):
    monkeypatch.setattr(si, "get_prediction_review", lambda *_: {"evaluated": True})
    monkeypatch.setattr(si, "_load_prediction_history", dict)
    monkeypatch.setattr(si, "_latest_prediction_snapshot", lambda entry: {})

    from app.api import llm as llm_module

    def explode():
        raise RuntimeError("GROQ_API_KEY is not set")

    monkeypatch.setattr(llm_module, "build_chat_llm", explode)

    assert si.generate_miss_postmortem(2026, 2) is None
    assert store.writes == []


@pytest.mark.unit
def test_a_generated_postmortem_records_the_misses_and_headline_accuracy(store, monkeypatch):
    monkeypatch.setattr(
        si,
        "get_prediction_review",
        lambda *_: {"evaluated": True, "winner_correct": False, "avg_position_error": 3.1},
    )
    monkeypatch.setattr(
        si,
        "_load_prediction_history",
        lambda: {"(2026,2)": {"predicted_positions": {"NOR": 3}, "actual_positions": {"NOR": 15}}},
    )
    llm = _FakeLLM("  Reliability was the driver.  ")
    _install_llm(monkeypatch, llm)

    payload = si.generate_miss_postmortem(2026, 2)

    assert payload["summary"] == "Reliability was the driver."
    assert payload["winner_correct"] is False
    assert payload["avg_position_error"] == 3.1
    assert payload["misses"] == [{"driver": "NOR", "predicted": 3, "actual": 15, "delta": 12}]
    assert payload["generated_at"].endswith("+00:00")
    assert store.payload["(2026,2)"] == payload
    assert "NOR" in llm.prompts[0]


@pytest.mark.unit
def test_a_pass_records_actuals_only_for_races_missing_them(store, monkeypatch):
    monkeypatch.setattr(
        si,
        "_load_prediction_history",
        lambda: {
            "(2026,1)": {"predicted_positions": {"VER": 1}, "actual_positions": {"VER": 1}},
            "(2026,2)": {"predicted_positions": {"VER": 1}},
            "(2025,1)": {"predicted_positions": {"VER": 1}},  # other season
            "not-a-key": {"predicted_positions": {"VER": 1}},
        },
    )
    recorded: list[tuple[int, int]] = []
    monkeypatch.setattr(si, "record_actual_result", lambda y, r: recorded.append((y, r)))
    monkeypatch.setattr(si, "generate_miss_postmortem", lambda y, r: None)

    summary = si.run_self_improvement_pass(2026)

    assert recorded == [(2026, 2)]
    assert summary == {"year": 2026, "actuals_recorded": 1, "postmortems_generated": 0}


@pytest.mark.unit
def test_a_pass_counts_only_newly_generated_postmortems(store, monkeypatch):
    store.payload = {"(2026,1)": {"summary": "already done"}}
    monkeypatch.setattr(
        si,
        "_load_prediction_history",
        lambda: {
            "(2026,1)": {"predicted_positions": {"VER": 1}, "actual_positions": {"VER": 1}},
            "(2026,2)": {"predicted_positions": {"VER": 1}, "actual_positions": {"VER": 3}},
        },
    )
    monkeypatch.setattr(si, "record_actual_result", lambda y, r: pytest.fail("actuals are already recorded"))
    generated: list[tuple[int, int]] = []
    monkeypatch.setattr(si, "generate_miss_postmortem", lambda y, r: generated.append((y, r)) or {"summary": "x"})

    summary = si.run_self_improvement_pass(2026)

    assert generated == [(2026, 2)], "the race that already has a post-mortem must be skipped"
    assert summary["postmortems_generated"] == 1
