"""Events (audit trail) read API — filterable by level, category, search."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import CurrentUserDep
from app.api.schemas import EventOut
from app.db.models import Event
from app.db.session import get_session

router = APIRouter(prefix="/api/events", tags=["events"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class EventPageOut(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("", response_model=EventPageOut)
async def list_events(
    _current: CurrentUserDep,
    session: SessionDep,
    level: Annotated[Literal["INFO", "WARN", "ERROR"] | None, Query()] = None,
    category: Annotated[
        Literal[
            "trade",
            "bot",
            "strategy",
            "reconciliation",
            "sms",
            "system",
            "news",
            "security",
            "breaker",
            "error",
        ]
        | None,
        Query(),
    ] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 50,
) -> EventPageOut:
    """Return recent events (newest first) with optional filters."""
    filters: list[ColumnElement[bool]] = []
    if level:
        filters.append(Event.level == level)
    if category:
        filters.append(Event.category == category)
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(Event.message).like(like),
                func.lower(func.coalesce(Event.ref, "")).like(like),
            )
        )
    total = (await session.execute(select(func.count(Event.id)).where(*filters))).scalar_one()
    stmt = (
        select(Event)
        .where(*filters)
        .order_by(Event.ts.desc(), Event.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return EventPageOut(
        items=[
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
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )
