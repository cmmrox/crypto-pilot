"""Events (audit trail) read API — filterable by level, category, search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import EventOut
from app.db.models import Event
from app.db.session import get_session

router = APIRouter(prefix="/api/events", tags=["events"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[EventOut])
async def list_events(
    _current: CurrentUserDep,
    session: SessionDep,
    level: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EventOut]:
    """Return recent events (newest first) with optional filters."""
    stmt = select(Event).order_by(Event.ts.desc()).limit(limit)
    if level:
        stmt = stmt.where(Event.level == level)
    if category:
        stmt = stmt.where(Event.category == category)
    if search:
        like = f"%{search.lower()}%"
        from sqlalchemy import func, or_

        stmt = stmt.where(
            or_(
                func.lower(Event.message).like(like),
                func.lower(func.coalesce(Event.ref, "")).like(like),
            )
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        EventOut(
            id=e.id,
            ts=e.ts.isoformat(),
            level=e.level,
            category=e.category,
            message=e.message,
            payload_json=e.payload_json,
            sms_status=e.sms_status,
            ref=e.ref,
        )
        for e in rows
    ]
