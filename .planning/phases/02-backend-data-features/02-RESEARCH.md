# Phase 2: Backend Data Features - Research

**Researched:** 2026-02-18
**Domain:** F1 race predictions, pit strategy analysis, live weather, LangChain tool integration, FastAPI REST endpoints
**Confidence:** HIGH

## Summary

Phase 2 adds three new backend capabilities — race predictions, pit strategy analysis, and live weather — on top of the existing FastF1 + LangChain + FastAPI stack already proven in Phase 1. The codebase already has 11 LangChain `@tool` functions in `backend/app/api/tools.py`, a working agentic loop in `routes.py`, and extensive FastF1 usage patterns. This phase extends that foundation with data-heavy computation modules.

The primary technical challenge is FastF1 session loading performance: each `session.load(laps=True)` call takes 5-15 seconds and the library is not thread-safe for concurrent loads. The existing `_fastf1_lock` threading pattern in `routes.py` must be extended to new modules. Predictions and strategy modules need historical data from multiple seasons, so aggressive caching is critical.

**Primary recommendation:** Build predictions, strategy, and weather as pure-function modules under `backend/app/data/`, then wrap them as thin `@tool` functions in `tools.py` following the existing pattern. Use in-memory dict caching with TTL for weather (10 min) and event-driven invalidation for predictions (recompute when new session data arrives).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Prediction output style
- Full grid predictions -- all 20 drivers, not just top contenders
- Confidence expressed as percentage ranges (e.g. "72-85% confidence"), not tier labels
- Top 3 reasoning factors per driver (e.g. "track suits high-downforce cars", "strong wet-weather record")
- Data sources: qualifying position, last 5 races form, driver's history at this circuit
- Pre-qualifying fallback: use practice session data + historical circuit data when qualifying hasn't happened yet
- Chat AI version is richer than REST -- adds narrative reasoning and race-engineer personality; API returns structured numbers + factors
- Include prediction accuracy tracker -- compare past predictions to actual results (e.g. "78% accurate for top-3 at last 5 races")

#### Weather data scope
- Full weather data: air temperature, rain probability, wind speed/direction, track surface temperature, humidity
- Include hourly forecast timeline for session duration (e.g. "rain expected lap 25-35")
- Start with OpenWeatherMap free tier (60 calls/min), upgrade to paid if needed later
- Combine weather data with track-specific context (e.g. "street circuits drain poorly", "Monaco is more affected by rain than Monaco")

#### Pit strategy depth
- Full stint breakdown: tyre compound per stint, lap ranges, degradation curves, pit window timing
- Reference historical strategy data from last 3 editions of the same circuit
- Works for any driver asked about -- tool pulls their specific stint/tyre data
- Include safety car probability based on circuit history (e.g. "Monaco has 65% SC rate -- one-stop gamble is riskier here")

#### REST API design
- GET /api/predictions/{year}/{round_num} is the only new REST endpoint -- strategy and weather are chat tools only
- Include full metadata: timestamp, data sources used, model accuracy stats
- Cache predictions until new data arrives (new qualifying/race session triggers recompute)

