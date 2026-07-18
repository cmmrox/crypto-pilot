"""Integration tests for the OrderManager + Reconciler against a FakeExchange (QA-4).

These verify the execution logic deterministically without network/credentials;
a live DEMO round-trip test validates the real adapter separately.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.models import Order
from app.execution.orders import OrderManager, new_client_order_id
from app.execution.reconcile import reconcile_position
from app.risk.sizing import size_long, size_short
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

D = Decimal


async def _filters(ex: FakeExchange):
    return await ex.get_filters("BTCUSDT")


@pytest.mark.asyncio
async def test_open_long_places_entry_stop_and_tp(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex)
    sizing = size_long(
        equity=D("5000"), risk_pct=D("2"), stop_distance=D("2000"),
        price=D("65000"), leverage_cap=D("3"), filters=await _filters(ex),
    )
    trade = await om.open_long(
        db_session, sizing=sizing, stop_price=D("63000"), tp1_price=D("67000"),
        tp1_fraction=D("0.4"), strategy="trend_rider_v6",
    )
    await db_session.commit()
    # Entry + stop + TP1 were placed.
    types = [t[0] for t in ex.placed]
    assert types == ["MARKET", "STOP_MARKET", "LIMIT"]
    # Persisted a trade and three orders.
    result = await db_session.execute(select(Order).where(Order.trade_id == trade.id))
    orders = result.scalars().all()
    assert len(orders) == 3
    assert trade.side == "LONG"


@pytest.mark.asyncio
async def test_open_short_has_no_price_stop(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("60000"))
    om = OrderManager(ex)
    sizing = size_short(
        equity=D("5000"), weight_pct=D("75"), vol_target=D("0.40"),
        realized_vol=D("0.40"), price=D("60000"), leverage_cap=D("3"),
        filters=await _filters(ex),
    )
    trade = await om.open_short(db_session, sizing=sizing, strategy="trend_rider_v6")
    await db_session.commit()
    # Only a MARKET entry — no STOP_MARKET by validated design.
    assert [t[0] for t in ex.placed] == ["MARKET"]
    assert not any(t[0] == "STOP_MARKET" for t in ex.placed)
    assert trade.side == "SHORT"


@pytest.mark.asyncio
async def test_idempotent_client_order_id(db_session: AsyncSession) -> None:
    ex = FakeExchange()
    cid = new_client_order_id("CPL")
    r1 = await ex.place_market("BTCUSDT", "BUY", D("0.01"), client_order_id=cid)
    r2 = await ex.place_market("BTCUSDT", "BUY", D("0.01"), client_order_id=cid)
    # The duplicate does not create a second fill.
    assert r1.status == "FILLED"
    assert r2.exchange_order_id == "DUP"
    pos = await ex.get_position("BTCUSDT")
    assert pos.qty == D("0.01")  # only one fill applied


@pytest.mark.asyncio
async def test_reconcile_matches_and_mismatches(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    await ex.place_market("BTCUSDT", "SELL", D("0.05"), client_order_id="x")  # short 0.05
    ok = await reconcile_position(ex, "BTCUSDT", expected_qty=D("-0.05"))
    assert ok.matched
    bad = await reconcile_position(ex, "BTCUSDT", expected_qty=D("0.10"))
    assert not bad.matched
    assert "mismatch" in bad.detail


@pytest.mark.asyncio
async def test_flatten_cancels_and_closes(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    await ex.place_market("BTCUSDT", "BUY", D("0.1"), client_order_id="e")
    await ex.place_stop_market("BTCUSDT", "SELL", D("0.1"), D("63000"), client_order_id="s")
    om = OrderManager(ex)
    await om.flatten(db_session, side="LONG", qty=D("0.1"), reason="test")
    await db_session.commit()
    pos = await ex.get_position("BTCUSDT")
    assert pos.qty == D("0")  # flattened
    assert len(await ex.get_open_orders("BTCUSDT")) == 0  # stop cancelled


@pytest.mark.asyncio
async def test_kill_switch_flattens_from_short(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("60000"))
    await ex.place_market("BTCUSDT", "SELL", D("0.08"), client_order_id="e")
    await ex.place_take_profit("BTCUSDT", "BUY", D("0.08"), D("55000"), client_order_id="t")
    om = OrderManager(ex)
    await om.kill(db_session)
    await db_session.commit()
    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    assert len(await ex.get_open_orders("BTCUSDT")) == 0


@pytest.mark.asyncio
async def test_order_rows_store_decimal_and_client_id(db_session: AsyncSession) -> None:
    ex = FakeExchange(mark_price=D("65000"))
    om = OrderManager(ex)
    sizing = size_long(
        equity=D("5000"), risk_pct=D("2"), stop_distance=D("2000"),
        price=D("65000"), leverage_cap=D("3"), filters=await _filters(ex),
    )
    await om.open_long(
        db_session, sizing=sizing, stop_price=D("63000"), tp1_price=D("67000"),
        tp1_fraction=D("0.4"), strategy="trend_rider_v6",
    )
    await db_session.commit()
    orders = (await db_session.execute(select(Order))).scalars().all()
    for o in orders:
        assert o.client_order_id  # every order has an idempotent client id
        assert isinstance(o.qty, Decimal)
