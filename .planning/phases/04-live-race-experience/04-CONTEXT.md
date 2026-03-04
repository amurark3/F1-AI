# Phase 4: Live Race Experience - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Dynamic Island live activity for real-time driver tracking and an AI commentary feed that fires on significant race events — both surfaced in the existing iOS Live tab and the web UI. Creating new tabs or push infrastructure is out of scope (Phase 5 handles push).

</domain>

<decisions>
## Implementation Decisions

### Driver Selection
- Favorite driver is configured in the **App Settings screen** (alongside the existing notifications settings)
- The Dynamic Island tracks the user's configured favorite driver
- If no favorite driver is set, Dynamic Island defaults to showing the **race leader**
- Users can change their favorite driver mid-session (Settings update propagates to the live activity)

### AI Commentary Style
- Tone: **Excited commentator — energetic, fan-friendly** (not technical race engineer voice)
- Commentary length: Claude's discretion — appropriate for event type
- Generation: Claude's discretion — LLM-generated or templated, whichever is more practical
- History: **Scrollable session history** — all commentary entries for the session are preserved and scrollable
- Personalization: **Neutral** — commentary covers all notable events, not personalized to the favorite driver
- Event type indicators: **Yes** — each entry has a small icon or color accent per event type (e.g., red for safety car, yellow for pit stop, blue for fastest lap)
- Audio: **Silent — visual only** — no sound or haptic feedback when commentary fires

### Commentary Panel Placement (iOS)
- Lives in the **existing Live tab** (already exists with timing tower)
- Layout: **Segmented picker** — "Timing" segment shows the driver leaderboard, "Commentary" segment shows the commentary feed
- New commentary: **Badge on the Commentary segment** (dot indicator) — does not auto-switch segments
- User stays on their selected segment at all times

### Commentary Panel Placement (Web)
- **Sidebar panel** next to the timing data on wider screens
- Runs as a column alongside the timing tower

### Session Detection & Live Trigger
- Dynamic Island **auto-starts** when a session is detected as `in_progress` (via existing calendar polling)
- Dynamic Island **auto-ends** with a post-session display: shows final result for **30 minutes**, then auto-dismisses
- Dynamic Island compact view shows: **race leader name + current lap** (e.g., "VER | Lap 34/57")
- Dynamic Island expanded view shows full timing data from the WebSocket feed
- Data source for Dynamic Island updates: **Claude's discretion** — use whatever mechanism is technically correct for iOS Live Activities (ActivityKit constraints may require push-based or periodic updates rather than open WebSockets)

### Claude's Discretion
- Commentary length per entry (1-2 vs 2-4 sentences)
- LLM-generated vs template-based commentary
- Exact Dynamic Island update mechanism (ActivityKit push vs app-driven updates)
- Color/icon palette for event type indicators
- Exact web sidebar layout and breakpoint behavior

</decisions>

<specifics>
## Specific Ideas

- The Live tab already exists with a `TimingTower` component and WebSocket-based `LiveTimingViewModel` — Dynamic Island and commentary build on this existing infrastructure
- The timing tower and commentary are split by a segmented picker within the live content view (not a new top-level tab)
- Commentary panel on web mirrors the sidebar approach common in F1 broadcast-style layouts

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-live-race-experience*
*Context gathered: 2026-03-03*
