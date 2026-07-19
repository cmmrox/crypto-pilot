"""Integration tests for the bot lifecycle + evaluate path (QA-5)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from app.bot.service import BotService
from app.bot.state import BotStatus
from app.db.models import Candle
from app.execution.orders import OrderManager
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import OWNER_PHONE  # noqa: F401  (ensures conftest import)
from tests.fakes import FakeExchange

D = Decimal
STEP_MS = 4 * 60 * 60 * 1000


def _bull_candles(n: int = 300) -> list[Candle]:
    """A steadily-rising series (bull regime), as DB Candle objects."""
    out: list[Candle] = []
    base = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    price = 100.0
    for i in range(n):
        price *= 1.004
        out.append(
            Candle(
                symbol="BTCUSDT", interval="4h",
                open_time=base + dt.timedelta(hours=4 * i),
                open=Decimal(str(round(price * 0.999, 2))),
                high=Decimal(str(round(price * 1.004, 2))),
                low=Decimal(str(round(price * 0.996, 2))),
                close=Decimal(str(round(price, 2))),
                volume=Decimal("10"),
            )
        )
    return out


@pytest.mark.asyncio
async def test_start_creates_run_and_status_running(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    run = await svc.start(db_session, ex, by="owner@example.com")
    await db_session.commit()
    assert run.id is not None
    snap = await svc.status(db_session)
    assert snap.status == BotStatus.RUNNING


@pytest.mark.asyncio
async def test_start_twice_conflicts(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    with pytest.raises(RuntimeError, match="already running"):
        await svc.start(db_session, ex, by="o")


@pytest.mark.asyncio
async def test_reconcile_mismatch_starts_in_safe_mode(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    # Exchange reports an unexpected open position → mismatch → safe mode.
    await ex.place_market("BTCUSDT", "BUY", D("0.05"), client_order_id="x")
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    snap = await svc.status(db_session)
    assert snap.status == BotStatus.SAFE_MODE


@pytest.mark.asyncio
async def test_stop_leaves_position(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    await ex.place_market("BTCUSDT", "BUY", D("0.05"), client_order_id="e")
    # Start clean first (flat), then simulate a position, then stop.
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    await svc.stop(db_session, reason="user")
    await db_session.commit()
    assert (await svc.status(db_session)).status == BotStatus.STOPPED
    # Position remains on the exchange.
    assert (await ex.get_position("BTCUSDT")).qty == D("0.05")


@pytest.mark.asyncio
async def test_stop_and_close_flattens(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    om = OrderManager(ex)
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    await ex.place_market("BTCUSDT", "BUY", D("0.05"), client_order_id="e")
    await svc.stop_and_close(db_session, ex, om)
    await db_session.commit()
    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    assert (await svc.status(db_session)).status == BotStatus.STOPPED


@pytest.mark.asyncio
async def test_safe_mode_blocks_evaluate(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    om = OrderManager(ex)
    await svc.start(db_session, ex, by="o")
    await svc.enter_safe_mode(db_session, reason="test")
    await db_session.commit()
    actions = await svc.evaluate_once(db_session, ex, om, candles=_bull_candles())
    assert actions == []  # no entries in safe mode


@pytest.mark.asyncio
async def test_evaluate_opens_long_on_fresh_regime(db_session: AsyncSession) -> None:
    from app.strategies.engine import add_indicators

    svc = BotService()
    ex = FakeExchange(mark_price=D("150"))
    om = OrderManager(ex)
    await svc.start(db_session, ex, by="o")
    await db_session.commit()

    candles = _bull_candles(320)
    # Slice at the first fresh-regime bar so on_candle emits EnterLong.
    import pandas as pd

    df = add_indicators(
        pd.DataFrame(
            {
                "dt": [c.open_time for c in candles],
                "open": [float(c.open) for c in candles],
                "high": [float(c.high) for c in candles],
                "low": [float(c.low) for c in candles],
                "close": [float(c.close) for c in candles],
                "volume": [float(c.volume) for c in candles],
            }
        )
    )
    regime = df["regime"].to_numpy()
    fresh = next(i for i in range(1, len(regime)) if regime[i] and not regime[i - 1])
    ex.mark = Decimal(str(candles[fresh].close))
    actions = await svc.evaluate_once(db_session, ex, om, candles=candles[: fresh + 1])
    await db_session.commit()
    assert "open_long" in actions
    assert (await ex.get_position("BTCUSDT")).qty > 0


@pytest.mark.asyncio
async def test_every_close_reconciliation_blocks_new_risk(
    db_session: AsyncSession,
) -> None:
    svc = BotService()
    ex = FakeExchange()
    om = OrderManager(ex)
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    await ex.place_market(
        "BTCUSDT", "BUY", D("0.05"), client_order_id="out-of-band"
    )

    actions = await svc.evaluate_once(
        db_session, ex, om, candles=_bull_candles()
    )
    await db_session.commit()

    assert actions == ["safe_mode"]
    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE


@pytest.mark.asyncio
async def test_restart_resume_detects_open_run(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    # A fresh service instance (simulating restart) sees the open run as running.
    fresh = BotService()
    assert (await fresh.status(db_session)).status == BotStatus.RUNNING
