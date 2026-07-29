"""Guarded exchange round-trip used to prove the production adapter safely."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.execution.exchange import Exchange
from app.execution.filters import clamp_qty, meets_min_notional, round_price
from app.execution.orders import new_client_order_id
from app.execution.reconcile import reconcile_position

SELF_CHECK_NOTIONAL_BUFFER = Decimal("1.20")
SELF_CHECK_PRICE_DISTANCE = Decimal("0.02")


@dataclass(frozen=True)
class ExecutionSelfCheck:
    side: str
    filled_qty: Decimal
    entry_price: Decimal
    reconciled: bool
    protective_stop_verified: bool
    take_profit_verified: bool
    individual_cancel_verified: bool
    flattened: bool
    zero_open_orders: bool


async def run_execution_self_check(
    exchange: Exchange,
    *,
    symbol: str,
    side: str,
) -> ExecutionSelfCheck:
    """Place one minimum-size round-trip and guarantee flat/order-free cleanup.

    LONG verifies MARKET entry, Algo STOP_MARKET, reduce-only LIMIT take-profit,
    individual Algo cancellation, cancel-all, reconciliation, and reduce-only exit.
    SHORT verifies the stop-free sleeve MARKET entry and reduce-only cover.
    """
    if side not in {"LONG", "SHORT"}:
        raise ValueError("self-check side must be LONG or SHORT")
    position = await exchange.get_position(symbol)
    open_orders = await exchange.get_open_orders(symbol)
    if position.qty != 0 or open_orders:
        raise RuntimeError("execution self-check requires a flat account with zero open orders")

    filters = await exchange.get_filters(symbol)
    mark = await exchange.get_mark_price(symbol)
    raw_qty = (filters.min_notional * SELF_CHECK_NOTIONAL_BUFFER) / mark
    # A minimum-notional quantity can sit between lot steps. Add one step before
    # the normal ROUND_DOWN clamp so the probe selects the smallest valid lot.
    qty = clamp_qty(max(filters.min_qty, raw_qty + filters.step_size), filters)
    if qty <= 0 or not meets_min_notional(qty, mark, filters):
        raise RuntimeError("exchange minimum order cannot be satisfied safely")

    entry = None
    reconciled = False
    stop_verified = False
    take_profit_verified = False
    individual_cancel_verified = False
    cleanup_error: BaseException | None = None
    try:
        entry = await exchange.place_market(
            symbol,
            "BUY" if side == "LONG" else "SELL",
            qty,
            client_order_id=new_client_order_id("CP-LIVE-CHECK"),
        )
        if entry.status != "FILLED" or entry.filled_qty != qty or entry.avg_price <= 0:
            raise RuntimeError("self-check entry fill was not fully confirmed")
        expected = qty if side == "LONG" else -qty
        reconciled = (await reconcile_position(exchange, symbol, expected_qty=expected)).matched
        if not reconciled:
            raise RuntimeError("self-check entry did not reconcile")

        if side == "LONG":
            stop_price = round_price(
                mark * (Decimal("1") - SELF_CHECK_PRICE_DISTANCE),
                filters.tick_size,
            )
            take_profit_price = round_price(
                mark * (Decimal("1") + SELF_CHECK_PRICE_DISTANCE),
                filters.tick_size,
            )
            stop = await exchange.place_stop_market(
                symbol,
                "SELL",
                qty,
                stop_price,
                client_order_id=new_client_order_id("CP-LIVE-STOP"),
            )
            take_profit = await exchange.place_take_profit(
                symbol,
                "SELL",
                qty,
                take_profit_price,
                client_order_id=new_client_order_id("CP-LIVE-TP"),
            )
            current = await exchange.get_open_orders(symbol)
            stop_verified = any(row.client_order_id == stop.client_order_id for row in current)
            take_profit_verified = any(
                row.client_order_id == take_profit.client_order_id for row in current
            )
            cancelled = await exchange.cancel_order(symbol, stop.client_order_id)
            individual_cancel_verified = cancelled.status == "CANCELED"
            if not (stop_verified and take_profit_verified and individual_cancel_verified):
                raise RuntimeError("protective-order lifecycle was not fully verified")
    finally:
        try:
            await exchange.cancel_all(symbol)
        except BaseException as exc:
            cleanup_error = exc
        try:
            current_position = await exchange.get_position(symbol)
            if current_position.qty != 0:
                await exchange.place_market(
                    symbol,
                    "SELL" if current_position.qty > 0 else "BUY",
                    abs(current_position.qty),
                    client_order_id=new_client_order_id("CP-LIVE-CLEANUP"),
                    reduce_only=True,
                )
        except BaseException as exc:
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            raise RuntimeError(
                "execution self-check cleanup was not confirmed; inspect Binance immediately"
            ) from cleanup_error

    final_position = await exchange.get_position(symbol)
    final_orders = await exchange.get_open_orders(symbol)
    flattened = final_position.qty == 0
    zero_open_orders = not final_orders
    if not flattened or not zero_open_orders:
        raise RuntimeError("execution self-check did not finish flat and order-free")
    assert entry is not None
    return ExecutionSelfCheck(
        side=side,
        filled_qty=entry.filled_qty,
        entry_price=entry.avg_price,
        reconciled=reconciled,
        protective_stop_verified=stop_verified,
        take_profit_verified=take_profit_verified,
        individual_cancel_verified=individual_cancel_verified,
        flattened=flattened,
        zero_open_orders=zero_open_orders,
    )
