"""
Centralized Configuration
=========================
All magic numbers, timeouts, model settings, and infrastructure constants
extracted from across the codebase into environment-configurable values.

Every constant uses os.getenv() with a sensible default so the app works
out of the box while remaining fully configurable for production tuning.
"""

from dataclasses import dataclass
import os

# ---------------------------------------------------------------------------
# Tool execution timeouts
# ---------------------------------------------------------------------------
# General tool timeout for the agentic loop (seconds)
TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))

# FastF1 session load timeout — generous because loads queue behind a lock
FASTF1_TIMEOUT_SECONDS = int(os.getenv("FASTF1_TIMEOUT_SECONDS", "60"))

# OpenF1 live-timing HTTP request timeout (seconds)
OPENF1_HTTP_TIMEOUT_SECONDS = int(os.getenv("OPENF1_HTTP_TIMEOUT_SECONDS", "10"))

# Least time between the starts of two OpenF1 requests from this process. The
# free tier allows about three a second and answers a burst of ~20 with 429.
OPENF1_MIN_REQUEST_GAP_SECONDS = float(os.getenv("OPENF1_MIN_REQUEST_GAP_SECONDS", "0.4"))

# ---------------------------------------------------------------------------
# WebSocket settings
# ---------------------------------------------------------------------------
# How long to wait for a client message before continuing the poll loop
WS_RECEIVE_TIMEOUT = float(os.getenv("WS_RECEIVE_TIMEOUT", "0.1"))

# Heartbeat interval for WebSocket keep-alive (seconds) — used by Plan 02
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "15"))

# How long before a stale WebSocket is considered dead (seconds) — used by Plan 02
WS_STALE_TIMEOUT = int(os.getenv("WS_STALE_TIMEOUT", "60"))

# Polling interval for OpenF1 position data (seconds)
WS_POLL_INTERVAL = int(os.getenv("WS_POLL_INTERVAL", "8"))

