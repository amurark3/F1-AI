---
phase: 5
slug: push-infrastructure
status: draft
shadcn_initialized: false
preset: not applicable
created: 2026-04-30
---

# Phase 5 — UI Design Contract

> Visual and interaction contract for Phase 5 (Push Infrastructure). The UI scope is iOS-only: extending the existing Phase 3 `NotificationSettingsView` sheet with five push event toggles (overtakes, safety car, red flags, penalties, fastest lap). No web frontend UI in this phase.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (native SwiftUI — shadcn N/A for iOS) |
| Preset | not applicable |
| Component library | SwiftUI `Form` + `Section` + `Toggle` (iOS system styling) |
| Icon library | SF Symbols (system) |
| Font | iOS system font (San Francisco) — accessed via SwiftUI `.system(...)` and semantic text styles |

**Pre-existing surface:** `ios/F1AI/Views/Settings/NotificationSettingsView.swift` (Phase 3) — already presented as a `.sheet` with `.presentationDetents([.medium, .large])` from `CalendarTab` toolbar. Phase 5 extends this same view; do NOT create a new sheet.

---

## Spacing Scale

Declared values (must be multiples of 4). iOS `Form`/`Section` provides system-default insets — only declare custom spacing for non-Form content.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Inline icon-to-text gaps inside Toggle labels |
| sm | 8px | Compact stack spacing inside Section footers |
| md | 16px | Default vertical spacing between non-Form elements |
| lg | 24px | Section padding (handled by Form automatically) |
| xl | 32px | Major layout gaps (not used in this phase) |

**Exceptions:**
- iOS `Form` rows enforce a 44pt minimum tap target by default — the standard `Toggle` rows already meet this; do NOT manually shrink row heights.
- Section header/footer typography spacing is system-managed; do NOT override.

---

## Typography

iOS-native semantic text styles where available; explicit pixel values only when matching existing in-file patterns.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Section header | 13px (`.subheadline`-like) | semibold (600) | system default (~1.3) |
| Toggle row label (body) | 17px (`.body`) | regular (400) | system default (~1.4) |
| Section footer / hint | 13px (`.footnote`) | regular (400) | system default (~1.4) |
| Navigation title (inline) | 17px | semibold (600) | system default (~1.2) |

**Constraints:**
- Use SwiftUI semantic styles (`.body`, `.footnote`, `.subheadline`) — do NOT introduce custom `.font(.system(size: N))` for new toggle rows; they must match existing Phase 3 session toggle rows for visual parity.
- Maximum 4 type roles in this view. No display/heading sizes — this is a settings sheet, not a marketing surface.
- Two weights total: regular (400) for body/footer, semibold (600) for headers and nav title.

---

## Color

iOS system semantic colors (auto-adapt to Light/Dark Mode). The app's brand accent is **F1 red** (`.red`), reserved for primary CTAs and active-state highlights only.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `Color(.systemBackground)` | Sheet background, Form background |
| Secondary (30%) | `Color(.secondarySystemGroupedBackground)` | Form Section row backgrounds (system default) |
| Accent (10%) | `.red` (F1 red, system) | Toggle "on" tint, Retry button tint, permission warning highlight |
| Destructive | `.red` (system) | DNF indicators and destructive confirmations elsewhere — NOT used in this view |

**Accent reserved for:**
- `Toggle` "on" tint when an event-type toggle is enabled (matches existing session toggles via system default `.tint(.red)` inheritance from `F1AIApp.swift` line 50)
- The `bell.slash` permission-denied warning Label (footnote, used as inline alert in existing Phase 3 sheet)
- NOT for section headers, NOT for footer text, NOT for chevrons or row dividers

**Dark mode:** All colors above auto-invert via SwiftUI semantic color tokens. No manual dark-mode overrides required.

---

## Copywriting Contract

Settings UI has no primary CTA in the form-button sense — the toggles ARE the primary interaction. "CTA" below refers to the most prominent affordance the user takes in this view.

| Element | Copy |
|---------|------|
| Section header | `Live Race Alerts` |
| Section footer (purpose) | `Push notifications during live sessions. Toggle individual event types on or off.` |
| Toggle label — Overtakes | `Overtakes (top 10)` |
| Toggle label — Safety Car | `Safety Car` |
| Toggle label — Red Flags | `Red Flags` |
| Toggle label — Penalties | `Penalties` |
| Toggle label — Fastest Lap | `Fastest Lap` |
| Primary CTA (implicit) | The five toggles themselves — no submit button (UserDefaults persists on toggle change, identical to Phase 3 session toggle pattern) |
| Empty state | Not applicable — toggles are always present with sensible defaults (all five enabled by default on first launch) |
| Error state — push permission denied | Reuse existing pattern: `Label("Notifications are disabled in Settings. Enable them to receive session alerts.", systemImage: "bell.slash")` (already in Phase 3 sheet — do not duplicate; the existing one applies to push events too) |
| Error state — registration failure (silent) | No UI — registration failures log to backend only. Toggles persist locally regardless; backend reconciles on next foreground re-registration |
| Destructive confirmation | None — toggling off is fully reversible and does not delete data; no confirmation dialog needed |

**Tone rules:**
- Use sentence-style label casing (`Safety Car`, not `SAFETY CAR`).
- Be specific, not generic: `Overtakes (top 10)` clarifies scope; `Red Flags` is unambiguous in F1 context.
- No emoji in any copy (consistent with project logging-style rule and existing Phase 3 strings).

---

## Component Inventory

Components used in this phase. All native SwiftUI — zero new dependencies.

