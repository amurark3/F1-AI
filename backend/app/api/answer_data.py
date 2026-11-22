"""What an answer read, gathered from its tool results: the subject, the source chips and any charts."""

from __future__ import annotations

from dataclasses import asdict

from langchain_core.messages import BaseMessage, ToolMessage

from app.api.tools.provenance import Provenance


def answer_data(messages: list[BaseMessage]) -> dict | None:
    """The ``[ANSWER_DATA]`` payload for ``messages``, or ``None`` when no tool result carried provenance."""
    found = [m.artifact for m in messages if isinstance(m, ToolMessage) and isinstance(m.artifact, Provenance)]
    if not found:
        return None
    charts = [asdict(item.chart) for item in found if item.chart is not None]
    return {
        "subject": next((item.subject for item in found if item.subject), None),
        "sources": list(dict.fromkeys(chip for item in found for chip in item.sources)),
        "charts": [chart for index, chart in enumerate(charts) if chart not in charts[:index]],
    }
