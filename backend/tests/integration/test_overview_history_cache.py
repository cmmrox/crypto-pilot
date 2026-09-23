"""The Overview recomputes strategy history only when the candle history changes.

It polls every four seconds, while the history it explains changes once per closed
candle (or when a backfill rewrites one). These tests pin both halves: no redundant
recomputation, and no stale watch panel.
"""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from app.db.models import Candle
from app.services import overview_service
from app.strategies import get_strategy
from app.strategies.base import Candle as StrategyCandle
from sqlalchemy.ext.asyncio import AsyncSession

STRATEGY = "atlas_dual_v1_4h"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "btcusdt_4h_2026.csv"


def _candles(limit: int) -> list[Candle]:
    with FIXTURE.open() as handle:
        rows = list(csv.DictReader(handle))[:limit]
    return [
        Candle(
            symbol="BTCUSDT",
            interval="4h",
            open_time=dt.datetime.fromisoformat(row["dt"]),
            open=Decimal(row["open"]),
            high=Decimal(row["high"]),
            low=Decimal(row["low"]),
            close=Decimal(row["close"]),
            volume=Decimal(row["volume"]),
            closed=True,
        )
        for row in rows
    ]


def _as_strategy_candles(rows: list[Candle]) -> list[StrategyCandle]:
    return [
        StrategyCandle(
            open_time_ms=int(row.open_time.timestamp() * 1000),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in rows
    ]


@pytest.fixture
def counted_inspect(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Start with an empty cache and count calls to the strategy's inspect()."""
    monkeypatch.setattr(overview_service, "_history_views", {})
    strategy = get_strategy(STRATEGY)
    original = strategy.inspect
    calls: list[int] = []

    def counting(candles: list[StrategyCandle]):  # type: ignore[no-untyped-def]
        calls.append(len(candles))
        return original(candles)

    monkeypatch.setattr(strategy, "inspect", counting)
    return calls


@pytest.mark.asyncio
async def test_unchanged_history_is_inspected_once(
    db_session: AsyncSession, counted_inspect: list[int]
) -> None:
    candles = _candles(600)
    db_session.add_all(candles)
    await db_session.flush()
    strategy = get_strategy(STRATEGY)

    first = await overview_service._history_view(db_session, strategy)
    second = await overview_service._history_view(db_session, strategy)

    assert counted_inspect == [600]
    assert second is first
    # The cached result is exactly what a fresh inspection returns.
    assert first.watch == strategy.inspect(_as_strategy_candles(candles))
    assert first.gap_count == 0


@pytest.mark.asyncio
async def test_a_new_closed_candle_refreshes_the_view(
    db_session: AsyncSession, counted_inspect: list[int]
) -> None:
    candles = _candles(601)
    db_session.add_all(candles[:600])
    await db_session.flush()
    strategy = get_strategy(STRATEGY)
    before = await overview_service._history_view(db_session, strategy)

    db_session.add(candles[600])
    await db_session.flush()
    after = await overview_service._history_view(db_session, strategy)

    assert counted_inspect == [600, 601]
    assert after.watch != before.watch
    assert after.watch == strategy.inspect(_as_strategy_candles(candles))


@pytest.mark.asyncio
async def test_a_rewritten_candle_refreshes_the_view(
    db_session: AsyncSession, counted_inspect: list[int]
) -> None:
    """Candles are upserted, so a backfill can revise a stored candle in place."""
    candles = _candles(600)
    db_session.add_all(candles)
    await db_session.flush()
    strategy = get_strategy(STRATEGY)
    await overview_service._history_view(db_session, strategy)

    candles[-1].close = candles[-1].close + Decimal("250")
    candles[-1].high = max(candles[-1].high, candles[-1].close)
    await db_session.flush()
    revised = await overview_service._history_view(db_session, strategy)

    assert counted_inspect == [600, 600]
    assert revised.watch == strategy.inspect(_as_strategy_candles(candles))


@pytest.mark.asyncio
async def test_a_missing_candle_is_reported_as_a_gap(
    db_session: AsyncSession, counted_inspect: list[int]
) -> None:
    candles = _candles(600)
    db_session.add_all(candles[:300] + candles[301:])
    await db_session.flush()

    view = await overview_service._history_view(db_session, get_strategy(STRATEGY))

    assert view.gap_count == 1
