"""Tests for the prediction logic version marker (app.data.predictions.version).

The risk this covers: the snapshot cache decides whether a stored prediction was
computed under current logic by comparing this integer, and the backfill script
imports it for the same reason. If it stopped being a plain comparable int, or
the module started pulling in the numeric stack it was split out to avoid, the
cache would either serve superseded predictions or make a version check
expensive.
"""

import ast
from pathlib import Path

import pytest

from app.data.predictions import version as version_module
from app.data.predictions.version import PREDICTION_LOGIC_VERSION


@pytest.mark.unit
def test_logic_version_is_a_positive_int_snapshots_can_be_compared_against():
    assert isinstance(PREDICTION_LOGIC_VERSION, int)
    assert PREDICTION_LOGIC_VERSION > 0


@pytest.mark.unit
def test_logic_version_matches_the_package_re_export():
    from app.data import predictions

    # The cache imports it from the package; the backfill script from the
    # module. They must be the same number or one of them recomputes forever.
    assert predictions.PREDICTION_LOGIC_VERSION == PREDICTION_LOGIC_VERSION


@pytest.mark.unit
def test_version_module_imports_nothing_but_future_annotations():
    # The module exists to be importable without dragging in FastF1, pandas or
    # sklearn, so its own import list is the thing worth pinning.
    tree = ast.parse(Path(version_module.__file__).read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }

    assert imported <= {"__future__"}
