"""Market-data health for the owner console: stored candles, gaps, exchange reach."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.scheduler import next_close_time, seconds_until_next_close, utc_now
from app.db.models import Candle
from app.execution import candles as candle_svc
from app.execution.binance_client import BinanceClient, console_client, log_unreachable
from app.services.settings_store import get_settings_row
from app.strategies import MarketSpec, get_strategy


@dataclass(frozen=True)
class MarketHealth:
    symbol: str
    interval: str
    environment: str
    candles_stored: int
    latest_open_time: str | None
    gaps: int
    next_close_utc: str
    seconds_to_next_close: float
    clock_drift_ms: int | None
    exchange_reachable: bool


async def market_health(session: AsyncSession) -> MarketHealth:
    """Connection and ingest health for the active environment and strategy market."""
    environment, market = await _active_market(session)
    stored = (
        await session.execute(
            select(func.count())
            .select_from(Candle)
            .where(Candle.symbol == market.symbol, Candle.interval == market.interval)
        )
    ).scalar_one()
    latest = await candle_svc.latest_open_time(session, market.symbol, market.interval)
    gaps = await candle_svc.detect_gaps(session, market.symbol, market.interval)

    drift: int | None = None
    reachable = False
    async with console_client(environment) as client:
        try:
            drift = await client.clock_drift_ms()
            reachable = True
        except Exception as exc:  # any failure means "unreachable"; record why
            log_unreachable(environment, "clock_drift", exc)

    now = utc_now()
    return MarketHealth(
        symbol=market.symbol,
        interval=market.interval,
        environment=environment,
        candles_stored=int(stored),
        latest_open_time=latest.isoformat() if latest else None,
        gaps=len(gaps),
        next_close_utc=next_close_time(now, market.interval).isoformat(),
        seconds_to_next_close=round(seconds_until_next_close(now, market.interval), 1),
        clock_drift_ms=drift,
        exchange_reachable=reachable,
    )


async def recent_candles(session: AsyncSession, *, limit: int) -> list[Candle]:
    """The most recent stored candles of the active strategy's market, oldest first."""
    _environment, market = await _active_market(session)
    rows = (
        (
            await session.execute(
                select(Candle)
                .where(Candle.symbol == market.symbol, Candle.interval == market.interval)
                .order_by(Candle.open_time.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


async def backfill_recent(session: AsyncSession) -> None:
    """Fetch recent closed candles from Binance (public REST) into storage.

    Writes candles, so it keeps the retrying client rather than the console's
    fail-fast one.
    """
    environment, market = await _active_market(session)
    async with BinanceClient(environment) as client:
        await candle_svc.backfill(session, client, market.symbol, market.interval, limit=500)


async def _active_market(session: AsyncSession) -> tuple[str, MarketSpec]:
    settings_row = await get_settings_row(session)
    market = get_strategy(settings_row.active_strategy).manifest.market
    return settings_row.active_environment, market
