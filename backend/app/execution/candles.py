"""Candle ingest: REST backfill, closed-only persistence, gap detection.

Only closed candles are persisted (BSD FR-03 — decisions act on closed 4h candles).
Idempotent upsert on (symbol, interval, open_time) so re-backfill is safe.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Candle
from app.execution.binance_client import BinanceClient, Kline

_log = get_logger("candles")
BINANCE_KLINE_LIMIT = 1500

INTERVAL_MS: dict[str, int] = {
    "4h": 4 * 60 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def _ms_to_utc(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC)


async def upsert_klines(
    session: AsyncSession, symbol: str, interval: str, klines: list[Kline]
) -> int:
    """Insert-or-update closed klines. Returns the number of new rows inserted."""
    inserted = 0
    for k in klines:
        if not k.is_closed:
            continue
        stmt = (
            pg_insert(Candle)
            .values(
                symbol=symbol,
                interval=interval,
                open_time=_ms_to_utc(k.open_time_ms),
                open=k.open,
                high=k.high,
                low=k.low,
                close=k.close,
                volume=k.volume,
                closed=True,
            )
            .on_conflict_do_update(
                index_elements=["symbol", "interval", "open_time"],
                set_={
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                },
            )
        )
        result = await session.execute(stmt)
        # rowcount is 1 for insert; on update it is also 1, so count via prior existence.
        inserted += 1 if result.rowcount else 0
    return inserted


async def backfill(
    session: AsyncSession, client: BinanceClient, symbol: str, interval: str, *, limit: int = 500
) -> int:
    """Backfill recent closed candles from REST. Returns rows upserted."""
    klines = await client.get_klines(symbol, interval, limit=limit)
    # Binance REST includes the current still-forming final kline. `Kline`
    # carries a close-time-derived flag, so `upsert_klines` drops it.
    count = await upsert_klines(session, symbol, interval, klines)
    _log.info("candles_backfilled", symbol=symbol, interval=interval, count=len(klines))
    return count


async def backfill_history(
    session: AsyncSession,
    client: BinanceClient,
    symbol: str,
    interval: str,
    *,
    bars: int,
) -> int:
    """Backfill an exact recent history window using bounded reverse pagination."""
    if bars <= 0:
        return 0
    by_open_time: dict[int, Kline] = {}
    end_time_ms: int | None = None
    while len(by_open_time) < bars:
        limit = min(BINANCE_KLINE_LIMIT, bars - len(by_open_time) + 1)
        batch = await client.get_klines(
            symbol,
            interval,
            limit=limit,
            end_time_ms=end_time_ms,
        )
        closed = [row for row in batch if row.is_closed]
        if not closed:
            break
        for row in closed:
            by_open_time[row.open_time_ms] = row
        earliest = min(row.open_time_ms for row in closed)
        next_end = earliest - 1
        if end_time_ms is not None and next_end >= end_time_ms:
            raise RuntimeError("Binance kline history pagination did not advance")
        end_time_ms = next_end
        if len(batch) < limit:
            break
    rows = [by_open_time[key] for key in sorted(by_open_time)[-bars:]]
    count = await upsert_klines(session, symbol, interval, rows)
    _log.info(
        "candle_history_backfilled",
        symbol=symbol,
        interval=interval,
        requested=bars,
        received=len(rows),
    )
    return count


async def detect_gaps(session: AsyncSession, symbol: str, interval: str) -> list[dt.datetime]:
    """Return expected candle open-times missing between the first and last stored.

    A healthy ingest has zero gaps (Stage 2 exit criterion).
    """
    step = INTERVAL_MS[interval]
    rows = (
        (
            await session.execute(
                select(Candle.open_time)
                .where(Candle.symbol == symbol, Candle.interval == interval)
                .order_by(Candle.open_time)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < 2:
        return []
    present = {r.replace(tzinfo=dt.UTC) if r.tzinfo is None else r for r in rows}
    start_ms = int(rows[0].timestamp() * 1000)
    end_ms = int(rows[-1].timestamp() * 1000)
    missing: list[dt.datetime] = []
    t = start_ms
    while t <= end_ms:
        when = _ms_to_utc(t)
        if when not in present:
            missing.append(when)
        t += step
    return missing


async def latest_open_time(session: AsyncSession, symbol: str, interval: str) -> dt.datetime | None:
    """Return the newest stored candle open-time, or None."""
    return (
        await session.execute(
            select(Candle.open_time)
            .where(Candle.symbol == symbol, Candle.interval == interval)
            .order_by(Candle.open_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
