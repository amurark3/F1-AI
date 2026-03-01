# Phase 3: Client Feature Surface - Research

**Researched:** 2026-02-28
**Domain:** iOS SwiftUI client features, Next.js web client, UNUserNotifications, championship math
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Predictions layout:**
- Driver cards layout, not list or bars
- Each card shows: driver name, team, win probability, confidence range (±X%), and 2-3 key factors driving the prediction
- Key factors are in an expandable section — tap card to expand and see factors with brief explanations (not always visible)
- Empty state when no upcoming race: friendly message with countdown/date to when predictions will be available for the next round (do not hide the view)

**Championship scenario UX:**
- What-if by remaining rounds — "if Driver X wins the next N races, can they beat Driver Y?"
- Interaction style: Claude's Discretion (pick based on how many contenders there typically are — stepper, slider, or preset buttons)
- Show only drivers still mathematically in contention (dynamic cutoff — could be 2 or 15 depending on season stage)
- Tabs for WDC and WCC (both drivers' and constructors' championship)

**Error states & retry:**
- Refresh failures (background/subsequent loads): Toast/snackbar — auto-dismisses after ~4s but user can tap during that window to retry before it disappears
- First load failure (empty view): Inline empty state with error illustration, "Something went wrong" message, and a prominent Retry button — not a toast
- iOS: use native SwiftUI feel for error presentation
- Web: use web conventions for toast/snackbar (independent of iOS style)

**Notification targeting:**
- All session types fire notifications by default: FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, Race
- Per session type toggles in settings — user can turn off individual session types
- Advance time is user-configurable: options of 5, 15, or 30 minutes before session start
- Notification text: short and direct — e.g., "Monaco Grand Prix starts in 15 minutes" (no emoji, no round number prefix)

### Claude's Discretion
- Championship interaction pattern (stepper vs slider vs preset buttons) — pick based on typical contender count and complexity tradeoff
- Loading skeleton design and exact timing
- Exact spacing, typography, team color implementation on prediction cards
- Toast animation style and exact positioning

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLIENT-01 | iOS PredictionsView displays race outcome probabilities with driver positions, confidence ranges, and key factors | Backend `/api/predictions/{year}/{round_num}` is fully built (Phase 2). Response shape documented below. iOS patterns for card layout, expandable rows, and @Observable ViewModels are all established in codebase. |
| CLIENT-02 | iOS championship scenario view shows "Driver X needs Y points to clinch the title" with interactive what-if scenarios | Points systems and mathematical elimination logic documented. Standings data comes from existing `/api/standings/drivers/{year}` and `/api/standings/constructors/{year}` — no new backend endpoint needed. |
| CLIENT-03 | iOS push notifications fire for all session types — FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race — not just race start | Existing NotificationService only handles "Race" session. Session names from the backend schedule dict are documented. UNUserNotifications API is already imported and working. Extension is straightforward. |
| CLIENT-04 | iOS and web views show proper empty states, error banners, and retry flows instead of blank screens on failure | iOS pattern is ContentUnavailableView (used in CalendarTab, StandingsTab). Web pattern is conditional SWR error rendering. Toast pattern not yet implemented on either platform — design documented. |
| CLIENT-05 | Web prediction panel displays race outcome analysis matching the iOS predictions view | Web uses SWR + framer-motion + Tailwind. Same API endpoint as iOS. New `/predictions` route and component needed following existing page/component patterns. |

</phase_requirements>

---

## Summary

Phase 3 is a pure client-side delivery phase. The backend prediction engine (`/api/predictions/{year}/{round_num}`) and standings endpoints are fully operational from Phase 2. This phase adds four distinct features across iOS and web: a predictions view, a championship scenario view, expanded notifications, and hardened error states.

The iOS codebase uses a consistent, well-understood pattern: `@Observable` ViewModels, SwiftUI views backed by `APIClient.shared`, SwiftData caching via `CacheService`, and `ContentUnavailableView` for first-load errors. All new iOS views follow this exact pattern — no new infrastructure needed. The app currently has 5 tabs (Pit Wall, Live, Calendar, H2H, Standings). Adding a Predictions tab is straightforward. The championship scenario view fits naturally either as a new tab or as a section within StandingsTab.

