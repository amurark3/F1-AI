"""Request schemas for the Race Control v2 API."""

from pydantic import BaseModel


class RulebookSearchRequest(BaseModel):
    """Inputs for a visual rulebook search."""

    query: str
    category: str | None = None
    year: int | None = None
