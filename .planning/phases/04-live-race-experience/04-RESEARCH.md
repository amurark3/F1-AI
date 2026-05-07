# Phase 4: Live Race Experience - Research

**Researched:** 2026-03-05
**Domain:** iOS ActivityKit / Dynamic Island, AI commentary generation, real-time WebSocket fanout
**Confidence:** HIGH (codebase), MEDIUM (ActivityKit constraints), HIGH (backend patterns)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Driver Selection**
- Favorite driver is configured in the App Settings screen (alongside existing notifications settings)
- Dynamic Island tracks the user's configured favorite driver
- If no favorite driver is set, Dynamic Island defaults to showing the race leader
- Users can change their favorite driver mid-session (Settings update propagates to the live activity)

**AI Commentary Style**
- Tone: Excited commentator — energetic, fan-friendly (not technical race engineer voice)
- History: Scrollable session history — all commentary entries for the session are preserved and scrollable
- Personalization: Neutral — commentary covers all notable events, not personalized to the favorite driver
- Event type indicators: Yes — each entry has a small icon or color accent per event type (red for safety car, yellow for pit stop, blue for fastest lap)
- Audio: Silent — visual only — no sound or haptic feedback when commentary fires

**Commentary Panel Placement (iOS)**
- Lives in the existing Live tab (already exists with timing tower)
- Layout: Segmented picker — "Timing" segment shows the driver leaderboard, "Commentary" segment shows the commentary feed
- New commentary: Badge on the Commentary segment (dot indicator) — does not auto-switch segments
- User stays on their selected segment at all times

**Commentary Panel Placement (Web)**
- Sidebar panel next to the timing data on wider screens
- Runs as a column alongside the timing tower

**Session Detection & Live Trigger**
- Dynamic Island auto-starts when a session is detected as `in_progress` (via existing calendar polling)
- Dynamic Island auto-ends with a post-session display: shows final result for 30 minutes, then auto-dismisses
- Dynamic Island compact view shows: race leader name + current lap (e.g., "VER | Lap 34/57") — OR — favorite driver position + gap + lap if favorite is set
- Dynamic Island expanded view shows full timing data from the WebSocket feed

### Claude's Discretion
- Commentary length per entry (1-2 vs 2-4 sentences)
- LLM-generated vs template-based commentary
- Exact Dynamic Island update mechanism (ActivityKit push vs app-driven updates)
- Color/icon palette for event type indicators
- Exact web sidebar layout and breakpoint behavior

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LIVE-01 | Dynamic Island shows current driver position, gap to leader, current lap, and safety car status during active sessions | ActivityKit `ActivityAttributes.ContentState` holds position/gap/lap/flag; compact view renders from `LivePosition` + `SessionStatus` already in the WebSocket stream |
| LIVE-02 | Dynamic Island compact and expanded views update in real-time from existing WebSocket timing data | App-driven `Activity.update(using:)` called from the foreground `LiveTimingViewModel` on every WebSocket message; no push infrastructure needed |
| LIVE-03 | AI commentary generates contextual insights when significant timing events occur (position changes, safety car, fastest lap, pit stops) | Backend event detector compares successive position arrays; calls Gemini on event; broadcasts `{"type":"commentary",...}` over the existing `/api/live/{year}/{round}` WebSocket |
| LIVE-04 | AI commentary does not fire more than once every 30 seconds regardless of event frequency | Server-side `last_commentary_time` float per room; guard `time.time() - last >= 30` before calling LLM |
| LIVE-05 | Commentary panel is visible in both iOS and web UIs | iOS: segmented picker in `LiveTab`; Web: new `/live` Next.js page with sidebar layout |
</phase_requirements>

---

## Summary

The app has a complete live-timing pipeline: a FastAPI WebSocket at `/api/live/{year}/{round}` polls OpenF1 every 8 s, and an `@Observable` `LiveTimingService` on iOS handles the WebSocket and publishes `positions`, `sessionStatus`, and `lastFlag` to `LiveTimingViewModel`, which is already consumed by `LiveTab`.

Phase 4 adds three new capabilities on top of this infrastructure:

**Dynamic Island** — a new `ActivityKit`-based Live Activity declared inside the existing `F1AIWidgets` target (which already has a `@main` `WidgetBundle`). The Live Activity is app-driven: when `LiveTimingViewModel` receives a position update, it calls `Activity.update(using:)` with fresh `ContentState`. No push token infrastructure is needed because the app drives the WebSocket itself. The compact view shows the tracked driver's position/gap/lap; the expanded view renders a mini timing tower. The activity starts when `calendarVM.schedule` contains a race with `status == "in_progress"` and ends 30 minutes after the session completes.

**AI Commentary** — the backend event detector runs inside the existing WebSocket handler loop. Each poll cycle it diffs the incoming position array against the previous snapshot to detect position changes, checks `sessionStatus.status` for safety car / red flag, checks the `lastLap` field for fastest laps, and checks `pitStops` deltas. When a significant event is found and 30 seconds have passed since the last commentary, it calls the Gemini API synchronously (inside `asyncio.to_thread`), builds a commentary entry, and broadcasts it as a new `{"type":"commentary"}` WebSocket message to all connected clients in the same room. The iOS `LiveTimingService` deserializes it; the web page processes it in the existing `useEffect` WebSocket handler.

**Web Live Page** — a new `/live` Next.js page (added to `NavShell` nav items) that opens a WebSocket connection and renders a two-column layout: timing tower on the left, commentary sidebar on the right for `lg:` breakpoints and stacked for mobile.