# Slower cadence while no session is on track. A socket can sit open for a
# whole race weekend, so idling at the live rate would hammer OpenF1 for days.
#
# Must stay below WS_STALE_TIMEOUT: the loop's own sends are what keep a
# connection marked active, so an idle sleep at or past the timeout would
# make every client look dead and get disconnected.
WS_IDLE_POLL_INTERVAL = min(
    int(os.getenv("WS_IDLE_POLL_INTERVAL", "30")),
    max(1, WS_STALE_TIMEOUT // 2),
)

# How often to re-check which session is running while idle (seconds)
SESSION_LOOKUP_INTERVAL = int(os.getenv("SESSION_LOOKUP_INTERVAL", "300"))

# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------
# Maximum number of tool-use turns before the model must produce a text answer.
#
# 3, not 5: every turn re-sends the system prompt and all bound tool schemas, so
# turn count multiplies directly into free-tier quota (Token Lab points, Gemini
# requests). The mandated worst-case chain is get_season_schedule → a results
# tool → answer, which fits in 3 — the engines batch parallel calls into one
# turn — and the chat router binds no tools on the final turn, so the model
# always spends the last one answering rather than asking for data it will not
# be allowed to fetch.
MAX_AGENT_TURNS = int(os.getenv("MAX_AGENT_TURNS", "3"))

# ---------------------------------------------------------------------------
# Background prefetch settings
# ---------------------------------------------------------------------------
# Delay after server start before beginning race detail prefetch (seconds)
PREFETCH_STARTUP_DELAY = int(os.getenv("PREFETCH_STARTUP_DELAY", "30"))

# Timeout for a single race detail prefetch (seconds)
PREFETCH_RACE_TIMEOUT_SECONDS = int(os.getenv("PREFETCH_RACE_TIMEOUT_SECONDS", "60"))

# Pause between loading individual races during prefetch (seconds)
PREFETCH_INTER_RACE_DELAY = int(os.getenv("PREFETCH_INTER_RACE_DELAY", "5"))

# How often the prefetch loop runs (seconds) — default 30 minutes
PREFETCH_INTERVAL = int(os.getenv("PREFETCH_INTERVAL", "1800"))

# ---------------------------------------------------------------------------
# Telemetry Lab (lap telemetry and tyre degradation, from OpenF1)
# ---------------------------------------------------------------------------
# How long after OpenF1's session end its rows are treated as final and kept.
# Before that a session may still be filling in, and a partial lap list kept
# for good would outlive the gap that caused it.
ANALYSIS_SESSION_SETTLE_MINUTES = int(os.getenv("ANALYSIS_SESSION_SETTLE_MINUTES", "60"))

# How long one request waits on a cold OpenF1 load before answering "still
# working". The load carries on, and the next request joins it.
ANALYSIS_WAIT_SECONDS = float(os.getenv("ANALYSIS_WAIT_SECONDS", "45"))

# Loads kept in process memory, in front of the database (or instead of it
# when DATABASE_URL is unset). A lap trace is ~20 KB; a race's laps ~150 KB.
ANALYSIS_MEMORY_ENTRIES = int(os.getenv("ANALYSIS_MEMORY_ENTRIES", "48"))

# Fuel correction for tyre degradation. Lap time falls as fuel burns off, which
# hides wear, so each lap is put on an empty-tank footing. Both numbers are
# modelled, not measured, and are returned with every result:
#   * ~0.03 s per kg is the effect commonly used in race-strategy work.
#   * Start fuel is not published. Up to 2025 the limit was 110 kg and cars
#     started near it; the 2026 rules cut the race fuel to roughly 70 kg.
# A season missing here gets no fuel-corrected times rather than a guess.
FUEL_EFFECT_SECONDS_PER_KG = float(os.getenv("FUEL_EFFECT_SECONDS_PER_KG", "0.03"))
RACE_START_FUEL_KG: dict[int, float] = {2023: 105.0, 2024: 105.0, 2025: 105.0, 2026: 70.0}

# A lap run closer than this to the car ahead (median over the lap) is flagged
# as traffic: dirty air, not the tyre, sets its pace. A heuristic.
TRAFFIC_GAP_SECONDS = float(os.getenv("TRAFFIC_GAP_SECONDS", "1.5"))

# ---------------------------------------------------------------------------
# f1db dataset freshness
# ---------------------------------------------------------------------------
# How often the background loop checks for a newer f1db release (seconds) —
# default 6 hours. f1db publishes a release within a day or so of each race, and
# the boot-time check covers every cold start, so this only has to catch the
# container that stays warm across a race weekend. Cheap either way: a check
# that finds nothing new is one small GitHub API call.
F1DB_REFRESH_INTERVAL_SECONDS = int(os.getenv("F1DB_REFRESH_INTERVAL_SECONDS", "21600"))

# ---------------------------------------------------------------------------
# Startup warm-up / readiness settings
# ---------------------------------------------------------------------------
# Ceiling for a single warm-up step (seconds). Generous because the first step
# may have to re-download the f1db database onto Render's ephemeral disk.
WARMUP_STEP_TIMEOUT_SECONDS = int(os.getenv("WARMUP_STEP_TIMEOUT_SECONDS", "120"))

# ---------------------------------------------------------------------------
# ChromaDB / RAG settings
# ---------------------------------------------------------------------------
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# Master switch for loading torch models inside the web process: the
# sentence-transformers embedder (rulebook queries, conversation memory) and the
# cross-encoder reranker.
#
# Off by default, and deliberately so. Loading them takes a request-time OOM kill
# on a 512MB instance — verified in production, where one rulebook query killed
# the container and every endpoint went down for minutes. An OOM cannot be caught,
# so the graceful-degradation paths those modules already have never get to run.
# A capability that can take the whole service down has to be opted into by a
# deployment that knows it has the memory, not assumed.
#
# Enable it where the memory exists: local development, and the offline ingest
# job (see .github/workflows/ingest-rulebook.yml), which must embed the corpus.
ENABLE_LOCAL_MODELS = os.getenv("ENABLE_LOCAL_MODELS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Number of top-K results to return from rulebook search
RULEBOOK_TOP_K = int(os.getenv("RULEBOOK_TOP_K", "6"))

# ---------------------------------------------------------------------------
# LLM settings — AMD Token Lab first, Gemini as the fallback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMProvider:
    """One chat engine: which model, where its key lives, and how to reach it.

    ``base_url`` set means an OpenAI-compatible endpoint (``ChatOpenAI``); None
    means Google's own Gemini client, which keeps Gemini's thought signatures
    across tool calls.
    """

    name: str
    model: str
    key_env: str
    base_url: str | None = None


# Tried in order: each question runs on the first engine whose key is set and
# that is not resting after a failure (app/api/llm.py). An engine that is out of
# quota, unauthorised or down mid-question hands the whole question to the next.
#
# AMD Token Lab (https://notebooks.amd.com/tokenlab) is a beta: a points budget
# and a 30-day access window you extend by hand. Gemini's free tier (key from
# https://aistudio.google.com, on a project with no billing) keeps the chat
# answering when Token Lab lapses — but only as a backup: the free tier allows
# 20 requests a day per Flash model (quota GenerateRequestsPerDayPerProjectPerModel,
# hit 2026-11-01 after ~7 questions), and a question takes two to four requests.
#
# Deliberately constants, not os.getenv: the model is not deployment config and
# not a secret. Which model the agent runs on is a code decision — it changes the
# quality of every answer and the tool-calling behaviour the agent loop depends
# on, so it belongs in review and git history, not in a dashboard where prod can
# silently diverge from this file. Only the keys come from the environment.
#
# Replaced Groq (openai/gpt-oss-120b) on 2026-11-01: its free tier's 8K
# tokens/minute could not carry one question, and gpt-oss malformed tool calls.
#
# Token Lab's model, measured 2026-11-01 with scripts.eval_answers: DeepSeek-V4-
# Flash answered 12/12 (11 clean; the 12th a claim-checker false positive),
# fastest, and batches parallel tool calls. Qwen3.8-27B errored 3/12: its chat
# template rejects a system message after the first, which the forced final
# turn sends — any engine put here must accept one. GLM-5.3-Flash was slow and
# wrong in a spike; DeepSeek-V4.1-Flash returned garbled SQL.
LLM_PROVIDERS: tuple[LLMProvider, ...] = (
    LLMProvider(
        name="tokenlab",
        model="DeepSeek-V4-Flash",
        key_env="TOKENLAB_API_KEY",
        base_url="https://api.tokenlab.amd.com/v1",
    ),
    LLMProvider(name="gemini", model="gemini-3.5-flash-lite", key_env="GOOGLE_API_KEY"),
)

# Gemini 3's thinking depth. Measured 2026-11-01 on the free tier: at the default
# depth 3.8 Flash took ~40 s on one tool turn and 504'd on the next. At "low",
# 3.6 Flash answered a multi-race question in ~12 s and 3.5 Flash-Lite in ~3 s,
# both with a correct table and three grounded observations. Flash-Lite is the
# fallback: fastest, and still answering when 3.6 and 3.5 Flash had spent their
# daily free quota. 3.8 Flash, Google's pick for new projects, 503'd ("high
# demand") on the free tier the same day.
GEMINI_THINKING_LEVEL = "low"

# Sent to OpenAI-compatible engines only. Gemini 3.5+ fixes its own sampling and
# warns on every request that sets it.
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Per-request ceiling. Without one a hung engine holds the chat stream open.
LLM_REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "60"))