### Claude's Discretion
- Dry vs wet race scenario split -- Claude decides whether to show dual scenarios based on rain probability
- Weather data caching interval -- Claude picks a sensible TTL
- API response shape (flat array vs grouped tiers) -- Claude picks what's easiest for iOS/web

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-01 | Predictions module computes race outcome probabilities using qualifying data, historical results, and track characteristics | FastF1 provides session.results (GridPosition, Position, Points), Ergast/Jolpica standings, and historical session data going back to 2018. Heuristic scoring model using qualifying position + recent form + circuit history is fully implementable. |
| DATA-02 | Pit strategy analysis tool evaluates undercut/overcut scenarios using historical stint data, tyre degradation curves, and pit window timing | FastF1 session.laps provides Stint, Compound, TyreLife, FreshTyre, LapTime, Sector1-3Time columns. Grouping by Driver/Stint/Compound gives stint breakdown. Historical data from last 3 editions loadable via get_session(year, gp, "R"). |
| DATA-03 | Live weather and track conditions tool returns real temperature, rainfall probability, and wind data for F1 venues | OpenWeatherMap One Call 3.0 API provides current + 48h hourly forecast with temp, humidity, wind, pop (rain probability). FastF1 session.weather provides AirTemp, TrackTemp, Humidity, Rainfall, WindSpeed, WindDirection for post-session analysis. Circuit GPS coordinates needed for API calls. |
| DATA-04 | Predictions and strategy tools are exposed as LangChain tools callable by the agentic chat | Existing @tool decorator pattern in tools.py + TOOL_LIST/TOOL_MAP registry proven with 11 tools. New tools follow identical pattern. |
| DATA-05 | REST endpoint serves predictions data for iOS and web consumption | Existing FastAPI router pattern in routes.py. New GET endpoint follows same APIRouter + Pydantic pattern. In-memory cache with dict keyed by (year, round_num) matches existing race_detail_cache pattern. |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastf1 | 3.8.1 | F1 session data, lap times, stint info, weather, results | Already used in 7+ tools; provides all historical race data needed |
| langchain-core | 1.2.12 | @tool decorator, ToolMessage, tool binding | Already used for all 11 existing tools |
| fastapi | (installed) | REST endpoints, APIRouter | Already used for all existing endpoints |
| httpx | 0.28.1 | Async HTTP client for OpenWeatherMap API | Already installed and used for OpenF1 live timing |
| structlog | (installed) | Structured logging | Already configured in Phase 1 |
| pandas | (installed) | Data manipulation for lap/stint analysis | Already used extensively in tools.py |

### New Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None required | - | - | All needed libraries are already installed. OpenWeatherMap uses plain httpx. No new pip installs needed. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| OpenWeatherMap | WeatherAPI.com | WeatherAPI has better free tier (1M calls/month) but OpenWeatherMap is locked decision |
| httpx for weather | pyowm wrapper | pyowm adds abstraction but httpx is already in use and sufficient for 2 API calls |
| In-memory cache | Redis / diskcache | Overkill for single-instance deployment on Render; dict cache matches existing pattern |

**Installation:**
```bash
# No new packages needed -- all dependencies already in requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── api/
│   ├── routes.py           # Add GET /api/predictions/{year}/{round_num}
│   ├── tools.py            # Add 3 new @tool functions wrapping data modules
│   ├── prompts.py          # Update persona to mention new capabilities
│   └── circuits.py         # Add GPS lat/lon coordinates for weather API
├── data/                   # NEW — pure computation modules
│   ├── __init__.py
│   ├── predictions.py      # Race prediction engine
│   ├── strategy.py         # Pit strategy analysis
│   └── weather.py          # OpenWeatherMap integration + caching
└── config.py               # Add OPENWEATHERMAP_API_KEY, weather TTL, etc.
```

### Pattern 1: Computation Module + Thin Tool Wrapper
**What:** Keep heavy computation logic in `app/data/` modules. Tool functions in `tools.py` are thin wrappers that call the module and format output.
**When to use:** Always, for all 3 new tools.
**Why:** Separation of concerns. The predictions module can be called by both the @tool (for chat) and the REST endpoint (for iOS/web) without duplicating logic. Testing is easier when computation is decoupled from LangChain.
**Example:**
```python
# app/data/predictions.py
def compute_race_predictions(year: int, round_num: int) -> dict:
    """Pure function — returns structured prediction data."""
    # ... FastF1 data loading + heuristic scoring ...
    return {
        "predictions": [...],  # All 20 drivers
        "metadata": {"timestamp": ..., "data_sources": [...], "accuracy": ...}
    }

# app/api/tools.py
@tool
def get_race_predictions(year: int, round_num: int):
    """Predicts race finishing order with confidence ranges and reasoning."""
    from app.data.predictions import compute_race_predictions
    data = compute_race_predictions(year, round_num)
    # Format for rich chat output with narrative reasoning
    return _format_predictions_for_chat(data)

# app/api/routes.py
@router.get("/predictions/{year}/{round_num}")
async def get_predictions_endpoint(year: int, round_num: int):
    """REST endpoint — returns structured JSON for iOS/web."""
    from app.data.predictions import compute_race_predictions
    # Check cache first, compute if missing
    return await asyncio.to_thread(compute_race_predictions, year, round_num)
```