**Primary recommendation:** Use app-driven ActivityKit updates (no push infrastructure), broadcast commentary over the existing WebSocket with a new `commentary` message type, and implement event detection inside the backend poll loop.

---

## Standard Stack

### Core (all already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ActivityKit | iOS 16.2+ | Declare/start/update/end Live Activities | Apple-first; only way to get Dynamic Island |
| WidgetKit | iOS 16.2+ | Render SwiftUI views in Dynamic Island | Required pair with ActivityKit |
| SwiftUI | iOS 17 target | Compact/expanded Dynamic Island views | Existing app target; @Observable already in use |
| FastAPI WebSocket | existing | Deliver commentary messages to clients | Already in backend; zero new infrastructure |
| Gemini (via `langchain-google-genai`) | existing | Generate commentary text | Already used for chat; same LLM |

### No New Dependencies Required

The entire phase builds on existing libraries. No new Swift packages, Python packages, or npm packages are needed.

**Installation:** none — all dependencies already present.

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
ios/F1AIWidgets/
├── NextRaceWidget.swift          # EXISTS — already has @main WidgetBundle
└── RaceLiveActivity.swift        # NEW — ActivityAttributes + ActivityConfiguration

ios/F1AI/
├── Services/
│   └── LiveActivityService.swift # NEW — start/update/end lifecycle
├── Views/
│   ├── Live/
│   │   └── CommentaryFeedView.swift # NEW — scrollable commentary list
│   └── Settings/
│       └── NotificationSettingsView.swift # MODIFY — add favorite driver picker
└── ViewModels/
    └── LiveTimingViewModel.swift # MODIFY — add commentary array + badge logic

backend/app/api/
└── routes.py                    # MODIFY — add commentary detection + broadcast

frontend/app/
├── live/
│   └── page.tsx                 # NEW — /live page with WebSocket hook
├── components/
│   ├── LiveTimingTower.tsx       # NEW — web timing tower component
│   └── CommentaryPanel.tsx       # NEW — web commentary sidebar
└── hooks/
    └── useLiveTiming.ts          # NEW — WebSocket connection hook
```

### Pattern 1: ActivityKit — ActivityAttributes Declaration

**What:** Declare a struct conforming to `ActivityAttributes` with static (per-session) and dynamic (`ContentState`) data. The widget extension renders the views; the main app controls the lifecycle.

**When to use:** The only way to use Dynamic Island. Must live in a file that is a member of BOTH the main app target AND the widget extension target (or in a shared group accessible to both — use target membership, not an app group, since we don't need cross-process data sharing here).

```swift
// Source: Apple ActivityKit documentation, sparrowcode.io/en/tutorials/live-activities
// File: ios/F1AIWidgets/RaceLiveActivity.swift
// Target membership: F1AI + F1AIWidgets

import ActivityKit
import WidgetKit
import SwiftUI

struct RaceLiveActivityAttributes: ActivityAttributes {
    // Static — set at activity start, never changes during session
    let raceName: String
    let round: Int
    let year: Int

    // Dynamic — updated every WebSocket cycle
    struct ContentState: Codable, Hashable {
        var trackedDriver: String      // abbreviation, e.g. "VER"
        var trackedPosition: Int
        var trackedGap: String         // "LEADER" or "+3.4s"
        var currentLap: Int
        var totalLaps: Int
        var sessionStatus: String      // "started", "safety car", "red flag", etc.
        var isLeader: Bool             // true if tracking race leader
    }
}

struct RaceLiveActivityView: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RaceLiveActivityAttributes.self) { context in
            // Lock screen banner
            RaceLockScreenView(context: context)
                .padding()
                .activityBackgroundTint(Color.black)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded (long-press)
                DynamicIslandExpandedRegion(.leading) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("P\(context.state.trackedPosition)")
                            .font(.system(size: 28, weight: .black))
                        Text(context.state.trackedDriver)
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("LAP \(context.state.currentLap)/\(context.state.totalLaps)")
                            .font(.system(size: 12, weight: .black, design: .monospaced))
                        Text(context.state.trackedGap)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(context.state.sessionStatus.uppercased())
                        .font(.system(size: 10, weight: .bold))
                        .tracking(1)
                        .foregroundStyle(statusColor(context.state.sessionStatus))
                }
            } compactLeading: {
                Text(context.state.trackedDriver)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
            } compactTrailing: {
                Text("P\(context.state.trackedPosition) L\(context.state.currentLap)")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
            } minimal: {
                Text("P\(context.state.trackedPosition)")
                    .font(.system(size: 11, weight: .black))
            }
        }
    }
}
```

### Pattern 2: ActivityKit — Lifecycle Management (App-Driven)

**What:** The main app starts, updates, and ends the Live Activity. Updates are driven by the existing WebSocket loop — no push tokens needed.

**When to use:** The app is running and has an active WebSocket connection (which it does during live timing). App-driven updates are unlimited in frequency when the app is in the foreground; they also work in the background as long as the app has background processing entitlement, but for this use case the app is always foregrounded during a live session.

```swift
// Source: sparrowcode.io/en/tutorials/live-activities, blog.logrocket.com/exploring-ios-live-activities-api/
// File: ios/F1AI/Services/LiveActivityService.swift

import ActivityKit
import Foundation

@Observable
final class LiveActivityService {
    private var currentActivity: Activity<RaceLiveActivityAttributes>?

