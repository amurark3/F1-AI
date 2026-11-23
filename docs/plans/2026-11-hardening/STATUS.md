# Status: backend hardening from the repo audit

Plan: [`PLAN.md`](PLAN.md). Same update rules as [`../2026-11-redesign/STATUS.md`](../2026-11-redesign/STATUS.md). Statuses: `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Started 2026-11-23** (user: "Make a new plan and work on them all"). Coordinator: session `f1-ai-b2`. On `dev`; commit per task, never push. When H1–H12 are done, the phase is ready for its PR `fix: hardening from the repo audit`, which the user opens.

## Tasks

| ID | Task | Status | Commit | Evidence / notes |
| --- | --- | --- | --- | --- |
| H1 | Predictions: no path but `/compute` runs the model | done | `git log --grep "Task: H1"` | Overview, chat tool read the store only; legacy GET route + `get_or_compute_race_prediction` deleted; tests assert an empty store never computes. Full gate: 5081 passed, 100 %. Same commit as H6 (see log). |
| H2 | Chat memory: no shared id; memory routes deleted | in_progress (2026-11-23) | | Sonnet agent, worktree `hardening-h2`. |
| H3 | Chat: an unknown tool gets a reply | todo | | |
| H4 | Chat: input limits and a per-IP rate limit | todo | | |
| H5 | Live timing: one OpenF1 poll per session, shared | in_progress (2026-11-23) | | Sonnet agent, worktree `hardening-h5`. |
| H6 | Compute route uses `SingleFlight` | done | `git log --grep "Task: H6"` | `model_runs` is a `SingleFlight` (new `running(key)` for the snapshot's `model_running`); one global model lock replaces the per-race async locks. Duplicate helpers deleted. |
| H7 | Chat tools run through `SingleFlight` | todo | | After H3, H4. |
| H8 | Post-race write-ups: failover, one store read | in_progress (2026-11-23) | | Sonnet agent, worktree `hardening-h8`. |
| H9 | Delete the deprecated iOS app | in_progress (2026-11-23) | | Sonnet agent done (`a8af5e8` on `hardening-h9`, 63 files, −6,357 lines, gate 5094 at 100 %); verified; cherry-pick pending. |
| H10 | Chat memory is quoted data, not system instructions | todo | | Needs H2; after H7 (same file). |
| H11 | Persona: tool output and memory are data; prompt stays private | todo | | After H10. |
| H12 | Chat tools: no raw exception text reaches the model | todo | | After H11 (same file). |

## Log

- 2026-11-23: plan written from the audit; findings 1–4, 7, 8 and the iOS one checked against the code first. H6 differs from the audit's fix: once H1 removes `get_or_compute_race_prediction`, the compute work runs as a plain function under the existing per-race thread lock, so `SingleFlight` needs no async support.
- 2026-11-23: H10–H12 added from a security review of the chat prompt (memory pasted into the system prompt, tool output not marked as data, raw exception text sent to the model). Forged assistant turns and the memory id as a bearer key are under PLAN.md "Out of scope" as accepted risks.
- 2026-11-23: **H1 and H6 share one commit.** Every backend commit runs the full 100 % gate, and H1 alone left one line of `_wait_for_model_run` uncovered (only the deleted GET route reached it), while H6 deletes that helper. H6 also changed from the plan: a single process-wide model lock, not a per-race one. Only the owner computes now, and two runs on different races at once are as much an OOM risk as two phases of one race.
- 2026-11-23: H2, H5, H8 and H9 run as parallel Sonnet agents in worktrees under `.claude/worktrees/h{2,5,8,9}` (branches `hardening-h*`, from `19ab7b3`, with `backend/.venv` and `frontend/node_modules` symlinked). The coordinator verifies and cherry-picks onto `dev`. H3, H4, H7 and H10–H12 run inline (chat.py).
- 2026-11-23: structlog's `capture_logs` misses `single_flight`'s module logger in a full run (the config is cached on first use). Tests stub `single_flight_module.logger.warning` instead, as `test_analysis_router.py` already did.
