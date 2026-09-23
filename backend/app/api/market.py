"""Market-data & connection status API (public Binance market data)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.api.schemas import CandleOut, MarketStatus
from app.bot.scheduler import next_close_time, seconds_until_next_close, utc_now
from app.db.models import Candle
from app.db.session import get_session
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient, console_client, log_unreachable
from app.services.settings_store import get_settings_row
from app.strategies import get_strategy

router = APIRouter(prefix="/api/market", tags=["market"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/status", response_model=MarketStatus)
async def market_status(_current: CurrentUserDep, session: SessionDep) -> MarketStatus:
    """Connection + ingest health for the active environment."""
    settings_row = await get_settings_row(session)
    env = settings_row.active_environment
    market = get_strategy(settings_row.active_strategy).manifest.market

    stored = (
        await session.execute(
            select(func.count())
            .select_from(Candle)
            .where(
                Candle.symbol == market.symbol,
                Candle.interval == market.interval,
            )
        )
    ).scalar_one()
    latest = await candle_svc.latest_open_time(session, market.symbol, market.interval)
    gaps = await candle_svc.detect_gaps(session, market.symbol, market.interval)

    drift: int | None = None
    reachable = False
    async with console_client(env) as client:
        try:
            drift = await client.clock_drift_ms()
            reachable = True
        except Exception as exc:  # any failure means "unreachable"; record why
            log_unreachable(env, "clock_drift", exc)

    now = utc_now()
    return MarketStatus(
        symbol=market.symbol,
        interval=market.interval,
        environment=env,
        candles_stored=int(stored),
        latest_open_time=latest.isoformat() if latest else None,
        gaps=len(gaps),
        next_close_utc=next_close_time(now, market.interval).isoformat(),
        seconds_to_next_close=round(seconds_until_next_close(now, market.interval), 1),
        clock_drift_ms=drift,
        exchange_reachable=reachable,
    )


@router.get("/candles", response_model=list[CandleOut])
async def recent_candles(
    _current: CurrentUserDep, session: SessionDep, limit: int = 200
) -> list[CandleOut]:
    """Return the most recent stored candles (oldest first)."""
    settings_row = await get_settings_row(session)
    market = get_strategy(settings_row.active_strategy).manifest.market
    rows = (
        (
            await session.execute(
                select(Candle)
                .where(
                    Candle.symbol == market.symbol,
                    Candle.interval == market.interval,
                )
                .order_by(Candle.open_time.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [
        CandleOut(
            open_time=c.open_time.isoformat(),
            open=str(c.open),
            high=str(c.high),
            low=str(c.low),
            close=str(c.close),
            volume=str(c.volume),
        )
        for c in rows
    ]


@router.post("/backfill", response_model=MarketStatus)
async def trigger_backfill(current: CurrentUserDep, session: SessionDep) -> MarketStatus:
    """Backfill recent closed candles from Binance (public REST)."""
    settings_row = await get_settings_row(session)
    env = settings_row.active_environment
    market = get_strategy(settings_row.active_strategy).manifest.market
    async with BinanceClient(env) as client:
        await candle_svc.backfill(
            session,
            client,
            market.symbol,
            market.interval,
            limit=500,
        )
    return await market_status(current, session)