    var isActive: Bool { currentActivity != nil }

    func startActivity(race: RaceEvent, initialState: RaceLiveActivityAttributes.ContentState) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        guard currentActivity == nil else { return }

        let attributes = RaceLiveActivityAttributes(
            raceName: race.name,
            round: race.round,
            year: Int(race.date?.prefix(4) ?? "2025") ?? 2025
        )
        do {
            currentActivity = try Activity.request(
                attributes: attributes,
                content: .init(state: initialState, staleDate: nil)
            )
        } catch {
            print("LiveActivity start failed: \(error)")
        }
    }

    func update(state: RaceLiveActivityAttributes.ContentState) async {
        await currentActivity?.update(.init(state: state, staleDate: nil))
    }

    func endActivity(finalState: RaceLiveActivityAttributes.ContentState) async {
        // Show final state for 30 minutes, then dismiss
        let dismissal = ActivityUIDismissalPolicy.after(Date().addingTimeInterval(30 * 60))
        await currentActivity?.end(.init(state: finalState, staleDate: nil), dismissalPolicy: dismissal)
        currentActivity = nil
    }
}
```

### Pattern 3: Commentary Detection in Backend Poll Loop

**What:** Inside the existing WebSocket handler, maintain previous state and compare each poll cycle. When a significant event is detected and the cooldown has passed, call Gemini and broadcast.

**When to use:** Simplest possible architecture — no new endpoints, no separate service. Commentary originates server-side so both iOS and web get it identically.

```python
# Source: existing routes.py pattern (polling loop already exists)
# File: backend/app/api/routes.py — modifications inside live_timing() handler

import time as time_module

# Per-room commentary state (in-memory, same pattern as race_detail_cache)
_commentary_state: dict[str, dict] = {}
# Keys per room: "last_time" (float), "prev_positions" (list[dict]), "prev_pit_stops" (dict)

COMMENTARY_COOLDOWN = 30  # seconds

def _detect_event(prev_positions: list[dict], curr_positions: list[dict],
                  prev_pit_stops: dict[str, int], session_status: str,
                  prev_session_status: str) -> dict | None:
    """
    Returns event dict or None. Checked in priority order:
      1. Safety car / red flag (flag change)
      2. Position change (any driver moved at least 1 place)
      3. Fastest lap (check last_lap field — requires OpenF1 to return it)
      4. Pit stop (pit_stops count increased for any driver)
    """
    # Safety car / red flag — highest priority
    if session_status != prev_session_status and session_status.lower() in (
        "safety car", "vsc", "red flag"
    ):
        return {"type": "safety_car", "status": session_status}

    # Position change
    curr_map = {p["driver"]: p["position"] for p in curr_positions}
    prev_map = {p["driver"]: p["position"] for p in prev_positions}
    for driver, curr_pos in curr_map.items():
        prev_pos = prev_map.get(driver)
        if prev_pos and curr_pos != prev_pos:
            gainer = driver if curr_pos < prev_pos else None
            # Find who they overtook
            return {
                "type": "position_change",
                "driver": driver,
                "from_pos": prev_pos,
                "to_pos": curr_pos,
                "positions": curr_positions[:5],  # top 5 for context
            }

    # Pit stop
    for p in curr_positions:
        drv = p["driver"]
        curr_pits = p.get("pit_stops") or 0
        prev_pits = prev_pit_stops.get(drv, 0)
        if curr_pits > prev_pits:
            return {"type": "pit_stop", "driver": drv, "pit_count": curr_pits,
                    "position": p["position"]}

    return None


async def _generate_commentary(event: dict, race_name: str) -> str:
    """
    Call Gemini to generate 2-3 sentence excited-commentator commentary.
    Runs inside asyncio.to_thread so it doesn't block the event loop.
    Falls back to a template string on LLM error.
    """
    event_type = event["type"]

    # Build a minimal prompt based on event type
    if event_type == "safety_car":
        prompt = (
            f"You are an excited F1 race commentator covering {race_name}. "
            f"The {event['status']} has been deployed. Write 2-3 energetic sentences "
            "explaining what this means for the race. Fan-friendly, no jargon."
        )
    elif event_type == "position_change":
        top5 = event.get("positions", [])
        top5_str = ", ".join(f"P{p['position']} {p['driver']}" for p in top5)
        prompt = (
            f"You are an excited F1 race commentator covering {race_name}. "
            f"Driver {event['driver']} just moved from P{event['from_pos']} to P{event['to_pos']}. "
            f"Current top 5: {top5_str}. Write 2-3 energetic sentences. Fan-friendly."
        )
    elif event_type == "pit_stop":
        prompt = (
            f"You are an excited F1 race commentator covering {race_name}. "
            f"Driver {event['driver']} has just pitted (stop #{event['pit_count']}), "
            f"currently running P{event['position']} after the stop. "
            "Write 2-3 energetic sentences. Fan-friendly."
        )
    else:
        return ""

    try:
        # Use existing llm (langchain ChatGoogleGenerativeAI) — no new client needed
        response = await asyncio.to_thread(llm.invoke, prompt)
        return response.content.strip()
    except Exception as e:
        logger.error("commentary.llm_error", error=str(e))
        # Template fallback
        if event_type == "safety_car":
            return f"Safety car is out at {race_name}! The field bunches up and strategy windows open wide!"
        elif event_type == "position_change":
            return f"Position change! {event['driver']} moves to P{event['to_pos']}!"
        elif event_type == "pit_stop":
            return f"{event['driver']} dives into the pits! Strategy call being made!"
        return ""
