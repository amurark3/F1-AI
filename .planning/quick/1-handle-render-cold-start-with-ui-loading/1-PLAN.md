---
phase: quick-1-cold-start
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ios/F1AI/Services/ServerStatusService.swift
  - ios/F1AI/Views/Tabs/PitWallTab.swift
  - ios/F1AI/Views/Tabs/LiveTab.swift
  - frontend/app/hooks/useServerStatus.ts
  - frontend/app/components/ServerWarmingBanner.tsx
  - frontend/app/page.tsx
  - frontend/app/live/page.tsx
autonomous: true
requirements: [COLD-START-01]

must_haves:
  truths:
    - "When server is cold, Chat and Live tabs show 'Warming up server...' banner instead of hanging spinner"
    - "User can navigate to Calendar, Standings, Predictions during warm-up (cached data tabs are not blocked)"
    - "Banner disappears automatically once server responds — no manual refresh needed"
    - "Web chat page and live page show the same warming banner state"
  artifacts:
    - path: "ios/F1AI/Services/ServerStatusService.swift"
      provides: "Observable service that probes /api/health, polls every 4s, exposes ServerStatus enum"
      exports: [ServerStatus, ServerStatusService]
    - path: "frontend/app/hooks/useServerStatus.ts"
      provides: "React hook that probes /api/health with 3s timeout, polls every 4s until warm"
      exports: [useServerStatus]
    - path: "frontend/app/components/ServerWarmingBanner.tsx"
      provides: "Inline info banner rendered when serverStatus == .warming"
  key_links:
    - from: "ios/F1AI/Views/Tabs/PitWallTab.swift"
      to: "ServerStatusService"
      via: "@State private var serverStatus = ServerStatusService.shared"
      pattern: "ServerStatusService"
    - from: "frontend/app/page.tsx"
      to: "useServerStatus"
      via: "const { isWarming } = useServerStatus()"
      pattern: "useServerStatus"
---

<objective>
Handle Render cold start by detecting server unavailability early and surfacing a "Warming up server..." banner in Chat and Live features — both iOS and web — rather than letting requests hang or fail silently.

Purpose: Render free tier sleeps after ~15 min inactivity. Cold starts take 20-60 seconds. Without feedback, users think the app is broken. A proactive warm-up indicator prevents confusion and lets users use cached-data features (Calendar, Standings) while waiting.

Output: ServerStatusService (iOS), useServerStatus hook (web), ServerWarmingBanner component (web), banner integration in PitWallTab, LiveTab, web chat page, and web live page.
</objective>

<execution_context>
@/Users/adityamurarka/.claude/get-shit-done/workflows/execute-plan.md
@/Users/adityamurarka/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md

@ios/F1AI/Services/APIClient.swift
@ios/F1AI/Views/Tabs/PitWallTab.swift
@ios/F1AI/Views/Tabs/LiveTab.swift
@frontend/app/hooks/useChat.ts
@frontend/app/constants/api.ts
@frontend/app/components/NavShell.tsx
</context>

<tasks>

<task type="auto">
  <name>Task 1: iOS ServerStatusService + banner in PitWallTab and LiveTab</name>
  <files>
    ios/F1AI/Services/ServerStatusService.swift
    ios/F1AI/Views/Tabs/PitWallTab.swift
    ios/F1AI/Views/Tabs/LiveTab.swift
  </files>
  <action>
Create `ios/F1AI/Services/ServerStatusService.swift` as an `@Observable final class` with a shared singleton.

Define `enum ServerStatus: Equatable { case unknown, warming, ready }`.

`ServerStatusService` fields:
- `var status: ServerStatus = .unknown`
- `private var pollTask: Task<Void, Never>?`

Implement `func startPolling()`:
- If `status == .ready`, return immediately (already warm, do not re-probe)
- Set `status = .warming`
- Launch a `Task` that loops:
  - Call `APIClient.shared.healthCheck()` (already exists — uses `/api/health`, 35s timeout is too long; override with a local URLSession that has `timeoutIntervalForRequest = 3` for the probe only)
  - If healthy: set `status = .ready`, cancel the task, break
  - Else: `try? await Task.sleep(for: .seconds(4))`
- Store the task in `pollTask` so it can be cancelled

Implement `func stopPolling()` that cancels `pollTask` and resets `status = .unknown`.

**Note on timeout:** `APIClient.healthCheck()` uses the shared 35s session — too long for warm-up detection. In `ServerStatusService`, use a separate `URLSession` with `timeoutIntervalForRequest = 3` specifically for probing. Do NOT modify `APIClient.healthCheck()`.

Update `PitWallTab.swift`:
- Add `@State private var serverStatus = ServerStatusService.shared`
- Call `serverStatus.startPolling()` in `.task { }` (the existing `.task` block, or add one)
- Before rendering `ChatView`, insert a conditional warm-up banner at the TOP of the NavigationStack body (inside the VStack or as an overlay):

```swift
if serverStatus.status == .warming {
    HStack(spacing: 8) {
        ProgressView()
            .scaleEffect(0.7)
        Text("Warming up server...")
            .font(.system(size: 13))
            .foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 10)
    .background(.ultraThinMaterial)
}
```

Show `ChatView` regardless — user can still type, send will just queue/fail gracefully as it already does.

Update `LiveTab.swift`:
- Add `@State private var serverStatus = ServerStatusService.shared`
- Call `serverStatus.startPolling()` in the existing `.task` block
- Insert the same warm-up banner above the tab segment picker when `serverStatus.status == .warming`

Both tabs: the banner must disappear automatically when `status` changes to `.ready` (the `@Observable` machinery handles this — no extra logic needed).
  </action>
  <verify>
