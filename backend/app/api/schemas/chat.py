"""Request schemas for chat endpoints."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

MAX_TURNS = 40
MAX_QUESTION_CHARS = 4_000
MAX_ANSWER_CHARS = 16_000


class UserTurn(BaseModel):
    role: Literal["user"]
    content: str = Field(max_length=MAX_QUESTION_CHARS)


class AssistantTurn(BaseModel):
    """An earlier answer; its tables make it longer than a question."""

    role: Literal["assistant"]
    content: str = Field(max_length=MAX_ANSWER_CHARS)


Turn = Annotated[UserTurn | AssistantTurn, Field(discriminator="role")]


class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat.

    ``user_id`` and ``thread_id`` are optional: when supplied (e.g. a stable id
    the client keeps in localStorage) the assistant personalises replies and
    remembers the conversation across sessions. Omitting them preserves the
    original stateless behaviour.
    """

    messages: list[Turn] = Field(min_length=1, max_length=MAX_TURNS)
    user_id: str | None = Field(None, max_length=64)
    thread_id: str | None = Field(None, max_length=64)
