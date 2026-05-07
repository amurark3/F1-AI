---
phase: 04-live-race-experience
plan: "06"
subsystem: ui
tags: [next.js, react, websocket, framer-motion, tailwind, typescript]

# Dependency graph
requires:
  - phase: 04-live-race-experience
    provides: "Backend WebSocket endpoint at /api/live/{year}/{round} with positions, session_status, commentary, ping message types"

provides:
  - useLiveTiming hook: WebSocket connection manager returning positions, sessionStatus, commentary, isConnected
  - LiveTimingTower component: table-based timing display with connection/loading/data states
  - CommentaryPanel component: AnimatePresence-animated commentary feed with event type styling
  - /live page: schedule-driven in-progress race detection, two-column layout (timing + commentary)
  - NavShell: Live nav item added for desktop and mobile menus

affects:
  - phase-05-push-notifications
  - any future web live/telemetry features

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "useLiveTiming hook guards against WebSocket open when year/round are 0 (no live race)"
    - "Always-called hook pattern: useLiveTiming called unconditionally, skips connection when round=0"
    - "Two-column layout: flex-col on mobile, lg:flex-row on large screens with w-80 fixed commentary sidebar"
    - "AnimatePresence with initial=false for commentary entries (no animation on mount, only on new entries)"

key-files:
  created:
    - frontend/app/hooks/useLiveTiming.ts
    - frontend/app/components/LiveTimingTower.tsx
    - frontend/app/components/CommentaryPanel.tsx
    - frontend/app/live/page.tsx
  modified:
    - frontend/app/components/NavShell.tsx

key-decisions:
  - "useLiveTiming skips WebSocket when round=0 so hook can be called unconditionally on /live page without conditional hooks violation"
  - "Schedule fetch uses current calendar year from new Date().getFullYear() — no hardcoded year"
  - "CommentaryPanel uses AnimatePresence initial=false so existing entries don't animate on first render"

patterns-established:
  - "WebSocket hook pattern: useRef for ws instance, cleanup via return () => ws.close()"
  - "Event type styling via Record<string, {icon, colorClass}> lookup with DEFAULT_STYLE fallback"

requirements-completed:
  - LIVE-05

# Metrics
duration: 8min
completed: 2026-03-08
---

# Phase 04 Plan 06: Web Live Page + Commentary Sidebar Summary

**Next.js /live page with useLiveTiming WebSocket hook, LiveTimingTower table, and AnimatePresence-animated CommentaryPanel — plus Live nav link in NavShell**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T00:00:00Z
- **Completed:** 2026-03-08T00:08:00Z
- **Tasks:** 5
- **Files modified:** 5

## Accomplishments

- `useLiveTiming` hook opens a WebSocket to `/api/live/{year}/{round}`, routing `positions`, `session_status`, `commentary`, and `ping` message types to their respective state slices; safely skips connection when round is 0
- `LiveTimingTower` renders a full-width table with position number, driver number, and gap — with distinct connecting/waiting/data states
- `CommentaryPanel` shows commentary entries with per-event-type icons and color accents, animated in via Framer Motion `AnimatePresence`
- `/live` page detects an in-progress race from `/api/schedule/{year}`, shows placeholder when none, and renders two-column layout when active
- `NavShell` updated with Live item visible in both desktop pill nav and mobile dropdown

## Task Commits

Each task was committed atomically:

1. **Task 1: useLiveTiming hook** - `79d4de5` (feat)
2. **Task 2: LiveTimingTower component** - `37df2a9` (feat)
3. **Task 3: CommentaryPanel component** - `866544a` (feat)
4. **Task 4: /live page** - `ae92d2e` (feat)
5. **Task 5: NavShell Live nav item** - `804b20a` (feat)

## Files Created/Modified

- `frontend/app/hooks/useLiveTiming.ts` - WebSocket hook exporting LivePosition, CommentaryEntry, SessionStatus interfaces and useLiveTiming function
- `frontend/app/components/LiveTimingTower.tsx` - Timing table with connecting/waiting/data states and session status pill
- `frontend/app/components/CommentaryPanel.tsx` - Animated commentary feed with EVENT_STYLES map and formatTime helper
- `frontend/app/live/page.tsx` - /live route: schedule fetch, in-progress detection, two-column live layout, placeholder
- `frontend/app/components/NavShell.tsx` - Added `{ href: '/live', label: 'Live' }` to NAV_ITEMS

## Decisions Made

- `useLiveTiming` guards `useEffect` with `if (!year || !round) return` so the hook can be called unconditionally on the page without violating the Rules of Hooks. Round 0 is never a valid F1 round, so this is safe.
- `AnimatePresence initial={false}` ensures only newly prepended commentary entries animate in; the initial render of existing entries is instant.
- `/live` page fetches the schedule with the current calendar year (`new Date().getFullYear()`) — no hardcoded season year.

## Deviations from Plan

None - plan executed exactly as written. `npm run build` TypeScript check passed on first attempt with no errors.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. The Live page connects to the existing backend WebSocket endpoint already implemented in 04-04.

## Next Phase Readiness

- Web live race UI is complete; backend WebSocket commentary engine (04-04) provides the data
- iOS live race tab (04-05) is the parallel mobile counterpart
- Phase 5 (Push Notifications / APNs) can proceed when Apple Developer account with p8 auth key is available

---
*Phase: 04-live-race-experience*
*Completed: 2026-03-08*
