"""Recover malformed tool calls from Groq.

Groq rejects a tool call it cannot validate with a ``tool_use_failed`` (HTTP
400) error whose body carries the raw ``failed_generation``. Two causes matter:

* The model emitted the call as text instead of a structured call. Llama writes
  ``<function=NAME{...json...}>``, most often when an argument is a long string
  containing quotes (e.g. a SQL query); gpt-oss writes bare JSON,
  ``{"name": NAME, "arguments": {...}}``.
* The model called a tool the request did not offer. Only the tools the
  question's keywords suggest are bound (see tool_router.py), so a model that
  decides it needs another one is refused outright.

This module parses the raw text back into ``{name, args, id}`` tool-call dicts,
and names the refused tool, so the agent loop can carry on instead of failing.
"""

from __future__ import annotations

import json
import re

_MARKER = "<function="

_UNBOUND_TOOL = re.compile(r"attempted to call tool '([^']+)' which was not in request\.tools")


def is_tool_use_failed(exc: Exception) -> bool:
    """True if ``exc`` is Groq's recoverable malformed-tool-call error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and (body.get("error") or {}).get("code") == "tool_use_failed":
        return True
    return "tool_use_failed" in str(exc)


def unbound_tool_name(exc: Exception) -> str | None:
    """Name of the tool Groq refused because the request did not offer it."""
    match = _UNBOUND_TOOL.search(_error_field(exc, "message"))
    return match.group(1) if match else None


def _error_field(exc: Exception, field: str) -> str:
    """One field of Groq's error body, or the exception text when it is absent."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        value = (body.get("error") or {}).get(field)
        if value:
            return str(value)
    return str(exc)


def _failed_generation(exc: Exception) -> str:
    return _error_field(exc, "failed_generation")


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
        elif ch == '"':
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
    if _MARKER in generation:
        return _inline_calls(generation)
    return _json_call(generation)


def _inline_calls(generation: str) -> list[dict]:
    """Every ``<function=NAME{...}>`` call in a Llama-style generation."""
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


def _json_call(generation: str) -> list[dict]:
    """The single ``{"name": ..., "arguments": {...}}`` call gpt-oss reports."""
    try:
        call = json.loads(generation)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(call, dict):
        return []
    name = call.get("name")
    args = call.get("arguments")
    if not isinstance(name, str) or not name.strip() or not isinstance(args, dict):
        return []
    return [{"name": name.strip(), "args": args, "id": "recovered_0"}]
