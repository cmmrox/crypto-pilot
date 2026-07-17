"""Health endpoint (LOGGING_GUIDELINES.md §Health). Cheap, no sensitive data."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Return service + database health."""
    try:
        await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # pragma: no cover - exercised via integration
        db_status = "error"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.version,
        database=db_status,
    )
