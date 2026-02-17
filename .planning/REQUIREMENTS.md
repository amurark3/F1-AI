# Requirements: F1 AI — Race Engineer

**Defined:** 2026-02-16
**Core Value:** An intelligent F1 race engineer that can answer any Formula 1 question using real data — race results, driver comparisons, regulations, and live timing — across web and mobile.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Infrastructure Hardening

- [ ] **INFRA-01**: ChromaDB vector store initializes once at startup as a singleton, not per tool call
- [ ] **INFRA-02**: WebSocket connections have heartbeat pings and stale connections are cleaned up automatically
- [ ] **INFRA-03**: Dead MCP prediction stubs and broken imports are removed from codebase
- [ ] **INFRA-04**: Backend uses structured JSON logging instead of print() with emoji prefixes
- [ ] **INFRA-05**: LLM safety settings are reviewed and set to appropriate levels for production
- [ ] **INFRA-06**: Hardcoded timeouts (30s tool, 60s race data) are extracted to configuration constants

### Test Infrastructure

- [ ] **TEST-01**: Backend has pytest + pytest-asyncio test suite covering chat endpoint, tool functions, and streaming responses
- [ ] **TEST-02**: Frontend has Vitest + MSW test suite covering useChat hook, stream parsing, and tool status markers
- [ ] **TEST-03**: iOS has XCTest stubs covering critical ViewModels (ChatViewModel, LiveTimingViewModel, PredictionsViewModel)

### Backend Data Features

- [ ] **DATA-01**: Predictions module computes race outcome probabilities using qualifying data, historical results, and track characteristics — output framed as probabilistic analysis with explicit uncertainty
- [ ] **DATA-02**: Pit strategy analysis tool evaluates undercut/overcut scenarios using historical stint data, tyre degradation curves, and pit window timing
- [ ] **DATA-03**: Live weather and track conditions tool returns real temperature, rainfall probability, and wind data for F1 venues — replacing the current stub
- [ ] **DATA-04**: Predictions and strategy tools are exposed as LangChain tools callable by the agentic chat
- [ ] **DATA-05**: REST endpoint serves predictions data for iOS and web consumption (GET /api/predictions/{year}/{round_num})

### Client Features

- [ ] **CLIENT-01**: iOS PredictionsView displays race outcome probabilities with driver positions, confidence ranges, and key factors
- [ ] **CLIENT-02**: iOS championship scenario view shows "Driver X needs Y points to clinch the title" with interactive what-if scenarios
- [ ] **CLIENT-03**: iOS push notifications fire for all session types — FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race — not just race start
- [ ] **CLIENT-04**: iOS and web views show proper empty states, error banners, and retry flows instead of blank screens on failure
- [ ] **CLIENT-05**: Web prediction panel displays race outcome analysis matching the iOS predictions view

### Live Race Experience

- [ ] **LIVE-01**: Dynamic Island shows current driver position, gap to leader, current lap, and safety car status during active sessions
- [ ] **LIVE-02**: Dynamic Island compact and expanded views update in real-time from existing WebSocket timing data
- [ ] **LIVE-03**: AI commentary generates contextual insights when significant timing events occur (position changes, safety car, fastest lap, pit stops)
- [ ] **LIVE-04**: AI commentary is rate-limited (30-second cooldown) to avoid Gemini API cost explosion during active sessions
- [ ] **LIVE-05**: AI commentary appears in both iOS and web UIs as a dedicated commentary panel

### Push Infrastructure

- [ ] **PUSH-01**: Backend endpoint accepts device token registration (POST /api/push/register)
- [ ] **PUSH-02**: Backend sends APNs push notifications for live race events — overtakes, safety car, red flag, penalties
- [ ] **PUSH-03**: iOS registers for remote notifications and delivers device token to backend on every app foreground activation
- [ ] **PUSH-04**: Push notifications work on physical iOS device with proper sandbox/production APNs configuration

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### AI Features

- **AI-V2-01**: Strategy simulator — user inputs hypothetical pit scenario and AI projects likely race outcome
- **AI-V2-02**: AI race preview — scheduled pre-weekend analysis synthesizing form, history, weather, and regulation changes
- **AI-V2-03**: Race engineer persona depth — team-specific dialect and technical jargon calibration based on user preference

### Data Visualization

- **VIZ-V2-01**: Tyre degradation visualization — SwiftUI Charts showing stints, compounds, and lap-time deltas
- **VIZ-V2-02**: Historical head-to-head stats — multi-year driver comparison across Ergast data

### iOS Enhancement

- **IOS-V2-01**: Multi-widget suite — driver championship table, points to lead, last race podium widgets
- **IOS-V2-02**: Shareable AI analysis cards — extend ShareableResultCard to AI chat messages with team colours

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-time lap telemetry streaming | FastF1 provides post-session data only; F1 Livetiming API has legal and rate-limit constraints |
| Fantasy F1 integration | Scope explosion — user accounts, scoring, team selection — zero AI differentiation |
| Video / highlight clips | F1 media rights restrictions; legal exposure for a portfolio project |
| Social / community features | Moderation, GDPR, auth infrastructure — far outside single-user portfolio scope |
| Betting odds integration | App Store policy risk (Apple 5.3), jurisdictional legal complexity |
| Custom ML model training | Statistical/heuristic approach is sufficient and more interpretable for F1 fans |
| F1TV replacement | Rights-protected content; focus on data and AI analysis |
| Android app | Doubles maintenance, fragments portfolio focus on iOS + SwiftUI |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | — | Pending |
| INFRA-02 | — | Pending |
| INFRA-03 | — | Pending |
| INFRA-04 | — | Pending |
| INFRA-05 | — | Pending |
| INFRA-06 | — | Pending |
| TEST-01 | — | Pending |
| TEST-02 | — | Pending |
| TEST-03 | — | Pending |
| DATA-01 | — | Pending |
| DATA-02 | — | Pending |
| DATA-03 | — | Pending |
| DATA-04 | — | Pending |
| DATA-05 | — | Pending |
| CLIENT-01 | — | Pending |
| CLIENT-02 | — | Pending |
| CLIENT-03 | — | Pending |
| CLIENT-04 | — | Pending |
| CLIENT-05 | — | Pending |
| LIVE-01 | — | Pending |
| LIVE-02 | — | Pending |
| LIVE-03 | — | Pending |
| LIVE-04 | — | Pending |
| LIVE-05 | — | Pending |
| PUSH-01 | — | Pending |
| PUSH-02 | — | Pending |
| PUSH-03 | — | Pending |
| PUSH-04 | — | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 0
- Unmapped: 28 (pending roadmap creation)

---
*Requirements defined: 2026-02-16*
*Last updated: 2026-02-16 after initial definition*
