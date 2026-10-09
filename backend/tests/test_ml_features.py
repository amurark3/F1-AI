"""Tests for app.ml.features — the train/serve feature contract.

This module is the single definition of the model's input vector, imported by
both the offline trainer and the live inference path. The risk it carries is
train/serve skew: if the column order, the rolling windows or the fallback
values drift, the served model silently receives a differently-shaped signal
and its predictions degrade without any error. Every assertion here pins one
half of that contract.
"""

from __future__ import annotations

import pytest

from app.ml.features import (
    CIRCUIT_FALLBACK,
    FEATURES,
    GRID_DELTA_FALLBACK,
    GRID_FALLBACK,
    RECENT_FORM_FALLBACK,
    RECENT_FORM_WINDOW,
    RECENT_SPRINT_FALLBACK,
    RECENT_SPRINT_WINDOW,
    STANDING_FALLBACK,
    TARGET,
    DriverSignals,
    _mean_or,
    build_feature_row,
    feature_vector,
)


@pytest.mark.unit
def test_feature_order_is_the_model_contract():
    # A trained estimator consumes positional columns; reordering this list
    # invalidates every persisted model artifact.
    assert FEATURES == [
        "grid_position",
        "sprint_position",
        "had_sprint",
        "recent_form_avg",
        "recent_sprint_avg",
        "circuit_avg",
        "team_standing",
        "driver_standing",
        "grid_delta_avg",
    ]
    assert TARGET == "finish_position"


@pytest.mark.unit
def test_feature_names_are_unique():
    assert len(set(FEATURES)) == len(FEATURES)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("values", "window", "expected"),
    [
        ([2, 4, 6], None, 4.0),
        ([1, 2, 3, 4, 5, 6], 3, 5.0),  # only the last three count
        ([7], 5, 7.0),  # window longer than the data keeps everything
    ],
)
def test_mean_or_averages_the_trailing_window(values, window, expected):
    assert _mean_or(values, default=99.0, window=window) == expected


@pytest.mark.unit
@pytest.mark.parametrize("empty", [None, [], ()])
def test_mean_or_returns_default_when_there_is_nothing_to_average(empty):
    assert _mean_or(empty, default=12.5) == 12.5


@pytest.mark.unit
def test_mean_or_returns_default_for_a_truthy_but_empty_iterable():
    """A generator is always truthy yet may yield nothing.

    The emptiness guard therefore has to run *after* materialising the values,
    otherwise ``statistics.mean`` would raise on an empty sequence.
    """
    assert _mean_or((v for v in []), default=3.5) == 3.5


@pytest.mark.unit
def test_build_feature_row_emits_exactly_the_contract_columns():
    row = build_feature_row(DriverSignals())

    assert set(row) == set(FEATURES)


@pytest.mark.unit
def test_build_feature_row_applies_every_fallback_when_no_signal_exists():
    row = build_feature_row(DriverSignals())

    assert row == {
        "grid_position": GRID_FALLBACK,
        "sprint_position": 0.0,
        "had_sprint": 0.0,
        "recent_form_avg": RECENT_FORM_FALLBACK,
        "recent_sprint_avg": RECENT_SPRINT_FALLBACK,
        "circuit_avg": CIRCUIT_FALLBACK,
        "team_standing": STANDING_FALLBACK,
        "driver_standing": STANDING_FALLBACK,
        "grid_delta_avg": GRID_DELTA_FALLBACK,
    }


@pytest.mark.unit
def test_build_feature_row_uses_supplied_signals_over_fallbacks():
    row = build_feature_row(
        DriverSignals(
            grid_position=3,
            sprint_position=2,
            had_sprint=True,
            recent_finishes=[1, 2, 3],
            recent_sprint_finishes=[4, 4],
            circuit_finishes=[5, 7],
            circuit_grid_deltas=[1.0, -3.0],
            team_standing=1,
            driver_standing=2,
        )
    )

    assert row == {
        "grid_position": 3.0,
        "sprint_position": 2.0,
        "had_sprint": 1.0,
        "recent_form_avg": 2.0,
        "recent_sprint_avg": 4.0,
        "circuit_avg": 6.0,
        "team_standing": 1.0,
        "driver_standing": 2.0,
        "grid_delta_avg": -1.0,
    }


@pytest.mark.unit
def test_build_feature_row_returns_floats_for_integer_inputs():
    row = build_feature_row(DriverSignals(grid_position=1, team_standing=2, driver_standing=3))

    assert all(isinstance(v, float) for v in row.values())


@pytest.mark.unit
def test_recent_form_only_considers_the_last_five_races():
    # Ten dismal results followed by five wins must read as "in form".
    row = build_feature_row(DriverSignals(recent_finishes=[20] * 10 + [1] * RECENT_FORM_WINDOW))

    assert row["recent_form_avg"] == 1.0


@pytest.mark.unit
def test_recent_sprint_form_only_considers_the_last_three_sprints():
    row = build_feature_row(DriverSignals(recent_sprint_finishes=[15] * 4 + [2] * RECENT_SPRINT_WINDOW))

    assert row["recent_sprint_avg"] == 2.0


@pytest.mark.unit
def test_circuit_history_uses_every_recorded_visit():
    # Unlike form, circuit history is unwindowed — all editions count, so a
    # visit far outside the 5-race form window still moves the average.
    row = build_feature_row(DriverSignals(circuit_finishes=[1] * 9 + [11]))

    assert row["circuit_avg"] == pytest.approx(2.0)


@pytest.mark.unit
def test_sprint_position_defaults_to_zero_not_the_grid_fallback():
    """0 is the trained sentinel for "no sprint", distinct from a real result."""
    row = build_feature_row(DriverSignals(had_sprint=False))

    assert row["sprint_position"] == 0.0


@pytest.mark.unit
def test_feature_vector_orders_a_row_by_the_feature_contract():
    row = {name: float(i) for i, name in enumerate(FEATURES)}

    assert feature_vector(row) == [float(i) for i in range(len(FEATURES))]


@pytest.mark.unit
def test_feature_vector_substitutes_zero_for_a_missing_column():
    vector = feature_vector({"grid_position": 4.0})

    assert vector[0] == 4.0
    assert vector[1:] == [0.0] * (len(FEATURES) - 1)


@pytest.mark.unit
def test_feature_vector_ignores_columns_outside_the_contract():
    vector = feature_vector({**dict.fromkeys(FEATURES, 1.0), "tyre_temperature": 99.0})

    assert vector == [1.0] * len(FEATURES)


@pytest.mark.unit
def test_driver_signals_is_immutable():
    signals = DriverSignals(grid_position=1)

    with pytest.raises(AttributeError):
        signals.grid_position = 2  # type: ignore[misc]
