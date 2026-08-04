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

Gate ownership of a rule lives in `SONAR_RULES` / `SONAR_RULE_PREFIX` at the top of
`eslint-gate-report.mjs`.

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