```

### Pattern 4: WebSocket Commentary Message Type

**What:** The backend broadcasts a new message type `"commentary"` over the existing WebSocket. The iOS `LiveTimingService` and the web `useLiveTiming` hook both need to handle it.

```python
# Backend broadcast (inside live_timing WebSocket handler, after event detection)
commentary_entry = {
    "type": "commentary",
    "data": {
        "id": str(time_module.time()),          # unique ID for React key
        "text": commentary_text,
        "event_type": event["type"],             # "safety_car" | "position_change" | "pit_stop"
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
}
await websocket.send_json(commentary_entry)
```

```swift
// iOS additions to LiveTiming.swift model
struct CommentaryEntry: Codable, Identifiable, Hashable {
    let id: String
    let text: String
    let eventType: String      // "safety_car" | "position_change" | "pit_stop"
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case id, text, timestamp
        case eventType = "event_type"
    }
}

// LiveTimingData enum — add new case
enum LiveTimingData: Codable {
    case positions([LivePosition])
    case sessionStatus(SessionStatus)
    case flag(FlagEvent)
    case commentary(CommentaryEntry)   // NEW
    // ... decoder updated to handle "commentary" type field
}
```

### Pattern 5: iOS Segmented Picker in LiveTab

**What:** Replace the plain `ScrollView + TimingTower` in `liveContent()` with a `Picker` + conditional view. Badge dot on Commentary segment when new entries arrive.

```swift
// Modification to LiveTab.swift
enum LiveSegment: String, CaseIterable {
    case timing = "Timing"
    case commentary = "Commentary"
}

// Inside liveContent(race:):
@State private var selectedSegment: LiveSegment = .timing
@State private var hasNewCommentary = false

VStack(spacing: 0) {
    // ... race header ...
    Picker("", selection: $selectedSegment) {
        ForEach(LiveSegment.allCases, id: \.self) { seg in
            if seg == .commentary && hasNewCommentary {
                Label(seg.rawValue, systemImage: "circle.fill")
                    .labelStyle(.titleAndIcon)
                    .tag(seg)
            } else {
                Text(seg.rawValue).tag(seg)
            }
        }
    }
    .pickerStyle(.segmented)
    .padding(.horizontal, 12)
    .padding(.vertical, 8)

    switch selectedSegment {
    case .timing: TimingTowerScrollView(vm: vm)
    case .commentary:
        CommentaryFeedView(entries: vm.commentaryEntries)
            .onAppear { hasNewCommentary = false }
    }
}
.onChange(of: vm.commentaryEntries.count) {
    if selectedSegment != .commentary {
        hasNewCommentary = true
    }
}
```

### Pattern 6: Web Live Page Layout

**What:** New `/live` page with two-column layout on large screens. WebSocket hook mirrors the iOS service pattern.

```typescript
// File: frontend/app/live/page.tsx
// Uses "use client" — WebSocket needs browser APIs

// Layout structure:
// lg: two columns — timing tower (flex-1) | commentary sidebar (w-80)
// mobile: stacked, commentary below timing

<div className="max-w-7xl mx-auto px-4 py-6">
  <div className="flex flex-col lg:flex-row gap-6">
    <div className="flex-1 min-w-0">
      <LiveTimingTower positions={positions} sessionStatus={sessionStatus} />
    </div>
    <div className="w-full lg:w-80 shrink-0">
      <CommentaryPanel entries={commentary} />
    </div>
  </div>
</div>
```

```typescript
// File: frontend/app/hooks/useLiveTiming.ts
"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { API_BASE } from "../constants/api";

export interface LivePosition { /* matches backend shape */ }
export interface CommentaryEntry {
  id: string; text: string; event_type: string; timestamp: string;
}

export function useLiveTiming(year: number, round: number) {
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [sessionStatus, setSessionStatus] = useState<{status:string;lap?:number;total_laps?:number}|null>(null);
  const [commentary, setCommentary] = useState<CommentaryEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsURL = API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
    const ws = new WebSocket(`${wsURL}/api/live/${year}/${round}`);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "positions") setPositions(msg.data);
      else if (msg.type === "session_status") setSessionStatus(msg.data);
      else if (msg.type === "commentary") {
        setCommentary(prev => [msg.data, ...prev].slice(0, 100)); // keep last 100
      }
    };

    return () => ws.close();
  }, [year, round]);

  return { positions, sessionStatus, commentary, isConnected };
}
```

### Pattern 7: Favorite Driver Setting

**What:** Add a `@AppStorage("favoriteDriver")` string (abbreviation, e.g. "VER") to `NotificationSettingsView`. `LiveActivityService` reads it to decide which driver to track.

```swift
// Modification to NotificationSettingsView.swift
@AppStorage("favoriteDriver") private var favoriteDriver: String = ""

Section {
    // Text field or Picker from known driver abbreviations
    TextField("Driver abbreviation (e.g. VER)", text: $favoriteDriver)
        .autocorrectionDisabled()
        .textInputAutocapitalization(.characters)
} header: {
    Text("Live Race Tracking")
} footer: {
    Text("Leave blank to track the race leader in Dynamic Island.")
}
```

```swift
// LiveActivityService reads this to decide ContentState.trackedDriver
let favorite = UserDefaults.standard.string(forKey: "favoriteDriver") ?? ""
let tracked = favorite.isEmpty
    ? positions.first  // race leader
    : positions.first(where: { $0.driver == favorite }) ?? positions.first
