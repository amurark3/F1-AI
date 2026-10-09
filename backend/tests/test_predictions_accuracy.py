"""Tests for app.data.predictions.accuracy — the rolling accuracy summary.

These percentages are shown to users as the model's track record, so the
failure mode that matters is *flattering arithmetic*:

* **A denominator that counts what was never predicted.** Top-3 accuracy is
  scored only over drivers present in both the prediction and the result;
  padding either side inflates the score.
* **Zero standing in for "nothing to measure".** A race with no DNFs must
  report ``None`` for DNF capture, not 0% (a failure) and not 100% (a win).
* **A stale rolling window.** The last N races means the N most recently
  generated, not the N first written to the store.
"""

from __future__ import annotations

import pytest

from app.data.predictions import accuracy as module
from app.data.predictions.accuracy import RaceTally

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _entry(
    *,
    predicted: dict[str, int] | None = None,
    actual: dict[str, int] | None = None,
    risks: dict[str, dict] | None = None,
    incidents: dict[str, dict] | None = None,
    generated_at: str = "2024-05-01T12:00:00+00:00",
) -> dict:
    """One history entry in the flat (snapshot-less) shape."""
    entry: dict = {"generated_at": generated_at}
    if predicted is not None:
        entry["predicted_positions"] = predicted
    if actual is not None:
        entry["actual_positions"] = actual
    if risks is not None:
        entry["risk_predictions"] = risks
    if incidents is not None:
        entry["actual_incidents"] = incidents
    return entry


def _stub_history(monkeypatch: pytest.MonkeyPatch, *histories, record=None) -> list[tuple[int, int]]:
    """Serve each history in turn across successive loads; record backfills.

    ``get_accuracy_stats`` may load twice — once up front and once after a
    backfill — so the stub walks the supplied histories and repeats the last.
    """
    recorded: list[tuple[int, int]] = []
    remaining = list(histories)

    def _load() -> dict:
        value = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        if isinstance(value, BaseException):
            raise value
        return value

    def _record(year: int, round_num: int) -> None:
        recorded.append((year, round_num))
        if record is not None:
            record(year, round_num)

    monkeypatch.setattr(module, "_load_prediction_history", _load)
    monkeypatch.setattr(module, "record_actual_result", _record)
    return recorded


# ---------------------------------------------------------------------------
# RaceTally
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tallies_add_field_wise_and_concatenate_their_errors():
    first = RaceTally(top3_correct=2, winner_correct=1, position_errors=(1.0, 2.0))
    second = RaceTally(top3_correct=1, drivers_compared=5, position_errors=(3.0,))

    total = first + second

    assert total.top3_correct == 3
    assert total.winner_correct == 1
    assert total.drivers_compared == 5
    assert total.position_errors == (1.0, 2.0, 3.0)


@pytest.mark.unit
def test_an_empty_tally_is_the_identity_for_summation():
    tally = RaceTally(top3_correct=2, position_errors=(1.0,))

    assert sum([tally], RaceTally()) == tally


# ---------------------------------------------------------------------------
# _percentage
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("correct", "possible", "expected"),
    [(3, 3, 100), (1, 3, 33), (2, 3, 67), (0, 5, 0)],
)
def test_percentage_rounds_to_whole_points(correct: int, possible: int, expected: int):
    assert module._percentage(correct, possible) == expected


@pytest.mark.unit
def test_percentage_of_nothing_returns_the_caller_supplied_default():
    assert module._percentage(0, 0) == 0
    assert module._percentage(0, 0, default=None) is None


# ---------------------------------------------------------------------------
# _evaluated_entries
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_only_entries_with_both_a_prediction_and_a_result_are_evaluated():
    history = {
        "(2024,1)": _entry(predicted={"VER": 1}, actual={"VER": 1}),
        "(2024,2)": _entry(predicted={"VER": 1}),
        "(2024,3)": _entry(actual={"VER": 1}),
        "(2024,4)": _entry(),
    }

    evaluated = module._evaluated_entries(history)

    assert len(evaluated) == 1
    assert evaluated[0]["predicted"] == {"VER": 1}
    assert evaluated[0]["risk_predictions"] == {}
    assert evaluated[0]["actual_incidents"] == {}


@pytest.mark.unit
def test_the_latest_snapshot_wins_over_the_entrys_own_prediction():
    """A re-prediction after qualifying is the one that should be scored."""
    history = {
        "(2024,1)": {
            "predicted_positions": {"VER": 5},
            "actual_positions": {"VER": 1},
            "generated_at": "2024-05-01T09:00:00+00:00",
            "snapshots": [
                {"predicted_positions": {"VER": 4}, "generated_at": "2024-05-01T10:00:00+00:00"},
                {
                    "predicted_positions": {"VER": 1},
                    "risk_predictions": {"VER": {"dnf_risk_pct": 20}},
                    "generated_at": "2024-05-01T18:00:00+00:00",
                },
            ],
        }
    }

    evaluated = module._evaluated_entries(history)

    assert evaluated[0]["predicted"] == {"VER": 1}
    assert evaluated[0]["generated_at"] == "2024-05-01T18:00:00+00:00"
    assert evaluated[0]["risk_predictions"] == {"VER": {"dnf_risk_pct": 20}}