Build the iOS target. In simulator, point `APIClient.shared.baseURL` at a non-responding host (e.g., change to `http://localhost:9999` temporarily). Launch the app, open Pit Wall tab — the warming banner should appear within 3 seconds. Open Live tab — same banner. Switch to Calendar or Standings — no banner (those tabs do not call `startPolling`).

Restore `baseURL` to production URL. Warm server scenario: banner should not appear if `/api/health` responds within 3s.
  </verify>
  <done>
- `ios/F1AI/Services/ServerStatusService.swift` exists with `ServerStatus` enum and `startPolling()` / `stopPolling()`
- PitWallTab shows warm-up banner when status is `.warming`, banner absent when `.ready`
- LiveTab shows warm-up banner when status is `.warming`, banner absent when `.ready`
- Calendar, Standings, Predictions tabs unaffected
- No change to `APIClient.swift`
  </done>
</task>

<task type="auto">
  <name>Task 2: Web useServerStatus hook + ServerWarmingBanner + page integration</name>
  <files>
    frontend/app/hooks/useServerStatus.ts
    frontend/app/components/ServerWarmingBanner.tsx
    frontend/app/page.tsx
    frontend/app/live/page.tsx
  </files>
  <action>
Create `frontend/app/hooks/useServerStatus.ts`:

```typescript
"use client";

import { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../constants/api';

export type ServerStatus = 'unknown' | 'warming' | 'ready';

// Module-level cache so all consumers share one probe cycle per page load
let cachedStatus: ServerStatus = 'unknown';
const listeners = new Set<(s: ServerStatus) => void>();

function notify(status: ServerStatus) {
  cachedStatus = status;
  listeners.forEach((fn) => fn(status));
}

let probeStarted = false;

async function probe() {
  if (probeStarted) return;
  probeStarted = true;
  notify('warming');

  const poll = async () => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
      clearTimeout(timeout);
      if (res.ok) {
        notify('ready');
        return; // done
      }
    } catch {
      // timeout or network error — server still cold
    }
    setTimeout(poll, 4000); // retry in 4s
  };

  poll();
}

export function useServerStatus(): { status: ServerStatus; isWarming: boolean } {
  const [status, setStatus] = useState<ServerStatus>(cachedStatus);

  useEffect(() => {
    const listener = (s: ServerStatus) => setStatus(s);
    listeners.add(listener);
    // Start probing if not already started
    probe();
    return () => { listeners.delete(listener); };
  }, []);

  return { status, isWarming: status === 'warming' };
}
```

Key design decisions:
- Module-level singleton (`probeStarted`, `cachedStatus`, `listeners`) so multiple components calling `useServerStatus()` on the same page share one probe loop — no duplicate fetches
- `probeStarted` flag prevents re-probing on React re-renders or StrictMode double-invocations
- AbortController with 3s timeout for cold detection
- 4s retry interval

Create `frontend/app/components/ServerWarmingBanner.tsx`:

```tsx
"use client";

import { useServerStatus } from '../hooks/useServerStatus';

export default function ServerWarmingBanner() {
  const { isWarming } = useServerStatus();

  if (!isWarming) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800/60 border-b border-white/5 text-sm text-neutral-400">
      <div className="w-3 h-3 rounded-full border-2 border-neutral-400 border-t-transparent animate-spin" />
      Warming up server — this may take up to 60 seconds on first load
    </div>
  );
}
```

Update `frontend/app/page.tsx` (web chat / Pit Wall page):
- Import `ServerWarmingBanner` from `../components/ServerWarmingBanner` (adjust relative path as needed)
- Render `<ServerWarmingBanner />` as the FIRST child inside the page's root container, before `<ChatScreen>` or whatever the current root component is

Update `frontend/app/live/page.tsx`:
- Same pattern: import and render `<ServerWarmingBanner />` at the top of the page layout, before the live timing content

Do NOT add the banner to `/calendar`, `/standings`, or `/predictions` pages — those use cached data and don't need backend to be warm.
  </action>
  <verify>
Run `cd /Users/adityamurarka/Desktop/F1-AI/frontend && npm run build` — must complete with no TypeScript errors.

Manual test: Open the chat page (`/`) in browser. Open DevTools Network tab, filter to `/api/health`. Confirm a health request fires within 3 seconds of page load. If the server is sleeping, the warming banner should be visible. If the server is up, the banner should not appear (or disappear quickly).

Check `/live` page also shows the banner on cold start. Check `/calendar` — no banner.
  </verify>
  <done>
- `frontend/app/hooks/useServerStatus.ts` exists with module-level probe singleton
- `frontend/app/components/ServerWarmingBanner.tsx` exists and renders only when `isWarming === true`
- Chat page (`/`) and Live page (`/live`) both render `<ServerWarmingBanner />` at top
- `npm run build` passes with no errors
- Calendar, Standings, Predictions pages unaffected
  </done>
</task>

</tasks>

<verification>
1. iOS builds without errors
2. Web `npm run build` passes
3. Warming banner appears in Pit Wall and Live tabs (iOS) and chat/live pages (web) when server is unreachable
4. Banner disappears automatically when server comes back — no refresh needed
5. Calendar, Standings, Predictions are fully usable during warm-up on both platforms
</verification>

<success_criteria>
- Server cold start is surfaced with a clear "Warming up server..." banner in all backend-dependent UI
- Passive navigation (cached-data tabs/pages) works normally during warm-up
- Banner auto-dismisses on server ready — zero user action required
- No new dependencies introduced
- iOS and web builds pass
</success_criteria>

<output>
After completion, create `.planning/quick/1-handle-render-cold-start-with-ui-loading/1-SUMMARY.md` following the summary template.
</output>
