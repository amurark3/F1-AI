# Hardcoded / Placeholder Data Audit — Race Control

> **Purpose:** Inventory of every place the Race Control UI shows fabricated, static, or
> heuristic values as if they were real/live data, plus fix instructions. Written so a
> fresh chat (or a future me) can pick up any item without prior context.
>
> **Scope audited:** `frontend/app/race-control/**`, `backend/app/services/race_control*.py`,
> `backend/app/data/weather.py`, `backend/app/api/circuits.py`, ML feature layer.
>
> **Status legend:** `[ ]` todo · `[~]` disclosed-but-improvable · `[x]` done · `[keep]` intentional, do not change

---

## Background context (read first)

- A **fully working OpenWeatherMap client already exists**: `backend/app/data/weather.py`,
  function `get_weather_for_circuit(location)`. It returns live air/track temp, humidity,
  wind, rain probability, a 4-hour hourly forecast, track context, and a strategy-impact
  assessment. It is TTL-cached and keyed off `OPENWEATHERMAP_API_KEY` (`backend/app/config.py:118`).
- **The Race Control command center never calls it.** `build_overview` hardcodes weather to
  null, so the frontend falls back to an invented lookup table. This is the root of the two
  worst issues below.
- **Before starting weather work:** confirm `OPENWEATHERMAP_API_KEY` is set in `backend/.env`.
  If empty, `get_weather_for_circuit` returns an `{"error": ...}` dict and the UI must degrade
  gracefully (keep an honest "live feed offline" state — do NOT silently show fake numbers).

---

## TIER 1 — Fabricated values shown as real data (highest priority)

These are the two issues that make the UI actively misleading. **Fix together** — one change
resolves both.

> **DONE (2026-07-22).** `build_overview` now calls `get_weather_for_circuit(race["location"])`
> via `build_weather_block` (`race_control.py`), driven by `asyncio.run` inside the worker
> thread the router already offloads to. On success the block carries live
> `rain_risk`/`track_temp_c`/`wind_kph` + `"Live forecast (OpenWeatherMap)"`; on no-key/error/no-location
> it returns nulls + `"External forecast feed not connected"`. The frontend `HISTORICAL_WEATHER`
> table and `getHistoricalWeather` are deleted; offline now renders honest "—" values and the
> feed-offline banner instead of fabricated numbers.

### [x] 1.1 — Invented weather lookup table in the frontend
- **File:** `frontend/app/race-control/page.tsx:70-74`
- **What:** `HISTORICAL_WEATHER` = three hardcoded rows:
  ```ts
  street:     { rain_risk: 32, track_temp_c: 30, wind_kph: 14 },
  high_speed: { rain_risk: 14, track_temp_c: 44, wind_kph: 11 },
  mixed:      { rain_risk: 20, track_temp_c: 37, wind_kph: 13 },
  ```
- **Where it surfaces:**
  - "RAIN RISK ~20%" metric card — `page.tsx:138-144`
  - "Weather & Risk" panel Rain/Track/Wind stats — `page.tsx:256-258`
- **Bugs within the bug:**
  - `getHistoricalWeather` (`page.tsx:76-80`) normalizes `circuit_type` to a snake_case key.
    Real circuit types are `"Purpose-built"` / `"Street circuit"`, which normalize to
    `purpose_built` / `street_circuit` — **neither matches the table keys** (`street`,
    `high_speed`, `mixed`), so almost everything falls through to `?? HISTORICAL_WEATHER.mixed`.
  - The rain card subtitle prints `Historical avg · ${circuit_type} circuit`
    (`page.tsx:141`) — e.g. "Purpose-built circuit" — even though the number came from the
    `mixed` bucket. **Label/value mismatch.**

### [x] 1.2 — Backend weather block hardcoded to null
- **File:** `backend/app/services/race_control.py:212-217`
- **What:**
  ```python
  "weather": {
      "rain_risk": None, "track_temp_c": None, "wind_kph": None,
      "confidence": "External forecast feed not connected",
  },
  ```
- **Why:** forces `weatherLive = false` in the frontend (`page.tsx:104`), which triggers 1.1.

### Fix plan for Tier 1
1. In `build_overview` (`backend/app/services/race_control.py:188`), call
   `get_weather_for_circuit(race["location"])` when a race + location exists, wrapped in
   try/except (mirror the existing `predictions` / `strategy_reference` error handling at
   lines 194-206). Map its `current` block → `{ rain_risk, track_temp_c, wind_kph, confidence }`.
   - `rain_risk` ← `current["rain_probability_pct"]`
   - `track_temp_c` ← `current["track_temp_c"]`
   - `wind_kph` ← `current["wind_speed_kph"]`
   - `confidence` ← `"Live forecast (OpenWeatherMap)"` on success; keep the null block +
     "External forecast feed not connected" on error/no-key.
