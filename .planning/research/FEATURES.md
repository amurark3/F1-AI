# Feature Landscape

**Domain:** AI-powered F1 companion / race-engineer app (subsequent milestone)
**Researched:** 2026-02-16
**Confidence note:** No web or Context7 access during this session. All findings
derive from (a) direct inspection of the existing codebase, (b) knowledge of
comparable products (official F1 app, F1TV, RaceFans, Autosport, WTF1, Pitwall),
and (c) established iOS/ML engineering patterns as of early 2026.
Confidence is MEDIUM for feature categorisation; LOW for specific competitor
feature claims where official sources could not be verified.

---

## Already Exists — Baseline Inventory

Before categorising what to build next, here is a precise list of what the app
already has, derived from direct code inspection:

| Layer | Feature | Implementation Status |
|-------|---------|----------------------|
| Backend | Agentic chat (Gemini 2.0 Flash + LangChain tool loop) | Complete |
| Backend | Race results (FastF1) | Complete |
| Backend | Qualifying results Q1/Q2/Q3 (FastF1) | Complete |
| Backend | Sprint race + Sprint Qualifying results (FastF1) | Complete |
| Backend | Driver telemetry comparison, sector-by-sector (FastF1) | Complete |
| Backend | FIA regulations RAG (ChromaDB + HuggingFace embeddings) | Complete |
| Backend | Driver + constructor standings (Ergast) | Complete |
| Backend | Season calendar (FastF1) | Complete |
| Backend | ML race predictions (scikit-learn) | Complete |
| Backend | Championship scenario calculator | Complete |
| Backend | Real-time web search (Tavily) | Complete |
| Backend | Track conditions stub | Not implemented |
| Backend | MCP server for Claude Desktop / Cursor | Complete |
| iOS | Tab-based nav: Pit Wall, Calendar, Live, Standings, Compare | Complete |
| iOS | Streaming chat (ChatStreamService) | Complete |
| iOS | Live timing tower: position, gap, last lap, tyre, pit stops | Complete |
| iOS | Session status (SC, red flag, VSC, started, finished) | Complete |
| iOS | Flag events (sector-scoped) | Complete |
| iOS | Countdown to next session | Complete |
| iOS | Next race widget (WidgetKit) | Complete — one widget |
| iOS | Local push notifications: 30-min + 5-min race reminders | Complete |
| iOS | Race detail view + circuit info card | Complete |
| iOS | Driver standings + constructor standings views | Complete |
| iOS | Driver comparison view | Complete |
| iOS | Shareable result card | Complete |
| iOS | Cache service (offline-tolerant) | Complete |

---

## Table Stakes

Features a "next level" F1 AI app must have, or the improvement feels
superficial. These are expected by sophisticated F1 fans and/or are needed to
make existing features production-grade.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Live weather + track conditions** | Existing tool is a stub. Race strategy is meaningless without temperature, rainfall chance, and wind. Users will ask the AI and get a placeholder response. | Medium | OpenWeatherMap or WeatherAPI.com free tier covers F1 venues; needs backend integration + LLM tool completion |
| **Push notifications: all session types** | Notifications currently only cover the race start. FP1, FP2, FP3, Qualifying, and Sprint sessions are uncovered. F1 fans track every session. | Low | Extend NotificationService.swift — the scaffold exists |
| **AI race predictions on iOS** | ML predictions exist in backend. No iOS UI surfaces them. Users expect "what will happen this weekend?" to show a structured answer, not just chat text. | Low | Dedicated PredictionsView + API endpoint; model already trained |
| **AI championship scenario on iOS** | Scenario calculator exists in backend chat only. Should be surfaced as a dedicated UI: "Verstappen needs X points to win." | Low | New view reusing existing backend calculation |
| **Error handling + offline UX** | Cache service exists but error states are unhandled in most views. App likely shows blank screens or spinners on failures. Portfolio pieces are judged by resilience. | Medium | Empty-state views, retry flows, error banners throughout |
| **Unit + integration tests** | Zero test targets currently. Any non-trivial engineering portfolio requires demonstrable test coverage. | Medium | XCTest for iOS ViewModels; pytest for FastAPI routes and tools |
| **Dynamic Island live activity** | Live timing tab exists but Dynamic Island (ActivityKit) is absent. For an app with a live timing view, this is the iOS-native companion users expect. | Medium | ActivityKit + Live Activities API; pairs with existing WebSocket timing data |
| **Real-time AI commentary events** | App has static chat. During sessions, AI commentary triggered by timing events (position changes, safety car, fastest lap) is the differentiating use for the LLM. Requires event-driven push from backend. | High | Server-Sent Events or WebSocket from backend; push notification or in-app alert; Gemini generates contextual comment |
| **Backend performance: caching + async** | FastF1 loads are synchronous and slow (3-10 seconds per session load). Multiple concurrent users will block. FastAPI is async but FastF1 is not. | Medium | Thread pool executor for FastF1 calls; Redis or in-memory cache for hot routes; background pre-load for upcoming sessions |

