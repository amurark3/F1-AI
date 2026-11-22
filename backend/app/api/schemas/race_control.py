"""Request schemas for the Race Control v2 API."""

from pydantic import BaseModel, Field


class RulebookSearchRequest(BaseModel):
    """Inputs for a visual rulebook search."""

    query: str = Field(min_length=1, max_length=300)
    category: str | None = None
    year: int | None = None
