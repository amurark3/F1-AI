# Roadmap: F1 AI — Race Engineer

## Overview

This milestone transforms a working F1 AI companion into a portfolio-grade application. The work flows in dependency order: harden the existing infrastructure (ChromaDB, WebSocket, logging), build new backend data capabilities (predictions, strategy, weather), surface those capabilities in iOS and web clients, add live race experience features (Dynamic Island, AI commentary), and finally wire up APNs push infrastructure that depends on everything before it being stable. Every phase delivers a coherent, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Infrastructure Hardening** - Fix production-blocking performance issues, remove dead code and stale README references, add structured logging
- [ ] **Phase 2: Backend Data Features** - Build predictions, pit strategy, and weather tools as new backend capabilities
- [ ] **Phase 3: Client Feature Surface** - Surface predictions, championship scenarios, and error handling in iOS and web UIs
- [ ] **Phase 4: Live Race Experience** - Add Dynamic Island live activities and real-time AI commentary during sessions
- [ ] **Phase 5: Push Infrastructure** - Wire up APNs push notifications for live race events on physical iOS devices

## Phase Details

### Phase 1: Infrastructure Hardening
**Goal**: The backend is stable, performant, and observable -- ChromaDB initializes once, WebSocket connections are managed, logging is structured, and dead code is gone
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):
  1. Rulebook queries return in under 500ms on second call (ChromaDB singleton eliminates re-initialization)
  2. WebSocket connections that stop responding are automatically cleaned up within 60 seconds
  3. Backend logs are structured JSON lines parseable by any log aggregator -- no more print() with emoji
  4. Codebase has zero references to removed MCP prediction modules or broken imports, and README.md has no references to removed prediction modules
  5. All timeout values and LLM safety settings are configurable constants, not hardcoded magic numbers
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Config constants, dead code removal, and LLM safety settings
- [ ] 01-02-PLAN.md — Structured logging, ChromaDB singleton, and WebSocket heartbeat

### Phase 2: Backend Data Features
**Goal**: The backend can compute race predictions, analyze pit strategy, and return live weather data -- all exposed as LangChain tools and REST endpoints
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):
  1. Asking the chat "Who will win the next race?" returns a probabilistic analysis with driver positions, confidence ranges, and reasoning factors
  2. Asking the chat about pit strategy returns undercut/overcut analysis with stint data and tyre degradation context
  3. GET /api/predictions/{year}/{round_num} returns structured JSON with race outcome probabilities consumable by iOS and web
  4. Weather tool returns real temperature, rainfall, and wind data for current F1 venues instead of stub responses
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Race prediction engine with heuristic scoring and accuracy tracker
- [ ] 02-02-PLAN.md — Pit strategy analysis, live weather module, and circuit GPS coordinates
- [ ] 02-03-PLAN.md — LangChain tool wiring, predictions REST endpoint, and system prompt update

### Phase 3: Client Feature Surface
**Goal**: Users see predictions, championship scenarios, and polished error states across iOS and web -- the app feels complete and handles failures gracefully
**Depends on**: Phase 2
**Requirements**: CLIENT-01, CLIENT-02, CLIENT-03, CLIENT-04, CLIENT-05
**Success Criteria** (what must be TRUE):
  1. iOS PredictionsView shows race outcome probabilities with driver positions, confidence ranges, and key factors for any upcoming race
  2. iOS championship scenario view shows points-to-clinch calculations with interactive what-if exploration
  3. iOS fires local notifications for all session types (FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race) not just race start
  4. Both iOS and web show meaningful empty states, error banners, and retry buttons instead of blank screens when API calls fail
  5. Web prediction panel displays race outcome analysis matching the iOS predictions view
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Live Race Experience
**Goal**: During active sessions, users get live position tracking on Dynamic Island and AI-generated commentary that explains what is happening in real time
**Depends on**: Phase 3
**Requirements**: LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05
**Success Criteria** (what must be TRUE):
  1. Dynamic Island compact view shows selected driver position, gap to leader, and current lap during an active session
  2. Dynamic Island expanded view shows full timing data and updates in real-time from WebSocket feed
  3. When a significant event occurs (position change, safety car, fastest lap, pit stop), AI commentary appears within 30 seconds explaining the context
  4. AI commentary does not fire more than once every 30 seconds regardless of event frequency
  5. Commentary panel is visible in both iOS and web UIs as a dedicated section during live sessions
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Push Infrastructure
**Goal**: iOS users receive real-time push notifications for live race events on physical devices, with reliable token management
**Depends on**: Phase 4
**Requirements**: PUSH-01, PUSH-02, PUSH-03, PUSH-04
**Success Criteria** (what must be TRUE):
  1. POST /api/push/register accepts a device token and stores it for push delivery
  2. During a live race, iOS device receives push notifications for overtakes, safety car deployments, red flags, and penalties
  3. iOS app re-registers its device token with the backend on every foreground activation, ensuring tokens survive cold starts
  4. Push notifications work on a physical iOS device with correct sandbox/production APNs configuration
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Hardening | 0/2 | Planning complete | - |
| 2. Backend Data Features | 0/3 | Planning complete | - |
| 3. Client Feature Surface | 0/0 | Not started | - |
| 4. Live Race Experience | 0/0 | Not started | - |
| 5. Push Infrastructure | 0/0 | Not started | - |
