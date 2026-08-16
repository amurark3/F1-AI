# Local quality gates

`pre-commit` blocks a commit when any of three gates fail:

`pre-commit` blocks a commit when any gate fails. Frontend and backend run the
same set of gates through different tools:

| Gate | Frontend | Backend | Runs when |
| --- | --- | --- | --- |
| **format** | — (Prettier is not gated) | `ruff format --check` | backend `.py` staged |
| **lint** | ESLint — correctness, type hygiene, imports, style | Ruff — same categories | matching file staged |
| **sonar** | the `sonarjs/*` rules + complexity/size budgets | the code-smell families + complexity budgets | matching file staged |
| **size** | ESLint `max-lines` (part of sonar) | `tools/check_module_size.py` | backend `.py` staged |
| **test** | — | `pytest` | backend `.py` staged |

Frontend gates run on a staged `frontend/**/*.{ts,tsx,js,jsx,mjs,cjs}`; backend
gates on a staged `backend/**/*.py`.

On each side the lint and sonar gates share a single pass — the split only
changes how failures are attributed, so a commit costs one lint run, not two.
Those runs are `eslint .` and `ruff check .`, identical to the `frontend_lint`
and `backend_lint` jobs in
[`pr-auto-review.yml`](../.github/workflows/pr-auto-review.yml), so the hook
cannot pass on a diff CI would reject. Warnings are printed but never block,
matching CI.

The test gate has the same relationship to the `backend_tests` job: both run
`pytest -q` from `backend/`. CI installs `requirements.txt` alongside
`requirements-dev.txt`, so a dependency-only change — which stages no `.py` file
and therefore skips this gate entirely — is still exercised by the suite on the PR.

The size gate is separate rather than part of lint because Ruff has no
per-module line budget rule; `backend/tools/check_module_size.py` is what
enforces the 500-line (800 for tests) budget that mirrors the frontend's
`max-lines`.

Gate ownership of a rule lives in `SONAR_RULES` / `SONAR_RULE_PREFIX` at the top
of `eslint-gate-report.mjs`, and in `SONAR_RULES` / `SONAR_PREFIXES` in
`ruff-gate-report.py`.

Every gate here is client-side and opt-in per clone, so it is a fast first
opinion, not the enforcement boundary. The jobs in `pr-auto-review.yml` are what
actually run on every PR, including ones no local hook can reach (Dependabot
bumps, GitHub web edits, `--no-verify`).

## Install

Hooks are not installed by cloning — each clone opts in once:

```bash
git config core.hooksPath .githooks
```

## Bypass

```bash
git commit --no-verify      # skip all git hooks
SKIP_GATES=1 git commit     # skip these gates only
```

## Requirements

- `frontend/node_modules` present (`cd frontend && npm ci`) — the lint and sonar
  gates fail loudly rather than silently passing when it is missing.
- `backend/.venv` with `requirements-dev.txt` installed (`ruff` and `pytest`), or
  both on `PATH`. Like the frontend gates, these fail loudly when a tool is
  missing rather than passing by default.
