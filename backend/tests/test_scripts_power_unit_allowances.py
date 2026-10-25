"""Tests for ``scripts.power_unit_allowances`` — pinning an allowance by hand.

The properties pinned: an override is attributed (a ``--note`` is required, and
a pasted placeholder is refused), it names a real element of the season, and a
failed or non-durable write exits non-zero instead of claiming success.
"""

from __future__ import annotations

import os

import pytest

# `load_dotenv()` at the script's module scope repopulates the credentials
# conftest cleared. Restore the environment the moment the import returns.
_ENV_BEFORE_IMPORT = dict(os.environ)
from scripts import power_unit_allowances as script  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_IMPORT)

from app.data.power_units import allowances  # noqa: E402
from app.data.power_units.allowances import SOURCE_MANUAL, load_allowances, save_allowances  # noqa: E402
from app.data.store_types import ReadResult, WriteResult  # noqa: E402
from tests.power_units_support import allowance_entries  # noqa: E402


@pytest.fixture
def store_dir(isolated_data_dir):
    return isolated_data_dir


def test_show_lists_each_allowance_and_its_source(store_dir, capsys):
    pinned = allowance_entries()["ICE"].__class__("ICE", 5, SOURCE_MANUAL, None, None, None, "t", "why")
    save_allowances(2026, allowance_entries(ICE=pinned))
    assert script.main(["show", "--year", "2026"]) == script.EXIT_OK

    out = capsys.readouterr().out
    assert "Document store backend: file" in out
    assert "ICE      5  manual      —  (updated t)" in out
    assert "note: why" in out
    assert "TC       4  fia_report  Doc 13 - New PU Elements for this Competition" in out


def test_show_with_nothing_stored_says_so(store_dir, capsys):
    assert script.main(["show", "--year", "2026"]) == script.EXIT_OK
    assert "No allowances stored for 2026 yet" in capsys.readouterr().out


def test_pin_and_unpin_round_trip(store_dir, capsys):
    assert script.main(["pin", "--year", "2026", "--element", "pu-ce", "--allowance", "4", "--note", "B8.2.3b"]) == 0
    entry = load_allowances(2026)["PU-CE"]
    assert (entry.allowance, entry.source, entry.note) == (4, SOURCE_MANUAL, "B8.2.3b")
    assert "Written." in capsys.readouterr().out

    assert script.main(["unpin", "--year", "2026", "--element", "PU-CE"]) == script.EXIT_OK
    assert "PU-CE" not in load_allowances(2026)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["pin", "--year", "2026", "--element", "MGU-H", "--allowance", "4", "--note", "x"], "not a 2026 element"),
        (["unpin", "--year", "2026", "--element", "MGU-H"], "not a 2026 element"),
        (["pin", "--year", "2019", "--element", "ICE", "--allowance", "4", "--note", "x"], "(known: none)"),
        (["pin", "--year", "2026", "--element", "ICE", "--allowance", "40", "--note", "x"], "outside 0–20"),
        (["pin", "--year", "2026", "--element", "ICE", "--allowance", "5", "--note", "<why>"], "placeholder"),
        (["pin", "--year", "2026", "--element", "ICE", "--allowance", "5", "--note", "  "], "must say why"),
    ],
)
def test_invalid_input_is_refused_before_anything_is_written(store_dir, capsys, argv, message):
    assert script.main(argv) == script.EXIT_INVALID
    assert message in capsys.readouterr().out
    assert load_allowances(2026) == {}


def test_a_write_that_does_not_land_exits_non_zero(store_dir, capsys, monkeypatch):
    monkeypatch.setattr(allowances.document_store, "write", lambda name, payload: WriteResult(ok=True, durable=False))
    assert script.main(["pin", "--year", "2026", "--element", "ICE", "--allowance", "5", "--note", "x"]) == 2
    assert "held in memory for retry" in capsys.readouterr().out


def test_an_unreadable_store_exits_non_zero(store_dir, capsys, monkeypatch):
    monkeypatch.setattr(allowances.document_store, "read", lambda name: ReadResult(ok=False, error="down"))
    assert script.main(["show", "--year", "2026"]) == script.EXIT_STORE
    assert "could not be read: down" in capsys.readouterr().out
