"""Tests for app.api.tools.provenance: the text a tool returns, with where it came from attached."""

from __future__ import annotations

from langchain_core.tools import tool
import pytest

from app.api.tools import provenance as module
from app.api.tools.provenance import Provenance, Sourced, chip, classification_chips, f1db_chip

pytestmark = pytest.mark.unit

PROVENANCE = Provenance(sources=("f1db",), subject="2026 calendar")


def test_a_sourced_text_reads_as_the_plain_text():
    text = Sourced("### Table", PROVENANCE)

    assert text == "### Table"
    assert text + "!" == "### Table!"
    assert text.provenance is PROVENANCE
    assert str(text) == "### Table"


def test_provenance_survives_a_tools_invoke():
    @tool
    def sourced() -> str:
        """A tool that reports where it read."""
        return Sourced("rows", PROVENANCE)

    assert sourced.invoke({}).provenance is PROVENANCE


@pytest.mark.parametrize(
    ("args", "version", "expected"),
    [
        (("f1db", "standings after R19"), "v2026.19.0", "f1db v2026.19.0 · standings after R19"),
        (("openf1-session-result", "provisional"), None, "OpenF1 session results · provisional"),
        (("OpenWeatherMap",), None, "OpenWeatherMap"),
        (("f1db", None, "", "calendar"), None, "f1db · calendar"),
    ],
)
def test_a_chip_names_the_source_its_version_and_each_detail(args, version, expected):
    assert chip(*args, version=version) == expected


def test_the_f1db_chip_carries_the_installed_version_when_there_is_one(monkeypatch):
    monkeypatch.setattr(module, "installed_version", lambda: "v2026.20.0")
    assert f1db_chip("calendar") == "f1db v2026.20.0 · calendar"

    monkeypatch.setattr(module, "installed_version", lambda: None)
    assert f1db_chip("calendar") == "f1db · calendar"


def test_a_classification_chip_per_source(monkeypatch):
    monkeypatch.setattr(module, "installed_version", lambda: "v2026.20.0")

    assert classification_chips([{"source": "f1db"}], final=True) == ("f1db v2026.20.0",)
    assert classification_chips([{"source": "f1db", "version": "v2026.19.0"}], final=True) == ("f1db v2026.19.0",)
    assert classification_chips([{"source": "fia-final-classification", "document": 86}], final=True) == (
        "FIA final classification · doc 86",
    )
    assert classification_chips([{"source": "openf1-session-result"}], final=False) == (
        "OpenF1 session results · provisional",
    )
