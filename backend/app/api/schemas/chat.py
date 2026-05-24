"""Request schemas for chat endpoints."""

from typing import List

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat."""

    messages: List[dict]