### Pattern 2: Heuristic Scoring Model for Predictions
**What:** Weighted scoring formula combining multiple data signals into a predicted finishing position with confidence ranges.
**When to use:** For DATA-01 predictions.
**Why:** User explicitly chose "statistical/heuristic approach, not ML training" (from PROJECT.md decisions). This is interpretable, explainable, and doesn't require training data.
**Example:**
```python
# Scoring factors (weights sum to 1.0)
QUALIFYING_WEIGHT = 0.35    # Qualifying position is strongest single predictor
RECENT_FORM_WEIGHT = 0.25   # Last 5 races finishing positions
CIRCUIT_HISTORY_WEIGHT = 0.20  # Driver's results at this specific circuit
TEAM_STRENGTH_WEIGHT = 0.15   # Constructor championship position
GRID_TO_FINISH_WEIGHT = 0.05  # Historical grid-to-finish correlation at circuit

def score_driver(driver_code, quali_pos, recent_results, circuit_results, team_pos):
    """Returns predicted position score (lower = better) and confidence range."""
    base_score = (
        QUALIFYING_WEIGHT * quali_pos +
        RECENT_FORM_WEIGHT * avg(recent_results) +
        CIRCUIT_HISTORY_WEIGHT * avg(circuit_results) +
        TEAM_STRENGTH_WEIGHT * team_pos +
        GRID_TO_FINISH_WEIGHT * historical_grid_delta(quali_pos, circuit)
    )
    # Confidence narrows when data signals agree, widens when they conflict
    variance = std_dev([quali_pos, avg(recent_results), avg(circuit_results)])
    confidence_low = max(0, 100 - variance * 10)
    confidence_high = min(100, confidence_low + 15)
    return base_score, (confidence_low, confidence_high)
```

### Pattern 3: Weather Caching with TTL
**What:** In-memory dict cache for weather data with time-based expiration.
**When to use:** For DATA-03 weather tool.
**Why:** Weather doesn't change fast enough to warrant real-time API calls on every chat message. 10-minute TTL balances freshness with API rate limits.
**Discretion recommendation: 10-minute TTL** — weather changes slowly enough that 10 min is fresh for race strategy decisions, and keeps us well under 60 calls/min free tier limit even with multiple concurrent users.
**Example:**
```python
import time

_weather_cache: dict[str, tuple[float, dict]] = {}  # location -> (timestamp, data)
WEATHER_TTL_SECONDS = 600  # 10 minutes

def get_weather(lat: float, lon: float, location_key: str) -> dict:
    now = time.time()
    if location_key in _weather_cache:
        cached_time, cached_data = _weather_cache[location_key]
        if now - cached_time < WEATHER_TTL_SECONDS:
            return cached_data

    data = _fetch_from_openweathermap(lat, lon)
    _weather_cache[location_key] = (now, data)
    return data
```

### Pattern 4: Prediction Accuracy Tracker
**What:** Compare past predictions to actual results and report accuracy statistics.
**When to use:** For the accuracy tracker requirement in DATA-01.
**Why:** User specifically requested "prediction accuracy tracker -- compare past predictions to actual results".
**Example:**
```python
# Store predictions in a simple JSON file or in-memory dict
_prediction_history: dict[tuple[int, int], dict] = {}  # (year, round) -> prediction

def track_accuracy(year: int, round_num: int) -> dict:
    """After race completes, compare prediction to actual result."""
    prediction = _prediction_history.get((year, round_num))
    if not prediction:
        return {"accuracy": None, "message": "No prediction stored for this race"}

    actual = _load_actual_results(year, round_num)

    # Accuracy metrics:
    # 1. Top-3 accuracy: did we predict the correct podium?
    # 2. Top-10 accuracy: what % of predicted top-10 finished top-10?
    # 3. Average position error: mean absolute difference
    top3_correct = len(set(prediction["top3"]) & set(actual["top3"]))
    avg_error = mean([abs(p - a) for p, a in zip(predicted_positions, actual_positions)])

    return {
        "top3_accuracy": f"{top3_correct}/3 correct",
        "avg_position_error": round(avg_error, 1),
        "recent_accuracy_pct": _calculate_rolling_accuracy(year, round_num)
    }
```

