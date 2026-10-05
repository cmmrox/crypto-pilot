"""Regressions for the research execution contract (real production order path)."""

from decimal import Decimal

import pytest
from app.db.models import Order
from app.execution.orders import OrderManager
from app.execution.trade_sync import sync_open_trade
from app.risk.sizing import SizingResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

D = Decimal


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_atlas_targets_anchor_to_confirmed_fill(db_session: AsyncSession, side: str) -> None:
    exchange = FakeExchange(mark_price=D("60100"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    open_trade = manager.open_long if side == "LONG" else manager.open_short_with_stop
    trade = await open_trade(
        db_session,
        sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
        stop_price=D("59000") if side == "LONG" else D("61000"),
        tp1_price=D("62000") if side == "LONG" else D("58000"),
        tp1_fraction=D("0.4"),
        stop_distance=D("1000"),
        tp1_r=D("2"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    orders = (await db_session.scalars(select(Order).where(Order.trade_id == trade.id))).all()
    stop = next(order for order in orders if order.type == "STOP_MARKET")
    tp = next(order for order in orders if order.type == "LIMIT")
    assert trade.entry_px == D("60100")
    assert stop.stop_price == (D("59100") if side == "LONG" else D("61100"))
    assert tp.price == (D("62100") if side == "LONG" else D("58100"))


async def test_atlas_partial_rounds_down_to_filter_not_decimal_precision(
    db_session: AsyncSession,
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    trade = await manager.open_long(
        db_session,
        sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
        stop_price=D("59000"),
        tp1_price=D("62000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    tp = await db_session.scalar(
        select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
    )
    assert tp is not None
    # Test exchange has 0.0001 lots: 0.004 * 40% = 0.0016, not nearest 0.001 = 0.002.
    assert tp.qty == D("0.0016")


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_atlas_tp_fill_moves_stop_without_a_candle_decision(
    db_session: AsyncSession, side: str
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    open_trade = manager.open_long if side == "LONG" else manager.open_short_with_stop
    trade = await open_trade(
        db_session,
        sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
        stop_price=D("59000") if side == "LONG" else D("61000"),
        tp1_price=D("62000") if side == "LONG" else D("58000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    tp = await db_session.scalar(
        select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
    )
    assert tp is not None and tp.price is not None
    exchange.fill_resting(tp.client_order_id, price=tp.price)
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    stop = await db_session.scalar(
        select(Order).where(
            Order.trade_id == trade.id, Order.type == "STOP_MARKET", Order.status == "NEW"
        )
    )
    assert stop is not None
    assert stop.stop_price == trade.entry_px
    assert stop.qty == trade.qty - tp.qty
    # Repeated event/recovery must not submit another stop.
    before = len(exchange.placed)
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert len(exchange.placed) == before
