"""Tests for .githooks/ruff-gate-report.py — the pre-commit Ruff reporter.

This script decides whether a commit is blocked, so the failure that matters is
the one that lets a dirty diff through. Two shapes of that:

* **Silence read as success.** Ruff producing no output at all, or output that is
  not JSON, means the run did not happen — not that the code is clean. Both must
  exit non-zero, because a gate that treats "I could not tell" as "fine" is
  worse than no gate.
* **A finding attributed to neither gate.** Every rule code has to land in
  exactly one of lint/sonar. A code that matches neither would be counted, but
  printed under a heading that hides what it was.

The module lives outside ``backend/`` and its filename has dashes, so it cannot
be imported normally; it is loaded from its path once and shared.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import types

_SCRIPT = Path(__file__).resolve().parents[2] / ".githooks" / "ruff-gate-report.py"


def _load() -> types.ModuleType:
    """Import the hook script by path, since `ruff-gate-report` is not an identifier."""
    spec = importlib.util.spec_from_file_location("ruff_gate_report", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered so coverage attributes the executed lines to this module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = _load()


def _finding(code: str, *, filename: str = "/repo/backend/app/x.py", row: int = 3, column: int = 7) -> dict:
    return {
        "code": code,
        "filename": filename,
        "location": {"row": row, "column": column},
        "message": f"message for {code}",
    }


def _run(module_findings: list[dict] | str, monkeypatch: pytest.MonkeyPatch, *, argv: list[str] | None = None) -> int:
    raw = module_findings if isinstance(module_findings, str) else json.dumps(module_findings)
    monkeypatch.setattr(report.sys, "argv", ["ruff-gate-report.py", *(argv or [])])
    monkeypatch.setattr(report.sys, "stdin", _Stdin(raw))
    return report.main()


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text

    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# is_sonar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "code",
    ["SIM103", "RET504", "PIE790", "C401", "PERF401", "FURB110", "ARG001", "SLF001", "RSE102"],
)
def test_code_smell_families_belong_to_the_sonar_gate(code: str) -> None:
    assert report.is_sonar(code) is True


@pytest.mark.parametrize(
    "code",
    ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0916", "PLR0917", "PLR1702"],
)
def test_the_complexity_budgets_belong_to_the_sonar_gate(code: str) -> None:
    """These are individually named because their family (PLR) is a lint family."""
    assert report.is_sonar(code) is True


@pytest.mark.parametrize("code", ["E501", "F401", "ANN001", "UP007", "PLR2004", "PLW0603", "T201"])
def test_everything_else_belongs_to_the_lint_gate(code: str) -> None:
    assert report.is_sonar(code) is False


@pytest.mark.parametrize("code", [None, "", "not-a-code", "SIM", "123"])
def test_a_missing_or_malformed_code_is_not_attributed_to_sonar(code: str | None) -> None:
    """A code the regex cannot parse falls to the lint gate rather than vanishing."""
    assert report.is_sonar(code) is False


def test_every_sonar_prefix_is_a_parseable_family() -> None:
    """Guards the table itself: a typo'd prefix would silently match nothing."""
    for prefix in report.SONAR_PREFIXES:
        assert report.is_sonar(f"{prefix}001") is True


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
def test_colour_wraps_text_in_ansi_when_enabled() -> None:
    colour = report.Colour(enabled=True)

    assert colour.red("x") == "\033[31mx\033[0m"
    assert colour.dim("x") == "\033[2mx\033[0m"
    assert colour.bold("x") == "\033[1mx\033[0m"


def test_colour_is_a_no_op_when_stderr_is_not_a_terminal() -> None:
    """Keeps escape codes out of CI logs and out of piped output."""
    colour = report.Colour(enabled=False)

    assert colour.red("x") == "x"
    assert colour.dim("x") == "x"
    assert colour.bold("x") == "x"