The web frontend uses Next.js with SWR for data fetching and framer-motion for animations. There is no Predictions page yet — it needs a new route (`/predictions`) following the established pattern of `page.tsx` + `NavShell` wrapper + dedicated component. The notification system needs significant expansion: the current `NotificationService` only schedules Race start notifications at hardcoded 30m and 5m offsets. Phase 3 expands it to all 7 session types with user-configurable advance times (5, 15, 30 min) and per-session-type toggles.

**Primary recommendation:** Build in this order — (1) iOS PredictionsView and ViewModel, (2) iOS notification expansion + settings UI, (3) championship scenario view, (4) error state hardening across iOS, (5) web predictions panel. This order delivers CLIENT-01 and CLIENT-03 early, and CLIENT-04 last since it cross-cuts all existing and new views.

---

## Standard Stack

### Core (all already in the project)

| Library/Framework | Version | Purpose | Notes |
|---|---|---|---|
| SwiftUI | iOS 17+ | iOS UI | All views, @Observable, ContentUnavailableView |
| UserNotifications | iOS 17+ | Local notifications | Already imported in NotificationService |
| SwiftData | iOS 17+ | Persistence layer | CachedResponse model already live |
| @Observable | iOS 17+ | ViewModel observation | All ViewModels use this macro |
| Next.js | 16.1.6 | Web routing/rendering | Existing pages follow page.tsx pattern |
| SWR | 2.3.8 | Web data fetching | Used in Standings and Calendar components |
| framer-motion | 12.34.0 | Web animations | Used throughout (staggered list entries, hover effects) |
| Tailwind CSS | 4 | Web styling | Utility classes, glass/dark theme already defined |
| lucide-react | 0.561.0 | Web icons | Used in NavShell |

### No New Dependencies Needed

All required functionality is achievable with the existing stack. Specifically:
- Expandable card accordion: SwiftUI `withAnimation` + `@State var isExpanded: Bool` on each card
- Toast/snackbar on iOS: Custom SwiftUI overlay with `withAnimation(.easeInOut)` and `Task { try await Task.sleep(nanoseconds: 4_000_000_000) }` for auto-dismiss
- Toast on web: Custom React component with `useState` + `useEffect` for auto-dismiss, positioned with Tailwind `fixed bottom-4`
- Championship math: Pure computed logic from the standings data already fetched

---

## Architecture Patterns

### Existing iOS ViewModel Pattern (MUST follow)

Every new ViewModel must use this exact pattern established in the codebase:

```swift
// Source: ios/F1AI/ViewModels/StandingsViewModel.swift
@Observable
final class PredictionsViewModel {
    var predictions: PredictionsResponse?
    var isLoading = false
    var error: String?

    private let api = APIClient.shared

    func loadPredictions(year: Int, round: Int) async {
        isLoading = true
        error = nil
        do {
            predictions = try await api.fetchPredictions(year: year, round: round)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func retry(year: Int, round: Int) {
        Task { await loadPredictions(year: year, round: round) }
    }
}
```

### Existing iOS APIClient Extension Pattern

New endpoints are added as methods on the existing `APIClient` singleton using `fetchCached`:

```swift
// Source: ios/F1AI/Services/APIClient.swift (pattern established)
func fetchPredictions(year: Int, round: Int) async throws -> PredictionsResponse {
    let url = URL(string: "\(baseURL)/api/predictions/\(year)/\(round)")!
    // Predictions can be cached ~30 min (recomputed when qualifying becomes available)
    return try await fetchCached(url: url, cacheKey: "predictions-\(year)-\(round)", maxAge: 1800)
}
```

### Existing iOS First-Load Error Pattern

```swift
// Source: ios/F1AI/Views/Tabs/StandingsTab.swift (established pattern for first-load errors)
if vm.isLoading {
    ProgressView("Loading predictions...")
        .padding(.top, 60)
} else if let error = vm.error {
    ContentUnavailableView {
        Label("Something went wrong", systemImage: "exclamationmark.triangle")
    } description: {
        Text(error)
    } actions: {
        Button("Retry") { Task { await vm.loadPredictions(year: year, round: round) } }
            .buttonStyle(.borderedProminent)
            .tint(.red)
    }
} else {
    // main content
}
```

