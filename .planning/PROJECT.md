# F1 AI — Race Engineer

## What This Is

An AI-powered Formula 1 analyst and race engineer. The web app (Next.js, "Race Control") is the primary surface: a pit-wall workspace with an agentic AI Engineer chat, a Grand Prix Hub for every race weekend, a Telemetry Lab, team and driver pages, a power unit tracker, champions history and FIA rules search. A Python FastAPI backend serves it, plus an MCP server for Claude Desktop / Cursor and a legacy SwiftUI iOS app. Built as a full-stack + AI portfolio project — all code AI-generated.

## Core Value

An intelligent F1 race engineer that answers any Formula 1 question from real data — results, standings, telemetry, regulations, power unit usage and the full 1950–present record — and never presents an invented number as fact.

## Requirements

### Validated

**AI Engineer (chat)**

- ✓ Agentic chat with 16 LangChain tools and up to 3 tool turns per answer — AI overhaul (2026-07); on AMD Token Lab with a Gemini fallback since 2026-11
- ✓ Recovery of malformed inline tool calls so the loop keeps running — AI overhaul (2026-07)
- ✓ Read-only text-to-SQL over f1db (`query_f1_database`) for any historical question — AI overhaul (2026-07)
- ✓ Answer-quality pipeline: tallies on SQL results, answer contract in the system prompt, driver↔team claim checker with one repair pass; measured with `python -m scripts.eval_answers` (12/12 clean on 2026-10-24) — 2026-10
- ✓ Per-user profile and semantic recall of past turns via pgvector, keyed by an anonymous browser id — AI overhaul (2026-07)
- ✓ Statistical race anomalies (grid-to-finish movers, teammate gaps, DNFs) — AI overhaul (2026-07)
- ✓ Streaming responses with tool status, chat history in localStorage, Tavily news search — v1
- ✓ Voice dictation and spoken replies in the browser (Web Speech API, no backend) — 2026-07
- ✓ Full-bleed AI Engineer page in the Race Control palette — 2026-10-31

**Race weekend**