---

## Differentiators

Features that set this app apart from both the official F1 app and generic
sports apps. These are portfolio-worthy demonstrations of full-stack + AI skills.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **AI-generated race preview** | Before each race weekend, the AI synthesises driver form, circuit history, weather forecast, regulation changes, and team radio patterns to generate a structured preview. Not available in any free F1 app. | High | Scheduled backend job (APScheduler) generates preview 24h before FP1; stored as JSON; iOS view with expandable sections |
| **Strategy simulator** | User inputs "what if Verstappen pits on lap 32?" and the AI reasons over tyre degradation data, safety car probability, and remaining laps to project likely outcome. Full agentic reasoning, not a lookup. | High | New agentic tool: get_tyre_strategy_analysis; uses historical FastF1 stint data; demonstrates complex multi-step LLM reasoning |
| **Natural language telemetry queries** | "Why was Hamilton 0.4s slower in sector 2?" The AI cross-references telemetry, circuit layout, tyre data, and weather to give a race-engineer-level answer. Extends existing compare_drivers tool. | High | Chain compare_drivers + get_track_conditions + consult_rulebook; response synthesised by LLM; showcases RAG + tool orchestration |
| **Dynamic Island timing mini-view** | Position, gap, current lap, and safety car status in the Dynamic Island during active sessions. Unique to this app; official F1 app charges for F1TV access for live data. | Medium | ActivityKit Live Activity with compact + expanded UI; data fed from existing WebSocket live timing |
| **Multi-widget suite on iOS** | Currently one "Next Race" widget. Add: Driver championship table widget, Points to lead widget, "Last race podium" widget. Home screen presence increases daily engagement. | Medium | Three additional WidgetKit widgets; static data from cached API calls; no new backend work |
| **Shareable AI analysis cards** | User gets an AI answer about race strategy or driver performance and can share it as a designed card (team colours, F1 branding style). Existing ShareableResultCard can be extended. | Low-Medium | Extend existing ShareableResultCard to capture AI chat messages; ImageRenderer; social share sheet |
| **Race engineer persona depth** | Current system prompt establishes persona. Extend with: team-specific dialect (Horner-style directness for Red Bull queries, Wolff-style for Mercedes), technical jargon calibration based on user query complexity. | Medium | Prompt engineering; user preference setting for "technical depth" (fan / enthusiast / engineer); stored in UserDefaults |
| **Historical head-to-head stats** | "Who won more races between Senna and Prost during their rivalry years?" Multi-year aggregation across Ergast. Not available in the AI chat currently. | Medium | New LLM tool: get_head_to_head_stats; Ergast multi-year queries; demonstrates broader data range than current season focus |
| **Tyre degradation visualisation** | Chart showing stints, tyre compound, and lap-time delta per stint for completed races. Visual, data-dense, and demonstrates FastF1 data depth. | Medium | SwiftUI Charts (iOS 16+); new API endpoint for stint data; FastF1 laps + tyre data |

---

## Anti-Features

