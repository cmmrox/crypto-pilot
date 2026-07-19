"""Live DEMO round-trip against the real Binance testnet (QA-4, @exchange).

Skipped unless CP_BINANCE_DEMO_KEY / CP_BINANCE_DEMO_SECRET are set. Places a
minimal real order on the DEMO account (fake funds), verifies the position, then
flattens it — always cleaning up. This validates the BinanceExchange adapter and
the OrderManager against real exchange responses.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from app.execution.binance_client import BinanceClient
from app.execution.binance_exchange import BinanceExchange
from app.execution.filters import clamp_qty
from app.execution.orders import new_client_order_id
from app.execution.reconcile import reconcile_position

pytestmark = pytest.mark.exchange

KEY = os.environ.get("CP_BINANCE_DEMO_KEY")
SECRET = os.environ.get("CP_BINANCE_DEMO_SECRET")
SKIP = not (KEY and SECRET)
SYMBOL = "BTCUSDT"


@pytest.fixture()
async def exchange() -> AsyncIterator[BinanceExchange]:
    async with BinanceClient("DEMO", api_key=KEY, api_secret=SECRET) as client:
        yield BinanceExchange(client)


@pytest.mark.skipif(SKIP, reason="DEMO credentials not set")
@pytest.mark.asyncio
async def test_account_readable(exchange: BinanceExchange) -> None:
    acct = await exchange.get_account()
    assert acct.balance > 0  # DEMO account is funded


@pytest.mark.skipif(SKIP, reason="DEMO credentials not set")
@pytest.mark.asyncio
async def test_live_long_round_trip(exchange: BinanceExchange) -> None:
    """Open a minimal real long on DEMO, verify, then flatten. Always cleans up."""
    filters = await exchange.get_filters(SYMBOL)
    async with BinanceClient("DEMO", api_key=KEY, api_secret=SECRET) as md:
        price = Decimal(str((await md.get_klines(SYMBOL, "4h", limit=1))[0].close))

    # Minimal qty above min-notional (50 USDT) with a small safety margin.
    raw_qty = (filters.min_notional * Decimal("1.2")) / price
    qty = clamp_qty(raw_qty, filters)
    assert qty > 0

    try:
        entry = await exchange.place_market(
            SYMBOL, "BUY", qty, client_order_id=new_client_order_id("QAL")
        )
        assert entry.status in ("FILLED", "NEW", "PARTIALLY_FILLED")

        pos = await exchange.get_position(SYMBOL)
        assert pos.qty >= qty - filters.step_size  # position opened
        rec = await reconcile_position(exchange, SYMBOL, expected_qty=pos.qty)
        assert rec.matched
    finally:
        # Always flatten so the DEMO account returns to flat.
        pos = await exchange.get_position(SYMBOL)
        if pos.qty != 0:
            side = "SELL" if pos.qty > 0 else "BUY"
            await exchange.place_market(
                SYMBOL,
                side,
                abs(pos.qty),
                client_order_id=new_client_order_id("QAX"),
                reduce_only=True,
            )
    final = await exchange.get_position(SYMBOL)
    assert abs(final.qty) <= filters.step_size  # flat again


@pytest.mark.skipif(SKIP, reason="DEMO credentials not set")
@pytest.mark.asyncio
async def test_live_short_round_trip(exchange: BinanceExchange) -> None:
    """Open a minimal real short on DEMO (sleeve mechanics), verify, then cover."""
    filters = await exchange.get_filters(SYMBOL)
    async with BinanceClient("DEMO", api_key=KEY, api_secret=SECRET) as md:
        price = Decimal(str((await md.get_klines(SYMBOL, "4h", limit=1))[0].close))
    qty = clamp_qty((filters.min_notional * Decimal("1.2")) / price, filters)
    assert qty > 0
    try:
        entry = await exchange.place_market(
            SYMBOL, "SELL", qty, client_order_id=new_client_order_id("QASH")
        )
        assert entry.status in ("FILLED", "NEW", "PARTIALLY_FILLED")
        pos = await exchange.get_position(SYMBOL)
        assert pos.qty < 0  # short opened (negative)
    finally:
        pos = await exchange.get_position(SYMBOL)
        if pos.qty != 0:
            side = "SELL" if pos.qty > 0 else "BUY"
            await exchange.place_market(
                SYMBOL,
                side,
                abs(pos.qty),
                client_order_id=new_client_order_id("QAXS"),
                reduce_only=True,
            )
    assert abs((await exchange.get_position(SYMBOL)).qty) <= filters.step_size
