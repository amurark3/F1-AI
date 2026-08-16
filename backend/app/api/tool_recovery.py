"""Recover malformed tool calls from Groq.

Models on Groq occasionally emit a tool call as inline text like
``<function=NAME{...json...}>`` instead of a structured tool call — most often
when an argument is a long string containing quotes (e.g. a SQL query).  Groq
rejects these with a ``tool_use_failed`` (HTTP 400) error whose body carries the
raw ``failed_generation``.

This module parses that raw text back into ``{name, args, id}`` tool-call dicts
so the agent loop can execute the model's intended calls instead of failing.
"""

from __future__ import annotations

import json

_MARKER = "<function="


def is_tool_use_failed(exc: Exception) -> bool:
    """True if ``exc`` is Groq's recoverable malformed-tool-call error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if (body.get("error") or {}).get("code") == "tool_use_failed":
            return True
    return "tool_use_failed" in str(exc)


def _failed_generation(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        gen = (body.get("error") or {}).get("failed_generation")
        if gen:
            return str(gen)
    return str(exc)


def _match_json_object(text: str, open_brace: int) -> int | None:
    """Return the index just past the JSON object starting at ``open_brace``.

    Brace-matches while respecting string literals, so a ``{`` or ``>`` inside a
    SQL string doesn't end the object early.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(open_brace, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
    return None


def recover_tool_calls(exc: Exception) -> list[dict]:
    """Parse recoverable tool calls out of a Groq ``tool_use_failed`` error.

    Returns a list of ``{"name", "args", "id"}`` dicts (empty if nothing could
    be recovered).
    """
    generation = _failed_generation(exc)
    calls: list[dict] = []
    cursor = 0
    while True:
        start = generation.find(_MARKER, cursor)
        if start == -1:
            break
        name_start = start + len(_MARKER)
        brace = generation.find("{", name_start)
        if brace == -1:
            break
        name = generation[name_start:brace].strip()
        end = _match_json_object(generation, brace)
        if end is None:
            break
        try:
            args = json.loads(generation[brace:end])
        except (json.JSONDecodeError, ValueError):
            args = None
        if name and isinstance(args, dict):
            calls.append({"name": name, "args": args, "id": f"recovered_{len(calls)}"})
        cursor = end
    return calls
