"""Request schemas for chat endpoints."""

from typing import List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat.

    ``user_id`` and ``thread_id`` are optional: when supplied (e.g. a stable id
    the client keeps in localStorage) the assistant personalises replies and
    remembers the conversation across sessions. Omitting them preserves the
    original stateless behaviour.
    """

    messages: List[dict]
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