### Expandable Card Pattern (iOS — new for this phase)

The prediction card uses `@State var isExpanded = false` per card. This avoids a separate selection state and works naturally with `LazyVStack`:

```swift
// Pattern: expandable card with tap-to-reveal
struct PredictionDriverCard: View {
    let prediction: DriverPrediction
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Always visible: name, position, probability
            HStack { ... }
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        isExpanded.toggle()
                    }
                }

            // Expandable: confidence range + factors
            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Confidence: \(prediction.confidenceLow)–\(prediction.confidenceHigh)%")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                    ForEach(prediction.factors, id: \.self) { factor in
                        Label(factor, systemImage: "chevron.right")
                            .font(.system(size: 11))
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
```

### Toast/Snackbar Pattern (iOS — new for this phase)

Implemented as a ZStack overlay at the root of the view hierarchy. State lives in the ViewModel:

```swift
// Toast state in ViewModel:
var toastMessage: String? = nil
var toastIsRetryable = false

// In View:
ZStack(alignment: .bottom) {
    // Main content
    ScrollView { ... }

    // Toast overlay
    if let message = vm.toastMessage {
        ToastView(message: message, onRetry: vm.toastIsRetryable ? { vm.retry() } : nil)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .padding(.bottom, 16)
            .onAppear {
                Task {
                    try? await Task.sleep(nanoseconds: 4_000_000_000)
                    withAnimation { vm.toastMessage = nil }
                }
            }
    }
}
.animation(.easeInOut, value: vm.toastMessage)
```

### Notification Scheduling Pattern (expanding existing)

Current `NotificationService.scheduleRaceReminders` only handles "Race" session at hardcoded 30/5 min. The new pattern schedules all sessions with user-configured offsets:

```swift
// Expanding NotificationService to handle all session types
// Session keys from backend: "Practice 1", "Practice 2", "Practice 3",
//                             "Sprint Qualifying", "Sprint", "Qualifying", "Race"
// User-facing names for notification body: FP1, FP2, FP3, Sprint Qualifying, Sprint Race, Qualifying, Race

struct NotificationSettings {
    var enabledSessions: Set<String> = ["Practice 1", "Practice 2", "Practice 3",
                                         "Sprint Qualifying", "Sprint", "Qualifying", "Race"]
    var advanceMinutes: Int = 15  // options: 5, 15, 30
}

func scheduleSessionReminders(for race: RaceEvent, settings: NotificationSettings) {
    let center = UNUserNotificationCenter.current()
    let prefix = "race-\(race.round)"

    // Remove all existing for this round
    center.removeAllPendingNotificationRequests() // or targeted by prefix pattern

    for (sessionName, timeStr) in race.sessions {
        guard settings.enabledSessions.contains(sessionName),
              let sessionDate = parseFlexibleDate(timeStr),
              let triggerDate = Calendar.current.date(
                  byAdding: .minute,
                  value: -settings.advanceMinutes,
                  to: sessionDate),
              triggerDate > Date()
        else { continue }

        let content = UNMutableNotificationContent()
        content.title = "F1 AI"
        content.body = "\(race.name) \(friendlySessionName(sessionName)) starts in \(settings.advanceMinutes) minutes"
        content.sound = .default

        let components = Calendar.current.dateComponents(
            [.year, .month, .day, .hour, .minute], from: triggerDate)
        let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
        let id = "\(prefix)-\(sessionName)-\(settings.advanceMinutes)"
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
    }
}

private func friendlySessionName(_ key: String) -> String {
    switch key {
    case "Practice 1": return "FP1"
    case "Practice 2": return "FP2"
    case "Practice 3": return "FP3"
    case "Sprint Qualifying": return "Sprint Qualifying"
    case "Sprint": return "Sprint Race"
    case "Qualifying": return "Qualifying"
    case "Race": return ""  // "Monaco Grand Prix starts in 15 minutes"
    default: return key
    }
}
```

### Championship Math Pattern

F1 WDC maximum points remaining calculation. This is pure computation from the standings data already fetched:

