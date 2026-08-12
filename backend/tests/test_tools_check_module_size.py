"""Tests for tools.check_module_size — the per-module line budget gate.

This module is gate tooling: it decides whether a commit is allowed to land. The
failure that matters is not a crash but a **pass that should have been a fail**,
because a gate that fails open still reports success and nobody looks again. So
the cases below lean on the ways a breach could go unnoticed:

* **Blank and comment lines must not count.** If they did, a well-documented
  module would breach on prose, and the budget would push authors to strip the
  comments a reader needs.
* **A `#` inside a string is not a comment.** Counting by string-matching would
  under-count any module holding SQL or a regex, letting a real breach through.
* **Excluded roots are anchored at the top level.** `data/` is excluded, but
  `app/data/` is the largest package in the backend — matching that name at any
  depth would exempt it silently.
* **An unmeasurable module must not read as a 0-line pass.** It returns 0 by
  design (ruff and the syntax check own that failure), and that contract is
  pinned here so it cannot change by accident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tools.check_module_size import (
    BUDGETS,
    ModuleSize,
    budget_for,
    count_code_lines,
    discover_modules,
    is_first_party,
    main,
    measure,
    render_breaches,
    render_listing,
)


def _write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ModuleSize
# ---------------------------------------------------------------------------
def test_a_module_at_exactly_its_budget_is_not_over() -> None:
    """The budget is inclusive — 500 lines against a 500 budget is a pass."""
    size = ModuleSize(path="app/x.py", lines=500, budget=500)

    assert size.over_budget is False
    assert size.overage == 0


def test_a_module_one_line_past_its_budget_is_over_by_one() -> None:
    size = ModuleSize(path="app/x.py", lines=501, budget=500)

    assert size.over_budget is True
    assert size.overage == 1


def test_overage_never_reports_a_negative_for_a_module_under_budget() -> None:
    """Overage is a breach size, so an under-budget module reports 0, not -300."""
    assert ModuleSize(path="app/x.py", lines=200, budget=500).overage == 0


# ---------------------------------------------------------------------------
# budget_for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("tests/test_thing.py", 800),
        ("tests/nested/test_thing.py", 800),
        ("app/api/routes.py", 500),
        ("main.py", 500),
        ("tools/check_module_size.py", 500),
        # Not under tests/ — the prefix alone must not buy the larger budget.
        ("testsuite.py", 500),
        ("app/tests/helper.py", 500),
    ],
)
def test_budget_for_resolves_the_most_specific_pattern_first(relative_path: str, expected: int) -> None:
    assert budget_for(relative_path) == expected


def test_budgets_ends_in_a_catch_all_so_every_path_resolves() -> None:
    """The invariant that makes the loop total: the last pattern matches all."""
    assert BUDGETS[-1][0] == "*"


def test_budget_for_rejects_a_budget_table_with_no_catch_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards the invariant above rather than silently inventing a budget."""
    monkeypatch.setattr("tools.check_module_size.BUDGETS", (("tests/*", 800),))

    with pytest.raises(AssertionError, match="no catch-all"):
        budget_for("app/api/routes.py")


# ---------------------------------------------------------------------------
# count_code_lines
# ---------------------------------------------------------------------------
def test_blank_and_comment_only_lines_are_not_counted(tmp_path: Path) -> None:
    """A module is measured by the code a reader must hold, not its prose."""
    path = _write(
        tmp_path,
        "module.py",
        '"""Docstring counts — it is a statement."""\n'
        "\n"
        "# a comment\n"
        "    \n"
        "x = 1\n"
        "\n"
        "y = 2  # trailing comment on a code line still counts the line\n",
    )

    assert count_code_lines(path) == 3


def test_a_hash_inside_a_string_literal_is_not_treated_as_a_comment(tmp_path: Path) -> None:
    """Tokenizing is what makes this correct; string-matching would under-count."""
    path = _write(
        tmp_path,
        "module.py",
        'QUERY = "SELECT 1 # not a comment"\nPATTERN = "#[0-9a-f]{6}"\n',
    )

    assert count_code_lines(path) == 2


def test_a_module_that_will_not_tokenize_measures_as_zero(tmp_path: Path) -> None:
    """Ruff and the syntax check own broken syntax.

    Reporting it here as a size breach would be a misleading diagnosis, so the
    gate stays silent about it — pinned because the alternative (a crash) would
    take the whole gate down over one unparseable file.
    """
    path = _write(tmp_path, "broken.py", "def f(:\n    pass\n")

    assert count_code_lines(path) == 0


def test_a_module_that_is_not_valid_utf8_measures_as_zero(tmp_path: Path) -> None:
    path = tmp_path / "latin.py"
    path.write_bytes(b'x = "\xff\xfe caf\xe9"\n')

    assert count_code_lines(path) == 0


def test_an_empty_module_measures_as_zero(tmp_path: Path) -> None:
    assert count_code_lines(_write(tmp_path, "empty.py", "")) == 0


