"""Exercise the actual worker transaction and safe-mode recovery boundaries."""

import datetime as dt
from contextlib import asynccontextmanager
from decimal import Decimal as D

import pytest
from app.bot import protection
from app.bot.state import BotStatus
from app.db.models import BotRun, Event, Order
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


async def running_worker(db_session, monkeypatch, exchange=None):
    """An open tracked trade, a RUNNING bot, and captured owner notifications."""
    exchange = exchange or FakeExchange(mark_price=D("60000"))
    await opened(db_session, exchange)
    db_session.add(
        BotRun(started_at=dt.datetime.now(dt.UTC), environment="DEMO", strategy="atlas_dual_v1_4h")
    )
    await db_session.commit()
    worker = wire_worker(monkeypatch, db_session, exchange)
    notices: list[dict] = []

    async def notify(_session, **kwargs):
        notices.append(kwargs)

    monkeypatch.setattr("app.services.notify_config.notify_event", notify)
    return worker, notices


def failing_sync(monkeypatch, failures, *, before=None):
    """Make the next `failures` syncs raise; later syncs run for real."""
    real = protection.sync_open_trade
    remaining = [failures]

    async def sync(session, exchange, **kwargs):
        if remaining[0] == 0:
            return await real(session, exchange, **kwargs)
        remaining[0] -= 1
        if before is not None:
            await before(exchange)
        raise transient_read_error()

    monkeypatch.setattr(protection, "sync_open_trade", sync)


def transient_read_error() -> BinanceError:
    return BinanceError(
        "Server is currently overloaded with other requests.",
        status=503,
        code=-1008,
        endpoint="GET /fapi/v1/income",
        transient=True,
    )


async def status(db_session):
    return (await protection.bot_service.status(db_session)).status


async def recovery_events(db_session):
    rows = await db_session.scalars(
        select(Event).where(Event.ref == "protection_recovery").order_by(Event.id)
    )
    return list(rows)


async def test_single_transient_read_failure_keeps_bot_running(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: 2026-11-17 16:00 UTC one rejected read latched LIVE safe mode."""
    worker, notices = await running_worker(db_session, monkeypatch)
    failing_sync(monkeypatch, 1)

    await worker.recover_once()
    assert await status(db_session) == BotStatus.RUNNING
    await worker.recover_once()
    assert await status(db_session) == BotStatus.RUNNING

    assert notices == []
    [event] = await recovery_events(db_session)
    assert event.level == "WARN"
    assert event.payload_json["binance_status"] == 503
    assert event.payload_json["binance_code"] == -1008
    assert event.payload_json["endpoint"] == "GET /fapi/v1/income"
    assert event.payload_json["consecutive_failures"] == 1


async def test_persistent_transient_failures_enter_safe_mode_and_notify_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, notices = await running_worker(db_session, monkeypatch)
    failing_sync(monkeypatch, 99)
    threshold = protection.SAFE_MODE_AFTER_TRANSIENT_FAILURES

    for _ in range(threshold - 1):
        await worker.recover_once()
        assert await status(db_session) == BotStatus.RUNNING
    for _ in range(2):
        with pytest.raises(BinanceError):
            await worker.recover_once()
        assert await status(db_session) == BotStatus.SAFE_MODE

    assert len(notices) == 1
    events = await recovery_events(db_session)
    # One warning for the streak, then one error per failure in safe mode.
    assert [e.level for e in events] == ["WARN", "ERROR", "ERROR"]
    blocked = events[1].payload_json
    assert blocked["consecutive_failures"] == threshold
    assert blocked["transient"] is True
    assert blocked["mutation_attempted"] is False
    assert blocked["endpoint"] == "GET /fapi/v1/income"
    assert "error" in blocked


async def test_successful_check_resets_the_failure_streak(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, notices = await running_worker(db_session, monkeypatch)
    threshold = protection.SAFE_MODE_AFTER_TRANSIENT_FAILURES
    failing_sync(monkeypatch, threshold - 1)
    for _ in range(threshold):  # failures, then one success
        await worker.recover_once()
    failing_sync(monkeypatch, threshold - 1)
    for _ in range(threshold - 1):
        await worker.recover_once()

    assert await status(db_session) == BotStatus.RUNNING
    assert notices == []
    assert [e.level for e in await recovery_events(db_session)] == ["WARN", "WARN"]


@pytest.mark.parametrize(
    "error",
    [
        BinanceError(
            "Invalid API-key, IP, or permissions for action.",
            status=401,
            code=-2015,
            endpoint="GET /fapi/v2/account",
        ),
        RuntimeError("unexpected"),
    ],
    ids=["binance-rejection", "unexpected"],
)
async def test_definitive_failure_blocks_entries_and_notifies_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    worker, notices = await running_worker(db_session, monkeypatch)

    async def failed(*args, **kwargs):
        raise error

    monkeypatch.setattr(protection, "sync_open_trade", failed)
    for _ in range(2):
        with pytest.raises(type(error)):
            await worker.recover_once()
        assert await status(db_session) == BotStatus.SAFE_MODE
    assert len(notices) == 1
    event = (await recovery_events(db_session))[0]
    assert event.level == "ERROR"
    assert event.payload_json["error_type"] == type(error).__name__
    assert event.payload_json["consecutive_failures"] == 1


async def test_failure_after_an_order_action_blocks_entries_immediately(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rolled-back check that already acted on the exchange needs owner review."""
    worker, notices = await running_worker(db_session, monkeypatch)

    async def act(exchange):
        await exchange.cancel_all("BTCUSDT")

    failing_sync(monkeypatch, 1, before=act)
    with pytest.raises(BinanceError):
        await worker.recover_once()

    assert await status(db_session) == BotStatus.SAFE_MODE
    assert len(notices) == 1
    [event] = await recovery_events(db_session)
    assert event.payload_json["mutation_attempted"] is True


async def test_recovery_event_never_carries_credentials_or_signed_query(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, _notices = await running_worker(db_session, monkeypatch)
    failing_sync(monkeypatch, 1)
    await worker.recover_once()
    [event] = await recovery_events(db_session)
    assert set(event.payload_json) <= {
        "error_type",
        "error",
        "binance_status",
        "binance_code",
        "endpoint",
        "transient",
        "mutation_attempted",
        "consecutive_failures",
        "threshold",
        "event_time_ms",
    }
    text = str(event.payload_json)
    for forbidden in ("signature", "timestamp=", "listenKey", "X-MBX-APIKEY"):
        assert forbidden not in text
