"""User profile + conversation memory endpoints."""

from typing import Optional

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.data import memory

logger = structlog.get_logger()
router = APIRouter(tags=["memory"])


class ProfileUpdate(BaseModel):
    """Partial profile update — only provided fields are changed."""

    favorite_driver: Optional[str] = None
    favorite_team: Optional[str] = None
    prefs: Optional[dict] = None


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    """Return the stored profile for a user (empty when none/disabled)."""
    return {"user_id": user_id, "profile": memory.get_profile(user_id), "enabled": memory.MEMORY_ENABLED}


@router.put("/profile/{user_id}")
async def update_profile(user_id: str, update: ProfileUpdate):
    """Upsert profile fields for a user and return the merged profile."""
    profile = memory.set_profile(
        user_id,
        favorite_driver=update.favorite_driver,
        favorite_team=update.favorite_team,
        prefs=update.prefs,
    )
    return {"user_id": user_id, "profile": profile, "enabled": memory.MEMORY_ENABLED}


@router.get("/threads/{user_id}/recall")
async def recall(user_id: str, q: str, k: int = 4):
    """Semantic recall of a user's past messages relevant to query ``q``."""
    return {"user_id": user_id, "query": q, "matches": memory.recall_relevant(user_id, q, k=k)}
