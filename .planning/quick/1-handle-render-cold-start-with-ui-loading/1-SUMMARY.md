---
phase: quick-1-cold-start
plan: 01
subsystem: ui
tags: [swift, observable, swiftui, react, nextjs, server-status, polling]

# Dependency graph
requires: []
provides:
  - ServerStatusService (iOS): @Observable singleton probing /api/health with 3s timeout, 4s retry
  - useServerStatus (web): module-level singleton hook sharing one probe cycle across all consumers
  - ServerWarmingBanner (web): inline banner component that auto-dismisses when server is ready
  - PitWallTab: warming banner shown at top when status == .warming
  - LiveTab: warming banner shown above live content when status == .warming
  - web chat page (/): ServerWarmingBanner rendered before ChatScreen
  - web live page (/live): ServerWarmingBanner rendered at top of all return branches
affects: [phase-05-push-infrastructure]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - iOS @Observable service singleton with separate short-timeout URLSession for health probing
    - Web module-level probe singleton (probeStarted flag + listeners Set) to share one probe cycle across React components

key-files:
  created:
    - ios/F1AI/Services/ServerStatusService.swift
    - frontend/app/hooks/useServerStatus.ts
    - frontend/app/components/ServerWarmingBanner.tsx
  modified:
    - ios/F1AI/Views/Tabs/PitWallTab.swift
    - ios/F1AI/Views/Tabs/LiveTab.swift
    - frontend/app/page.tsx
    - frontend/app/live/page.tsx

key-decisions:
  - "ServerStatusService uses a separate URLSession with 3s timeout for probing — does not modify APIClient's 35s session"
  - "iOS ServerStatusService.startPolling() returns early if status == .ready — no re-probe on tab revisit"
  - "Web useServerStatus uses module-level probeStarted flag to prevent duplicate fetches across StrictMode double-invocations and multiple hook consumers"
  - "Web live/page.tsx uses React fragments to add ServerWarmingBanner at top of all three return branches (loading, no-session, live content)"
  - "Calendar, Standings, Predictions pages excluded from banner — they use cached data and don't require backend to be warm"

patterns-established:
  - "Short-timeout health probe pattern: separate URLSession/AbortController for warm-up detection, leaving main session timeout unchanged"
  - "Module-level singleton probe (web): probeStarted flag + listeners Set allows multiple React components to share one probe without duplicate requests"

requirements-completed: [COLD-START-01]

# Metrics
duration: 7min
completed: 2026-03-10
---

# Quick Task 1: Handle Render Cold Start Summary

**Warming banner on Render cold start: iOS ServerStatusService with 3s probe + 4s retry, web useServerStatus hook with shared module-level singleton, auto-dismissing banner in PitWallTab, LiveTab, web chat, and web live pages**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-10T00:22:00Z
- **Completed:** 2026-03-10T00:29:45Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- iOS: `ServerStatusService` polls `/api/health` with a dedicated 3s-timeout `URLSession` (independent of APIClient's 35s session), exposes `ServerStatus` enum (unknown/warming/ready) via `@Observable`
- iOS: PitWallTab and LiveTab both show "Warming up server..." spinner banner when status is `.warming`, auto-dismiss via `@Observable` reactivity when `.ready`
- Web: `useServerStatus` hook with module-level probe singleton — all consumers on the same page share one probe cycle; no duplicate requests on re-renders or StrictMode double-invocations
- Web: `ServerWarmingBanner` component integrated into `/` (chat) and `/live` pages; Calendar, Standings, Predictions unaffected
- `npm run build` passes with no TypeScript errors

## Task Commits

Each task was committed atomically:

1. **Task 1: iOS ServerStatusService + banner in PitWallTab and LiveTab** - `0e28bdc` (feat)
2. **Task 2: Web useServerStatus hook + ServerWarmingBanner + page integration** - `f54ea5d` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified
- `ios/F1AI/Services/ServerStatusService.swift` - @Observable singleton; ServerStatus enum; 3s probe URLSession; startPolling/stopPolling
- `ios/F1AI/Views/Tabs/PitWallTab.swift` - Added serverStatus state, warming banner in VStack above ChatView, .task { startPolling() }
- `ios/F1AI/Views/Tabs/LiveTab.swift` - Added serverStatus state, warming banner at top of liveContent, startPolling() in .task
- `frontend/app/hooks/useServerStatus.ts` - Module-level probe singleton; 3s AbortController timeout; 4s retry; listeners Set for multi-consumer sharing
- `frontend/app/components/ServerWarmingBanner.tsx` - Client component; renders only when isWarming; inline spinner + message
- `frontend/app/page.tsx` - Added ServerWarmingBanner import and render before ChatScreen
- `frontend/app/live/page.tsx` - Added ServerWarmingBanner import; wrapped all three return branches (loading/no-session/live) in React fragments with banner at top

## Decisions Made
- **Separate probe URLSession (iOS):** `APIClient` uses a 35s timeout suitable for data fetches. For warm-up detection, a 3s timeout is needed. Created a dedicated `URLSession` in `ServerStatusService` rather than modifying `APIClient` — clean separation with no side effects.
- **Module-level singleton (web):** React's StrictMode double-invokes effects; multiple components calling `useServerStatus()` would create duplicate probe loops. A module-level `probeStarted` flag and `listeners` Set ensures exactly one probe loop per page load regardless of how many components use the hook.
- **React fragments for /live page:** The live page has three distinct return branches. Rather than restructuring into a single return, each branch is wrapped in a `<>` fragment with `<ServerWarmingBanner />` as the first child — minimal diff, no behavior change.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Cold start UX is handled. Users will see a clear warm-up indicator in all backend-dependent features (Pit Wall chat and Live timing on both iOS and web).
- Calendar, Standings, and Predictions remain fully usable during warm-up.
- Pending todo resolved: "Handle Render cold start with UI loading state" can be marked complete.

---
*Phase: quick-1-cold-start*
*Completed: 2026-03-10*
