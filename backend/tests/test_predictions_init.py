"""Tests for the prediction package's public surface (app.data.predictions).

The package was split into a stack of modules (sessions, form, standings,
incidents, scoring, history, model, review, accuracy, compute) behind a
re-export shim, precisely so that ``from app.data.predictions import
compute_race_predictions`` kept working for every existing caller — routers,
services, the MCP server and the self-improvement loop.

The risk this file covers is that shim silently drifting: a name dropped from
``__all__`` breaks a star import, and a name in ``__all__`` that no longer
resolves breaks it louder. Both are invisible to the modules' own tests, which
import from the defining module rather than the package.
"""

from __future__ import annotations

import importlib

import pytest

from app.data import predictions

# name -> module that defines it. Re-exports must be the *same object*, not a
# copy: app.services.self_improvement monkeypatches some of these in tests, and
# a rebound duplicate would make the patch a no-op.
_DEFINING_MODULE = {
    "ACTUAL_RESULT_RETRY_SECONDS": "app.data.predictions.history",
    "ADAPTIVE_CORRECTION_WEIGHT": "app.data.predictions.compute",
    "ML_BLEND_WEIGHT": "app.data.predictions.compute",
    "MODEL_PATH": "app.data.predictions.model",
    "PREDICTION_LOGIC_VERSION": "app.data.predictions.version",
    "_latest_prediction_snapshot": "app.data.predictions.review",
    "_load_prediction_history": "app.data.predictions.history",
    "build_prediction_review": "app.data.predictions.review",
    "compute_race_predictions": "app.data.predictions.compute",
    "get_accuracy_stats": "app.data.predictions.accuracy",
    "get_prediction_review": "app.data.predictions.review",
    "record_actual_result": "app.data.predictions.history",
    "safe_number": "app.data.predictions.scoring",
    "save_prediction": "app.data.predictions.history",
    "warm_model_cache": "app.data.predictions.model",
}


@pytest.mark.unit
def test_public_surface_is_exactly_the_documented_export_list():
    assert set(predictions.__all__) == set(_DEFINING_MODULE)


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_DEFINING_MODULE))
def test_every_exported_name_is_the_object_its_module_defines(name):
    module = importlib.import_module(_DEFINING_MODULE[name])

    assert getattr(predictions, name) is getattr(module, name)


@pytest.mark.unit
def test_export_list_is_sorted_so_additions_do_not_churn_the_diff():
    assert predictions.__all__ == sorted(predictions.__all__)


@pytest.mark.unit
def test_the_layering_documented_in_the_docstring_is_the_import_order():
    # The package docstring promises a line, not a web: scoring must not reach
    # back up into compute, or the "lowest first" claim is false and an import
    # cycle is one edit away.
    from app.data.predictions import scoring

    assert not hasattr(scoring, "compute_race_predictions")