```swift
// Points available per remaining race (including fastest lap)
// Race: 25 points for 1st, 18 for 2nd, etc.
// Sprint: 8 points for 1st
// Fastest lap: 1 point (if in top 10)
// Maximum points per standard race weekend: 26 (25 + fastest lap bonus)
// Maximum points per sprint weekend: 34 (25 + fastest lap + 8 sprint)

func maxPointsRemaining(remainingRaces: [RaceEvent]) -> Int {
    var total = 0
    for race in remainingRaces {
        total += 26  // race + fastest lap
        if race.isSprint == true {
            total += 8  // sprint race win
        }
    }
    return total
}

func isInContention(driver: DriverStanding, leader: DriverStanding, maxPointsRemaining: Int) -> Bool {
    return (leader.points - driver.points) <= Double(maxPointsRemaining)
}

func pointsToOvertake(driver: DriverStanding, target: DriverStanding) -> Double {
    return target.points - driver.points + 1
}
```

**WCC follows identical math but on `ConstructorStanding`.** Maximum points per race weekend for constructors is 2x driver max (both cars score).

### Web Component Pattern (must follow existing)

```typescript
// Source: frontend/app/components/Standings.tsx (established SWR pattern)
"use client";
import useSWR from 'swr';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';

const Predictions = () => {
  const { data, isLoading, error, mutate } = useSWR<PredictionsResponse>(
    `${API_BASE}/api/predictions/${year}/${round}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  // Loading: skeleton (following Standings pattern with animate-pulse)
  // Error: inline error state with Retry button calling mutate()
  // Data: framer-motion staggered driver cards
};
```

### Web Toast Pattern (new for this phase)

```typescript
// Toast component — positioned fixed bottom-right, auto-dismisses
const useToast = () => {
  const [toast, setToast] = useState<{ message: string; onRetry?: () => void } | null>(null);

  const showToast = (message: string, onRetry?: () => void) => {
    setToast({ message, onRetry });
    setTimeout(() => setToast(null), 4000);
  };

  return { toast, showToast };
};

// In JSX:
{toast && (
  <div className="fixed bottom-4 right-4 z-50 glass rounded-2xl px-4 py-3 flex items-center gap-3">
    <span className="text-sm text-white">{toast.message}</span>
    {toast.onRetry && (
      <button onClick={toast.onRetry} className="text-xs font-bold text-red-400 hover:text-red-300">
        Retry
      </button>
    )}
  </div>
)}
```

### Recommended iOS File Structure (new files for Phase 3)

```
ios/F1AI/
├── Models/
│   └── Predictions.swift          # PredictionsResponse, DriverPrediction, AccuracyStats
├── ViewModels/
│   ├── PredictionsViewModel.swift  # @Observable, fetches predictions, handles errors
│   └── ChampionshipViewModel.swift # @Observable, championship math, what-if scenarios
├── Views/
│   ├── Tabs/
│   │   └── PredictionsTab.swift    # New tab (or embed in StandingsTab)
│   ├── Predictions/
│   │   ├── PredictionsView.swift   # Main predictions list with error states
│   │   └── PredictionDriverCard.swift  # Individual expandable card
│   ├── Championship/
│   │   ├── ChampionshipView.swift  # What-if scenario view with WDC/WCC tabs
│   │   └── ChampionshipDriverRow.swift # Per-driver contender row
│   └── Shared/
│       └── ToastView.swift         # Reusable toast overlay component
└── Services/
    └── NotificationService.swift   # Extended (existing file, new methods)
