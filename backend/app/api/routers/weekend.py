"""HTTP router for the weekend live feed: a round's FIA documents as typed events."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.errors import client_error
from app.data.fia_documents.feed import weekend_feed

router = APIRouter(prefix="/weekend", tags=["weekend"])

# fia.com's document archive starts with the 2019 season.
FIRST_DOCUMENT_SEASON = 2019

Year = Annotated[int, Path(ge=FIRST_DOCUMENT_SEASON, le=2100)]
Round = Annotated[int, Path(ge=1, le=30)]
After = Annotated[int | None, Query(ge=0, description="Only documents numbered above this one")]


@router.get("/{year}/{round_num}/feed")
async def get_weekend_feed(
    year: Year,
    round_num: Round,
    after: After = None,
) -> dict:
    """The round's FIA documents, newest first, each with what its parser read."""
    try:
        return await asyncio.to_thread(weekend_feed, year, round_num, after)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "event": None,
            "latest": None,
            "events": [],
            **client_error("api.weekend_feed.error", exc, year=year, round=round_num),
        }