Features to explicitly NOT build for this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Real-time lap telemetry streaming** | FastF1 provides post-session data, not live telemetry (live data requires F1's proprietary Livetiming API with rate limits and legal complexity). Building it promises something that cannot be reliably delivered. | Use post-session lap data; be transparent that comparisons are post-race |
| **Fantasy F1 integration** | Adds user accounts, team selection, scoring logic, and a points system. Scope explosion for zero AI differentiation. | Fantasy F1 is a separate product; exclude entirely |
| **Video / highlight clips** | F1 media rights are among the most restrictive in sport. Any video embedding creates legal exposure. | Link to YouTube highlights via web search; never embed or store |
| **Social / community features** | Comments, follows, and user-generated content require moderation, GDPR compliance, backend user models, and auth infrastructure. Far outside portfolio scope. | Shareable cards via iOS share sheet is sufficient social surface |
| **Betting odds integration** | Jurisdictional legal complexity, app store policy risk (Apple guidelines 5.3), and brand risk for a portfolio piece. | AI strategy analysis already surfaces probability language without odds |
| **Custom ML model training in-app** | scikit-learn predictions already exist. Retraining on-device is infeasible for the model size and data pipeline. | Update model weights server-side when new season data is available |
| **Full F1TV replacement** | Official live race video, radio, team radio streams. Rights-protected, requires F1 commercial agreements. | Reference F1TV as a companion; focus on data and AI analysis |
| **Android app** | Doubles maintenance cost, requires Kotlin/Compose expertise on top of SwiftUI, fragments the portfolio focus. | iOS only; ensures widget + Dynamic Island showcase is complete |

---

## Feature Dependencies

```
Live weather → AI race preview (preview needs weather input)
Live weather → Strategy simulator (strategy factors in rain probability)
Live weather → Natural language telemetry queries (sector time explanation needs conditions)

AI race preview → Race engineer persona depth (preview uses persona voice)

Dynamic Island → LiveTimingService WebSocket (feeds ActivityKit)
Dynamic Island → (requires real-time session detection — knows when to start activity)

Real-time AI commentary → Backend event detection on timing data
Real-time AI commentary → Push notifications infrastructure (already exists)
Real-time AI commentary → Gemini API (already exists)

Strategy simulator → Historical tyre data (FastF1 laps with compound)
Strategy simulator → Track conditions (rain changes strategy completely)

Historical head-to-head → Ergast multi-year query (Ergast supports this; new tool needed)

Tyre degradation visualisation → SwiftUI Charts (iOS 16+ built-in, no dep needed)
Tyre degradation visualisation → New stint API endpoint (backend work)

Error handling → All views (cross-cutting; should be done early)
Tests → All backend tools (should be done early; prevents regressions)
Backend performance caching → All API routes (cross-cutting; gates reliability)

AI championship scenario on iOS → Existing backend logic (no new backend work)
AI predictions on iOS → Existing ML model (no new backend work)
Push notifications all sessions → Existing NotificationService (extend only)
```

---

## MVP Recommendation for Next Milestone

Based on the dependency graph and the project goal (full-stack + AI portfolio
piece that demonstrates hardening and new capability):

**Prioritise for milestone MVP:**

1. **Error handling + offline UX** — Gate everything else. A hardened app reads
   as professional. Blank screens and unhandled errors disqualify a portfolio piece.

2. **Unit + integration tests** — Backend route tests and iOS ViewModel tests.
   30-40% coverage on critical paths is enough to demonstrate discipline.

3. **Backend performance: caching + async** — FastF1 blocking calls will fail
   under demo load. Fix before adding more data-heavy features.

4. **Push notifications: all session types** — Low effort, high perceived value.
   Extends existing NotificationService scaffold with no new backend routes.

5. **Live weather + track conditions** — Completes the stub tool. Unlocks AI
   race preview and strategy simulator later. Single backend integration point.

6. **AI predictions + championship scenario on iOS** — No new backend work.
   Surfaces existing intelligence as native UI. High portfolio visibility.

7. **Dynamic Island live activity** — iOS-native, visually impressive, technically
   non-trivial. Strong portfolio signal for iOS engineering depth.

8. **Real-time AI commentary** — Highest complexity but highest differentiation.
   Reserve for late in the milestone or as a stretch goal.

**Defer:**

- Strategy simulator: Depends on live weather and stable performance layer.
  Build in a subsequent milestone.
- AI race preview scheduled job: APScheduler + storage adds backend complexity.
  Defer until backend hardening is solid.
- Tyre degradation visualisation: Good feature, medium effort, but not
  differentiated enough to prioritise over Dynamic Island or AI commentary.
- Historical head-to-head: Nice-to-have; Ergast multi-year is reliable but
  the feature is incremental.

---

## Sources

- Direct code inspection: `/Users/adityamurarka/Desktop/F1-AI/backend/app/api/tools.py`,
  `routes.py`, `prompts.py` (all endpoints and tools verified)
- Direct code inspection: `/Users/adityamurarka/Desktop/F1-AI/ios/F1AI/Services/NotificationService.swift`,
  `LiveTimingService.swift`, `AdManager.swift`, all Views and ViewModels
- Baseline inventory: `/Users/adityamurarka/Desktop/F1-AI/README.md`
- F1 app ecosystem knowledge: official F1 app (App Store description as of training
  cutoff), RaceFans, WTF1, Pitwall.app, F1TV feature set — MEDIUM confidence
  (training data; official sources not verified during this session)
- iOS ActivityKit / WidgetKit capabilities: Apple developer documentation as of
  training cutoff — MEDIUM confidence; verify against current Apple docs before
  implementing Dynamic Island
- FastF1 live data limitations: FastF1 GitHub documentation as of training cutoff —
  MEDIUM confidence; verify current version capabilities