### Pattern 5: Dual Scenario Split (Claude's Discretion)
**What:** When rain probability exceeds 40%, show both dry and wet race predictions side by side.
**Discretion recommendation:** Show dual scenarios when OpenWeatherMap `pop` (probability of precipitation) >= 0.4 for any hour during the race window. Below 0.4, show single dry-weather prediction with a weather note.
**Why:** 40% is the threshold where rain materially affects strategy (teams prepare wet-weather setups above ~30-40%). Showing both scenarios gives the most useful information without cluttering responses for clearly dry races.

### Pattern 6: REST Response Shape (Claude's Discretion)
**What:** API response structure for GET /api/predictions/{year}/{round_num}.
**Discretion recommendation:** Flat array sorted by predicted position, with metadata envelope.
**Why:** Flat array is simplest for iOS (directly maps to SwiftUI List) and web (directly maps to table rows). No need for grouping by tiers since we're showing all 20 drivers.
```json
{
  "year": 2026,
  "round": 5,
  "grand_prix": "Monaco Grand Prix",
  "generated_at": "2026-05-22T14:30:00Z",
  "data_sources": ["qualifying", "last_5_races", "circuit_history"],
  "accuracy": {
    "recent_top3_pct": 78,
    "recent_top10_pct": 65,
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
        "2nd at Monaco 2024, 1st 2023"
      ]
    }
  ],
  "weather_impact": "dry",
  "wet_scenario": null
}
```

### Anti-Patterns to Avoid
- **Loading FastF1 sessions inside the event loop:** Always use `asyncio.to_thread()` with the existing `_fastf1_lock` pattern. Session loads are blocking I/O that take 5-15 seconds.
- **Loading full telemetry when only results are needed:** Use `session.load(telemetry=False, laps=True, weather=False)` -- only load what you need. Telemetry data is 10-100x larger than lap data.
- **Making OpenWeatherMap calls synchronously in a tool:** Use httpx async client, called from `asyncio.to_thread()` wrapper or async tool if LangChain supports it.
- **Recomputing predictions on every chat message:** Cache aggressively. Predictions only change when new session data arrives (qualifying, race).
- **Loading 5+ years of historical data on every request:** Pre-compute and cache circuit-specific historical stats. Load once per circuit, reuse across requests.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| F1 session data parsing | Custom web scraper or API client | FastF1 3.8.1 `get_session()` + `session.load()` | FastF1 handles F1 timing data format, caching, fallbacks, and data normalization |
| Tyre compound mapping | Manual compound name lookups | FastF1 `Compound` column in laps DataFrame | Already normalized to SOFT/MEDIUM/HARD/INTERMEDIATE/WET |
| Championship standings | Custom Ergast/Jolpica client | FastF1's `Ergast()` class (now backed by Jolpica) | Already handles API deprecation transparently |
| HTTP client with connection pooling | requests library or custom client | httpx.AsyncClient (already installed) | Already used in codebase; async support, connection pooling built-in |
| Weather API wrapper | pyowm library | Direct httpx call to OpenWeatherMap | Only 2 endpoints needed (current + hourly); wrapper adds unnecessary dependency |
| Tool schema generation | Manual JSON schema | LangChain `@tool` decorator | Automatic schema from type hints + docstring |

**Key insight:** The existing codebase already has the entire infrastructure. Phase 2 is about adding computation modules, not new infrastructure. Every integration pattern needed (FastF1, LangChain tools, FastAPI routing, async threading) already has working examples in the codebase.

## Common Pitfalls

### Pitfall 1: FastF1 Session Load Blocking the Event Loop
**What goes wrong:** Calling `fastf1.get_session().load()` directly in an async handler blocks the entire FastAPI event loop for 5-15 seconds, freezing all other requests.
**Why it happens:** FastF1 session loading involves network I/O and heavy pandas processing, all synchronous.
**How to avoid:** Always wrap in `asyncio.to_thread()` with the existing `_fastf1_lock`. The codebase already does this correctly in `routes.py` lines 504-506.
**Warning signs:** Server stops responding to health checks during data loads.