```

### Anti-Patterns to Avoid

- **Separate polling timer for Live Activity:** Do NOT add a `Timer` to update the Live Activity independently. Use the existing WebSocket `onChange` path — when `vm.positions` updates, update the activity.
- **Storing Activity in ViewModel:** Keep `LiveActivityService` as a separate `@Observable` class injected into `LiveTab`; do not put `Activity<...>` directly on `LiveTimingViewModel` — it imports `ActivityKit` which the widget target also needs and mixing concerns causes target membership confusion.
- **Push notifications for commentary:** Do NOT implement APNs push for commentary. The app already maintains an active WebSocket; broadcasting over that is simpler and more reliable for this use case.
- **Blocking the WebSocket event loop with LLM calls:** Always use `asyncio.to_thread` for the Gemini call. The WebSocket handler is async; blocking it will stall all connected clients.
- **New message type breaking existing decoder:** The `LiveTimingMessage.type` field is a string discriminator. Adding `"commentary"` as a new type value will NOT break existing clients — the iOS decoder's `switch decoded.data` just needs a new case; old web clients that don't handle it will log an unrecognized type, which is acceptable.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dynamic Island rendering | Custom overlay view | `ActivityKit` + `DynamicIsland { }` | Dynamic Island is system-controlled; only ActivityKit can place content there |
| Cross-process data sharing (main app → widget) | App group UserDefaults or file sharing | None needed — app drives updates via `Activity.update()` | Widget reads `context.state` which ActivityKit provides; no manual IPC |
| Rate limiter class | Custom time-based queue | Simple `time.time()` comparison in handler | 30-second cooldown is stateless; no queue, no lock needed |
| Commentary delivery separate channel | New REST endpoint for polling | Add `"commentary"` type to existing WebSocket | Both clients already maintain the connection; free broadcast |
| LLM client for commentary | New Anthropic/OpenAI client | Existing `langchain_google_genai` `llm.invoke` | Gemini is already configured with safety settings and model name |

**Key insight:** Every non-trivial problem in this phase already has infrastructure. The work is wiring, not building from scratch.

---

## Common Pitfalls

### Pitfall 1: ActivityKit File Target Membership
**What goes wrong:** `RaceLiveActivity.swift` is added to only one target. Either the widget can't see the `ActivityAttributes` type, or the main app can't see it.
**Why it happens:** Xcode doesn't auto-add files to both targets when you create them in the widget folder.
**How to avoid:** In Xcode's File Inspector, check both `F1AI` and `F1AIWidgets` under Target Membership for `RaceLiveActivity.swift`.
**Warning signs:** Compile error "cannot find type 'RaceLiveActivityAttributes' in scope" in either target.

### Pitfall 2: Missing Info.plist Keys
**What goes wrong:** `Activity.request()` always throws; `areActivitiesEnabled` is always false.
**Why it happens:** The app target `Info.plist` is missing `NSSupportsLiveActivities = YES`. The project uses `GENERATE_INFOPLIST_FILE: YES` in `project.yml` (XcodeGen), so keys must be added under `settings.base` or a custom Info.plist.
**How to avoid:** In `project.yml`, add to `F1AI.settings.base`:
```yaml
INFOPLIST_KEY_NSSupportsLiveActivities: YES
# Optional — for higher update priority budget:
INFOPLIST_KEY_NSSupportsLiveActivitiesFrequentUpdates: YES
```
**Warning signs:** `ActivityAuthorizationInfo().areActivitiesEnabled` returns `false` on device.

### Pitfall 3: `@main` Conflict in Widget Bundle
**What goes wrong:** Adding `RaceLiveActivityView: Widget` causes a build error about multiple `@main` entry points.
**Why it happens:** `NextRaceWidget.swift` already has `@main struct F1AIWidgets: WidgetBundle`. You cannot add another `@main`.
**How to avoid:** Add `RaceLiveActivityView` to the EXISTING `F1AIWidgets` bundle body, not as a separate entry point:
```swift
@main
struct F1AIWidgets: WidgetBundle {
    var body: some Widget {
        NextRaceWidget()
        RaceLiveActivityView()   // add here, not with @main
    }
}
```

### Pitfall 4: ActivityKit Update When App is Backgrounded
**What goes wrong:** Live Activity stops updating when the user leaves the app, even though the WebSocket is still connected.
**Why it happens:** Without Background Modes entitlement, the WebSocket is paused when the app backgrounds. `Activity.update()` can technically be called from background tasks, but receiving WebSocket messages requires the socket to be alive.
**How to avoid:** For Phase 4 scope, this is acceptable — the Live Activity is most useful when the user is actively watching. Document this limitation. If background updates are needed later (Phase 5 scope), APNs push would be the solution.
**Warning signs:** Activity shows stale data when user switches to another app.

### Pitfall 5: Commentary LLM Latency Blocking WebSocket Clients
**What goes wrong:** Calling Gemini synchronously inside the async WebSocket handler blocks all position updates for 1-3 seconds while LLM responds.
**Why it happens:** `langchain-google-genai` `llm.invoke` is synchronous; the FastAPI event loop can't yield during it.
**How to avoid:** Always wrap with `asyncio.to_thread`:
```python
commentary_text = await asyncio.to_thread(llm.invoke, prompt)
```
The existing `routes.py` already uses this pattern for FastF1 calls.

### Pitfall 6: Previous Position State Not Maintained Per Room
**What goes wrong:** Commentary fires for every position seen on first connect, because there's no "previous" snapshot.
**Why it happens:** `_commentary_state` dict doesn't exist for a new connection.
**How to avoid:** Initialize on first data receipt:
```python
state = _commentary_state.setdefault(room, {
    "last_time": 0.0,
    "prev_positions": [],
    "prev_pit_stops": {},
    "prev_session_status": "",
})
# Only detect events after the first full snapshot is stored
if not state["prev_positions"]:
    state["prev_positions"] = curr_positions
    continue  # skip detection on first snapshot
