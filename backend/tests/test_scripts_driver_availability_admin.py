"""Tests for ``scripts.driver_availability_admin`` — the manual entry-list bridge.

This CLI writes straight into the grid production predicts from, so what it
reports matters as much as what it does:

* **A write is only "Written." when it is durable.** A write held in memory on
  an ephemeral disk would vanish with the container while the operator believed
  the grid was fixed — that must be a non-zero exit, not a success.
* **Validation failures are refused loudly.** An adjustment without attribution
  (or with a placeholder pasted from the docs) is rejected with an error and a
  non-zero exit rather than a stack trace.
* **The target store is announced first.** Whether this run changes production
  depends on ``DATABASE_URL``, so the backend is printed before anything else.

The availability module and the document store are replaced at their own
module attributes, because the handlers import them lazily.
"""

from __future__ import annotations

import sys

import pytest

from app.data import driver_availability, store
from app.data.driver_availability import (
    STATUS_OUT,
    DriverAdjustment,
    InvalidAdjustmentError,
    WeekendAvailability,
    Withdrawal,
)
from app.data.store_types import WriteResult
from scripts import driver_availability_admin as admin

pytestmark = pytest.mark.unit

ADJUSTMENT = DriverAdjustment(
    driver_code="HAD",
    status=STATUS_OUT,
    reason="wrist injury",
    source="https://example.test/announcement",
    noted_at="2026-08-20T09:00:00+00:00",
)


class _Health:
    backend = "file"


class _FakeStore:
    def health(self) -> _Health:
        return _Health()


@pytest.fixture(autouse=True)
def _file_store(monkeypatch):
    monkeypatch.setattr(store, "document_store", _FakeStore())


def _run(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["driver_availability_admin", *argv])
    return admin.main()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_prints_each_recorded_adjustment(monkeypatch, capsys):
    monkeypatch.setattr(
        driver_availability,
        "load_weekend_availability",
        lambda year, round_num: WeekendAvailability(adjustments=(ADJUSTMENT,)),
    )

    assert _run(monkeypatch, "list", "--year", "2026", "--round", "15") == 0

    out = capsys.readouterr().out
    assert out.startswith("Document store backend: file"), "the target store is named before anything else"
    assert "HAD withdrawn (wrist injury)" in out
    assert "noted 2026-08-20T09:00:00+00:00" in out


def test_list_says_so_when_nothing_is_recorded(monkeypatch, capsys):
    monkeypatch.setattr(driver_availability, "load_weekend_availability", lambda year, round_num: WeekendAvailability())

    assert _run(monkeypatch, "list", "--year", "2026", "--round", "15") == 0
    assert "No adjustments recorded for 2026 round 15." in capsys.readouterr().out


def test_list_fails_when_the_document_cannot_be_read(monkeypatch, capsys):
    """An outage is not "no adjustments" — saying so would hide a withdrawal."""
    monkeypatch.setattr(
        driver_availability,
        "load_weekend_availability",
        lambda year, round_num: WeekendAvailability(ok=False, error="connection refused"),
    )

    assert _run(monkeypatch, "list", "--year", "2026", "--round", "15") == 1
    assert "ERROR: could not read availability document: connection refused" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# out
# ---------------------------------------------------------------------------


def test_out_records_the_withdrawal_with_its_replacement(monkeypatch, capsys):
    recorded: list[tuple] = []

    def _record(year, round_num, withdrawal) -> WriteResult:
        recorded.append((year, round_num, withdrawal))
        return WriteResult()

    monkeypatch.setattr(driver_availability, "record_driver_out", _record)

    code = _run(
        monkeypatch,
        "out", "--year", "2026", "--round", "15", "--driver", "HAD",
        "--reason", "wrist injury", "--source", "https://example.test/a",
        "--replacement-code", "LIN", "--replacement-name", "Arvid Lindblad", "--replacement-team", "Red Bull",
    )  # fmt: skip

    assert code == 0
    assert recorded == [
        (
            2026,
            15,
            Withdrawal(
                driver_code="HAD",
                reason="wrist injury",
                source="https://example.test/a",
                replacement_code="LIN",
                replacement_name="Arvid Lindblad",
                replacement_team="Red Bull",
            ),
        )
    ]
    assert "Written." in capsys.readouterr().out


def test_out_without_a_replacement_sends_empty_replacement_fields(monkeypatch):
    recorded: list[Withdrawal] = []
    monkeypatch.setattr(
        driver_availability,
        "record_driver_out",
        lambda year, round_num, withdrawal: recorded.append(withdrawal) or WriteResult(),
    )

    _run(monkeypatch, "out", "--year", "2026", "--round", "15", "--driver", "HAD", "--reason", "r", "--source", "s")

    assert recorded == [Withdrawal(driver_code="HAD", reason="r", source="s")]


def test_out_refuses_an_invalid_adjustment(monkeypatch, capsys):
    def _reject(*_args):
        raise InvalidAdjustmentError("source looks like an unfilled placeholder: <announcement-url>")

    monkeypatch.setattr(driver_availability, "record_driver_out", _reject)

    code = _run(
        monkeypatch,
        "out", "--year", "2026", "--round", "15", "--driver", "HAD",
        "--reason", "r", "--source", "<announcement-url>",
    )  # fmt: skip

    assert code == 1
    assert "ERROR: source looks like an unfilled placeholder" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (WriteResult(ok=False, durable=False, error="permission denied"), "ERROR: write failed: permission denied"),
        (WriteResult(ok=True, durable=False), "WARNING: write is not durable"),
    ],
    ids=["failed", "not-durable"],
)
def test_out_is_a_failure_unless_the_write_is_durable(monkeypatch, capsys, result, message):
    monkeypatch.setattr(driver_availability, "record_driver_out", lambda *_args: result)

    code = _run(
        monkeypatch, "out", "--year", "2026", "--round", "15", "--driver", "HAD", "--reason", "r", "--source", "s"
    )

    assert code == 1
    assert message in capsys.readouterr().out


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_removes_the_drivers_adjustment(monkeypatch, capsys):
    cleared: list[tuple] = []
    monkeypatch.setattr(
        driver_availability,
        "clear_driver_adjustment",
        lambda year, round_num, driver: cleared.append((year, round_num, driver)) or WriteResult(),
    )

    assert _run(monkeypatch, "clear", "--year", "2026", "--round", "15", "--driver", "HAD") == 0
    assert cleared == [(2026, 15, "HAD")]
    assert "Written." in capsys.readouterr().out


def test_clear_refuses_an_invalid_driver_code(monkeypatch, capsys):
    def _reject(*_args):
        raise InvalidAdjustmentError("driver_code must be three letters")

    monkeypatch.setattr(driver_availability, "clear_driver_adjustment", _reject)

    assert _run(monkeypatch, "clear", "--year", "2026", "--round", "15", "--driver", "H4D") == 1
    assert "ERROR: driver_code must be three letters" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def test_a_command_is_required(monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch)


def test_out_requires_attribution(monkeypatch):
    """No --reason / --source means no write — argparse refuses before any I/O."""
    with pytest.raises(SystemExit):
        _run(monkeypatch, "out", "--year", "2026", "--round", "15", "--driver", "HAD")