```

### Recommended Web File Structure (new files for Phase 3)

```
frontend/app/
├── predictions/
│   └── page.tsx                    # New route (/predictions)
├── components/
│   ├── PredictionPanel.tsx         # Main predictions component (SWR + cards)
│   ├── PredictionDriverCard.tsx    # Individual driver card with expand
│   └── Toast.tsx                   # Reusable toast component
```

### Where Predictions Tab Lives in iOS

The app currently has 5 tabs (Pit Wall=0, Live=1, Calendar=2, H2H=3, Standings=4). Adding a Predictions tab makes 6 — fine for iOS tab bars (iOS renders up to 5 before "More"). With 6 tabs iOS shows "More" overflow. **Recommendation: embed the Predictions view within StandingsTab** as a segmented picker selection (Driver Standings | Constructor Standings | Predictions), or add it as a floating "Predictions" button on the CalendarTab's race detail. This avoids the 6-tab problem. The championship scenario view fits naturally within StandingsTab alongside driver/constructor standings.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| iOS expandable animation | Custom UIKit animation | SwiftUI `withAnimation(.spring)` + `if isExpanded` | SwiftUI handles layout transitions automatically |
| iOS toast auto-dismiss | Timer/DispatchQueue | `Task { try? await Task.sleep(nanoseconds:) }` | Structured concurrency, cancellation-safe |
| iOS notification scheduling | Manual date arithmetic | `Calendar.current.date(byAdding:)` + `UNCalendarNotificationTrigger` | Already in the codebase, correct for DST |
| Championship math | External library | Inline Swift computed properties | It's simple arithmetic — leader_pts - driver_pts |
| Web data fetching | fetch() + useEffect | SWR `useSWR` (already installed) | Automatic deduplication, revalidation, error state |
| Web loading skeleton | CSS spinner | `animate-pulse` Tailwind utility (already used in Standings) | Consistent with existing UI patterns |
| Web expandable card | React accordion library | `useState` + conditional render + CSS transition | framer-motion's `AnimatePresence` or simple conditional render is sufficient |

---

## Common Pitfalls

### Pitfall 1: Notification Identifier Collisions

**What goes wrong:** When rescheduling notifications (e.g., user changes advance time from 15 to 30 min), old notifications remain scheduled if identifiers don't change.

**Why it happens:** `UNUserNotificationCenter.add()` only replaces if the identifier matches exactly. If the advance time is baked into the identifier, a time change creates duplicates.

**How to avoid:** Include all varying parameters in the identifier: `"\(prefix)-\(sessionName)-\(advanceMinutes)"`. On any settings change, call `center.getPendingNotificationRequests()`, filter by the race prefix pattern, remove matching ones, then re-schedule.

**Warning signs:** User receives double notifications.

### Pitfall 2: iOS 6-Tab Overflow

**What goes wrong:** Adding a 6th tab to `TabView` in `F1AIApp.swift` causes iOS to show a "More" tab, hiding some items.

**Why it happens:** iOS tab bars have a hard limit of 5 before overflow behavior kicks in.

**How to avoid:** Integrate Predictions and Championship within the existing StandingsTab using a segmented picker with 3 options (Drivers | Constructors | Predictions). Championship scenarios live under Standings.

**Warning signs:** Tab bar shows "More" item.

### Pitfall 3: Championship Math Edge Cases

**What goes wrong:** The what-if view shows drivers who are mathematically eliminated as still "in contention."

**Why it happens:** The cutoff formula must use `max remaining points` across the remaining schedule, not a fixed number. Sprint weekends add 8 points, fastest lap adds 1. Missing these inflates the cutoff.

**How to avoid:** Compute `maxPointsRemaining` from the actual schedule data (already available in `RaceEvent.isSprint`). Mark a driver out of contention when `leader.points - driver.points > maxPointsRemaining`.

**Warning signs:** Mathematically eliminated drivers shown as contenders late in season.

### Pitfall 4: Predictions Empty State Logic

**What goes wrong:** The view hides itself or shows nothing when there is no upcoming race (end of season).

**Why it happens:** Developers often `guard` on data and return empty view. The CONTEXT.md decision locks this: "do not hide the view — show friendly message with next round date."

**How to avoid:** Separate "no data from API" from "no upcoming race." When the prediction response has an empty `predictions` array OR the API returns an error indicating no upcoming race, show the empty state with the next season start date.

**Warning signs:** Predictions tab disappears in November–February off-season.

### Pitfall 5: Toast During Background Refresh Overwrites User's Scroll Position

**What goes wrong:** A background refresh failure shows a toast overlay that causes layout reflow or scroll jump.

**Why it happens:** If the toast triggers a parent view re-render that affects layout.

**How to avoid:** Position toast as a `ZStack` overlay with `alignment: .bottom` and `ignoresSafeArea()` so it floats over content without affecting scroll.

### Pitfall 6: Notification Permission Not Requested

**What goes wrong:** Notifications silently fail because the app never requested permission.

**Why it happens:** `NotificationService.requestPermission()` exists but nothing calls it in the app lifecycle.

**How to avoid:** Call `requestPermission()` in `F1AIApp` body or in the CalendarTab's `.task` modifier on first load. Show permission explanation to user before the system prompt.

**Warning signs:** No notifications delivered despite schedule being set.

### Pitfall 7: Web SWR Error vs Empty Data

**What goes wrong:** When the predictions endpoint returns `{"error": "...", "year": ..., "round": ...}` (HTTP 200 with error body), SWR's `error` field is nil but `data` contains the error dict.

**Why it happens:** The backend returns HTTP 200 with a JSON error body on prediction failure. SWR's fetcher only throws on non-2xx.

**How to avoid:** Check `data?.error` in addition to `error` from SWR. The `fetcher` in `fetcher.ts` only throws on non-ok HTTP, so a 200 with error JSON arrives as `data`. Add a null check: `if (data?.error) showToast(data.error, () => mutate())`.

---

## Code Examples

### Prediction API Response Shape (from `backend/app/data/predictions.py`)

The REST endpoint `/api/predictions/{year}/{round_num}` returns:

```json
{
  "year": 2025,
  "round": 5,
  "grand_prix": "Monaco Grand Prix",
  "generated_at": "2025-05-20T14:30:00Z",
  "data_sources": ["qualifying", "constructor_standings", "circuit_history", "last_5_races"],
  "accuracy": {
    "recent_top3_pct": 67,
    "recent_top10_pct": 78,
    "avg_position_error": 2.3,
    "races_evaluated": 4
  },
  "predictions": [
    {
      "position": 1,
      "driver_code": "VER",
      "driver_name": "Max Verstappen",
      "team": "Red Bull Racing",
      "confidence_low": 72,
      "confidence_high": 85,
      "factors": [
        "Pole position (qualifying P1)",
        "Won 3 of last 5 races",
        "Previous winner at this circuit (best P1 in last 3 editions)"
      ]
    }
    // ... 19 more drivers
  ],
  "weather_impact": "dry",
  "wet_scenario": null,
  "warnings": null
}
```

**Key insight for iOS model:** The "win probability" field the CONTEXT.md describes is derived from `position` + `confidence_low/confidence_high`. Position 1 driver with 72–85% confidence range maps to the card showing "72–85% confidence" as the probability expression. There is no separate "win_probability_pct" field — the card reads confidence range as the probability signal.

### iOS Swift Model for Predictions

```swift
// Source: ios/F1AI/Models/ (new file: Predictions.swift)
struct PredictionsResponse: Codable {
    let year: Int
    let round: Int
    let grandPrix: String
    let generatedAt: String
    let dataSources: [String]
    let accuracy: AccuracyStats?
    let predictions: [DriverPrediction]
    let weatherImpact: String?
    let warnings: [String]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case year, round, predictions, accuracy, warnings, error
        case grandPrix = "grand_prix"
        case generatedAt = "generated_at"
        case dataSources = "data_sources"
        case weatherImpact = "weather_impact"
    }
}

