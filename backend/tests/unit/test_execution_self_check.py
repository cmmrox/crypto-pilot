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
