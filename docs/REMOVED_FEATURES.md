# Removed Features

Features that used to exist in this codebase and have since been taken out. If you
find one of these described in `.planning/`, an old README or a commit message, it
is **not** a current feature. Don't go looking for it in the code.

## Live AI race commentary (removed 2026-09-29)

**What it was.** During a live session, the backend compared successive timing
snapshots and picked the most newsworthy change: a safety car or red flag, a
position change, or a pit stop. It then asked the LLM to narrate that change in
two or three sentences, with a 30-second cooldown and a template fallback. Each
entry went out over the live-timing WebSocket as a `{"type": "commentary"}`
message. The web live page (itself removed on 2026-09-30, see below) showed entries in a "Strategy Commentary" panel, and
the iOS Live tab showed them on a separate "Commentary" segment.

**What was removed.**

| Area    | Removed                                                                                                                                                                                |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend | `backend/app/services/live_commentary.py` (event detection, LLM narration, per-room cooldown), its call from `_run_live_loop` in `backend/app/api/routes.py`, and `backend/tests/test_live_commentary.py` |
| Web     | `frontend/app/components/CommentaryPanel.tsx`, the `commentary` message and state in `frontend/app/hooks/useLiveTiming.ts`, the commentary column in `LiveView.tsx`, and the commentary starter prompt in the AI Engineer chat |
| iOS     | `ios/F1AI/Views/Live/CommentaryFeedView.swift`, the `CommentaryEntry` model, `commentaryEntries` on `LiveTimingService` and `LiveTimingViewModel`, and the Timing/Commentary picker in `LiveTab.swift` |

**What still works.** The live-timing WebSocket (`/api/live/{year}/{round_num}`)
still streams `session_status` and `positions`. The timing tower on web and iOS
and the Dynamic Island Live Activity are unaffected. The socket simply never
sends a `commentary` message any more.

**Planning docs that still describe it.** Phase 4 in `.planning/` built this
feature: requirements LIVE-03, LIVE-04 and LIVE-05, delivered by plans 04-04,
04-05 and 04-06. Those docs are kept as history. Each one that mentions
commentary carries a banner pointing here, and `ROADMAP.md`, `REQUIREMENTS.md`,
`PROJECT.md` and `STATE.md` mark the affected items as removed.

**Phase 5 push notifications depend on it.** Phase 5 hasn't started, but it was
planned on top of the commentary engine. `05-CONTEXT.md` decides that push
notification bodies reuse the commentary text, and `05-03-PLAN.md` hooks push
dispatch into the commentary event detection. Neither exists now, so event
detection and notification text for PUSH-02 need re-planning before Phase 5 is
executed.

**Finding the old code.** Commit `2ea4835` is the last one that contains the
feature:

```bash
git show 2ea4835:backend/app/services/live_commentary.py
git show 2ea4835:frontend/app/components/CommentaryPanel.tsx
git show 2ea4835:ios/F1AI/Views/Live/CommentaryFeedView.swift
```

## Standalone Live Timing page (removed 2026-09-30)

**What it was.** A web page at `/race-control/live` (also reached from `/live`)
with a "Live Timing" entry in the Race Control sidebar and a tile on the landing
page. While a session ran it showed the timing tower. The rest of the time,
which is almost all of it, it showed a weekend countdown, a "Control Room Idle"
notice and a link to the AI Engineer. The landing tile promised "sector deltas",
which never existed.

**What was removed.**

| Area | Removed                                                                                                                                             |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web  | `frontend/app/race-control/live/` (`page.tsx`, `LiveView.tsx`, `WeekendCountdown.tsx`), `frontend/app/live/page.tsx`, the sidebar entry and the landing tile |

**Where live timing is now.** The Command Center (`/race-control`) renders
`LiveTimingPanel`, which shows the same timing tower only while the socket
reports a `live` session and renders nothing otherwise. The header LIVE pill
links there, and so does the "Live Control" workstream. `/live` and
`/race-control/live` redirect to `/race-control` through `frontend/next.config.ts`.

**What still works.** Everything outside that web page: the live-timing
WebSocket, `LiveTimingTower`, `useLiveTiming`, the iOS Live tab and the Dynamic
Island Live Activity.

**Finding the old code.** Commit `abb924c` is the last one that contains the page:

```bash
git show abb924c:frontend/app/race-control/live/LiveView.tsx
git show abb924c:frontend/app/race-control/live/WeekendCountdown.tsx
```