2. **Async note:** `build_overview` is sync; `get_weather_for_circuit` is `async`. Either make
   the overview path async up to the router (`backend/app/api/routers/race_control.py`), or run
   the coroutine in a thread (`anyio.from_thread` / `asyncio.run` in an executor). Prefer making
   the router endpoint `async` and awaiting properly.
3. Once the backend returns real numbers, **delete `HISTORICAL_WEATHER` and `getHistoricalWeather`**
   (`page.tsx:70-80`). Keep the `weatherLive` branch so that when the feed is offline the UI shows
   an explicit "live feed offline" state (the banner at `page.tsx:249-254` already does this) rather
   than fabricated values.
4. Fix the subtitle at `page.tsx:141` so it never claims a circuit-specific figure it didn't use.
5. **Verify:** `OPENWEATHERMAP_API_KEY` present → card shows real % + "Live forecast"; key absent →
   card shows honest offline state, no fake number.

---

## TIER 2 — Heuristic estimates shown as precise metrics (disclosed, improve visibility)

Real-ish but derived from formulas, not data. Currently disclosed in fine print; decide whether
to make disclosure louder or actually compute them.

### [~] 2.1 — Undercut / overcut deltas are circuit-shape formulas
- **File:** `backend/app/services/race_control.py` (`build_strategy_context`)
  ```python
  undercut_delta = undercut_from_ref or round(1.2 + (0.4 if is_street else 0.2), 1)
  overcut_delta  = overcut_from_ref  or round(0.8 + (0.2 if is_sprint else 0.1), 1)
  ```
- **Surfaces as:** "Pit Lane Delta" card (`Undercut 1.4s · overcut 0.9s`) and the UNDERCUT/OVERCUT
  stat tiles. The telemetry `ref` never provides these keys, so the fallback always wins — even
  when the green "2025 TELEMETRY" badge shows (that badge only covers pit loss + tyre windows).
- **DONE (2026-07-22) — disclosure hardened (did NOT compute fuel-corrected deltas).**
  `pit_model` now emits `undercut_modeled` / `overcut_modeled` (true whenever the value came from
  the fallback rather than `ref`). The UI surfaces a yellow **"modeled"** badge on the Undercut and
  Overcut stat tiles and appends `· modeled` to the Pit Lane Delta card subtitle, so the estimate is
  flagged at the tile, not just in the assumptions list. The assumption line is retained.
- **Still TODO to make real:** compute per-compound, fuel-corrected stint pace deltas from FastF1 lap
  data in `backend/app/data/strategy.py` and populate `ref["undercut_delta"]` / `ref["overcut_delta"]`.
  Non-trivial (needs fuel-burn normalization). Deliberately deferred — showing a wrong "real" number
  is worse than an honestly-flagged estimate. When done, the modeled flags flip to false automatically.

### [x] 2.2 — `traffic_threshold` hardcoded to "medium"
- **File:** `backend/app/services/race_control.py` (`derive_traffic_threshold` + `build_strategy_context`)
- **Was:** `"traffic_threshold": "medium"` — **always** "medium", never computed.
- **DONE (2026-07-22).** New `derive_traffic_threshold(ref, is_street)` computes the value from the
  real first-stop window spread (`first_stop_p75 - first_stop_p25`): a narrow window (field converges
  on one pit lap → cars rejoin into packs) → `high`, mid → `medium`, wide → `low`; street circuits
  bump one level (clean air is scarce). Returns `(label, modeled)` — `modeled=False` when telemetry
  drove it, `True` when it fell back to circuit shape only (no completed edition). `pit_model` now
  carries `traffic_modeled`, and the UI shows the "modeled" badge on the Traffic tile only in that
  fallback case.

### [~] 2.3 — Pit-loss / tyre-window heuristic fallback
- **File:** `backend/app/services/race_control.py:250-259` (`24 if is_street else 21`, stops from
  `laps * 0.42`, etc.)
- **Least problematic of the tier:** honestly flagged via `data_source.mode = "heuristic"`
  (`race_control.py:321`) and the "no completed edition" assumption. Leave unless upgrading.

### [~] 2.4 — Competitor threat labels & thresholds
- **File:** `backend/app/services/race_control.py:294-311`
- Points/gaps are real (from standings), but `"Primary"/"High"/"Monitor"`, the `gap <= 60` cutoff,
  and the `operating_read` sentences are hardcoded editorial thresholds. Fine as heuristics; just
  know they're not modeled.