# ---------------------------------------------------------------------------
# print_gate
# ---------------------------------------------------------------------------
def test_print_gate_reports_no_findings_and_counts_zero(capsys: pytest.CaptureFixture) -> None:
    count = report.print_gate("lint gate", [], Path("/repo"), report.Colour(enabled=False))

    assert count == 0
    assert "lint gate: no findings" in capsys.readouterr().err


def test_print_gate_groups_findings_by_file_with_position_and_rule(capsys: pytest.CaptureFixture) -> None:
    findings = [
        _finding("SIM103", filename="/repo/app/b.py", row=10, column=2),
        _finding("SIM102", filename="/repo/app/a.py", row=4, column=1),
        _finding("RET504", filename="/repo/app/a.py", row=9, column=5),
    ]

    count = report.print_gate("sonar gate", findings, Path("/repo"), report.Colour(enabled=False))
    err = capsys.readouterr().err

    assert count == 3
    assert "3 error(s)" in err
    # Files are sorted, so a.py (with both its findings) precedes b.py.
    assert err.index("app/a.py") < err.index("app/b.py")
    assert "4:1" in err
    assert "SIM102" in err


def test_print_gate_falls_back_to_the_absolute_path_for_a_file_outside_the_root(
    capsys: pytest.CaptureFixture,
) -> None:
    """A path that is not under the root cannot be relativised; show it whole."""
    findings = [_finding("E501", filename="/elsewhere/tool.py")]

    report.print_gate("lint gate", findings, Path("/repo"), report.Colour(enabled=False))

    assert "/elsewhere/tool.py" in capsys.readouterr().err


def test_print_gate_renders_a_finding_that_is_missing_every_optional_field(
    capsys: pytest.CaptureFixture,
) -> None:
    """Ruff's JSON shape is an external contract — a sparse record must not crash."""
    count = report.print_gate("lint gate", [{}], Path("/repo"), report.Colour(enabled=False))
    err = capsys.readouterr().err

    assert count == 1
    assert "(unknown)" in err
    assert "?:?" in err
    assert "(no rule)" in err


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_exits_zero_on_an_empty_finding_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert _run([], monkeypatch) == 0

    err = capsys.readouterr().err
    assert "lint gate : no findings" in err
    assert "sonar gate: no findings" in err


def test_main_exits_one_when_only_the_lint_gate_has_findings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert _run([_finding("F401")], monkeypatch) == 1

    err = capsys.readouterr().err
    assert "F401" in err
    assert "sonar gate: no findings" in err


def test_main_exits_one_when_only_the_sonar_gate_has_findings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert _run([_finding("C901")], monkeypatch) == 1

    err = capsys.readouterr().err
    assert "C901" in err
    assert "lint gate : no findings" in err


def test_main_splits_a_mixed_report_across_both_gates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert _run([_finding("F401"), _finding("SIM103")], monkeypatch) == 1

    err = capsys.readouterr().err
    assert err.count("1 error(s)") == 2


def test_main_treats_empty_ruff_output_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """No output means the run did not happen, which is not the same as clean."""
    assert _run("   \n  ", monkeypatch) == 1
    assert "no output" in capsys.readouterr().err


def test_main_treats_unparseable_ruff_output_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    assert _run("error: unknown option --output-format", monkeypatch) == 1

    err = capsys.readouterr().err
    assert "Could not parse" in err
    # The raw text is echoed so the author can see what Ruff actually said.
    assert "unknown option" in err


def test_main_relativises_against_the_root_given_as_an_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    findings = [_finding("F401", filename=str(tmp_path / "app" / "x.py"))]

    assert _run(findings, monkeypatch, argv=[str(tmp_path)]) == 1
    assert "app/x.py" in capsys.readouterr().err


def test_main_falls_back_to_the_working_directory_when_given_no_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    findings = [_finding("F401", filename=str(tmp_path / "app" / "x.py"))]

    assert _run(findings, monkeypatch) == 1
    assert "app/x.py" in capsys.readouterr().err