@pytest.mark.unit
def test_a_snapshot_without_its_own_timestamp_falls_back_to_the_entrys():
    history = {
        "(2024,1)": {
            "actual_positions": {"VER": 1},
            "generated_at": "2024-05-01T09:00:00+00:00",
            "snapshots": [{"predicted_positions": {"VER": 1}}],
        }
    }

    assert module._evaluated_entries(history)[0]["generated_at"] == "2024-05-01T09:00:00+00:00"


# ---------------------------------------------------------------------------
# _backfill_actuals
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_backfill_requests_results_only_for_predictions_still_missing_them(
    monkeypatch: pytest.MonkeyPatch,
):
    recorded = _stub_history(monkeypatch, {})
    history = {
        "(2024,1)": _entry(predicted={"VER": 1}),
        "(2024,2)": _entry(predicted={"VER": 1}, actual={"VER": 1}),
        "(2024,3)": _entry(),
    }

    module._backfill_actuals(history)

    assert recorded == [(2024, 1)]


@pytest.mark.unit
def test_an_unparsable_history_key_is_skipped_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
):
    recorded = _stub_history(monkeypatch, {})

    module._backfill_actuals({"not-a-key": _entry(predicted={"VER": 1})})

    assert recorded == []


# ---------------------------------------------------------------------------
# _score_race
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_race_with_no_shared_drivers_scores_nothing():
    tally = module._score_race({"predicted": {"VER": 1}, "actual": {"NOR": 1}})

    assert tally == RaceTally()


@pytest.mark.unit
def test_a_perfect_prediction_scores_every_metric():
    race = {
        "predicted": {"VER": 1, "NOR": 2, "LEC": 3, "HAM": 4},
        "actual": {"VER": 1, "NOR": 2, "LEC": 3, "HAM": 4},
    }

    tally = module._score_race(race)

    assert tally.winner_correct == 1
    assert tally.top3_correct == 3
    assert tally.top3_possible == 3
    assert tally.top10_correct == 4
    assert tally.top10_possible == 4
    assert tally.exact_positions == 4
    assert tally.drivers_compared == 4
    assert tally.position_errors == (0, 0, 0, 0)


@pytest.mark.unit
def test_a_shuffled_podium_still_counts_the_drivers_who_made_it():
    race = {
        "predicted": {"VER": 1, "NOR": 2, "LEC": 3},
        "actual": {"NOR": 1, "VER": 2, "HAM": 3, "LEC": 4},
    }

    tally = module._score_race(race)

    assert tally.winner_correct == 0
    assert tally.top3_correct == 2  # VER and NOR made the real podium; LEC did not.
    assert tally.exact_positions == 0
    assert sorted(tally.position_errors) == [1, 1, 1]


@pytest.mark.unit
def test_drivers_outside_the_shared_set_never_reach_the_denominator():
    """A driver predicted but absent from the result cannot make top-3 possible."""
    race = {"predicted": {"VER": 1, "NOR": 2, "LEC": 3}, "actual": {"VER": 1}}

    tally = module._score_race(race)

    assert tally.top3_possible == 1
    assert tally.top3_correct == 1
    assert tally.drivers_compared == 1


@pytest.mark.unit
def test_risk_flags_are_scored_against_their_thresholds():
    race = {
        "predicted": {"VER": 1, "NOR": 2, "LEC": 3},
        "actual": {"VER": 1, "NOR": 2, "LEC": 3},
        "risk_predictions": {
            "VER": {"dnf_risk_pct": 16, "crash_risk_pct": 10},
            "NOR": {"dnf_risk_pct": 15.9, "crash_risk_pct": 9.9},
            "LEC": {"dnf_risk_pct": 40, "crash_risk_pct": 30},
        },
        "actual_incidents": {
            "VER": {"dnf": True, "crash": True},
            "NOR": {"dnf": True, "crash": False},
        },
    }

    tally = module._score_race(race)

    assert tally.dnf_actual == 2
    assert tally.dnf_correct == 1  # VER was flagged at the threshold; NOR just under.
    assert tally.crash_actual == 1
    assert tally.crash_correct == 1


@pytest.mark.unit
def test_unparsable_risk_values_do_not_count_as_a_flag():
    race = {
        "predicted": {"VER": 1},
        "actual": {"VER": 1},
        "risk_predictions": {"VER": {"dnf_risk_pct": None, "crash_risk_pct": "n/a"}},
        "actual_incidents": {"VER": {"dnf": True, "crash": True}},
    }

    tally = module._score_race(race)

    assert tally.dnf_correct == 0
    assert tally.crash_correct == 0
    assert tally.dnf_actual == 1


@pytest.mark.unit
def test_a_race_without_risk_or_incident_data_scores_no_risk_metrics():
    tally = module._score_race({"predicted": {"VER": 1}, "actual": {"VER": 1}})

    assert (tally.dnf_actual, tally.dnf_correct) == (0, 0)
    assert (tally.crash_actual, tally.crash_correct) == (0, 0)


