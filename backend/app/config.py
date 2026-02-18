"""
Centralized Configuration
=========================
All magic numbers, timeouts, model settings, and infrastructure constants
extracted from across the codebase into environment-configurable values.

Every constant uses os.getenv() with a sensible default so the app works
out of the box while remaining fully configurable for production tuning.
"""

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

# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------
# Maximum number of tool-use turns before the model must produce a text answer
MAX_AGENT_TURNS = int(os.getenv("MAX_AGENT_TURNS", "5"))

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
# ChromaDB / RAG settings
# ---------------------------------------------------------------------------
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma")

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)

# Number of top-K results to return from rulebook search
RULEBOOK_TOP_K = int(os.getenv("RULEBOOK_TOP_K", "6"))

# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash")

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

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
