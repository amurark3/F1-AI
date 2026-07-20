"""Request schemas for the Race Control v2 API."""

from typing import Optional

from pydantic import BaseModel, Field


class RulebookSearchRequest(BaseModel):
    """Inputs for a visual rulebook search."""

    query: str
    category: Optional[str] = None
    year: Optional[int] = None