### Pitfall 2: FastF1 Concurrent Session Loads Causing Data Corruption
**What goes wrong:** Two threads loading different FastF1 sessions simultaneously can corrupt shared state.
**Why it happens:** FastF1 uses module-level state that is not thread-safe.
**How to avoid:** Use the existing `_fastf1_lock = threading.Lock()` for ALL FastF1 session loads, including new prediction/strategy modules.
**Warning signs:** Random KeyError or IndexError exceptions from pandas operations during load.

### Pitfall 3: Loading Historical Data for Every Prediction Request
**What goes wrong:** Computing predictions for 20 drivers requires loading qualifying + last 5 races + circuit history. That's potentially 6+ FastF1 session loads (30-90 seconds).
**Why it happens:** Naive implementation loads fresh data for every prediction request.
**How to avoid:** Cache historical data aggressively. Load historical circuit data once per (circuit, season) pair. Cache qualifying data per (year, round). Only recompute when new data arrives.
**Warning signs:** Prediction requests timing out after 60 seconds.

### Pitfall 4: OpenWeatherMap API Key Not in .env
**What goes wrong:** Weather tool returns errors because OPENWEATHERMAP_API_KEY is not configured.
**Why it happens:** New env var not documented or added to .env.example.
**How to avoid:** Add `OPENWEATHERMAP_API_KEY` to config.py with os.getenv() pattern, document in README, and fail gracefully with "weather data unavailable" message.
**Warning signs:** HTTPError 401 from OpenWeatherMap.

### Pitfall 5: Circuit GPS Coordinates Missing for Weather Lookups
**What goes wrong:** Weather tool can't fetch data because it doesn't know the latitude/longitude of the circuit.
**Why it happens:** Existing `circuits.py` has track metadata but no GPS coordinates.
**How to avoid:** Add `lat` and `lon` fields to the CIRCUIT_DATA dict in `circuits.py`. All 2025/2026 circuits need coordinates.
**Warning signs:** Weather tool returns "location not found" errors.

### Pitfall 6: Ergast/Jolpica API Rate Limiting
**What goes wrong:** Loading standings and historical results for multiple seasons hits Jolpica rate limits.
**Why it happens:** The Ergast() class makes HTTP calls that can be rate-limited.
**How to avoid:** FastF1's disk cache (`f1_cache/`) mitigates this for repeated calls. For batch historical loading, add small delays between calls and cache results in memory.
**Warning signs:** 429 HTTP responses or timeout errors from Ergast queries.

### Pitfall 7: Stale Prediction Cache After Qualifying
**What goes wrong:** Predictions still show pre-qualifying estimates after qualifying results are available.
**Why it happens:** Cache uses simple TTL without event-driven invalidation.
**How to avoid:** Implement cache invalidation keyed to session completion. When qualifying data becomes available for a round, invalidate the prediction cache for that round. The existing prefetch loop in `main.py` provides a pattern for detecting session completion.
**Warning signs:** Users see predictions that don't reflect qualifying results.

## Code Examples

Verified patterns from the existing codebase and official documentation:

### Loading Lap/Stint Data from FastF1
```python
# Source: Existing pattern in tools.py + FastF1 docs
import fastf1

session = fastf1.get_session(2024, "Monaco", "R")
session.load(telemetry=False, laps=True, weather=False)

# Stint breakdown for all drivers
stints = session.laps[["Driver", "Stint", "Compound", "LapNumber", "LapTime", "TyreLife"]]
stints_grouped = stints.groupby(["Driver", "Stint", "Compound"])
stint_summary = stints_grouped.agg(
    stint_length=("LapNumber", "count"),
    avg_lap_time=("LapTime", "mean"),
    max_tyre_life=("TyreLife", "max"),
).reset_index()
```

