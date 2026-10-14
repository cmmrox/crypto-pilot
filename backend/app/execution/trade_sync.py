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
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candle, Order, Trade
from app.execution.exchange import Exchange, Fill, Position
from app.services.events import record_event
from app.services.trade_alerts import notify_tp1_filled, notify_trade_closed


@dataclass(frozen=True)
class SyncedTrade:
    trade: Trade | None
    position: Position
    expected_qty: Decimal
    matched: bool
    # The active protective stop of the open trade, whichever side it is on.
    stop_price: Decimal | None
    tp1_done: bool
    tp1_sold: bool = False


async def sync_open_trade(
    session: AsyncSession,
    exchange: Exchange,
    *,
    environment: str,
    symbol: str,
    decision_candle: Candle | None = None,
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

    await recover_pending_targets(session, exchange, trade, symbol)
    await recover_stop_replacements(session, exchange, trade, symbol)
    orders = (
        (await session.execute(select(Order).where(Order.trade_id == trade.id).order_by(Order.id)))
        .scalars()
        .all()
    )
    fills_by_order: dict[int, list[Fill]] = {}
    newly_filled_targets: list[Order] = []
    for order in orders:
        if order.raw_json.get("virtual_tp"):
            if (
                decision_candle is not None
                and order.status == "VIRTUAL"
                and order.price is not None
            ):
                crossed = (
                    decision_candle.high >= order.price
                    if trade.side == "LONG"
                    else decision_candle.low <= order.price
                )
                if crossed and decision_candle.open_time + dt.timedelta(hours=4) > trade.opened_at:
                    order.status = "VIRTUAL_TRIGGERED"
            continue
        if order.status in {"REJECTED", "CANCELED"} and order.binance_order_id is None:
            continue
        result = await exchange.get_order(symbol, order.client_order_id)
        if (
            order.type == "LIMIT"
            and order.reduce_only
            and order.status != "FILLED"
            and result.status == "FILLED"
        ):
            newly_filled_targets.append(order)
        order.binance_order_id = result.exchange_order_id
        order.status = result.status
        order.filled_qty = result.filled_qty
        order.avg_fill_px = result.avg_price if result.avg_price > 0 else None
        order.filled_at = (
            dt.datetime.now(dt.UTC)
            if result.status == "FILLED" and order.filled_at is None
            else order.filled_at
        )
        order.raw_json = {**order.raw_json, **result.raw}
        if result.filled_qty > 0 and result.exchange_order_id:
            fills = await exchange.get_order_fills(symbol, result.exchange_order_id)
            fills_by_order[order.id] = fills
            if result.status == "FILLED" and fills:
                order.filled_at = max(fill.filled_at for fill in fills)
            order.raw_json = {
                **order.raw_json,
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
    position = await exchange.get_position(symbol)
    matched = position.qty == expected_qty

    all_fills = [fill for fills in fills_by_order.values() for fill in fills]
    trade.fees = sum((abs(fill.commission) for fill in all_fills), Decimal("0"))
    trade.realized_pnl = sum((fill.realized_pnl for fill in all_fills), Decimal("0"))
    funding = await exchange.get_funding_income(symbol, start_at=trade.opened_at)
    trade.funding = sum((row.amount for row in funding), Decimal("0"))

    if matched:
        trade.remaining_qty = remaining
        if remaining == 0:
            await exchange.cancel_all(symbol)
            await _close_from_fills(session, trade, orders, fills_by_order)

    active_stops = [
        order
        for order in orders
        if order.type == "STOP_MARKET"
        and order.status in {"NEW", "PARTIALLY_FILLED"}
        and order.stop_price is not None
    ]
    stop_price = active_stops[-1].stop_price if active_stops else None
    partial_sold = any(
        order.type == "LIMIT"
        and order.reduce_only
        and order.status == "FILLED"
        and order.filled_qty >= order.qty
        and order.qty > 0
        for order in orders
    )
    tp1_done = partial_sold or any(order.status == "VIRTUAL_TRIGGERED" for order in orders)

    from app.execution.orders import OrderManager
    from app.execution.policy import execution_policy

    policy = execution_policy(trade.strategy, trade.strategy_release)
    if (
        matched
        and remaining > 0
        and policy.breakeven_on_tp_fill
        and (partial_sold or stop_price is None)
    ):
        manager = OrderManager(exchange, symbol, environment)
        move = manager.move_long_stop if trade.side == "LONG" else manager.move_short_stop
        moved = await move(
            session,
            trade=trade,
            new_stop_price=trade.entry_px if partial_sold else Decimal("0"),
            remaining_qty=remaining,
            filters=await exchange.get_filters(symbol),
        )
        if moved:
            newest = await session.scalar(
                select(Order)
                .where(
                    Order.trade_id == trade.id, Order.type == "STOP_MARKET", Order.status == "NEW"
                )
                .order_by(Order.id.desc())
                .limit(1)
            )
            stop_price = newest.stop_price if newest is not None else None
        if trade.closed_at is not None:
            position = await exchange.get_position(symbol)
            expected_qty = Decimal("0")
            matched = position.qty == 0
            stop_price = None
    if trade.closed_at is None and remaining > 0:
        for target in newly_filled_targets:
            await notify_tp1_filled(
                session,
                trade,
                qty=target.filled_qty,
                price=target.avg_fill_px or target.price,
                remaining=remaining,
                stop=stop_price,
            )
    return SyncedTrade(
        trade=trade,
        position=position,
        expected_qty=expected_qty,
        matched=matched,
        stop_price=stop_price,
        tp1_done=tp1_done,
        tp1_sold=partial_sold,
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
    target_sold = any(
        order.type == "LIMIT" and order.reduce_only and order.filled_qty > 0 for order in orders
    )
    if stop_filled and target_sold:
        alert_reason = "trailing/breakeven stop after TP1"
    elif stop_filled:
        alert_reason = "stop loss"
    else:
        alert_reason = "take profit / exchange fill"
    await notify_trade_closed(session, trade, reason=alert_reason)


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


async def recover_stop_replacements(
    session: AsyncSession, exchange: Exchange, trade: Trade, symbol: str
) -> None:
    """Resolve durable stop intents using exchange truth before any new mutation."""
    from app.execution.binance_client import BinanceError

    rows = (
        await session.scalars(
            select(Order)
            .where(Order.trade_id == trade.id, Order.type == "STOP_MARKET")
            .order_by(Order.id)
        )
    ).all()
    by_client = {row.client_order_id: row for row in rows}
    for row in rows:
        old_id = row.raw_json.get("replaces")
        if not old_id or row.status not in {"PENDING", "NEW", "PARTIALLY_FILLED"}:
            continue
        try:
            truth = await exchange.get_order(symbol, row.client_order_id)
        except BinanceError as exc:
            if exc.code not in {-2013, -2011}:
                raise
            # Retry this durable client ID and its original target, not a newly
            # generated order. The adapter resolves ambiguous submissions by ID.
            position = await exchange.get_position(symbol)
            if position.qty == 0:
                row.status = "CANCELED"
                await session.commit()
                continue
            if (position.qty > 0) != (trade.side == "LONG") or row.stop_price is None:
                raise RuntimeError("pending protection no longer matches position") from exc
            options: dict[str, Any] = {}
            if row.raw_json.get("workingType") == "CONTRACT_PRICE":
                options["working_type"] = "CONTRACT_PRICE"
            try:
                truth = await exchange.place_stop_market(
                    symbol,
                    "SELL" if trade.side == "LONG" else "BUY",
                    row.qty,
                    row.stop_price,
                    client_order_id=row.client_order_id,
                    **options,
                )
            except BinanceError as rejection:
                if rejection.code != -2021:
                    raise
                from app.execution.orders import OrderManager

                row.status = "REJECTED"
                await session.commit()
                await OrderManager(exchange, symbol, trade.environment).flatten(
                    session,
                    side=trade.side,
                    qty=abs(position.qty),
                    reason="recovered stop already crossed",
                )
                await session.commit()
                continue
        row.status = truth.status
        row.binance_order_id = truth.exchange_order_id
        row.raw_json = {**row.raw_json, **truth.raw}
        await session.commit()
        old = by_client.get(old_id)
        if old is None:
            raise RuntimeError("replacement refers to an untracked protective stop")
        if truth.status in {"NEW", "PARTIALLY_FILLED"} and old.status in {
            "NEW",
            "PARTIALLY_FILLED",
            "PENDING",
        }:
            previous = await exchange.get_order(symbol, old_id)
            if previous.status in {"NEW", "PARTIALLY_FILLED"}:
                previous = await exchange.cancel_order(symbol, old_id)
            old.status = previous.status
            old.filled_qty = previous.filled_qty
            old.raw_json = {**old.raw_json, **previous.raw}
            await session.commit()


async def recover_pending_targets(
    session: AsyncSession, exchange: Exchange, trade: Trade, symbol: str
) -> None:
    """Query/retry the *same* TP client ID after a crash or ambiguous placement."""
    from app.execution.binance_client import BinanceError

    rows = (
        await session.scalars(
            select(Order).where(
                Order.trade_id == trade.id, Order.type == "LIMIT", Order.status == "PENDING"
            )
        )
    ).all()
    for row in rows:
        try:
            result = await exchange.get_order(symbol, row.client_order_id)
        except BinanceError as exc:
            if exc.code not in {-2011, -2013}:
                raise
            position = await exchange.get_position(symbol)
            if position.qty == 0:
                row.status = "CANCELED"
                await session.commit()
                continue
            if (position.qty > 0) != (trade.side == "LONG") or abs(position.qty) < row.qty:
                raise RuntimeError(
                    "pending TP quantity/side no longer matches exchange position"
                ) from exc
            if row.price is None:
                raise RuntimeError("pending TP has no target price") from exc
            result = await exchange.place_take_profit(
                symbol,
                "SELL" if trade.side == "LONG" else "BUY",
                row.qty,
                row.price,
                client_order_id=row.client_order_id,
            )
        row.status = result.status
        row.binance_order_id = result.exchange_order_id
        row.filled_qty = result.filled_qty
        row.raw_json = {**row.raw_json, **result.raw}
        await session.commit()
