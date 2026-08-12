#!/usr/bin/env python3
"""Reads a Ruff JSON report on stdin and splits the findings into two gates.

  - sonar gate — the code-smell rule families plus the complexity budgets that
    mirror them (see `backend/ruff.toml`, "Code smells" and "Complexity
    budgets" sections).
  - lint gate  — every other rule (correctness, type hygiene, imports, style).

This is the Python counterpart to `eslint-gate-report.mjs`, and works the same
way: both gates read one Ruff run, so there is exactly one lint pass per commit
and the split only changes how failures are reported and attributed.

Exit code: 0 when there are no findings, 1 when either gate has at least one.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# Rule families attributed to the sonar gate. Everything else is the lint gate.
# Ruff codes are a letter prefix plus digits, so a family is matched on prefix.
SONAR_PREFIXES = (
    "SIM",  # flake8-simplify — collapsible ifs, redundant booleans
    "RET",  # flake8-return — superfluous else, unnecessary assign
    "PIE",  # unnecessary/duplicated code
    "C4",  # comprehension smells
    "PERF",  # avoidable overhead
    "FURB",  # modernisation refactors
    "ARG",  # unused arguments
    "SLF",  # private-member access
    "RSE",  # raise smells
)

# Individual rules that belong to the sonar gate regardless of family — the
# complexity budgets ported from the frontend's `complexity` / `max-depth` /
# `max-params` / `max-lines-per-function` rules.
SONAR_RULES = frozenset(
    {
        "C901",  # cyclomatic complexity
        "PLR0911",  # too many returns
        "PLR0912",  # too many branches
        "PLR0913",  # too many arguments
        "PLR0915",  # too many statements
        "PLR0916",  # too many boolean expressions
        "PLR0917",  # too many positional arguments
        "PLR1702",  # too many nested blocks
    }
)

# A Ruff code is a family prefix followed by digits. Used only to reject strings
# that are not rule codes at all, so a stray log line cannot match a prefix.
_CODE = re.compile(r"^[A-Z]+\d+$")


def is_sonar(code: str | None) -> bool:
    """True when a rule code is owned by the sonar gate."""
    if not code:
        return False
    if code in SONAR_RULES:
        return True
    if not _CODE.match(code):
        return False
    # Prefix test rather than a letters-only capture: `C4` (the comprehension
    # family) contains a digit, so splitting letters from digits would reduce
    # `C401` to `C` and quietly file every comprehension smell under lint.
    return code.startswith(SONAR_PREFIXES)


class Colour:
    """ANSI helpers that no-op when stderr is not a terminal."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def print_gate(label: str, findings: list[dict], root: Path, colour: Colour) -> int:
    """Print one gate's findings, grouped by file. Returns the finding count."""
    if not findings:
        print(f"  {label}: no findings", file=sys.stderr)
        return 0

    print(f"  {colour.bold(label)}: {colour.red(f'{len(findings)} error(s)')}", file=sys.stderr)

    by_file: dict[str, list[dict]] = {}
    for finding in findings:
        raw = finding.get("filename") or "(unknown)"
        try:
            name = str(Path(raw).relative_to(root))
        except ValueError:
            name = raw
        by_file.setdefault(name, []).append(finding)

    for name, file_findings in sorted(by_file.items()):
        print(f"    {name}", file=sys.stderr)
        for finding in file_findings:
            location = finding.get("location") or {}
            position = colour.dim(f"{location.get('row', '?')}:{location.get('column', '?')}")
            rule = colour.dim(finding.get("code") or "(no rule)")
            print(f"      {position}  {finding.get('message', '')}  {rule}", file=sys.stderr)

    return len(findings)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    colour = Colour(sys.stderr.isatty())
    raw = sys.stdin.read().strip()

    if not raw:
        print(colour.red("Ruff produced no output — treating as a gate failure."), file=sys.stderr)
        return 1

    try:
        findings = json.loads(raw)
    except json.JSONDecodeError:
        print(colour.red("Could not parse the Ruff report:"), file=sys.stderr)
        print(raw, file=sys.stderr)
        return 1

    lint = print_gate(
        "lint gate ", [f for f in findings if not is_sonar(f.get("code"))], root, colour
    )
    sonar = print_gate("sonar gate", [f for f in findings if is_sonar(f.get("code"))], root, colour)

    return 1 if lint + sonar > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
