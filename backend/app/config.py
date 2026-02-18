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
