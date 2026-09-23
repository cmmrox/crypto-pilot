"""Overview API: the real-time owner command center (BSD §12 Overview)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.db.session import get_session
from app.services.overview_service import OverviewSnapshot, build_overview, equity_history

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
    rows = await equity_history(session, limit=limit)
    return [
        EquityPoint(ts=r.ts.isoformat(), equity=str(r.balance + r.unrealized_pnl)) for r in rows
    ]