| Component | Source | Reuse vs New |
|-----------|--------|--------------|
| `Form` | SwiftUI | Reuse — already in `NotificationSettingsView` |
| `Section` (with header + footer) | SwiftUI | Reuse — append one new Section for "Live Race Alerts" |
| `Toggle` | SwiftUI | Reuse — same pattern as Phase 3 session toggles (Binding on Set<String>) |
| `Label` (for permission warning) | SwiftUI | Reuse — already in Phase 3 sheet |
| SF Symbols `bell.slash` | System | Reuse — already in Phase 3 permission warning |

**No new files** are created for the UI surface in this phase. The new toggles append a single `Section` to the existing `NotificationSettingsView.swift`. State persistence follows the existing UserDefaults extension pattern (`extension UserDefaults` with computed property), adding one new key: `pushEnabledEventTypes` (Set<String> of event keys).

---

## Interaction Contract

**Toggle behavior (per event type):**
1. User taps toggle — state flips immediately.
2. New state writes to UserDefaults synchronously (matches Phase 3 inline-Binding-set pattern).
3. iOS `LiveActivityService` / push registration layer reads UserDefaults on next foreground activation and POSTs preferences to `/api/push/register` alongside the device token.
4. Backend filters which event types to send per device based on stored preferences (no immediate API call from the toggle change itself — preferences are pushed at registration, not on every toggle).

**Default state (first launch, no UserDefaults entry):**
- All five toggles ON. Rationale: opt-out model matches Phase 3 session-type toggles default (all sessions enabled).

**Permission gating:**
- If iOS push permission is `.denied`, the existing `bell.slash` Section already in `NotificationSettingsView` covers this; no new permission UI needed for Phase 5.
- If permission is `.notDetermined`, the toggles still render and persist values — permission request is triggered separately by `CalendarTab.task` on app open (existing Phase 3 behavior).

**Accessibility:**
- Each `Toggle` inherits the SwiftUI default accessibility label from its title — no custom `accessibilityLabel` overrides needed.
- The Section footer text becomes the contextual hint via the standard `Form` semantics; VoiceOver reads it after the section header.
- Minimum tap target 44pt: enforced by SwiftUI `Form` row defaults.

---

## Layout Diagram (Wireframe)

```
┌─ NotificationSettingsView (sheet, .medium / .large) ─────────────┐
│  Notifications                                                    │
│                                                                   │
│  ▼ LIVE RACE TRACKING        (Phase 4 — existing)                 │
│    [ Driver abbreviation field         ]                          │
│    Dynamic Island tracks this driver during live sessions...      │
│                                                                   │
│  ▼ ADVANCE NOTICE            (Phase 3 — existing)                 │
│    ◉  5 minutes before                                            │
│    ◉  15 minutes before                                           │
│    ◉  30 minutes before                                           │
│                                                                   │
│  ▼ SESSION TYPES             (Phase 3 — existing)                 │
│    FP1 (Practice 1)                              [ ◉  ON ]        │
│    FP2 (Practice 2)                              [ ◉  ON ]        │
│    ...                                                            │
│                                                                   │
│  ▼ LIVE RACE ALERTS          (Phase 5 — NEW)  ◀───── this phase   │
│    Overtakes (top 10)                            [ ◉  ON ]        │
│    Safety Car                                    [ ◉  ON ]        │
│    Red Flags                                     [ ◉  ON ]        │
│    Penalties                                     [ ◉  ON ]        │
│    Fastest Lap                                   [ ◉  ON ]        │
│    Push notifications during live sessions...                     │
│                                                                   │
│  (permission denied warning, if applicable — existing)            │
└───────────────────────────────────────────────────────────────────┘
```

The new Phase 5 section is appended **below** the existing Session Types section, **above** the permission-denied warning. This places dynamic live-event preferences after pre-scheduled session preferences in a natural reading order (scheduled → live).

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none (iOS phase) | not applicable |
| Third-party registries | none | not applicable |

Phase 5 introduces zero new component dependencies. All UI is native SwiftUI extending an existing in-repo file. No registry vetting gate required.

---

## Out of Scope (UI)

Confirmed out of scope for this phase per CONTEXT.md and roadmap:

- Web frontend UI: Phase 5 has no web UI. The web app receives no notification preference UI in this phase. The backend `POST /api/push/register` endpoint is iOS-only.
- New screens: No new SwiftUI views are introduced. Phase 5 modifies one existing file.
- Notification banner styling: Push notification appearance (title, body, sound, badge) is governed by iOS system defaults and the APNs payload — not a SwiftUI design contract.
- Deep-link landing UI: Tapping a push notification deep-links to the existing `LiveTab` — no new landing view is built.

---

## Pre-Population Sources

| Field | Source |
|-------|--------|
| iOS-only scope | CONTEXT.md `<specifics>` + orchestrator brief |
| Toggle event types (5) | CONTEXT.md `<decisions>` Per-type opt-out |
| Reuse existing settings sheet | CONTEXT.md `<specifics>` ("extend that sheet rather than create a new one") |
| Storage pattern (UserDefaults) | CONTEXT.md `<decisions>` Token management + Phase 3 pattern in `NotificationService.swift` |
| Color `.red` accent | Existing app `tint(.red)` in `F1AIApp.swift:50` |
| Form / Section / Toggle pattern | Existing `NotificationSettingsView.swift` Phase 3 implementation |
| Default-all-on opt-out model | Existing Phase 3 `enabledNotificationSessions` UserDefaults default behavior |
| Permission warning copy | Existing Phase 3 `bell.slash` Label (line 77 of NotificationSettingsView.swift) |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
