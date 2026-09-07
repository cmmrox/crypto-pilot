"""Execution self-check lifecycle and cleanup tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.execution.self_check import run_execution_self_check

from tests.fakes import FakeExchange


@pytest.mark.asyncio
async def test_long_self_check_verifies_protection_cancellation_and_cleanup() -> None:
    exchange = FakeExchange(mark_price=Decimal("65000"))

    result = await run_execution_self_check(
        exchange,
        symbol="BTCUSDT",
        side="LONG",
    )

    assert result.reconciled
    assert result.protective_stop_verified
    assert result.take_profit_verified
    assert result.individual_cancel_verified
    assert result.flattened
    assert result.zero_open_orders


@pytest.mark.asyncio
async def test_short_self_check_covers_without_a_price_stop() -> None:
    exchange = FakeExchange(mark_price=Decimal("65000"))

    result = await run_execution_self_check(
        exchange,
        symbol="BTCUSDT",
        side="SHORT",
    )

    assert result.reconciled
    assert not result.protective_stop_verified
    assert result.flattened
    assert result.zero_open_orders


@pytest.mark.asyncio
async def test_self_check_emergency_cleanup_flattens_after_protective_order_failure() -> None:
    class StopFailingExchange(FakeExchange):
        async def place_stop_market(
            self,
            symbol: str,
            side: str,
            qty: Decimal,
            stop_price: Decimal,
            *,
            client_order_id: str,
            reduce_only: bool = True,
        ):
            raise RuntimeError("simulated stop rejection")

    exchange = StopFailingExchange(mark_price=Decimal("65000"))

    with pytest.raises(RuntimeError, match="simulated stop rejection"):
        await run_execution_self_check(
            exchange,
            symbol="BTCUSDT",
            side="LONG",
        )

    assert (await exchange.get_position("BTCUSDT")).qty == 0
    assert await exchange.get_open_orders("BTCUSDT") == []


@pytest.mark.parametrize(
    "side,position,message",
    [
        ("BUY", "0", "side must"),
        ("LONG", "0.001", "flat account"),
    ],
)
async def test_self_check_rejects_invalid_initial_state_without_mutation(side, position, message):
    exchange = FakeExchange()
    exchange._pos = Decimal(position)
    with pytest.raises((ValueError, RuntimeError), match=message):
        await run_execution_self_check(exchange, symbol="BTCUSDT", side=side)
    assert exchange.placed == []


async def test_cleanup_still_flattens_when_cancel_all_fails():
    class CancelFailingExchange(FakeExchange):
        async def cancel_all(self, symbol):
            raise RuntimeError("cancel unavailable")

    exchange = CancelFailingExchange()
    with pytest.raises(RuntimeError, match="cleanup was not confirmed") as failure:
        await run_execution_self_check(exchange, symbol="BTCUSDT", side="SHORT")
    assert str(failure.value.__cause__) == "cancel unavailable"
    assert (await exchange.get_position("BTCUSDT")).qty == 0


async def test_cleanup_failure_is_reported_when_reduce_only_exit_fails():
    class ExitFailingExchange(FakeExchange):
        async def place_market(self, *args, **kwargs):
            if kwargs.get("reduce_only"):
                raise RuntimeError("exit unavailable")
            return await super().place_market(*args, **kwargs)

    exchange = ExitFailingExchange()
    with pytest.raises(RuntimeError, match="inspect Binance immediately") as failure:
        await run_execution_self_check(exchange, symbol="BTCUSDT", side="SHORT")
    assert str(failure.value.__cause__) == "exit unavailable"
    assert (await exchange.get_position("BTCUSDT")).qty < 0


async def test_unconfirmed_entry_triggers_cleanup():
    from dataclasses import replace

    class PartialExchange(FakeExchange):
        async def place_market(self, *args, **kwargs):
            result = await super().place_market(*args, **kwargs)
            return (
                result if kwargs.get("reduce_only") else replace(result, status="PARTIALLY_FILLED")
            )

    exchange = PartialExchange()
    with pytest.raises(RuntimeError, match="not fully confirmed"):
        await run_execution_self_check(exchange, symbol="BTCUSDT", side="SHORT")
    assert (await exchange.get_position("BTCUSDT")).qty == 0