```

### Pitfall 7: Web Navigation — Missing Live Route
**What goes wrong:** `/live` page exists but no nav link; users can't find it.
**Why it happens:** `NavShell.tsx` has a hardcoded `NAV_ITEMS` array.
**How to avoid:** Add `{ href: '/live', label: 'Live' }` to `NAV_ITEMS` in `NavShell.tsx`. The live page should gracefully handle no-session state (show "No live session").

### Pitfall 8: OpenF1 Does Not Return Lap Number in Position Data
**What goes wrong:** `SessionStatus.lap` is always `null` in the backend, making the compact view show "Lap --/57".
**Why it happens:** The current `_poll_openf1_positions` function only calls `/v1/position`; lap count comes from a separate OpenF1 `/v1/sessions` or `/v1/laps` endpoint.
**How to avoid:** The backend already queries `/v1/sessions` in `_find_openf1_session`. Add a session info fetch to also retrieve `lap_count` if available, or source lap info from the `SessionStatus` message. Check the actual OpenF1 response to confirm which fields are present. This is a LOW confidence area — verify during implementation.

---

## Code Examples

### Starting/Ending Live Activity from LiveTab

```swift
// Source: sparrowcode.io/en/tutorials/live-activities, blog.logrocket.com/exploring-ios-live-activities-api/

// In LiveTab.liveContent():
.onAppear {
    vm.connect(year: calendarVM.selectedYear, round: race.round)
    // Start activity with current leader as default
    if let leader = vm.positions.first,
       let status = vm.sessionStatus {
        let state = RaceLiveActivityAttributes.ContentState(
            trackedDriver: resolveTrackedDriver(positions: vm.positions),
            trackedPosition: 1,
            trackedGap: "LEADER",
            currentLap: status.lap ?? 0,
            totalLaps: status.totalLaps ?? 0,
            sessionStatus: status.status,
            isLeader: true
        )
        liveActivityService.startActivity(race: race, initialState: state)
    }
}
.onChange(of: vm.positions) {
    // Update activity on every WebSocket position update
    Task { await liveActivityService.updateFromPositions(vm.positions, status: vm.sessionStatus) }
}
```

### Commentary Event Icons (iOS)

```swift
// CommentaryFeedView.swift
func eventIcon(_ eventType: String) -> (name: String, color: Color) {
    switch eventType {
    case "safety_car": return ("exclamationmark.triangle.fill", .yellow)
    case "position_change": return ("arrow.up.arrow.down", .blue)
    case "pit_stop": return ("wrench.and.screwdriver.fill", .orange)
    case "fastest_lap": return ("bolt.fill", .purple)
    default: return ("flag.fill", .gray)
    }
}
```

### Commentary Panel Web (TypeScript)

```typescript
// CommentaryPanel.tsx
const EVENT_STYLES: Record<string, { icon: string; color: string }> = {
  safety_car: { icon: "⚠️", color: "text-yellow-400 border-yellow-400/30" },
  position_change: { icon: "↕", color: "text-blue-400 border-blue-400/30" },
  pit_stop: { icon: "🔧", color: "text-orange-400 border-orange-400/30" },
};
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Widget Timeline (WidgetKit) | ActivityKit Live Activities | iOS 16.1 (2022) | Enables real-time Dynamic Island; widgets are still for home screen static data |
| Push-only Live Activity updates | App-driven `Activity.update()` from foreground | iOS 16.1 | No push infrastructure needed for in-app real-time updates |
| `Activity<A>.request(attributes:contentState:)` | `Activity<A>.request(attributes:content:)` with `ActivityContent` wrapper | iOS 16.2 | Newer API uses `ActivityContent` struct; older form still works but deprecated in iOS 17 |
| `await activity.update(using: state)` | `await activity.update(.init(state: state, staleDate: nil))` | iOS 16.2 | Same semantic change; use `ActivityContent` wrapper |

**Deprecated/outdated:**
- `Activity.request(attributes:contentState:pushType:)` — the `pushType` parameter: use `nil` for app-driven (no push), or the newer `ActivityContent` API. Do not use `pushType: .token` unless you have APNs infrastructure ready.
- Single `@main` struct in widget target: must add Live Activity widget to the EXISTING `WidgetBundle`, not create a new `@main`.

---

## Open Questions

1. **Does OpenF1 `/v1/position` return lap number?**
   - What we know: the existing `_poll_openf1_positions` function maps OpenF1's position data to `LivePosition`. The current `SessionStatus` struct has `lap` and `total_laps` but the existing backend doesn't populate them — they come from a separate message type that isn't currently wired.
   - What's unclear: whether OpenF1 provides per-session lap count in the positions endpoint, or whether it requires a separate `/v1/laps` call.
   - Recommendation: Check the actual OpenF1 API response during implementation. If not available in `/v1/position`, fetch from `/v1/sessions` (which `_find_openf1_session` already calls) and broadcast as part of `session_status` messages. LOW confidence.