---

## TIER 3 — Fully static editorial content (decide if you care)

Not data-derived at all. Reasonable as scaffolding; flag only if you want everything data-backed.

> **DONE (2026-07-22).** All three items are now derived from live state. `build_risk_register`
> and `build_workstreams` were moved into `build_overview` (from `build_strategy_dashboard`) so
> they receive the weather block and `strategy_context` (competitors + data-source mode); the
> decision-gate and stint prose is built from the values `build_strategy_context` already computes.

### [x] 3.1 — Risk register static cards
- **File:** `backend/app/services/race_control.py` (`build_risk_register` + `_weather_risk` + `_rival_risk`)
- **Was:** fixed "Weather confirmation" and "Rival offset plans" Medium risks on every event.
- **Now:** the weather risk is graded from the live forecast — offline → Medium "Weather feed
  offline"; rain ≥40% → High; 20–40% → Medium; <20% → Low, each quoting the real % — and the rival
  risk is graded from the real constructor point gap (≤25 High / ≤60 Medium / else Low, naming the
  actual nearest rival). Returns no rival card when there is no trailing rival in the standings.

### [x] 3.2 — Workstreams static statuses
- **File:** `backend/app/services/race_control.py` (`build_workstreams` + `_*_status` helpers)
- **Was:** statuses `"Build"`, `"Monitor"`, `"Standby"` hardcoded; never reflected progress.
- **Now:** every status is derived — Weekend Brief from event status (Waiting/Ready/Live/Complete);
  Race Model from prediction + telemetry availability (Waiting → Build → Ready); Rival Watch from
  competitor threat (Standby/Monitor/Active); Live Control from session status (Idle/Standby/Live/
  Complete). P1/P2 priorities are kept static — they are fixed operational weightings, not live data.

### [x] 3.3 — Decision gates & stint targets prose
- **File:** `backend/app/services/race_control.py` (`build_strategy_context`)
- **Was:** lap windows computed, but "decision"/"target" strings were fixed copy (e.g. the hardcoded
  "rival gap is inside 2.5s").
- **Now:** the First-stop-call decision quotes the real `undercut_delta` and `traffic_threshold`, the
  Safety-car-branch decision quotes the real `pit_loss`, and the stint targets name the actual
  opening/finishing compounds and the derived alternate strategy (`alt_word`).

### [keep] 3.4 — Prompt / question suggestion chips
- `frontend/app/race-control/engineer/page.tsx:10` (`PROMPTS`),
  `frontend/app/race-control/rulebook/page.tsx:33` (`QUICK_QUESTIONS`).
- These are UI affordances, not data. **Leave as-is.**

---

## TIER 4 — Legitimate constants (DO NOT CHANGE)

- **`POINTS_BY_POSITION = [25, 18, 15, …]`** — `frontend/app/race-control/predictions/RacePredictionBoard.tsx:121`
  — the actual F1 points system.
- **`CIRCUIT_DATA`** — `backend/app/api/circuits.py:12` — factual reference (laps, GPS, circuit
  type). Static because the facts are static.
- **ML feature fallbacks** (`GRID_FALLBACK`, `STANDING_FALLBACK`, …) — `backend/app/ml/features.py:34-42`
  — a documented, intentional model contract (see the module docstring), not UI fabrication.

---

## Verified-clean surfaces (no fabricated data)

For reference, these were checked and genuinely derive from real data — no action needed:
- **Intel / Rival page** — `backend/app/services/race_control_standings.py:139` (from standings feed)
- **Debriefs** — `backend/app/services/race_control_debriefs.py` (from race classification)
- **Championship forecast** — `backend/app/services/race_control_championship.py`
- **Live Timing** — `frontend/app/race-control/live/page.tsx` + `useLiveTiming` hook

---

## Suggested execution order

1. **Tier 1** (weather wiring) — single highest-impact change; kills the two worst offenders and
   also fixes the "Weather & Risk" panel. Start here.
2. ~~**2.2** (`traffic_threshold`)~~ — DONE: computed from first-stop window spread.
3. ~~**2.1** (undercut/overcut)~~ — DONE: UI disclosure hardened (per-tile "modeled" badge);
   fuel-corrected computation deliberately deferred.
4. **2.3 / 2.4** — intentionally left as honest heuristics (already disclosed).
5. ~~**Tier 3**~~ — DONE: risk register, workstreams, and decision/stint prose all derive from
   live weather, standings, prediction, and telemetry state.
