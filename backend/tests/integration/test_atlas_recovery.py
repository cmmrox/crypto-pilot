"""Atlas 1.2 protects positions across partial fills, crashes and exchange races."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
from app.db.models import Order, Trade
from app.execution.binance_client import BinanceError
from app.execution.orders import OrderManager
from app.execution.trade_sync import sync_open_trade
from app.risk.sizing import SizingResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange


async def opened(session: AsyncSession, exchange: FakeExchange) -> tuple[Trade, Order, Order]:
    trade = await OrderManager(exchange, "BTCUSDT").open_long(
        session,
        sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
        stop_price=D("59000"),
        tp1_price=D("62000"),
        tp1_fraction=D("0.4"),
        stop_distance=D("1000"),
        tp1_r=D("2"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    stop = await session.scalar(
        select(Order).where(Order.trade_id == trade.id, Order.type == "STOP_MARKET")
    )
    tp = await session.scalar(
        select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
    )
    assert stop is not None and tp is not None
    await session.commit()
    return trade, stop, tp


async def test_partial_tp_fill_does_not_move_stop_early(db_session: AsyncSession) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, stop, tp = await opened(db_session, exchange)
    exchange._resting[tp.client_order_id] = ("SELL", tp.qty / 2)
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    truth = exchange._orders[tp.client_order_id]
    exchange._orders[tp.client_order_id] = replace(truth, status="PARTIALLY_FILLED")
    synced = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert synced.matched and not synced.tp1_done
    assert synced.stop_price == D("59000")
    assert trade.remaining_qty == D("0.0032")
    assert exchange._orders[stop.client_order_id].status == "NEW"


async def test_accepted_stop_survives_failure_before_recording_response(
    db_session: AsyncSession,
) -> None:
    class CrashAfterAcceptance(FakeExchange):
        crash = True

        async def place_stop_market(self, *args, **kwargs):
            result = await super().place_stop_market(*args, **kwargs)
            if self.crash and kwargs["client_order_id"].startswith("CPSR-"):
                self.crash = False
                raise RuntimeError("process interrupted after exchange acceptance")
            return result

    exchange = CrashAfterAcceptance(mark_price=D("60000"))
    _trade, old, tp = await opened(db_session, exchange)
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    with pytest.raises(RuntimeError, match="interrupted"):
        await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    await db_session.rollback()
    before = len(exchange.placed)
    recovered = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert recovered.matched and recovered.stop_price == D("60000")
    assert len(exchange.placed) == before  # query existing replacement, never place another
    assert exchange._orders[old.client_order_id].status == "CANCELED"
    active = (
        await db_session.scalars(
            select(Order).where(Order.type == "STOP_MARKET", Order.status == "NEW")
        )
    ).all()
    assert len(active) == 1 and active[0].qty == D("0.0024")


async def test_stop_rejection_after_price_crosses_flattens_remaining(
    db_session: AsyncSession,
) -> None:
    class CrossedStop(FakeExchange):
        async def place_stop_market(self, *args, **kwargs):
            if kwargs["client_order_id"].startswith("CPSR-"):
                raise BinanceError("would immediately trigger", code=-2021)
            return await super().place_stop_market(*args, **kwargs)

    exchange = CrossedStop(mark_price=D("60000"))
    trade, _stop, tp = await opened(db_session, exchange)
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    exchange.mark = D("59990")
    recovered = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert recovered.matched and recovered.position.qty == 0
    assert trade.closed_at is not None and trade.remaining_qty == 0
    assert not await exchange.get_open_orders("BTCUSDT")


async def test_old_stop_filling_during_replacement_cancel_never_reverses(
    db_session: AsyncSession,
) -> None:
    class FillDuringCancel(FakeExchange):
        old_id: str | None = None

        async def cancel_order(self, symbol: str, client_order_id: str):
            if client_order_id == self.old_id:
                self.fill_resting(client_order_id, price=D("59000"))
                raise BinanceError("order already filled", code=-2011)
            return await super().cancel_order(symbol, client_order_id)

    exchange = FillDuringCancel(mark_price=D("60000"))
    trade, old, tp = await opened(db_session, exchange)
    exchange.old_id = old.client_order_id
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    final = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert final.matched and final.position.qty == 0
    assert trade.closed_at is not None
    assert not await exchange.get_open_orders("BTCUSDT")


async def test_tp_rejection_preserves_confirmed_entry_and_stop(db_session: AsyncSession) -> None:
    class RejectTarget(FakeExchange):
        async def place_take_profit(self, *args, **kwargs):
            raise BinanceError("invalid target", code=-1111)

    exchange = RejectTarget(mark_price=D("60000"))
    with pytest.raises(BinanceError):
        await opened(db_session, exchange)
    await db_session.rollback()
    synced = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert synced.matched and synced.trade is not None
    assert synced.stop_price == D("59000") and not synced.tp1_done
    assert synced.position.qty == D("0.004")


async def test_cancelled_protection_is_restored_from_last_ratchet(db_session: AsyncSession) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    _trade, old, _tp = await opened(db_session, exchange)
    await exchange.cancel_order("BTCUSDT", old.client_order_id)
    recovered = await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    assert recovered.matched and recovered.stop_price == D("59000")
    assert (
        len(
            [
                row
                for row in await exchange.get_open_orders("BTCUSDT")
                if row.client_order_id.startswith("CPSR-")
            ]
        )
        == 1
    )


async def test_zero_lot_partial_preserves_research_trail_trigger(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.models import Candle

    exchange = FakeExchange(mark_price=D("60000"))
    original = await exchange.get_filters("BTCUSDT")

    async def real_lot(_symbol):
        return replace(original, step_size=D("0.001"), min_qty=D("0.001"))

    monkeypatch.setattr(exchange, "get_filters", real_lot)
    trade = await OrderManager(exchange, "BTCUSDT").open_long(
        db_session,
        sizing=SizingResult(D("0.001"), D("60"), D("1"), True, "ok"),
        stop_price=D("59000"),
        tp1_price=D("62000"),
        tp1_fraction=D("0.4"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )
    assert not any(kind == "LIMIT" for kind, _, _ in exchange.placed)
    candle = Candle(
        symbol="BTCUSDT",
        interval="4h",
        open_time=trade.opened_at,
        open=D("60000"),
        high=D("62100"),
        low=D("59900"),
        close=D("62000"),
        volume=D("1"),
    )
    before = len(exchange.placed)
    synced = await sync_open_trade(
        db_session, exchange, environment="DEMO", symbol="BTCUSDT", decision_candle=candle
    )
    assert synced.tp1_done and synced.position.qty == D("0.001")
    assert synced.stop_price == D("59000")  # no partial sale means no immediate BE
    assert len(exchange.placed) == before
