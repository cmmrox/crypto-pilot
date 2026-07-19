"""Overview API: the real-time owner command center (BSD §12 Overview)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.models import EquitySnapshot
from app.db.session import get_session
from app.services.overview_service import OverviewSnapshot, build_overview
from app.services.settings_store import get_settings_row

router = APIRouter(prefix="/api/overview", tags=["overview"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=OverviewSnapshot)
async def overview(_current: CurrentUserDep, session: SessionDep) -> OverviewSnapshot:
    return await build_overview(session)


class EquityPoint(BaseModel):
    ts: str
    equity: str


@router.get("/equity", response_model=list[EquityPoint])
async def equity_curve(
    current: CurrentUserDep, session: SessionDep, limit: int = 500
) -> list[EquityPoint]:
    settings_row = await get_settings_row(session)
    rows = (
        (
            await session.execute(
                select(EquitySnapshot)
                .where(EquitySnapshot.environment == settings_row.active_environment)
                .order_by(EquitySnapshot.ts.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [
        EquityPoint(ts=r.ts.isoformat(), equity=str(r.balance + r.unrealized_pnl)) for r in rows
    ]
