"""Synchronize persisted orders/trades from Binance account truth.

The bot calls this before reconciliation on every closed candle.  Tracked
exchange fills are allowed to move the expected position; unexplained position
changes still fail reconciliation and enter safe mode.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, Trade
from app.execution.exchange import Exchange, Fill, Position
from app.services.events import record_event


@dataclass(frozen=True)
class SyncedTrade:
    trade: Trade | None
    position: Position
    expected_qty: Decimal
    matched: bool
    # The active protective stop of the open trade, whichever side it is on.
    stop_price: Decimal | None
    tp1_done: bool


async def sync_open_trade(
    session: AsyncSession,
    exchange: Exchange,
    *,
    environment: str,
    symbol: str,
) -> SyncedTrade:
    """Refresh the one open trade and return its reconciled strategy state."""
    trade = (
        await session.execute(
            select(Trade)
            .where(
                Trade.environment == environment,
                Trade.closed_at.is_(None),
            )
            .order_by(Trade.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    position = await exchange.get_position(symbol)
    if trade is None:
        return SyncedTrade(
            trade=None,
            position=position,
            expected_qty=Decimal("0"),
            matched=position.qty == 0,
            stop_price=None,
            tp1_done=False,
        )

    orders = (
        (await session.execute(select(Order).where(Order.trade_id == trade.id).order_by(Order.id)))
        .scalars()
        .all()
    )
    fills_by_order: dict[int, list[Fill]] = {}
    for order in orders:
        result = await exchange.get_order(symbol, order.client_order_id)
        order.binance_order_id = result.exchange_order_id
        order.status = result.status
        order.filled_qty = result.filled_qty
        order.avg_fill_px = result.avg_price if result.avg_price > 0 else None
        order.filled_at = (
            dt.datetime.now(dt.UTC)
            if result.status == "FILLED" and order.filled_at is None
            else order.filled_at
        )
        order.raw_json = result.raw
        if result.filled_qty > 0 and result.exchange_order_id:
            fills = await exchange.get_order_fills(symbol, result.exchange_order_id)
            fills_by_order[order.id] = fills
            order.raw_json = {
                **result.raw,
                "fills": [_fill_payload(fill) for fill in fills],
            }

    entry_qty = sum(
        (order.filled_qty for order in orders if not order.reduce_only),
        Decimal("0"),
    )
    reduction_qty = sum(
        (order.filled_qty for order in orders if order.reduce_only),
        Decimal("0"),
    )
    remaining = max(Decimal("0"), entry_qty - reduction_qty)
    expected_qty = remaining if trade.side == "LONG" else -remaining
    matched = position.qty == expected_qty

    all_fills = [fill for fills in fills_by_order.values() for fill in fills]
    trade.fees = sum((abs(fill.commission) for fill in all_fills), Decimal("0"))
    trade.realized_pnl = sum((fill.realized_pnl for fill in all_fills), Decimal("0"))
    funding = await exchange.get_funding_income(symbol, start_at=trade.opened_at)
    trade.funding = sum((row.amount for row in funding), Decimal("0"))

    if matched:
        trade.remaining_qty = remaining
        if remaining == 0:
            await _close_from_fills(session, trade, orders, fills_by_order)

    active_stops = [
        order
        for order in orders
        if order.type == "STOP_MARKET"
        and order.status in {"NEW", "PARTIALLY_FILLED"}
        and order.stop_price is not None
    ]
    stop_price = active_stops[-1].stop_price if active_stops else None
    tp1_done = any(
        order.type == "LIMIT"
        and order.reduce_only
        and order.status == "FILLED"
        and order.filled_qty > 0
        for order in orders
    )
    return SyncedTrade(
        trade=trade,
        position=position,
        expected_qty=expected_qty,
        matched=matched,
        stop_price=stop_price,
        tp1_done=tp1_done,
    )


async def _close_from_fills(
    session: AsyncSession,
    trade: Trade,
    orders: Sequence[Order],
    fills_by_order: dict[int, list[Fill]],
) -> None:
    reductions = [
        fill for order in orders if order.reduce_only for fill in fills_by_order.get(order.id, [])
    ]
    if reductions:
        total_qty = sum((fill.qty for fill in reductions), Decimal("0"))
        if total_qty > 0:
            trade.exit_px = (
                sum((fill.price * fill.qty for fill in reductions), Decimal("0")) / total_qty
            )
        trade.closed_at = max(fill.filled_at for fill in reductions)
    else:
        trade.closed_at = dt.datetime.now(dt.UTC)
    stop_filled = any(order.type == "STOP_MARKET" and order.filled_qty > 0 for order in orders)
    trade.exit_reason = "protective_stop" if stop_filled else "exchange_fill"
    await record_event(
        session,
        level="INFO",
        category="trade",
        message=f"{trade.side} closed from synchronized exchange fills",
        ref=f"trade:{trade.id}",
        payload={
            "exit": str(trade.exit_px) if trade.exit_px is not None else None,
            "realized_pnl": str(trade.realized_pnl),
            "fees": str(trade.fees),
            "funding": str(trade.funding),
            "reason": trade.exit_reason,
        },
    )


def _fill_payload(fill: Fill) -> dict[str, object]:
    return {
        "trade_id": fill.exchange_trade_id,
        "order_id": fill.exchange_order_id,
        "side": fill.side,
        "qty": str(fill.qty),
        "price": str(fill.price),
        "commission": str(fill.commission),
        "realized_pnl": str(fill.realized_pnl),
        "filled_at": fill.filled_at.isoformat(),
    }