# Client-side retries before an engine counts as failed. Kept low: the fallback
# engine is a faster recovery than backing off against an exhausted quota.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

# How long an engine rests after failing. A key, quota or model problem (401,
# 402, 403, 404) will not clear in seconds; a rate limit or outage might.
LLM_ACCOUNT_COOLDOWN_SECONDS = float(os.getenv("LLM_ACCOUNT_COOLDOWN_SECONDS", "600"))
LLM_TRANSIENT_COOLDOWN_SECONDS = float(os.getenv("LLM_TRANSIENT_COOLDOWN_SECONDS", "60"))

# ---------------------------------------------------------------------------
# Prediction scoring weights (sum to 1.0)
# ---------------------------------------------------------------------------
# Qualifying position — strongest single predictor of race finish
QUALIFYING_WEIGHT = float(os.getenv("QUALIFYING_WEIGHT", "0.35"))

# Average finishing position over last 5 races — recent form signal
RECENT_FORM_WEIGHT = float(os.getenv("RECENT_FORM_WEIGHT", "0.25"))

# Driver's historical results at this specific circuit (last 3 editions)
CIRCUIT_HISTORY_WEIGHT = float(os.getenv("CIRCUIT_HISTORY_WEIGHT", "0.20"))

# Constructor championship position — team car performance proxy
TEAM_STRENGTH_WEIGHT = float(os.getenv("TEAM_STRENGTH_WEIGHT", "0.15"))

# Historical grid-to-finish delta at this circuit (overtaking difficulty)
GRID_TO_FINISH_WEIGHT = float(os.getenv("GRID_TO_FINISH_WEIGHT", "0.05"))

# ---------------------------------------------------------------------------
# ML / heuristic ensemble blend
# ---------------------------------------------------------------------------
# Fraction of the final score taken from the trained model; the remainder comes
# from the heuristic weighted score above. Backtesting over 2021-2026 (124 races)
# shows the trained model carries essentially all the signal — the blend is a
# statistical tie with pure ML, with a mild edge toward more ML weight. Default
# 0.65 leans on the model while keeping the heuristic as a light stabilizer.
# Set to 1.0 for pure model, 0.0 for pure heuristic.
ML_PREDICTION_BLEND_WEIGHT = float(os.getenv("ML_PREDICTION_BLEND_WEIGHT", "0.65"))

# Weight applied to the learned per-driver adaptive correction (from past misses).
PREDICTION_ADAPTIVE_WEIGHT = float(os.getenv("PREDICTION_ADAPTIVE_WEIGHT", "0.22"))

# ---------------------------------------------------------------------------
# Weather settings (used by Plan 02 weather module)
# ---------------------------------------------------------------------------
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")

# How long to cache weather data before re-fetching (seconds) — 10 min default
WEATHER_CACHE_TTL = int(os.getenv("WEATHER_CACHE_TTL", "600"))

# ---------------------------------------------------------------------------
# Prediction accuracy tracking
# ---------------------------------------------------------------------------
# Path to JSON file storing prediction history for accuracy comparison
PREDICTION_HISTORY_PATH = os.getenv("PREDICTION_HISTORY_PATH", "data/prediction_history.json")

# Path to JSON file storing race prediction snapshots between backend restarts
PREDICTION_CACHE_PATH = os.getenv("PREDICTION_CACHE_PATH", "data/prediction_cache.json")