### Getting Qualifying Results for Predictions
```python
# Source: Existing pattern in tools.py get_qualifying_results
session = fastf1.get_session(2024, "Monaco", "Q")
session.load(telemetry=False, laps=False, weather=False)
results = session.results

# Grid positions for prediction input
for _, row in results.sort_values("Position").iterrows():
    driver = row["Abbreviation"]
    quali_pos = int(row["Position"])
    team = row["TeamName"]
    # Q3 time for relative performance
    q3_time = row.get("Q3")
```

### Registering a New LangChain Tool
```python
# Source: Existing pattern in tools.py
from langchain_core.tools import tool

@tool
def get_race_predictions(year: int, round_num: int):
    """
    Predicts race finishing order for all 20 drivers with confidence ranges.

    Returns probabilistic analysis including predicted positions, confidence
    percentage ranges, and top 3 reasoning factors per driver. Uses qualifying
    data, recent form, and circuit history.
    """
    from app.data.predictions import compute_race_predictions
    data = compute_race_predictions(year, round_num)
    return _format_predictions_for_chat(data)

# Add to TOOL_LIST and TOOL_MAP at bottom of tools.py
TOOL_LIST = [
    # ... existing tools ...
    get_race_predictions,
    get_pit_strategy,
    get_weather_conditions,  # replaces get_track_conditions stub
]
TOOL_MAP = {t.name: t for t in TOOL_LIST}
```

### OpenWeatherMap API Call with httpx
```python
# Source: OpenWeatherMap docs + existing httpx pattern in routes.py
import httpx
from app.config import OPENWEATHERMAP_API_KEY

async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current + hourly forecast from OpenWeatherMap One Call 3.0."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.openweathermap.org/data/3.0/onecall",
            params={
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHERMAP_API_KEY,
                "units": "metric",
                "exclude": "minutely,daily,alerts",
            },
        )
        resp.raise_for_status()
        return resp.json()

# Response includes:
# current.temp, current.humidity, current.wind_speed, current.wind_deg
# hourly[].temp, hourly[].pop (rain probability 0-1), hourly[].wind_speed
```

### Adding GPS Coordinates to Circuit Data
```python
# Source: circuits.py existing pattern, coordinates from public F1 data
# Add lat/lon to each circuit entry in CIRCUIT_DATA
"Sakhir": {
    "circuit_name": "Bahrain International Circuit",
    "track_length_km": 5.412,
    "laps": 57,
    "lat": 26.0325,
    "lon": 50.5106,
    # ... existing fields ...
},
```