struct DriverPrediction: Codable, Identifiable {
    let position: Int
    let driverCode: String
    let driverName: String
    let team: String
    let confidenceLow: Int
    let confidenceHigh: Int
    let factors: [String]

    var id: String { driverCode }

    // Derived display value: "72–85%"
    var confidenceRange: String { "\(confidenceLow)–\(confidenceHigh)%" }

    enum CodingKeys: String, CodingKey {
        case position, team, factors
        case driverCode = "driver_code"
        case driverName = "driver_name"
        case confidenceLow = "confidence_low"
        case confidenceHigh = "confidence_high"
    }
}

struct AccuracyStats: Codable {
    let recentTop3Pct: Int?
    let recentTop10Pct: Int?
    let avgPositionError: Double?
    let racesEvaluated: Int

    enum CodingKeys: String, CodingKey {
        case racesEvaluated = "races_evaluated"
        case recentTop3Pct = "recent_top3_pct"
        case recentTop10Pct = "recent_top10_pct"
        case avgPositionError = "avg_position_error"
    }
}
```

### Championship Contention Calculation

```swift
// In ChampionshipViewModel
// Source: F1 2025 points system
let racePoints = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]

var remainingRaces: [RaceEvent] {
    schedule.filter { $0.raceStatus == .upcoming }
}

