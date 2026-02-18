# Phase 2: Backend Data Features - Context

**Gathered:** 2026-02-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Build race predictions, pit strategy analysis, and live weather as new backend capabilities. Predictions and strategy are exposed as LangChain tools for the agentic chat. Predictions also get a REST endpoint (GET /api/predictions/{year}/{round_num}) for iOS and web consumption. Weather replaces the existing stub tool. No iOS/web UI work — that's Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Prediction output style
- Full grid predictions — all 20 drivers, not just top contenders
- Confidence expressed as percentage ranges (e.g. "72-85% confidence"), not tier labels
- Top 3 reasoning factors per driver (e.g. "track suits high-downforce cars", "strong wet-weather record")
- Data sources: qualifying position, last 5 races form, driver's history at this circuit
- Pre-qualifying fallback: use practice session data + historical circuit data when qualifying hasn't happened yet
- Chat AI version is richer than REST — adds narrative reasoning and race-engineer personality; API returns structured numbers + factors
- Include prediction accuracy tracker — compare past predictions to actual results (e.g. "78% accurate for top-3 at last 5 races")

### Weather data scope
- Full weather data: air temperature, rain probability, wind speed/direction, track surface temperature, humidity
- Include hourly forecast timeline for session duration (e.g. "rain expected lap 25-35")
- Start with OpenWeatherMap free tier (60 calls/min), upgrade to paid if needed later
- Combine weather data with track-specific context (e.g. "street circuits drain poorly", "Monaco is more affected by rain than Bahrain")

### Pit strategy depth
- Full stint breakdown: tyre compound per stint, lap ranges, degradation curves, pit window timing
- Reference historical strategy data from last 3 editions of the same circuit
- Works for any driver asked about — tool pulls their specific stint/tyre data
- Include safety car probability based on circuit history (e.g. "Monaco has 65% SC rate — one-stop gamble is riskier here")

### REST API design
- GET /api/predictions/{year}/{round_num} is the only new REST endpoint — strategy and weather are chat tools only
- Include full metadata: timestamp, data sources used, model accuracy stats
- Cache predictions until new data arrives (new qualifying/race session triggers recompute)

### Claude's Discretion
- Dry vs wet race scenario split — Claude decides whether to show dual scenarios based on rain probability
- Weather data caching interval — Claude picks a sensible TTL
- API response shape (flat array vs grouped tiers) — Claude picks what's easiest for iOS/web

</decisions>

<specifics>
## Specific Ideas

- Predictions should feel like a race engineer briefing — data-driven with clear uncertainty, not clickbait "X WILL WIN"
- Strategy analysis should reference real stint data from FastF1, not generic tyre models
- Weather tool should actually help the AI reason about strategy, not just return numbers

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-backend-data-features*
*Context gathered: 2026-02-18*