# ---------------------------------------------------------------------------
# _summarise
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_summary_turns_the_tally_into_reported_percentages():
    tally = RaceTally(
        top3_correct=4,
        top3_possible=6,
        top10_correct=15,
        top10_possible=20,
        winner_correct=1,
        exact_positions=5,
        drivers_compared=40,
        dnf_correct=1,
        dnf_actual=4,
        crash_correct=0,
        crash_actual=2,
        position_errors=(1.0, 2.0, 3.0),
    )

    summary = module._summarise(tally, races_evaluated=2, window=8)

    assert summary == {
        "recent_winner_pct": 50,
        "recent_top3_pct": 67,
        "recent_top10_pct": 75,
        # 5/40 is 12.5%, and round() breaks the half toward even.
        "exact_position_pct": 12,
        "avg_position_error": 2.0,
        "dnf_capture_pct": 25,
        "crash_capture_pct": 0,
        "races_evaluated": 2,
        "rolling_window": 8,
    }


@pytest.mark.unit
def test_a_clean_race_reports_no_capture_rate_rather_than_zero():
    """Nothing to catch is not the same as failing to catch anything."""
    summary = module._summarise(RaceTally(drivers_compared=20), races_evaluated=1, window=8)

    assert summary["dnf_capture_pct"] is None
    assert summary["crash_capture_pct"] is None
    assert summary["avg_position_error"] == 0.0


# ---------------------------------------------------------------------------
# get_accuracy_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_unreadable_history_reports_nothing_evaluated(monkeypatch: pytest.MonkeyPatch):
    _stub_history(monkeypatch, RuntimeError("store offline"))

    assert module.get_accuracy_stats() == {"races_evaluated": 0}


@pytest.mark.unit
def test_an_empty_history_reports_nothing_evaluated(monkeypatch: pytest.MonkeyPatch):
    _stub_history(monkeypatch, {})

    assert module.get_accuracy_stats() == {"races_evaluated": 0}


@pytest.mark.unit
def test_stats_are_computed_across_every_scorable_race(monkeypatch: pytest.MonkeyPatch):
    _stub_history(
        monkeypatch,
        {
            "(2024,1)": _entry(
                predicted={"VER": 1, "NOR": 2, "LEC": 3},
                actual={"VER": 1, "NOR": 2, "LEC": 3},
                generated_at="2024-03-01T00:00:00+00:00",
            ),
            "(2024,2)": _entry(
                predicted={"VER": 1, "NOR": 2, "LEC": 3},
                actual={"NOR": 1, "VER": 2, "LEC": 3},
                generated_at="2024-03-15T00:00:00+00:00",
            ),
        },
    )

    stats = module.get_accuracy_stats()

    assert stats["races_evaluated"] == 2
    assert stats["rolling_window"] == 8
    assert stats["recent_winner_pct"] == 50
    assert stats["recent_top3_pct"] == 100
    assert stats["exact_position_pct"] == 67


@pytest.mark.unit
def test_only_the_most_recent_races_inside_the_window_are_scored(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_history(
        monkeypatch,
        {
            "(2024,1)": _entry(
                predicted={"VER": 1},
                actual={"NOR": 1, "VER": 9},
                generated_at="2024-03-01T00:00:00+00:00",
            ),
            "(2024,2)": _entry(
                predicted={"VER": 1},
                actual={"VER": 1},
                generated_at="2024-03-15T00:00:00+00:00",
            ),
        },
    )

    stats = module.get_accuracy_stats(last_n_races=1)

    assert stats["races_evaluated"] == 1
    assert stats["rolling_window"] == 1
    assert stats["exact_position_pct"] == 100


@pytest.mark.unit
def test_results_are_backfilled_once_before_giving_up(monkeypatch: pytest.MonkeyPatch):
    unscored = {"(2024,1)": _entry(predicted={"VER": 1})}
    scored = {"(2024,1)": _entry(predicted={"VER": 1}, actual={"VER": 1})}
    recorded = _stub_history(monkeypatch, unscored, scored)

    stats = module.get_accuracy_stats()

    assert recorded == [(2024, 1)]
    assert stats["races_evaluated"] == 1


@pytest.mark.unit
def test_a_history_that_fails_on_reload_after_backfill_reports_nothing(
    monkeypatch: pytest.MonkeyPatch,
):
    unscored = {"(2024,1)": _entry(predicted={"VER": 1})}
    _stub_history(monkeypatch, unscored, RuntimeError("store offline"))

    assert module.get_accuracy_stats() == {"races_evaluated": 0}


@pytest.mark.unit
def test_a_backfill_that_finds_no_result_reports_nothing_evaluated(
    monkeypatch: pytest.MonkeyPatch,
):
    unscored = {"(2024,1)": _entry(predicted={"VER": 1})}
    _stub_history(monkeypatch, unscored, unscored)

    assert module.get_accuracy_stats() == {"races_evaluated": 0}
