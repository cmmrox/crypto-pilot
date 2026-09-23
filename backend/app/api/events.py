"""Events (audit trail) read API — filterable by level, category, search."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import EventOut
from app.db.session import get_session
from app.services.events import EventFilter, event_page

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
    total, rows = await event_page(
        session, EventFilter(level, category, search), page=page, page_size=page_size
    )
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