### REST Endpoint Following Existing Pattern
```python
# Source: Existing pattern in routes.py
from app.data.predictions import compute_race_predictions

# In-memory cache matching existing race_detail_cache pattern
predictions_cache: dict[tuple[int, int], dict] = {}

@router.get("/predictions/{year}/{round_num}")
async def get_predictions_endpoint(year: int, round_num: int):
    """Structured race predictions for iOS and web consumption."""
    cache_key = (year, round_num)

    if cache_key in predictions_cache:
        cached = predictions_cache[cache_key]
        # Invalidate if qualifying data changed
        if not _needs_recompute(year, round_num, cached):
            return cached

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(compute_race_predictions, year, round_num),
            timeout=FASTF1_TIMEOUT_SECONDS,
        )
        predictions_cache[cache_key] = result
        return result
    except asyncio.TimeoutError:
        return {"error": "Prediction computation timed out. Try again later."}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ergast API for standings/results | Jolpica-F1 API (drop-in replacement) | Early 2025 | FastF1 3.8.1 handles transparently; no code changes needed |
| OpenWeatherMap 2.5 | One Call 3.0 | 2024 | Requires separate "One Call by Call" subscription; 1000 free calls/day |
| LangChain `BaseTool` subclass | `@tool` decorator | LangChain 0.1+ | Simpler tool creation; existing codebase already uses @tool |
| FastF1 < 3.0 | FastF1 3.8.1 | 2023-2024 | Better caching, Jolpica migration, improved data reliability |

**Deprecated/outdated:**
- Ergast API: Shut down early 2025. FastF1 3.8.1 migrated to Jolpica transparently.
- OpenWeatherMap 2.5 API: Still works but One Call 3.0 provides hourly `pop` (rain probability) needed for this phase.
- `get_track_conditions` stub in tools.py: Will be replaced by real weather tool.

## Open Questions

1. **OpenWeatherMap One Call 3.0 subscription requirement**
   - What we know: One Call 3.0 requires a separate "One Call by Call" subscription, distinct from the free tier. It provides 1000 free calls/day.
   - What's unclear: Whether the user has already signed up for this subscription, or if the standard free tier API (2.5) should be used as fallback.
   - Recommendation: Use One Call 3.0 for the `pop` (rain probability) field. If subscription is not available, fall back to the 2.5 current weather API (no rain probability, only actual rain data). Document this in config with `OPENWEATHERMAP_API_VERSION` setting.

2. **Prediction accuracy tracker persistence**
   - What we know: User wants accuracy tracking ("78% accurate for top-3 at last 5 races"). This requires storing past predictions and comparing to actual results.
   - What's unclear: Where to persist prediction history. In-memory dict resets on server restart. File-based JSON is simple but not ideal.
   - Recommendation: Use a JSON file in `data/` directory (e.g., `data/prediction_history.json`). Simple, survives restarts, no new infrastructure. Can migrate to DB later if needed.

3. **FastF1 session loading time for historical data**
   - What we know: Loading 3 years of circuit history + last 5 races + qualifying = potentially 9+ session loads at 5-15s each.
   - What's unclear: Exact impact of FastF1 disk cache on subsequent loads. First load is slow, cached loads are faster but still not instant.
   - Recommendation: Build a background precomputation task (similar to existing `_prefetch_race_details()`) that pre-loads historical data for upcoming races. Predictions use cached data.

4. **Practice session data quality for pre-qualifying fallback**
   - What we know: User wants pre-qualifying fallback using practice session data. FastF1 provides FP1/FP2/FP3 data.
   - What's unclear: How reliable FP data is for predictions (teams run different fuel loads, test parts, etc.).
   - Recommendation: Use practice data as a weak signal (low weight, ~0.10) with explicit "pre-qualifying estimate" labeling and wider confidence ranges. Primarily rely on historical circuit data + championship position when qualifying hasn't happened yet.

## Sources

### Primary (HIGH confidence)
- FastF1 3.8.1 official docs: https://docs.fastf1.dev/ — Session loading, lap data columns, weather data, Ergast/Jolpica interface
- FastF1 strategy example: https://docs.fastf1.dev/gen_modules/examples_gallery/plot_strategy.html — Stint grouping pattern
- OpenWeatherMap One Call 3.0 docs: https://openweathermap.org/api/one-call-3 — API endpoints, response format, pricing
- OpenWeatherMap current weather docs: https://openweathermap.org/current — Current weather endpoint, response fields
- LangChain tools docs: https://docs.langchain.com/oss/python/langchain/tools — @tool decorator pattern
- Existing codebase: `backend/app/api/tools.py` (11 working tools), `routes.py` (agentic loop, caching, FastF1 patterns)

### Secondary (MEDIUM confidence)
- FastF1 GitHub issues: https://github.com/theOehrly/Fast-F1/issues/779 — Tyre compound data quality issues (2025 season data)
- Jolpica-F1 migration: https://github.com/theOehrly/Fast-F1/discussions/445 — Ergast deprecation and Jolpica successor details
- FastF1 data reference: https://docs.fastf1.dev/data_reference/index.html — Column listings (still under construction)

### Tertiary (LOW confidence)
- None — all findings verified through official docs or existing working code in the codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and proven in codebase; no new dependencies
- Architecture: HIGH — extending existing patterns (tools, routes, caching) that already work in production
- Pitfalls: HIGH — identified from direct codebase inspection (FastF1 locking, session load times, cache invalidation)
- Weather integration: MEDIUM — One Call 3.0 subscription requirement needs user confirmation; API itself is well-documented
- Prediction accuracy: MEDIUM — persistence mechanism (JSON file) is practical but not verified against restart scenarios on Render

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days — stable domain, no fast-moving changes expected)
