"""Market-data & connection status API (public Binance market data)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import CandleOut, MarketStatus
from app.db.session import get_session
from app.services import market_status as market_svc

router = APIRouter(prefix="/api/market", tags=["market"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/status", response_model=MarketStatus)
async def market_status(_current: CurrentUserDep, session: SessionDep) -> MarketStatus:
    """Connection + ingest health for the active environment."""
    return MarketStatus(**asdict(await market_svc.market_health(session)))


@router.get("/candles", response_model=list[CandleOut])
async def recent_candles(
    _current: CurrentUserDep, session: SessionDep, limit: int = 200
) -> list[CandleOut]:
    """Return the most recent stored candles (oldest first)."""
    return [
        CandleOut(
            open_time=c.open_time.isoformat(),
            open=str(c.open),
            high=str(c.high),
            low=str(c.low),
            close=str(c.close),
            volume=str(c.volume),
        )
        for c in await market_svc.recent_candles(session, limit=limit)
    ]


@router.post("/backfill", response_model=MarketStatus)
async def trigger_backfill(_current: CurrentUserDep, session: SessionDep) -> MarketStatus:
    """Backfill recent closed candles from Binance (public REST)."""
    await market_svc.backfill_recent(session)
    return MarketStatus(**asdict(await market_svc.market_health(session)))
