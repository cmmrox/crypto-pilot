"""Exchange-fill synchronization regressions for the live money path."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.models import Order
from app.execution.orders import OrderManager
from app.execution.trade_sync import sync_open_trade
from app.risk.sizing import size_long
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

D = Decimal


@pytest.mark.asyncio
async def test_tp_fill_updates_remaining_position_and_exact_trade_money(
    db_session: AsyncSession,
) -> None:
    exchange = FakeExchange(mark_price=D("65000"), balance=D("5000"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    filters = await exchange.get_filters("BTCUSDT")
    sizing = size_long(
        equity=D("5000"),
        risk_pct=D("2"),
        stop_distance=D("2000"),
        price=D("65000"),
        leverage_cap=D("3"),
        filters=filters,
    )
    trade = await manager.open_long(
        db_session,
        sizing=sizing,
        stop_price=D("63000"),
        tp1_price=D("67000"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    await db_session.flush()
    tp = (
        await db_session.execute(
            select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
        )
    ).scalar_one()

    exchange.fill_resting(tp.client_order_id, price=D("67000"))
    synced = await sync_open_trade(
        db_session,
        exchange,
        environment="DEMO",
        symbol="BTCUSDT",
    )

    assert synced.matched is True
    assert synced.tp1_done is True
    assert trade.remaining_qty == sizing.qty - tp.qty
    assert trade.realized_pnl == (D("67000") - D("65000")) * tp.qty
    assert trade.fees > 0
    assert trade.closed_at is None