var maxPointsRemaining: Int {
    remainingRaces.reduce(0) { total, race in
        let raceMax = 26  // 25 + 1 fastest lap
        let sprintMax = race.isSprint == true ? 8 : 0
        return total + raceMax + sprintMax
    }
}

var contenders: [DriverStanding] {
    guard let leader = drivers.first else { return [] }
    return drivers.filter { driver in
        (leader.points - driver.points) <= Double(maxPointsRemaining)
    }
}
```

### Notification Settings Persistence

```swift
// Store in UserDefaults (following AdManager pattern in codebase)
// Key: "notificationEnabledSessions" -> [String] (session name list)
// Key: "notificationAdvanceMinutes" -> Int (5, 15, or 30)

extension UserDefaults {
    var enabledNotificationSessions: Set<String> {
        get {
            let arr = array(forKey: "notificationEnabledSessions") as? [String]
            return Set(arr ?? ["Practice 1", "Practice 2", "Practice 3",
                               "Sprint Qualifying", "Sprint", "Qualifying", "Race"])
        }
        set { set(Array(newValue), forKey: "notificationEnabledSessions") }
    }

    var notificationAdvanceMinutes: Int {
        get {
            let stored = integer(forKey: "notificationAdvanceMinutes")
            return stored > 0 ? stored : 15  // default 15 min
        }
        set { set(newValue, forKey: "notificationAdvanceMinutes") }
    }
}
```

### Settings View for Notifications (iOS)

A `SettingsView` shown as a `.sheet` or embedded in a new Settings tab. Given the app already has 5 tabs and we're not adding a 6th, expose settings via a `ToolbarItem` button (gear icon) from the CalendarTab, which opens a sheet:

```swift
// Add to CalendarTab toolbar:
ToolbarItem(placement: .topBarLeading) {
    Button {
        showingSettings = true
    } label: {
        Image(systemName: "gear")
    }
    .sheet(isPresented: $showingSettings) {
        NotificationSettingsView()
    }
}

// NotificationSettingsView:
struct NotificationSettingsView: View {
    @AppStorage("notificationAdvanceMinutes") private var advanceMinutes = 15

