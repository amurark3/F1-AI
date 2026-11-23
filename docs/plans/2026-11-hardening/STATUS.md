# Status: backend hardening from the repo audit

Plan: [`PLAN.md`](PLAN.md). Same update rules as [`../2026-11-redesign/STATUS.md`](../2026-11-redesign/STATUS.md). Statuses: `todo` · `in_progress` · `done` · `blocked`.

## Current focus

- **Started 2026-11-23** (user: "Make a new plan and work on them all"). Coordinator: session `f1-ai-b2`. On `dev`; commit per task, never push. When H1–H9 are done, the phase is ready for its PR `fix: hardening from the repo audit`, which the user opens.

## Tasks

| ID | Task | Status | Commit | Evidence / notes |
| --- | --- | --- | --- | --- |
| H1 | Predictions: no path but `/compute` runs the model | todo | | |
| H2 | Chat memory: no shared id; memory routes deleted | todo | | |
| H3 | Chat: an unknown tool gets a reply | todo | | |
| H4 | Chat: input limits and a per-IP rate limit | todo | | |
| H5 | Live timing: one OpenF1 poll per session, shared | todo | | |
| H6 | Compute route uses `SingleFlight` | todo | | Needs H1. |
| H7 | Chat tools run through `SingleFlight` | todo | | After H3, H4. |
| H8 | Post-race write-ups: failover, one store read | todo | | |
| H9 | Delete the deprecated iOS app | todo | | |

## Log

- 2026-11-23: plan written from the audit; findings 1–4, 7, 8 and the iOS one checked against the code first. H6 differs from the audit's fix: once H1 removes `get_or_compute_race_prediction`, the compute work runs as a plain function under the existing per-race thread lock, so `SingleFlight` needs no async support.
