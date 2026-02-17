# F1 AI — Race Engineer

## What This Is

An AI-powered F1 companion app spanning web (Next.js), iOS (SwiftUI), and a Python backend. It features an agentic race engineer chatbot that can query race results, compare drivers, consult FIA regulations, and search for live F1 news. The app also provides race calendars, standings, live timing, and rich race detail cards. Built as a full-stack learning project — all code AI-generated.

## Core Value

An intelligent F1 race engineer that can answer any Formula 1 question using real data — race results, driver comparisons, regulations, and live timing — across web and mobile.

## Requirements

### Validated

- ✓ Agentic chat with Gemini 2.0 Flash and 11 LLM-callable tools — existing
- ✓ Race results, qualifying, and sprint results via FastF1 — existing
- ✓ Driver head-to-head comparison with lap time analysis — existing
- ✓ FIA regulations lookup via ChromaDB RAG — existing
- ✓ Web search for real-time F1 news via Tavily — existing
- ✓ Season calendar with session times and sprint detection — existing
- ✓ Driver and constructor championship standings — existing
- ✓ Live timing via WebSocket (OpenF1 positions) — existing
- ✓ Rich race detail cards with podium display — existing
- ✓ Chat history persistence in localStorage — existing
- ✓ Streaming responses with tool status indicators — existing
- ✓ iOS app with chat, calendar, standings, driver compare, and live timing — existing
- ✓ iOS home screen widget for next race — existing
- ✓ Backend deployed on Render.com — existing

### Active

- [ ] Race outcome predictions based on qualifying, history, and conditions
- [ ] Tire strategy analysis — pit windows, undercut/overcut scenarios
- [ ] Richer driver comparisons — sector times, career arcs, trend analysis
- [ ] Live AI race commentary — real-time insights during sessions
- [ ] iOS push notifications — overtakes, pit stops, safety cars, penalties
- [ ] iOS live timing widget — Dynamic Island / home screen glanceable positions
- [ ] iOS session countdown reminders before FP, Quali, Race
- [ ] Test coverage across backend tools, agentic loop, and frontend hooks
- [ ] Performance optimization — ChromaDB singleton, FastF1 lock improvements
- [ ] Error handling and observability — structured logging, sanitized error messages
- [ ] Clean up dead code — remove broken MCP prediction stubs

### Out of Scope

- User accounts / authentication — single-user learning project
- Payment processing — no monetization planned
- Android app — focused on iOS for mobile learning
- Social features — not a community app
- Video content — storage/bandwidth overhead not justified

## Context

This is a brownfield project with a working v1 across all three platforms. The codebase mapping revealed several areas for improvement:

- **No test coverage** — the biggest reliability risk. Agentic loop, tool functions, and stream parsing are all untested.
- **Performance bottlenecks** — FastF1 global lock serializes all race data requests; ChromaDB re-initializes on every rulebook query.
- **Dead code** — MCP server references removed prediction modules (`app.ml.predict`, `app.ml.scenario`).
- **WebSocket cleanup** — stale connections accumulate during live races.

The user wants this to be a portfolio piece — polished, tested, and demonstrating full-stack + AI skills.

## Constraints

- **Tech stack**: Keep existing stack (FastAPI, Next.js, SwiftUI, Gemini) — learning continuity
- **Deployment**: Backend on Render.com (free tier limitations — cold starts, sleep after inactivity)
- **Data sources**: FastF1 is not thread-safe — must serialize session loads
- **AI model**: Gemini 2.0 Flash via LangChain — no model switching planned
- **iOS**: Target iOS 17.0+ with SwiftUI

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep Gemini as LLM | Already integrated, learning continuity | — Pending |
| Implement predictions without ML | Use statistical/heuristic approach rather than training models | — Pending |
| iOS as live race companion | Differentiates mobile from web — phone is what you have trackside | — Pending |
| Portfolio-quality bar | Tests, clean code, performance — not just features | — Pending |

---
*Last updated: 2026-02-16 after initialization*
