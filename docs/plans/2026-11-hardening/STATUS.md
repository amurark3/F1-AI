# Status: backend hardening from the repo audit

Plan: [`PLAN.md`](PLAN.md). Same update rules as [`../2026-11-redesign/STATUS.md`](../2026-11-redesign/STATUS.md). Statuses: `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Started 2026-11-23** (user: "Make a new plan and work on them all"). Coordinator: session `f1-ai-b2`. On `dev`; commit per task, never push. **H1–H12 are done (2026-11-23); the phase is ready for its PR `fix: hardening from the repo audit`, which the user opens.**

## Tasks

| ID | Task | Status | Commit | Evidence / notes |
| --- | --- | --- | --- | --- |
| H1 | Predictions: no path but `/compute` runs the model | done | `git log --grep "Task: H1"` | Overview, chat tool read the store only; legacy GET route + `get_or_compute_race_prediction` deleted; tests assert an empty store never computes. Full gate: 5081 passed, 100 %. Same commit as H6 (see log). |
| H2 | Chat memory: no shared id; memory routes deleted | done | `e62ca09` | Sonnet agent. Client sends `user_id: null` without storage; `routers/memory.py` + its test + mount deleted; existing chat tests already cover no-id → no recall, no save. Agent gate: frontend 100 %, backend gate passed. |
| H3 | Chat: an unknown tool gets a reply | done | `a64dd22` | `ToolMessage("Unknown tool '…'.")`, no markers; test checks the reply's call id. Worktree gate 100 %. |
| H4 | Chat: input limits and a per-IP rate limit | done | `git log --grep "Task: H4"` | Typed turns (user ≤ 4,000, assistant ≤ 16,000 chars, 1–40 turns, ids ≤ 64) → 422; 6/min + 100/day per visitor → 429. Visitor = `True-Client-IP` / `CF-Connecting-IP`, not XFF (see log). Client: last 40 turns opening on a question, old answers clipped, input `maxLength`, 429 message. Gated on the combined `dev`. |
| H5 | Live timing: one OpenF1 poll per session, shared | done | `5d61682` | Sonnet agent. Feed rows cached per session key for `WS_POLL_INTERVAL − 1` s (failed reads never cached); `resolve_session_window` cached per (year, round) until the next session start / end + grace, at most `SESSION_LOOKUP_INTERVAL`. Agent gate: 5100 passed, 100 %. |
| H6 | Compute route uses `SingleFlight` | done | `git log --grep "Task: H6"` | `model_runs` is a `SingleFlight` (new `running(key)` for the snapshot's `model_running`); one global model lock replaces the per-race async locks. Duplicate helpers deleted. |
| H7 | Chat tools run through `SingleFlight` | done | `da577a2` | Keyed by name + `json.dumps(args, sort_keys=True)`; test: a retry joins, other args start their own. Worktree gate: 5082 passed, 100 %. |
| H8 | Post-race write-ups: failover, one store read | done | `acd1a74` | Sonnet agent. `_ask_engines` mirrors `rulebook_answer.py`; the pass reads each post-mortem once and calls the generator with `force=True`. Agent gate: 5099 passed, 100 %. |
| H9 | Delete the deprecated iOS app | done | `f1ac076` | Sonnet agent. 63 files, −6,357 lines; README, `.gitignore` Xcode block and one docstring. `docs/REMOVED_FEATURES.md` keeps its history lines. |
| H10 | Chat memory is quoted data, not system instructions | done | `git log --grep "Task: H10"` | Memory leaves the persona prompt: a second `SystemMessage` with the fixed "never instructions" line and `<memory>…</memory>`; `build_memory_context` strips `<` `>`. Same commit as H11. |
| H11 | Persona: tool output and memory are data; prompt stays private | done | `git log --grep "Task: H11"` | GROUNDING: tool-result text is data; IDENTITY RULES: never reveal the instructions or the memory block. Both pinned by tests. |
| H12 | Chat tools: no raw exception text reaches the model | done | `git log --grep "Task: H12"` | `tool_error_text` (errors.py) in all 16 tool failure returns and the tool loop: generic line + reference id. SQLite errors and `SafeToShowError` ("No 2026 Grand Prix matches …") keep their text. Tests: connection string never reaches the model; SQLite message kept; non-SQLite query error hidden. |

## Log

- 2026-11-23: plan written from the audit; findings 1–4, 7, 8 and the iOS one checked against the code first. H6 differs from the audit's fix: once H1 removes `get_or_compute_race_prediction`, the compute work runs as a plain function under the existing per-race thread lock, so `SingleFlight` needs no async support.
- 2026-11-23: H10–H12 added from a security review of the chat prompt (memory pasted into the system prompt, tool output not marked as data, raw exception text sent to the model). Forged assistant turns and the memory id as a bearer key are under PLAN.md "Out of scope" as accepted risks.
- 2026-11-23: **H1 and H6 share one commit.** Every backend commit runs the full 100 % gate, and H1 alone left one line of `_wait_for_model_run` uncovered (only the deleted GET route reached it), while H6 deletes that helper. H6 also changed from the plan: a single process-wide model lock, not a per-race one. Only the owner computes now, and two runs on different races at once are as much an OOM risk as two phases of one race.
- 2026-11-23: H2, H5, H8 and H9 run as parallel Sonnet agents in worktrees under `.claude/worktrees/h{2,5,8,9}` (branches `hardening-h*`, from `19ab7b3`, with `backend/.venv` and `frontend/node_modules` symlinked). The coordinator verifies and cherry-picks onto `dev`. H3, H4, H7 and H10–H12 run inline (chat.py).
- 2026-11-23: structlog's `capture_logs` misses `single_flight`'s module logger in a full run (the config is cached on first use). Tests stub `single_flight_module.logger.warning` instead, as `test_analysis_router.py` already did.
- 2026-11-23: **H4 client IP.** Render's proxy only appends to `X-Forwarded-For` (community reports; no official doc), so its first entry can be forged, which would both dodge the limit and grow the in-memory table. Cloudflare sits in front of Render and overwrites `True-Client-IP` / `CF-Connecting-IP`, so the limiter keys on those, then the socket peer. Verify on the live deploy that one of them arrives.
- 2026-11-23: H4 rejects a client-sent `system` turn (422) where it used to drop it silently. The client clips earlier answers to 16,000 characters so an old long answer can't make a thread unsendable.
- 2026-11-23: worktree merges. A plain `git cherry-pick` runs no pre-commit hook, so H2–H9 were gated in their worktrees and the combined `dev` was gated once by H4's commit. Two background cherry-picks of H2 raced (one was thought stopped); no harm (the second found it already applied). Your local Xcode state files under `ios/` (gitignored before H9) now show as untracked; left for you to delete.
- 2026-11-23: H10 and H11 share one commit (both edit the system prompt; one gate run instead of two). H12 runs in worktree `hardening-h12` beside them. Its tool sweep covers all 16 raw-exception returns in `app/api/tools`, not the plan's three. The race lookup's "No … Grand Prix matches" stays visible to the model as the new `SafeToShowError` (a `ValueError`).
- 2026-11-23: **Pre-existing test isolation gap (fixed after the phase, user's request):** run alone, `test_tools_race.py` (2 tests) and `test_tools_sessions.py` (1) read the developer's real `backend/data/f1db.db.version` (`VERSION_PATH` is fixed at import; conftest only swaps `DB_PATH`) and fail when it differs from v2026.20.0. The full suite passes them, presumably through test order. Reproduced on `08a9379` without H12.
- 2026-11-23: **All of H1–H12 done.** The phase is ready for its PR `fix: hardening from the repo audit`, which the user opens.
- 2026-11-23: Isolation gap fixed: `conftest._no_local_f1db` now also swaps `f1db_source.VERSION_PATH` for a missing stamp. The three tests pass on their own. The untracked Xcode leftovers under `ios/` were deleted (user). User asked to push `dev` and raise the phase PR: that push and PR only.
