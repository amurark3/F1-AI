---
phase: 03-client-feature-surface
plan: 06
subsystem: ui
tags: [next.js, react, swr, framer-motion, typescript, tailwind]

# Dependency graph
requires:
  - phase: 02-backend-data-features
    provides: /api/predictions/{year}/{round} and /api/schedule/{year} REST endpoints

provides:
  - /predictions Next.js route with PredictionPanel using SWR two-step fetch
  - Toast hook and component (auto-dismiss 4s, optional Retry)
  - PredictionDriverCard expandable card with team colour accent and confidence range
  - NavShell updated with Predictions nav item (desktop + mobile)

affects: [03-client-feature-surface, 04-mobile-push-notifications]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Two-step SWR fetch: schedule endpoint to find upcoming round, then predictions for that round
    - HTTP 200 + error body handling: check data?.error explicitly in addition to SWR network error
    - Dual error state pattern: inline error+Retry for first-load failure, toast for background refresh failure
    - useToast hook pattern: useState for toast state, useCallback for showToast/dismissToast

key-files:
  created:
    - frontend/app/components/Toast.tsx
    - frontend/app/components/PredictionDriverCard.tsx
    - frontend/app/components/PredictionPanel.tsx
    - frontend/app/predictions/page.tsx
  modified:
    - frontend/app/components/NavShell.tsx

key-decisions:
  - "Web predictions use two-step SWR fetch (schedule then predictions) to find upcoming round dynamically"
  - "data?.error checked explicitly in onSuccess callback to handle HTTP 200+error body (Pitfall 7)"
  - "Toast used only for background refresh failures; first-load failures use inline error state with Retry"
  - "No upcoming race shows friendly empty state (not blank page, not error)"
  - "PredictionDriverCard team colour map extended beyond Standings.tsx to include Red Bull Racing, Alpine, RB, Haas, Kick Sauber, Audi, Cadillac variants"

patterns-established:
  - "Dual error state: inline (first-load) vs toast (background refresh) — consistent error UX"
  - "useToast hook: encapsulate toast state + auto-dismiss timer in custom hook"
  - "SWR schedule-first pattern: resolve round dynamically before fetching predictions"

requirements-completed: [CLIENT-05, CLIENT-04]

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 3 Plan 06: Web Predictions Page Summary

**SWR-powered /predictions route with expandable driver cards, dual error states (inline+toast), and team-colour-accented PredictionDriverCard components matching the iOS design**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-01T04:42:29Z
- **Completed:** 2026-03-01T04:44:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Built full /predictions web page: NavShell route, PredictionPanel with SWR two-step fetch, PredictionDriverCard with expand/collapse factors
- Implemented CLIENT-04 web error states: inline error+Retry for first-load failures, toast (auto-dismiss 4s) for background refresh failures
- Extended NavShell NAV_ITEMS array with Predictions entry — desktop nav and mobile dropdown both pick it up automatically

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Toast component and PredictionDriverCard** - `af3811f` (feat)
2. **Task 2: Create PredictionPanel, predictions page, and update NavShell** - `4d62626` (feat)

**Plan metadata:** (see docs commit below)

## Files Created/Modified

- `frontend/app/components/Toast.tsx` - useToast hook (showToast/dismissToast) + Toast component (fixed bottom-right, 4s auto-dismiss, optional Retry button)
- `frontend/app/components/PredictionDriverCard.tsx` - Expandable driver card: team colour accent bar, position, driver name, confidence range always visible; factors revealed via AnimatePresence on click
- `frontend/app/components/PredictionPanel.tsx` - Main predictions component: two-step SWR fetch (schedule→predictions), skeleton loading, inline error with Retry, background refresh toast, friendly empty state for no upcoming race
- `frontend/app/predictions/page.tsx` - Next.js /predictions route wrapping PredictionPanel in NavShell
- `frontend/app/components/NavShell.tsx` - Added Predictions nav item to NAV_ITEMS array

## Decisions Made

- Two-step SWR fetch chosen to find upcoming round dynamically from the schedule endpoint rather than hardcoding round numbers
- HTTP 200+error body (Pitfall 7 from research) handled by checking `data?.error` in `onSuccess` callback, separate from SWR's `error` for network failures
- PredictionDriverCard team colour map extended with additional constructor name variants (e.g., "Red Bull Racing" alongside "Red Bull") to handle backend naming variations

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Web predictions page is complete and matches iOS CLIENT-05/CLIENT-04 requirements
- All 5 plan artifacts created/modified as specified
- NavShell now has 4 nav items; any future routes should follow the same NAV_ITEMS pattern

---
*Phase: 03-client-feature-surface*
*Completed: 2026-02-28*

## Self-Check: PASSED

Files verified:
- FOUND: frontend/app/components/Toast.tsx
- FOUND: frontend/app/components/PredictionDriverCard.tsx
- FOUND: frontend/app/components/PredictionPanel.tsx
- FOUND: frontend/app/predictions/page.tsx
- FOUND: frontend/app/components/NavShell.tsx

Commits verified:
- FOUND: af3811f (feat(03-06): create Toast and PredictionDriverCard components)
- FOUND: 4d62626 (feat(03-06): create PredictionPanel, predictions page, update NavShell)
