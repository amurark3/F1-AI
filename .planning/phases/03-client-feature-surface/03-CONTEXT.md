# Phase 3: Client Feature Surface - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Surface predictions, championship scenarios, and polished error states across iOS and web. The app should feel complete and handle failures gracefully. Backend data (predictions, strategy, weather) is already built in Phase 2 — this phase is about displaying it. Creating new backend capabilities is out of scope.

</domain>

<decisions>
## Implementation Decisions

### Predictions layout
- Driver cards layout, not list or bars
- Each card shows: driver name, team, win probability, confidence range (±X%), and 2-3 key factors driving the prediction
- Key factors are in an expandable section — tap card to expand and see factors with brief explanations (not always visible)
- Empty state when no upcoming race: friendly message with countdown/date to when predictions will be available for the next round (do not hide the view)

### Championship scenario UX
- What-if by remaining rounds — "if Driver X wins the next N races, can they beat Driver Y?"
- Interaction style: Claude's Discretion (pick based on how many contenders there typically are — stepper, slider, or preset buttons)
- Show only drivers still mathematically in contention (dynamic cutoff — could be 2 or 15 depending on season stage)
- Tabs for WDC and WCC (both drivers' and constructors' championship)

### Error states & retry
- **Refresh failures (background/subsequent loads):** Toast/snackbar — auto-dismisses after ~4s but user can tap during that window to retry before it disappears
- **First load failure (empty view):** Inline empty state with error illustration, "Something went wrong" message, and a prominent Retry button — not a toast
- iOS: use native SwiftUI feel for error presentation
- Web: use web conventions for toast/snackbar (independent of iOS style)

### Notification targeting
- All session types fire notifications by default: FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, Race
- Per session type toggles in settings — user can turn off individual session types
- Advance time is user-configurable: options of 5, 15, or 30 minutes before session start
- Notification text: short and direct — e.g., "Monaco Grand Prix starts in 15 minutes" (no emoji, no round number prefix)

### Claude's Discretion
- Championship interaction pattern (stepper vs slider vs preset buttons) — pick based on typical contender count and complexity tradeoff
- Loading skeleton design and exact timing
- Exact spacing, typography, team color implementation on prediction cards
- Toast animation style and exact positioning

</decisions>

<specifics>
## Specific Ideas

- Prediction card UX should feel tap-to-reveal — collapsed by default showing name + probability, expanded showing confidence range + factors
- Championship view must handle edge cases: mid-season (many contenders), late-season (2-3 fight), post-clinching (show actual result, not scenarios)
- Notifications fire as local notifications (not push) — scheduled against the race calendar already in the app

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-client-feature-surface*
*Context gathered: 2026-02-28*
