# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** An intelligent F1 race engineer that can answer any Formula 1 question using real data -- race results, driver comparisons, regulations, and live timing -- across web and mobile.
**Current focus:** Phase 5 (next)
**Completed:** Phase 1: Infrastructure Hardening, Phase 2: Backend Data Features, Phase 3: Client Feature Surface, Phase 4: Live Race Experience

## Current Position

Phase: 4 of 5 -- COMPLETE
Plan: 7 of 7 complete
Status: Phase 4 Complete -- 04-07 done (2026-03-08)
Last activity: 2026-03-08 -- Completed 04-07: Lap count integration — backend broadcasts session_status with lap/total_laps via OpenF1 /v1/laps

Progress: [█████████░] 90%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 8min
- Total execution time: 1.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-hardening | 2/2 | 14min | 7min |
| 02-backend-data-features | 3/3 | 53min | 18min |
| 03-client-feature-surface | 6/6 | ~35min | 6min |

**Recent Trend:**
- Last 6 plans: 02-02 (28min), 02-03 (5min), 03-01 (1min), 03-02 (8min), 03-03 (12min), 03-05 (2min)
- Trend: 03-05 very fast (plan provided complete Swift code, no deviations needed)

*Updated after each plan completion*
| Phase 03-client-feature-surface P06 | 2 | 2 tasks | 5 files |
| Phase 03 P02 | 8 | 2 tasks | 3 files |
| Phase 03 P03 | 12 | 2 tasks | 4 files |
| Phase 03-client-feature-surface P05 | 2 | 2 tasks | 2 files |
| Phase 04-live-race-experience P01 | 2 | 4 tasks | 4 files |
| Phase 04-live-race-experience P04-04 | 2 | 1 tasks | 1 files |
| Phase 04-live-race-experience P04-03 | 3 | 1 tasks | 1 files |
| Phase 04-live-race-experience P02 | 2 | 2 tasks | 3 files |
| Phase 04-live-race-experience P04-06 | 8 | 5 tasks | 5 files |
| Phase 04-live-race-experience P05 | 3 | 5 tasks | 6 files |
| Phase 04-live-race-experience P04-07 | 5 | 1 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: 5-phase structure after removing Test Infrastructure (personal project, not going to production)
- Roadmap: TEST-01, TEST-02, TEST-03 deferred to v2
- Roadmap: Predictions use statistical/heuristic approach, not ML training (per PROJECT.md)
- Roadmap: APNs push is Phase 5 (last) due to external infrastructure dependency and complexity
- 01-01: LLM safety uses BLOCK_ONLY_HIGH for dangerous/harassment (F1 crash content), BLOCK_MEDIUM_AND_ABOVE for hate/sexual (not F1-relevant)
- 01-01: All config constants in backend/app/config.py with os.getenv() pattern for env overrides
- 01-01: Removed dead MCP prediction tools (predict_race_results, calculate_championship_scenario) importing from non-existent app.ml
- 01-02: structlog with ConsoleRenderer (dev) / JSONRenderer (prod) based on ENVIRONMENT env var
- 01-02: ChromaDB singleton uses threading.Lock with double-check pattern for thread safety
- 01-02: WebSocket heartbeat uses application-level JSON pings for client compatibility
- 02-01: Prediction scoring uses 5 weighted factors with proportional rebalancing when data sources missing
- 02-01: Confidence ranges from stdev of input signals; pre-qualifying fallback widens by 15pp
- 02-01: Accuracy history stored as JSON with atomic write-to-temp-then-rename
- 02-01: Data module pattern established: pure computation in app/data/, thin wrappers in tools.py
- 02-02: Strategy module uses same _fastf1_lock and caching pattern as predictions.py for consistency
- 02-02: Weather uses httpx.AsyncClient with One Call 3.0 -> 2.5 current weather fallback chain
- 02-02: Track surface temp estimated from air temp + cloud cover heuristic (no API provides track temp)
- 02-02: Strategy impact uses 40% rain threshold for dual scenario, 20% for intermediate backup
- 02-02: GPS coordinates embedded in CIRCUIT_DATA dict rather than separate mapping
- 02-03: Weather tool uses asyncio.run() with RuntimeError fallback for event loop detection
- 02-03: Predictions REST caches until qualifying data available, then recomputes
- 02-03: Chat predictions include rich narrative; REST returns structured JSON (per CONTEXT.md)
- 02-03: Old get_track_conditions stub fully removed and replaced by get_weather_conditions
- 03-01: PredictionsResponse.error field decodes HTTP 200 error body (no upcoming race / data failure)
- 03-01: First-load failure sets self.error (ContentUnavailableView); background refresh sets toastMessage (toast overlay)
- 03-01: fetchPredictions caches 1800s (30 min) — backend recomputes on qualifying data availability
- 03-02: Segment picker uses integer tag (0/1/2) not Bool — clean extension point for future segments
- 03-02: PredictionsView receives upcomingRace+year as params from StandingsTab to avoid duplicating schedule fetch
- 03-02: ProgressView used for loading state (no .shimmering() third-party dependency)
- 03-03: ChampionshipView receives vm.selectedYear from StandingsTab year picker so both standings and championship stay in sync
- 03-03: wdcContenders / wccContenders use dynamic maxPointsRemaining from actual schedule — sprint weekends add 8 pts (both cars)
- 03-03: whatIfRaces defaults to 3 (Next 3 preset) — most actionable scenario for mid-season viewers
- [Phase 03-06]: Web predictions use two-step SWR fetch (schedule then predictions) to find upcoming round dynamically
- [Phase 03-06]: Toast used only for background refresh failures; first-load failures use inline error state with Retry
- [Phase 03-05]: ToastView holds no internal state — caller controls visibility via onDismiss closure, making it stateless and reusable
- [Phase 03-05]: Auto-dismiss uses Task.sleep structured concurrency (not DispatchQueue) — cancellation-safe
- [Phase 04-01]: RaceLiveActivity.swift placed in F1AIWidgets/ and added to F1AI target via xcodegen explicit source path — avoids third Shared/ directory
- [Phase 04-01]: isLeader Bool included in ContentState for UI branching without gap string parsing
- [Phase 04-live-race-experience]: Commentary state keyed by room string at module level for shared 30s cooldown across connections
- [Phase 04-live-race-experience]: asyncio.to_thread wraps llm.invoke to prevent blocking WebSocket event loop; template fallback on LLM error
- [Phase 04-live-race-experience]: favoriteDriver AppStorage key empty-string default — LiveActivityService interprets empty as track-leader fallback; no validation in settings layer
- [Phase 04-live-race-experience]: LiveActivityService keeps ActivityKit isolated in its own service file — not on LiveTimingViewModel — avoiding import confusion between app and widget targets
- [Phase 04-live-race-experience]: Tracked driver re-read from UserDefaults on every update() so mid-session favorite changes propagate without restart
- [Phase 04-live-race-experience]: Two-step WebSocket decode (JSONSerialization for type, then JSONDecoder) avoids touching brittle LiveTimingData singleValueContainer enum
- [Phase 04-live-race-experience]: Commentary badge dot uses @State hasNewCommentary cleared on Commentary tab .onAppear — no auto-switch, visual only
- [Phase 04-06]: useLiveTiming guards useEffect with !year || !round check so hook can be called unconditionally; round 0 is never a valid F1 round
- [Phase 04-06]: AnimatePresence initial=false on CommentaryPanel so only newly prepended entries animate in; initial render is instant
- [Phase 04-07]: _find_openf1_session returns tuple[str, int] | None so session_key and total_laps are fetched atomically in one call
- [Phase 04-07]: last_known_lap cache variable preserves last good lap count across failed /v1/laps fetches rather than broadcasting null
- [Phase 04-07]: session_status message sent after positions so iOS receives positions first (triggering activity start) then lap update follows

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 requires Apple Developer account with p8 auth key -- confirm availability before planning Phase 5
- Render.com free tier: ChromaDB on ephemeral storage resets on deploy -- may need persistent disk or managed vector DB
- FastF1 thread safety on current version should be verified before Phase 1 implementation

## Session Continuity

Last session: 2026-03-08
Stopped at: Completed 04-07-PLAN.md. Phase 4 complete. Lap count integration: backend broadcasts session_status with lap/total_laps via OpenF1 /v1/laps. Ready to plan Phase 5.
Resume file: None
