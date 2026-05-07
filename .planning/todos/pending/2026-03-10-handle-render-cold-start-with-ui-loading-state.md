---
created: 2026-03-10T00:18:33.684Z
title: Handle Render cold start with UI loading state
area: ui
files:
  - ios/F1AI/Views/Tabs/LiveTab.swift
  - web/src/
---

## Problem

Render free tier spins down after inactivity (~15 min). First request after sleep triggers a cold start that can take 20-60 seconds before the server responds. Currently the UI has no awareness of this — requests just hang or fail silently, leaving users confused.

Additionally, ChromaDB vectors stored on ephemeral disk are lost on every restart (redeploy or sleep). Documents need to be re-indexed on startup, which adds to cold start time.

## Solution

**UI cold start handling:**
- On first app launch / tab focus, probe the backend health endpoint (`/health` or equivalent)
- If no response within ~3s, show a "Warming up server..." info banner/state instead of a spinner that hangs forever
- Poll every 3-5s until server responds, then proceed with normal navigation/data fetch
- Allow passive navigation (standings, schedule — cached data) during warm-up; block only live/chat features that require backend
- iOS: show inline banner in affected tabs (Chat, Live). Web: similar inline state

**ChromaDB persistence (separate decision):**
- Option A: Re-index at startup automatically (free, ~30-60s extra cold start)
- Option B: Render persistent disk $7/mo (eliminates re-index time)
- Evaluate corpus size — if small, Option A is fine for now
