# Local quality gates

`pre-commit` blocks a commit when any of three gates fail:

| Gate | What it runs | Runs when |
| --- | --- | --- |
| **lint** | ESLint — correctness, type hygiene, imports, style | a `frontend/**/*.{ts,tsx,js,jsx,mjs,cjs}` file is staged |
| **sonar** | the `sonarjs/*` rules + complexity/size budgets | same as above |
| **test** | `pytest` (backend suite) | a `backend/**/*.py` file is staged |

The lint and sonar gates share a single ESLint pass — the split only changes how
failures are attributed, so a commit costs one lint run, not two. That run is
`eslint .`, identical to the `frontend_lint` job in
[`pr-auto-review.yml`](../.github/workflows/pr-auto-review.yml), so the hook cannot
pass on a diff CI would reject. Warnings are printed but never block, matching CI.

The test gate has the same relationship to the `backend_tests` job: both run
`pytest -q` from `backend/`. CI installs `requirements.txt` alongside
`requirements-dev.txt`, so a dependency-only change — which stages no `.py` file
and therefore skips this gate entirely — is still exercised by the suite on the PR.

Gate ownership of a rule lives in `SONAR_RULES` / `SONAR_RULE_PREFIX` at the top of
`eslint-gate-report.mjs`.

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
- `backend/.venv` with `pytest` installed, or `pytest` on `PATH`.
