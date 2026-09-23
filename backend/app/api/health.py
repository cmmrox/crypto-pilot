"""Health endpoint (LOGGING_GUIDELINES.md §Health). Cheap, no sensitive data."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import database_ok, get_session

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
    db_status = "ok" if await database_ok(session) else "error"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.version,
        database=db_status,
    )


class DeepHealthResponse(BaseModel):
    status: str
    version: str
    database: str
    worker_heartbeat_at: str | None
    worker_heartbeat_age_seconds: float | None
    worker_healthy: bool
    ingest_last_tick: str | None
    ingest_overdue: bool
    scheduler_alive: bool


@router.get("/health/deep", response_model=DeepHealthResponse)
async def deep_health(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeepHealthResponse:
    """Deeper health for the dead-man's-switch cron and ops page."""
    import datetime as dt

    db_status = "ok" if await database_ok(session) else "error"

    from app.bot.ingest import WORKER_HEARTBEAT_SECONDS, ingest_service

    dm = ingest_service.dead_man
    now = dt.datetime.now(dt.UTC)
    last_tick = dm.last_tick
    overdue = dm.is_overdue(now)
    scheduler_alive = ingest_service.is_running
    heartbeat = ingest_service.worker_heartbeat_at
    heartbeat_age = ingest_service.worker_heartbeat_age(now)
    worker_healthy = (
        scheduler_alive
        and heartbeat_age is not None
        and heartbeat_age <= WORKER_HEARTBEAT_SECONDS * 3
    )
    healthy = db_status == "ok" and not overdue and worker_healthy
    return DeepHealthResponse(
        status="ok" if healthy else "degraded",
        version=settings.version,
        database=db_status,
        worker_heartbeat_at=heartbeat.isoformat() if heartbeat else None,
        worker_heartbeat_age_seconds=(
            round(heartbeat_age, 1) if heartbeat_age is not None else None
        ),
        worker_healthy=worker_healthy,
        ingest_last_tick=last_tick.isoformat() if last_tick else None,
        ingest_overdue=overdue,
        scheduler_alive=scheduler_alive,
    )
