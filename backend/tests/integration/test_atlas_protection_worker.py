"""Exercise the actual worker transaction and safe-mode recovery boundaries."""

import datetime as dt
from contextlib import asynccontextmanager
from decimal import Decimal as D

import pytest
from app.bot import protection
from app.bot.state import BotStatus
from app.db.models import BotRun, Order
from app.execution.binance_client import BinanceError
from app.execution.orders import OrderManager
from app.services.execution_service import ExecutionContext
from app.strategies import get_strategy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange
from tests.integration.test_atlas_recovery import opened


def wire_worker(monkeypatch, session, exchange):
    @asynccontextmanager
    async def sessions():
        yield session

    @asynccontextmanager
    async def context(_session):
        yield ExecutionContext(
            environment="DEMO",
            market=get_strategy("atlas_dual_v1_4h").manifest.market,
            exchange=exchange,
            orders=OrderManager(exchange, "BTCUSDT"),
        )

    monkeypatch.setattr(protection, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr(protection, "execution_context", context)
    return protection.ProtectionService()


async def test_worker_protects_tp_fill_even_in_safe_mode(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    _trade, _stop, tp = await opened(db_session, exchange)
    db_session.add(
        BotRun(
            started_at=dt.datetime.now(dt.UTC),
            environment="DEMO",
            strategy="atlas_dual_v1_4h",
            stop_reason="safe_mode",
        )
    )
    await db_session.commit()
    worker = wire_worker(monkeypatch, db_session, exchange)
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    await worker.recover_once()
    active = await exchange.get_open_orders("BTCUSDT")
    assert len(active) == 1
    stop = await db_session.scalar(
        select(Order).where(Order.client_order_id == active[0].client_order_id)
    )
    assert stop is not None and stop.stop_price == D("60000")
    before = len(exchange.placed)
    await worker.recover_once()
    assert len(exchange.placed) == before
    assert (await protection.bot_service.status(db_session)).status == BotStatus.SAFE_MODE


async def test_stopped_worker_does_not_query_exchange(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def sessions():
        yield db_session

    @asynccontextmanager
    async def forbidden(_session):
        raise AssertionError("stopped bot must not enter execution context")
        yield

    monkeypatch.setattr(protection, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr(protection, "execution_context", forbidden)
    await protection.ProtectionService().recover_once()


async def test_failed_worker_blocks_entries_and_notifies_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    await opened(db_session, exchange)
    db_session.add(
        BotRun(started_at=dt.datetime.now(dt.UTC), environment="DEMO", strategy="atlas_dual_v1_4h")
    )
    await db_session.commit()
    worker = wire_worker(monkeypatch, db_session, exchange)
    notices = []

    async def notify(_session, **kwargs):
        notices.append(kwargs)

    async def failed(*args, **kwargs):
        raise BinanceError("exchange temporarily unavailable", code=-1001)

    monkeypatch.setattr("app.services.notify_config.notify_event", notify)
    monkeypatch.setattr(protection, "sync_open_trade", failed)
    for _ in range(2):
        with pytest.raises(BinanceError):
            await worker.recover_once()
        assert (await protection.bot_service.status(db_session)).status == BotStatus.SAFE_MODE
    assert len(notices) == 1