- ✓ Command Center: strategy baseline, projected podium, weather risk from the live forecast, championship picture, call sheet, stint plan, competitor matrix, data assumptions — 2026-07 / 2026-09
- ✓ Live timing WebSocket (positions, gaps, lap count, session status); the tower shows on the Command Center only while a session is live — Phase 4 / 2026-09-30
- ✓ Grand Prix Hub with five tabs (Weekend, Sessions, Grid, Stints, Predictions); round, tab and view live in the URL — 2026-09-13, reworked 2026-10-31
- ✓ Starting grid from the weekend entry list (fallbacks: previous weekend's list, then championship table), with grid penalty decisions from FIA documents — 2026-09 / 2026-10
- ✓ Stints from the store, then OpenF1, then FastF1, aligned with pit-stop data — 2026-10
- ✓ Post-race debriefs built from the classification: podium, biggest movers, constructor impact — 2026-05
- ✓ Sprint classification and sprint/sprint-qualifying results — Phase 2 / 2026-10

**Predictions**

- ✓ Ridge model (StandardScaler → Ridge) blended with a transparent heuristic and a per-driver adaptive correction, with exact per-feature attribution — ML overhaul (2026-07)
- ✓ Overall and after-qualifying phases, persisted pre-race snapshots, accuracy history, LLM post-mortems on misses — 2026-07 / 2026-09
- ✓ Weekly retrain Action that promotes a challenger only if it beats the grid-order baseline, via an auto-merged PR — 2026-07
- ✓ Point-in-time backfill of past-round predictions (`scripts/backfill_predictions.py`) — 2026-10

**Analysis and reference**

- ✓ Telemetry Lab (web): track speed map, head-to-head lap traces, tyre degradation with the raw slope beside the fuel-corrected one, from OpenF1 — 2026-10-31
- ✓ Teams & Drivers pages for the current season: line-up, wins, per-round results, cumulative points, power units per car; replaces Rival Intel — 2026-10-31
- ✓ Power Unit Tracker: element usage per car from FIA documents, allowances stored in Supabase, scheduled ingest Action with a staleness flag — 2026-10-24
- ✓ Champions 1950→present: title leaderboards and every race winner per season — 2026-07
- ✓ Driver and constructor standings with charts — 2026-05
- ✓ FIA rules search over pgvector with cross-encoder rerank and page citations — 2026-07

**Platform**

- ✓ f1db SQLite (downloaded on boot, release-tracked) replaces rate-limited Ergast as the history source — 2026-07
- ✓ Supabase Postgres document store (prediction cache, accuracy history, PU data, analysis cache) with row-level security and a JSON-file fallback — 2026-07 / 2026-08
- ✓ Blocking warm-up screen while Render cold-starts, rechecking on stale tabs and 502–504 responses — 2026-10-30
- ✓ Sentry on web and backend, Vercel Analytics and Speed Insights — 2026-10-30
- ✓ CI quality gates: strict type-aware ESLint, Ruff + module-size check, backend coverage at 100% (~2,900 tests), pip-audit / audit-ci, CodeQL — 2026-07 / 2026-08
- ✓ Structured logging, centralized config, dead MCP prediction stubs removed — Phase 1
- ✓ MCP server exposing 10 F1 tools plus a health check — v1

**iOS (legacy)**

- ✓ Chat, calendar, standings, driver compare, live timing, predictions, championship what-if — v1 / Phase 3
- ✓ Reminders for all seven session types; favourite driver setting — Phase 3 / Phase 4
- ✓ Dynamic Island Live Activity with positions and lap count; home screen widget for the next race — v1 / Phase 4

### Active

- [ ] Push notifications for live race events (Phase 5). Re-plan event detection and notification text first: the plan reused the removed commentary engine
- [ ] Power Unit Tracker gaps: reason column in `GridPenalties`, seasons before 2026, inheriting a round from the same event's other documents
- [ ] Single-flight guard for compute-heavy chat tools, the last path that can orphan runs and exhaust Render's memory
- [ ] Cold-start gate gaps: chat streaming bypasses the fetcher's recheck; cold deep links need a `loading.tsx`
- [ ] FastF1 lap timing on a cold cache. The F1 live timing archive has returned 401 since 2026-10-15; `race_detail.py` still loads with `laps=False`
- [ ] Identity resolution: apply canonical f1db names on the stored-snapshot read path
- [ ] Prediction model: validate the blend (0.65) and adaptive (0.22) weights by backtest; add pace-relative features (gap to pole, teammate deltas)
- [ ] Answer checks for numeric cross-row claims (sums, gaps) that the claim checker does not catch

### Out of Scope

- User accounts / authentication — single-user project; memory uses an anonymous browser id
- Payment processing — no monetization planned
- Android app — iOS was the mobile learning target, and it is now legacy
- Social features — not a community app
- Video content — storage/bandwidth overhead not justified
- Live AI race commentary — built in Phase 4, removed from backend, web and iOS on 2026-09-29. See [docs/REMOVED_FEATURES.md](../docs/REMOVED_FEATURES.md)
- Standalone live timing page — folded into the Command Center on 2026-09-30; `/live` and `/race-control/live` redirect
- Strategy Lab screen — removed; the shared pit-strategy tool stays
- Race Rewind (overtakes, lap chart scrubber) and team radio tabs — deferred 2026-09-13. The design is decided; F1 publishes no overtake feed, so any overtake label would be derived
- Teams & Drivers for past seasons — current season only, by choice
- Telemetry Lab on iOS — web only, by choice

## Context

The original GSD milestone (Phases 1–4) is complete. Most work since March 2026 happened outside GSD phases: the Groq/AI overhaul, the ML prediction overhaul, f1db and Supabase, the Race Control workspace, the Grand Prix Hub, the Telemetry Lab, the Power Unit Tracker, and Teams & Drivers. Phases 5 and 6 in `ROADMAP.md` have not started.

The web app is the primary surface. Old top-level routes (`/calendar`, `/standings`, `/champions`, `/predictions`, `/consumer`) redirect into `/race-control`. The Race Control sidebar groups pages as Operations (Command Center, AI Engineer), Decision Tools (Grand Prix Hub, Telemetry Lab, Standings, Teams & Drivers, Power Units) and Reference (Champions, Race Debriefs, Rules Search). The iOS app predates this and does not expose the newer features.

Data sources and their known failure modes:

- **f1db** — canonical history and names. On Render, a failed GitHub release lookup leaves production on a pinned fallback version; check `/api/ready` for `f1db_version` when data looks stale.
- **FastF1** — results `Position` is NaN until Jolpica publishes. The F1 live timing archive returns 401 without an F1 TV token, and Render's FastF1 cache is ephemeral, so production always loads cold.
- **OpenF1** — 401s during live sessions. `/stints` splits on pit-lane passes and numbers some races a lap low. Deleted-lap race-control messages give a lap number one ahead.
- **fia.com** — slow, two HTML layouts by user agent, 10 s crawl delay, unreliable cover dates.

Provenance rules: never index OpenF1 by round or select sessions by type; judge feed rows by provenance, not age; don't show heuristic or placeholder values as measured data. `docs/HARDCODED_DATA_AUDIT.md` has the Tier 1 and Tier 3 fixes done and the Tier 2 heuristics disclosed in the UI.

Models fill gaps from stale knowledge, so facts belong in tool results rather than in schema docs. Temperature 0 is not deterministic, so measure answer quality with the eval rather than with single probes. (The gpt-oss quirks — one tool per turn, ignoring `tool_choice=none`, malformed calls — left with Groq; DeepSeek-V4-Flash and Gemini make parallel structured calls.)

## Constraints

- **Tech stack**: FastAPI on Python 3.13, Next.js 16 / React 19 / Tailwind 4, SwiftUI (iOS 17+). LLM is AMD Token Lab (DeepSeek-V4-Flash) with a Gemini free-tier fallback (3.5 Flash-Lite), via LangChain; engines and models are the code constant `LLM_PROVIDERS`, only the keys are env vars
- **Deployment**: backend on Render's free tier (512 MB, cold starts, ephemeral disk); frontend on Vercel; Supabase Postgres + pgvector. `DATABASE_URL` must use the session-pooler host, because the direct host is IPv6-only
- **Memory**: torch models (embedder, reranker) load only with `ENABLE_LOCAL_MODELS`, which is off by default on Render. Without it, rules search reports itself disabled and chat skips semantic recall. LLM and torch imports stay lazy; Sentry runs with `auto_enabling_integrations=False`
- **FastF1**: not thread-safe — one process-wide RLock serializes session loads
- **Dependencies**: keep `requests==2.33.1` (2.34.x breaks FastF1 loads); install the venv from the manifests CI installs
- **Quality gates**: `npm run lint`, Ruff and 100% backend coverage must be clean before commit. No `eslint-disable` and no `pragma: no cover`; fix the code or delete dead code

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep Gemini as LLM | Already integrated, learning continuity | ⚠️ Reversed — Groq-only (GPT-OSS 120B) since 2026-07; Gemini and Anthropic code removed |
| Replace Groq with AMD Token Lab + Gemini fallback (2026-11) | Groq's free 8K tokens/min could not carry one question, gpt-oss malformed tool calls and the keyword tool router hid tools. Token Lab is a beta with expiring access, so Gemini's free tier backs it | — Pending — gate on `scripts.eval_answers` per engine |
| Implement predictions without ML | Use statistical/heuristic approach rather than training models | ⚠️ Reversed — Ridge model blended with the heuristic; every model change gated on beating grid order in `evaluate.py` |
| Ridge over GradientBoosting | GBR lost to the grid-order baseline on every metric; Ridge beats it, including on the 2026 regulation-change season | ✓ Good |
| iOS as live race companion | Differentiates mobile from web — phone is what you have trackside | ⚠️ Revisit — web became primary; iOS is legacy and lags the web features |
| Portfolio-quality bar | Tests, clean code, performance — not just features | ✓ Good — 100% coverage, strict lint, dependency audit and CodeQL in CI |
| f1db SQLite replaces Ergast | No rate limits; full 1950–present record queryable offline | ✓ Good |
| Supabase Postgres + pgvector for store, memory and rulebook | One durable store; ChromaDB removed; JSON fallback when `DATABASE_URL` is unset | ✓ Good |
| Text-to-SQL for open-ended history questions | Fixed tools can't cover every stat question | ✓ Good — needed tallies and a claim checker to keep the prose honest |
| Never show invented data as real | Fabricated weather and static risk cards eroded trust | ✓ Good — audit Tiers 1 and 3 done; PU penalties cite FIA documents |
| PU usage belongs to the car, mapped by printed team + number | FIA reports sometimes print a stale line-up | ✓ Good |
| Remove live AI commentary | Feature removed from all platforms on 2026-09-29 | ✓ Done — Phase 5 needs re-planning |
| Fold live timing into the Command Center | The standalone page sat idle almost all the time | ✓ Good |
| Blocking warm-up gate over a non-blocking banner | Stale mobile tabs hit a spun-down Render instance | ✓ Good |
| Teams & Drivers pages for the current season only | Keep scope small; links fall back to plain text for other seasons | — Pending |

---
*Last updated: 2026-10-31 after Teams & Drivers pages and AI Engineer restyle*