# ---------------------------------------------------------------------------
# is_first_party / discover_modules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("app", "api", "routes.py"), True),
        (("main.py",), True),
        # Excluded roots, anchored at the top level.
        ((".venv", "lib", "thing.py"), False),
        (("data", "generated.py"), False),
        (("models", "x.py"), False),
        (("reports", "x.py"), False),
        (("node_modules", "x.py"), False),
        # The same names *below* the root stay in scope — app/data/ is the
        # largest package in the backend and must not be exempt.
        (("app", "data", "store.py"), True),
        (("app", "models", "x.py"), True),
        # Generated artefacts, matched at any depth.
        (("app", "__pycache__", "routes.cpython-310.pyc.py"), False),
        (("__pycache__", "x.py"), False),
        ((), True),
    ],
)
def test_is_first_party_anchors_excluded_roots_but_not_generated_dirs(parts: tuple[str, ...], expected: bool) -> None:
    assert is_first_party(parts) is expected


def test_discover_modules_finds_sources_recursively_and_skips_excluded_trees(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "x = 1\n")
    _write(tmp_path, "app/api/routes.py", "x = 1\n")
    _write(tmp_path, "app/data/store.py", "x = 1\n")
    _write(tmp_path, ".venv/lib/dependency.py", "x = 1\n")
    _write(tmp_path, "data/generated.py", "x = 1\n")
    _write(tmp_path, "app/__pycache__/cached.py", "x = 1\n")
    _write(tmp_path, "notes.md", "not python\n")

    found = sorted(str(path.relative_to(tmp_path)) for path in discover_modules(tmp_path))

    assert found == ["app/api/routes.py", "app/data/store.py", "main.py"]


# ---------------------------------------------------------------------------
# measure
# ---------------------------------------------------------------------------
def test_measure_sorts_largest_first_and_applies_the_matching_budget(tmp_path: Path) -> None:
    _write(tmp_path, "app/small.py", "x = 1\n")
    _write(tmp_path, "app/big.py", "x = 1\n" * 3)
    _write(tmp_path, "tests/test_thing.py", "x = 1\n" * 2)

    sizes = measure(tmp_path)

    assert [(size.path, size.lines, size.budget) for size in sizes] == [
        ("app/big.py", 3, 500),
        ("tests/test_thing.py", 2, 800),
        ("app/small.py", 1, 500),
    ]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def test_render_breaches_names_the_module_its_size_and_its_overage() -> None:
    report = render_breaches([ModuleSize(path="app/api/routes.py", lines=612, budget=500)])

    assert "1 module over the line budget" in report
    assert "app/api/routes.py" in report
    assert "612 / 500" in report
    assert "(+112)" in report
    assert "Split the module" in report


def test_render_breaches_pluralises_for_more_than_one_module() -> None:
    report = render_breaches(
        [
            ModuleSize(path="app/a.py", lines=600, budget=500),
            ModuleSize(path="app/b.py", lines=700, budget=500),
        ]
    )

    assert "2 modules over the line budget" in report


def test_render_listing_marks_only_the_modules_over_budget() -> None:
    listing = render_listing(
        [
            ModuleSize(path="app/over.py", lines=600, budget=500),
            ModuleSize(path="app/under.py", lines=100, budget=500),
        ]
    )

    over_line, under_line = listing.splitlines()

    assert over_line.strip().startswith("✗")
    assert not under_line.strip().startswith("✗")
    assert "600 / 500" in over_line
    assert "100 / 500" in under_line


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_exits_zero_when_every_module_is_within_budget(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write(tmp_path, "app/small.py", "x = 1\n")

    assert main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_main_exits_one_and_reports_on_stderr_when_a_module_breaches(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The report goes to stderr so a caller piping stdout away still sees it."""
    _write(tmp_path, "app/huge.py", "x = 1\n" * 501)

    exit_code = main(["--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "app/huge.py" in captured.err
    assert "501 / 500" in captured.err


def test_main_with_list_prints_every_module_and_exits_zero_even_with_a_breach(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--list is an inspection mode, not a gate, so a breach does not fail it."""
    _write(tmp_path, "app/huge.py", "x = 1\n" * 501)
    _write(tmp_path, "app/small.py", "x = 1\n")

    exit_code = main(["--root", str(tmp_path), "--list"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "app/huge.py" in captured.out
    assert "app/small.py" in captured.out


def test_main_exits_two_when_the_root_is_not_a_directory(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Exit 2 is a usage error, distinct from exit 1 (a real breach)."""
    missing = tmp_path / "nope"

    assert main(["--root", str(missing)]) == 2
    assert "Not a directory" in capsys.readouterr().err


def test_main_exits_two_when_the_root_holds_no_python_at_all(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """An empty scan is a misconfigured root, not a clean pass.

    Returning 0 here is exactly how this gate would fail open: pointed at the
    wrong directory it would report success forever.
    """
    (tmp_path / "notes.md").write_text("no python here\n", encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 2
    assert "No Python modules found" in capsys.readouterr().err


def test_the_real_backend_tree_is_within_budget() -> None:
    """The gate run against the repo it guards — this is what CI asserts."""
    assert main([]) == 0
