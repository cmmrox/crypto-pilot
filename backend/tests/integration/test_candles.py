"""Integration tests for candle ingest & gap detection (QA-2)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from app.db.models import Candle
from app.execution.binance_client import Kline
from app.execution.candles import detect_gaps, latest_open_time, upsert_klines
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

STEP_MS = 4 * 60 * 60 * 1000
BASE_MS = 1784318400000  # a 4h boundary


def _kline(i: int, *, closed: bool = True, close: str = "100") -> Kline:
    t = BASE_MS + i * STEP_MS
    return Kline(
        open_time_ms=t,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(close),
        volume=Decimal("5"),
        close_time_ms=t + STEP_MS - 1,
        is_closed=closed,
    )


@pytest.mark.asyncio
async def test_upsert_persists_closed_candles(db_session: AsyncSession) -> None:
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0), _kline(1), _kline(2)])
    await db_session.commit()
    count = (await db_session.execute(select(func.count()).select_from(Candle))).scalar_one()
    assert count == 3


@pytest.mark.asyncio
async def test_upsert_skips_unclosed_candles(db_session: AsyncSession) -> None:
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0), _kline(1, closed=False)])
    await db_session.commit()
    count = (await db_session.execute(select(func.count()).select_from(Candle))).scalar_one()
    assert count == 1  # the unclosed candle is not persisted


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_updates(db_session: AsyncSession) -> None:
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0, close="100")])
    await db_session.commit()
    # Re-ingest the same open_time with a corrected close.
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0, close="105")])
    await db_session.commit()
    rows = (await db_session.execute(select(Candle))).scalars().all()
    assert len(rows) == 1
    assert rows[0].close == Decimal("105")


@pytest.mark.asyncio
async def test_detect_gaps_finds_missing_candle(db_session: AsyncSession) -> None:
    # Insert 0, 1, 3 — candle 2 is missing.
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0), _kline(1), _kline(3)])
    await db_session.commit()
    gaps = await detect_gaps(db_session, "BTCUSDT", "4h")
    assert len(gaps) == 1
    expected = dt.datetime.fromtimestamp((BASE_MS + 2 * STEP_MS) / 1000, tz=dt.UTC)
    assert gaps[0] == expected


@pytest.mark.asyncio
async def test_no_gaps_when_contiguous(db_session: AsyncSession) -> None:
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(i) for i in range(5)])
    await db_session.commit()
    assert await detect_gaps(db_session, "BTCUSDT", "4h") == []


@pytest.mark.asyncio
async def test_latest_open_time(db_session: AsyncSession) -> None:
    await upsert_klines(db_session, "BTCUSDT", "4h", [_kline(0), _kline(1)])
    await db_session.commit()
    latest = await latest_open_time(db_session, "BTCUSDT", "4h")
    assert latest is not None
    assert int(latest.timestamp() * 1000) == BASE_MS + STEP_MS