2. **ActivityKit update budget when app is backgrounded**
   - What we know: App-driven updates work while app is foregrounded. The update budget limit is undocumented by Apple publicly; community reports suggest ~15 updates/hour for push-based updates. App-driven (local) updates appear to be unconstrained when app is foregrounded.
   - What's unclear: Exact behavior when app moves to background with an open WebSocket.
   - Recommendation: Accept that background updates may be throttled or stopped. The Live Activity will show stale data when the user leaves the app — this is acceptable for Phase 4. Add a "staleDate" to `ActivityContent` so iOS greys out the display when data is stale: `staleDate: Date().addingTimeInterval(30)`.

3. **Gemini commentary latency impact on WebSocket clients**
   - What we know: Gemini flash response time is typically 1-3 seconds. `asyncio.to_thread` prevents blocking. The 30-second cooldown means at most one LLM call per 30 seconds per room.
   - What's unclear: Whether concurrent rooms (if multiple races are live simultaneously, which is rare) would queue up.
   - Recommendation: Use `asyncio.to_thread` and accept 1-3s commentary generation delay. Commentary will appear slightly after the event — this is fine.

4. **Web live page — how does it find the current race?**
   - What we know: The iOS app reads `calendarVM.schedule.first(where: { $0.status == "in_progress" })`. The web can use `useSWR` to fetch `/api/schedule/{year}` and find the in_progress race.
   - What's unclear: Whether the web `/live` page should auto-detect the race or show a "no live session" placeholder.
   - Recommendation: Fetch schedule on page load, auto-detect in_progress race, connect WebSocket. If no in_progress race, show placeholder. MEDIUM confidence.

---

## Codebase Findings

### Key Files to Modify

| File | Change Type | What Changes |
|------|-------------|--------------|
| `ios/F1AIWidgets/NextRaceWidget.swift` | Modify | Add `RaceLiveActivityView()` to `F1AIWidgets` WidgetBundle body |
| `ios/F1AI/Views/Tabs/LiveTab.swift` | Modify | Add segmented picker, badge logic, connect/disconnect LiveActivityService |
| `ios/F1AI/ViewModels/LiveTimingViewModel.swift` | Modify | Add `commentaryEntries: [CommentaryEntry]` array, `hasNewCommentary: Bool` |
| `ios/F1AI/Services/LiveTimingService.swift` | Modify | Handle new `"commentary"` message type in `handleMessage()` |
| `ios/F1AI/Models/LiveTiming.swift` | Modify | Add `CommentaryEntry` struct, add `.commentary` case to `LiveTimingData` |
| `ios/F1AI/Views/Settings/NotificationSettingsView.swift` | Modify | Add favorite driver text field section |
| `backend/app/api/routes.py` | Modify | Add `_detect_event`, `_generate_commentary`, commentary state dict, call in WebSocket loop |
| `ios/project.yml` | Modify | Add `NSSupportsLiveActivities: YES` to F1AI settings |
| `frontend/app/components/NavShell.tsx` | Modify | Add `/live` to NAV_ITEMS |

### Key Files to Create

| File | Purpose |
|------|---------|
| `ios/F1AIWidgets/RaceLiveActivity.swift` | ActivityAttributes struct + Widget view with Dynamic Island views |
| `ios/F1AI/Services/LiveActivityService.swift` | start/update/end lifecycle management |
| `ios/F1AI/Views/Live/CommentaryFeedView.swift` | Scrollable commentary list with event icons |
| `frontend/app/live/page.tsx` | /live Next.js page |
| `frontend/app/hooks/useLiveTiming.ts` | WebSocket hook for live data |
| `frontend/app/components/LiveTimingTower.tsx` | Web timing tower (mirrors iOS TimingTower) |
| `frontend/app/components/CommentaryPanel.tsx` | Web commentary sidebar |

### Existing Patterns to Follow

- **`@Observable` service pattern:** `LiveTimingService` → `LiveTimingViewModel` → View. Follow same pattern for `LiveActivityService`.
- **`@AppStorage` for user preferences:** `NotificationSettingsView` uses `@AppStorage("notificationAdvanceMinutes")`. Add `@AppStorage("favoriteDriver")` same way.
- **`asyncio.to_thread` for blocking calls:** All heavy I/O in `routes.py` uses this pattern. Commentary LLM call must follow it.
- **`manager.broadcast` pattern:** `ConnectionManager` already exists with room-based fanout. Use `await websocket.send_json(commentary_entry)` (per-connection send inside the handler, since each connection is its own task).
- **useSWR for data fetching:** All web pages use SWR. The live page needs a custom WebSocket hook (`useLiveTiming`) since SWR is HTTP-only.
- **`glass` / `glass-strong` CSS utilities:** Already defined in `globals.css`. Commentary panel uses these.
- **Framer Motion:** Already installed (`framer-motion: ^12`). Use `AnimatePresence` + `motion.div` for commentary entries sliding in.

### Session `in_progress` Detection

The schedule endpoint (`/api/schedule/{year}`) computes `status = "in_progress"` when:
```python
elif first_session_date and now_utc >= first_session_date:
    event["status"] = "in_progress"
```
This means "in_progress" covers the entire race **weekend** (from FP1 through Race), not just when a session is actively running. The iOS `LiveTab` checks `calendarVM.schedule.first(where: { $0.status == "in_progress" })`. The Dynamic Island should only start when the WebSocket connects successfully AND position data arrives — don't start it purely on calendar status.

---