    var body: some View {
        NavigationStack {
            Form {
                Section("Advance Notice") {
                    Picker("Notify me", selection: $advanceMinutes) {
                        Text("5 minutes before").tag(5)
                        Text("15 minutes before").tag(15)
                        Text("30 minutes before").tag(30)
                    }
                    .pickerStyle(.inline)
                }

                Section("Session Types") {
                    // Toggle per session type
                    ForEach(["Practice 1", "Practice 2", "Practice 3",
                              "Qualifying", "Sprint Qualifying", "Sprint", "Race"], id: \.self) { session in
                        SessionNotificationToggle(session: session)
                    }
                }
            }
            .navigationTitle("Notifications")
        }
    }
}
```

**Use `@AppStorage` instead of manual `UserDefaults`** — it's the SwiftUI-native wrapper and automatically publishes changes to the view. For the session toggles, use `@AppStorage` with a JSON-encoded set or individual boolean keys per session.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|---|---|---|
| `@ObservableObject` + `@Published` | `@Observable` macro (iOS 17+) | No `@StateObject`/`@ObservedObject` boilerplate; all ViewModels in this codebase already use @Observable |
| Manual timer for notifications | `UNCalendarNotificationTrigger` | DST-safe; fires correctly across timezone changes |
| Custom error banner UIKit | `ContentUnavailableView` (iOS 17+) | Native look, system-consistent; already used in CalendarTab and StandingsTab |
| `@State` + manual binding for settings | `@AppStorage` | Automatically backed by UserDefaults, no manual sync |
| SWR `mutate()` for manual refresh | `SWR` v2 `revalidateOnMount` + `mutate` | Already established in codebase; `mutate()` is the retry mechanism |

---

## Open Questions

1. **Where does Predictions live in the tab bar?**
   - What we know: Adding a 6th tab causes iOS "More" overflow. CONTEXT.md locks the UX for the views but not which tab they live in.
   - What's unclear: Whether the user wants Predictions as a standalone tab (accepting 6-tab overflow) or embedded within Standings.
   - Recommendation: Embed within StandingsTab as a third segment in the segmented picker (Drivers | Constructors | Predictions). Championship scenarios also live there. This keeps the tab bar clean.

2. **Championship view: stepper vs preset buttons (Claude's Discretion)**
   - What we know: Contender count varies from 2 (late season) to 15+ (early season). CONTEXT.md leaves this to Claude.
   - Recommendation: Use **preset buttons** for the what-if scenario: "Next 3 races", "Next 5 races", "Remaining season" — these are the meaningful F1 milestones fans actually think about. Avoids stepper awkwardness for large numbers and slider imprecision. Supplement with a Stepper for fine-grained control (±1 race). This handles both edge cases naturally.

3. **Notification permission request timing**
   - What we know: `requestPermission()` exists but has no call site.
   - Recommendation: Request permission on first launch in the CalendarTab `.task` modifier (since that's the primary notification-relevant view). Show a pre-permission explanation inline before the system dialog.

---

## Sources

### Primary (HIGH confidence)

- Codebase: `ios/F1AI/Services/NotificationService.swift` — current notification implementation, session key names, identifier patterns
- Codebase: `ios/F1AI/Models/Race.swift` — `RaceEvent.sessions: [String: String]` dict with session keys ("Practice 1", "Qualifying", "Sprint", etc.)
- Codebase: `ios/F1AI/Services/APIClient.swift` — `fetchCached()` pattern for all new API methods
- Codebase: `ios/F1AI/ViewModels/StandingsViewModel.swift` — `@Observable` ViewModel pattern with `isLoading`, `error`, `retry()` shape
- Codebase: `ios/F1AI/Views/Tabs/StandingsTab.swift` — `ContentUnavailableView` first-load error pattern
- Codebase: `ios/F1AI/Views/Tabs/CalendarTab.swift` — `.task`, `.refreshable`, error handling patterns
- Codebase: `ios/F1AI/Views/Shared/TeamColor.swift` — team color map used for prediction card accent colors
- Codebase: `ios/F1AI/F1AIApp.swift` — current 5-tab structure; confirms 6-tab limit constraint
- Codebase: `backend/app/data/predictions.py` — exact JSON response shape for predictions endpoint
- Codebase: `backend/app/api/routes.py` — `/api/predictions/{year}/{round_num}` endpoint confirmed at line 1021
- Codebase: `frontend/app/components/Standings.tsx` — SWR pattern, team colors, framer-motion animation style
- Codebase: `frontend/app/utils/fetcher.ts` — `fetcher` and `fetcherWithTimeout` wrappers
- Codebase: `frontend/app/components/NavShell.tsx` — nav items, page structure for adding /predictions route
- Codebase: `.planning/phases/02-backend-data-features/02-VERIFICATION.md` — confirms all Phase 2 backend is done and verified
- Codebase: `.planning/REQUIREMENTS.md` — CLIENT-01 through CLIENT-05 definitions

### Secondary (MEDIUM confidence)

- F1 2025 points system: 25-18-15-12-10-8-6-4-2-1 for race; 8-7-6-5-4-3-2-1 for sprint; +1 fastest lap if in top 10. (Standard knowledge, confirmed by F1.com structure, no API needed.)
- WCC max points: Both cars score, so constructors can earn 2x driver points per race weekend. Standard F1 rules.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all verified from codebase files; no new dependencies
- iOS patterns: HIGH — all patterns taken directly from existing ViewModels and Views
- API contract: HIGH — backend verified and documented in Phase 2 verification report
- Championship math: HIGH — straightforward arithmetic from publicly known F1 points system
- Notification expansion: HIGH — existing `NotificationService` confirms all foundations; extension is additive
- Web patterns: HIGH — Standings and Calendar components are the direct templates to follow

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable stack; APIs don't change between phases)
