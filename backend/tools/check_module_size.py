"""Enforce a per-module line budget across the backend.

This is the Python half of the frontend's ``max-lines`` ESLint rule. Ruff has no
equivalent — pylint's ``C0302`` is not implemented — so without this check the
"files stay small" half of the quality gate would simply be unenforced while
looking enforced from the config.

Budgets and counting rules match the frontend one-for-one: blank lines and
comment-only lines are excluded, so a module is measured by the code a reader
has to hold, not by its docstrings.

    cd backend
    python -m tools.check_module_size          # exit 1 on any breach
    python -m tools.check_module_size --list   # every module, largest first
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import sys
import tokenize

# Budgets, most specific pattern first — the first match wins. Mirrors the
# `max-lines` settings in frontend/eslint.config.mjs: 500 for sources, 800 for
# test suites, which hold whole scenarios in one module by design.
BUDGETS: tuple[tuple[str, int], ...] = (
    ("tests/*", 800),
    ("*", 500),
)

# Directories that hold no first-party source, as paths relative to the backend
# root. Kept in sync with `extend-exclude` in ruff.toml.
#
# Root-anchored on purpose: matching these names at any depth would exempt
# `app/data/` — the largest package in the backend — from the budget.
EXCLUDED_ROOTS = frozenset(
    {
        ".venv",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "f1_cache",
        "data",
        "models",
        "reports",
        "node_modules",
    }
)

# Matched at any depth: these hold generated artefacts, never source.
EXCLUDED_DIRS = frozenset({"__pycache__"})


@dataclass(frozen=True)
class ModuleSize:
    """Measured size of one module, relative to its budget."""

    path: str
    lines: int
    budget: int

    @property
    def over_budget(self) -> bool:
        return self.lines > self.budget

    @property
    def overage(self) -> int:
        return max(0, self.lines - self.budget)


def budget_for(relative_path: str) -> int:
    """Return the line budget governing ``relative_path``."""
    for pattern, budget in BUDGETS:
        if fnmatch(relative_path, pattern) or relative_path.startswith(pattern.rstrip("*")):
            return budget
    return BUDGETS[-1][1]


def count_code_lines(path: Path) -> int:
    """Count lines in ``path`` excluding blanks and comment-only lines.

    Tokenizing rather than string-matching keeps a ``#`` inside a string literal
    from being miscounted as a comment.
    """
    comment_lines: set[int] = set()
    try:
        with path.open("rb") as handle:
            for token in tokenize.tokenize(handle.readline):
                if token.type == tokenize.COMMENT:
                    comment_lines.add(token.start[0])
    except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        # A module that will not tokenize cannot be measured. Ruff and the
        # syntax check own that failure; reporting it here as a size breach
        # would be a misleading diagnosis.
        return 0

    source_lines = path.read_text(encoding="utf-8").splitlines()
    return sum(1 for number, text in enumerate(source_lines, start=1) if text.strip() and number not in comment_lines)


def is_first_party(relative_parts: tuple[str, ...]) -> bool:
    """True when a module path is neither under an excluded root nor generated."""
    if relative_parts and relative_parts[0] in EXCLUDED_ROOTS:
        return False
    return not EXCLUDED_DIRS.intersection(relative_parts)


def discover_modules(root: Path) -> list[Path]:
    """Return every first-party Python module under ``root``, sorted by path."""
    return sorted(path for path in root.rglob("*.py") if is_first_party(path.relative_to(root).parts))


def measure(root: Path) -> list[ModuleSize]:
    """Measure every discovered module, largest first."""
    sizes = [
        ModuleSize(
            path=str(path.relative_to(root)),
            lines=count_code_lines(path),
            budget=budget_for(str(path.relative_to(root))),
        )
        for path in discover_modules(root)
    ]
    return sorted(sizes, key=lambda size: size.lines, reverse=True)


def render_breaches(breaches: list[ModuleSize]) -> str:
    """Format the failure report for modules that exceed their budget."""
    width = max(len(breach.path) for breach in breaches)
    rows = "\n".join(
        f"  {breach.path:<{width}}  {breach.lines:>5} / {breach.budget}  (+{breach.overage})" for breach in breaches
    )
    plural = "module" if len(breaches) == 1 else "modules"
    return (
        f"{len(breaches)} {plural} over the line budget:\n\n"
        f"{rows}\n\n"
        "Split the module along a seam its callers already imply — a cohesive "
        "group of functions becomes its own module, and the original re-exports "
        "so import paths stay stable."
    )


def render_listing(sizes: list[ModuleSize]) -> str:
    """Format every module, largest first, marking those over budget."""
    width = max(len(size.path) for size in sizes)
    return "\n".join(
        f"  {'✗' if size.over_budget else ' '} {size.path:<{width}}  {size.lines:>5} / {size.budget}" for size in sizes
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Directory to scan (defaults to the backend root).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print every module with its size instead of only breaches.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    sizes = measure(root)
    if not sizes:
        print(f"No Python modules found under {root}", file=sys.stderr)
        return 2

    if args.list:
        print(render_listing(sizes))
        return 0

    breaches = [size for size in sizes if size.over_budget]
    if breaches:
        # Breaches go to stderr: this is the gate's failure report, and callers
        # that pipe stdout away still have to see which module blew its budget.
        print(render_breaches(breaches), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