## Plan Shape (Recommended Task Breakdown)

**7 tasks, sequential with one parallel group:**

| Task | Scope | Files | Estimated Complexity |
|------|-------|-------|---------------------|
| 04-01 | ActivityKit declarations — `RaceLiveActivityAttributes` struct and `RaceLiveActivityView` widget with Dynamic Island compact/expanded views | `RaceLiveActivity.swift` (new), `NextRaceWidget.swift` (modify bundle), `project.yml` (Info.plist key) | Medium |
| 04-02 | `LiveActivityService` — start/update/end lifecycle wired to `LiveTab` `onAppear`/`onChange`/session-end | `LiveActivityService.swift` (new), `LiveTab.swift` (modify), `LiveTimingViewModel.swift` (modify) | Medium |
| 04-03 | Favorite driver setting — `@AppStorage("favoriteDriver")` picker in `NotificationSettingsView`, read in `LiveActivityService` | `NotificationSettingsView.swift` (modify), `LiveActivityService.swift` (modify) | Low |
| 04-04 | Commentary model + WebSocket handling — `CommentaryEntry` model, `LiveTimingData.commentary` case, service handling, ViewModel array | `LiveTiming.swift` (modify), `LiveTimingService.swift` (modify), `LiveTimingViewModel.swift` (modify) | Low |
| 04-05 | iOS Commentary UI — `CommentaryFeedView`, segmented picker in `LiveTab`, badge dot | `CommentaryFeedView.swift` (new), `LiveTab.swift` (modify) | Medium |
| 04-06 | Backend commentary — event detection, Gemini generation, 30s cooldown, broadcast | `routes.py` (modify) | Medium |
| 04-07 | Web live page — `/live` route, `useLiveTiming` hook, `LiveTimingTower`, `CommentaryPanel`, nav link | `live/page.tsx` (new), `useLiveTiming.ts` (new), `LiveTimingTower.tsx` (new), `CommentaryPanel.tsx` (new), `NavShell.tsx` (modify) | Medium |

**Dependencies:** 04-01 must precede 04-02. 04-04 must precede 04-05. 04-06 can run parallel to 04-01 through 04-05. 04-03 can run parallel to 04-04 and 04-05. 04-07 depends on 04-06.

---

## Key Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| ActivityKit target membership causes build failures | HIGH | Follow pitfall #1 exactly — check both targets in File Inspector for `RaceLiveActivity.swift` |
| Missing `NSSupportsLiveActivities` in generated Info.plist | HIGH | Add to `project.yml` under `F1AI.settings.base`, then re-run XcodeGen |
| `@main` conflict when adding Live Activity to widget bundle | HIGH | Add to existing `F1AIWidgets` bundle body, never create new `@main` |
| LLM latency blocking WebSocket position updates | MEDIUM | Always `asyncio.to_thread`; already the project pattern |
| OpenF1 lap number not available in position data | MEDIUM | Fall back to showing lap from `SessionStatus` if available; show "—" if not |
| Commentary never fires because events aren't detected correctly | MEDIUM | Start with position-change detection only (simplest); add safety car + pit stop after verifying |
| Web live page WebSocket disconnects on Next.js hot reload in dev | LOW | Expected behavior in dev; fine in production |
| Dynamic Island shows stale data when app backgrounds | LOW | Acceptable for Phase 4; add `staleDate` to `ActivityContent` for system visual feedback |

---

## Sources

### Primary (HIGH confidence)
- Codebase exploration — all files read directly and quoted above
- Apple ActivityKit documentation (via sparrowcode.io, logrocket.com, createwithswift.com) — ActivityAttributes protocol, start/update/end APIs, Dynamic Island view structure

### Secondary (MEDIUM confidence)
- [Sparrow Code Live Activities Tutorial](https://sparrowcode.io/en/tutorials/live-activities) — ActivityAttributes struct pattern, push vs app-driven
- [LogRocket iOS Live Activities](https://blog.logrocket.com/exploring-ios-live-activities-api/) — complete code examples verified against Apple docs
- [Create with Swift — Implementing Live Activities](https://www.createwithswift.com/implementing-live-activities-in-a-swiftui-app/) — target setup and file membership requirements
- [OneSignal Live Activities Setup](https://documentation.onesignal.com/docs/en/live-activities-developer-setup) — `NSSupportsLiveActivities` and `NSSupportsLiveActivitiesFrequentUpdates` Info.plist keys confirmed
- [Christian Selig — Server-Side Live Activities](https://christianselig.com/2024/09/server-side-live-activities/) — push token infrastructure; confirms app-driven is simpler for foreground use

### Tertiary (LOW confidence)
- ActivityKit update budget for backgrounded apps — not officially documented; community reports suggest throttling; needs validation during implementation
- OpenF1 lap number availability in position endpoint — not confirmed; needs runtime verification

---

## Metadata

**Confidence breakdown:**
- Codebase findings: HIGH — all files read directly
- Standard stack: HIGH — no new dependencies needed, all patterns verified in existing code
- ActivityKit approach: MEDIUM — APIs confirmed from multiple sources; target membership pitfalls are documented community knowledge
- Commentary architecture: HIGH — follows existing backend patterns exactly
- Web integration: HIGH — follows existing Next.js patterns (SWR, hooks, Tailwind)
- Pitfalls: MEDIUM-HIGH — mix of verified (target membership, `@main` conflict) and speculative (OpenF1 lap data)

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (stable; ActivityKit API has been stable since iOS 16.2)
