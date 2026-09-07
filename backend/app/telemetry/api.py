"""Cursor-based committed decision export; historical missing coverage is explicit."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.models import Event
from app.db.session import get_session

router = APIRouter(prefix="/api/experiment-lab", tags=["research-observations"])


@router.get("/observations")
async def observations(
    _current: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    after_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    if _current.user.role != "owner":
        raise HTTPException(403, "Owner access required")
    rows = (
        (
            await session.execute(
                select(Event)
                .where(
                    Event.id > after_id,
                    Event.category == "strategy",
                    Event.ref.startswith("decision:"),
                )
                .order_by(Event.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "schema_version": 1,
        "coverage": "COMMITTED_DECISIONS_ONLY",
        "warning": (
            "No observation is not proof of no signal. Pre-instrumentation and "
            "rolled-back decisions require retained operational logs."
        ),
        "items": [
            {"event_id": row.id, "timestamp": row.ts.isoformat(), "observation": row.payload_json}
            for row in rows
        ],
        "next_cursor": rows[-1].id if rows else after_id,
    }
