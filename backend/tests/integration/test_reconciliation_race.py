"""A stop can fill between REST order and position reads; it is not a manual trade."""

import datetime as dt
from dataclasses import replace
from decimal import Decimal as D

import pytest
from app.bot import protection
from app.bot.state import BotStatus
from app.db.models import BotRun, Event, Order
from app.execution import trade_sync
from app.execution.binance_client import BinanceError
from app.execution.exchange import OrderResult, Position
from app.execution.orders import OrderManager
from app.risk.sizing import SizingResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange
from tests.integration.test_atlas_protection_worker import wire_worker
from tests.integration.test_atlas_recovery import opened


@pytest.fixture(autouse=True)
def retry_waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(trade_sync, "sleep", sleep)
    return waits


class FillDuringOrderRead(FakeExchange):
    """Return a pre-fill order response while the next position read is post-fill."""

    fill_id: str | None = None
    fill_price = D("59000")

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult:
        result = await super().get_order(symbol, client_order_id)
        if client_order_id == self.fill_id:
            self.fill_id = None
            self.fill_resting(client_order_id, price=self.fill_price)
        return result


@pytest.mark.parametrize("already_safe", [False, True])
@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_stop_fill_race_recovers_without_latching_or_clearing_safe_mode(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    already_safe: bool,
    side: str,
    retry_waits: list[float],
) -> None:
    exchange = FillDuringOrderRead(mark_price=D("60000"))
    if side == "LONG":
        trade, stop, _tp = await opened(db_session, exchange)
    else:
        exchange.fill_price = D("61000")
        trade = await OrderManager(exchange, "BTCUSDT").open_short_with_stop(
            db_session,
            sizing=SizingResult(D("0.004"), D("240"), D("1"), True, "ok"),
            stop_price=D("61000"),
            tp1_price=D("58000"),
            tp1_fraction=D("0.4"),
            strategy="atlas_dual_v1_4h",
            strategy_release="1.2",
            strategy_interval="4h",
        )
        stop = await db_session.scalar(select(Order).where(Order.type == "STOP_MARKET"))
        assert stop is not None
    db_session.add(
        BotRun(
            started_at=dt.datetime.now(dt.UTC),
            environment="DEMO",
            strategy="atlas_dual_v1_4h",
            stop_reason="safe_mode" if already_safe else None,
        )
    )
    await db_session.commit()
    worker = wire_worker(monkeypatch, db_session, exchange)
    exchange.fill_id = stop.client_order_id
    before = len(exchange.placed)

    await worker.recover_once()

    assert (await protection.bot_service.status(db_session)).status == (
        BotStatus.SAFE_MODE if already_safe else BotStatus.RUNNING
    )
    assert trade.closed_at is not None
    assert trade.remaining_qty == D("0")
    assert trade.exit_reason == "protective_stop"
    assert (await exchange.get_position("BTCUSDT")).qty == D("0")
    assert not await exchange.get_open_orders("BTCUSDT")
    # Duplicate stream notification / periodic recovery cannot duplicate the close.
    await worker.recover_once()
    assert len(exchange.placed) == before
    events = (await db_session.scalars(select(Event).where(Event.ref == f"trade:{trade.id}"))).all()
    assert sum(e.message == f"{side} closed from synchronized exchange fills" for e in events) == 1
    assert not any(e.category == "bot" for e in (await db_session.scalars(select(Event))).all())
    audit = next(e for e in events if e.category == "reconciliation")
    assert audit.payload_json["recovered"] is True
    assert audit.payload_json["attempts"] == 2
    first, last = audit.payload_json["snapshots"]
    assert D(first["expected_qty"]) == (D("0.004") if side == "LONG" else D("-0.004"))
    assert D(first["actual_qty"]) == D("0")
    assert D(last["expected_qty"]) == D(last["actual_qty"]) == D("0")
    assert next(o for o in first["orders"] if o["id"] == stop.id)["status"] == "NEW"
    assert next(o for o in last["orders"] if o["id"] == stop.id)["status"] == "FILLED"
    assert retry_waits == [0.5]


async def running_worker(session, monkeypatch, exchange):
    session.add(
        BotRun(
            started_at=dt.datetime.now(dt.UTC),
            environment="DEMO",
            strategy="atlas_dual_v1_4h",
        )
    )
    await session.commit()
    return wire_worker(monkeypatch, session, exchange)


@pytest.mark.parametrize("partial", [False, True])
async def test_tp_fill_race_protects_remaining_without_duplicate_orders_or_alerts(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
) -> None:
    exchange = FillDuringOrderRead(mark_price=D("60000"))
    trade, old_stop, tp = await opened(db_session, exchange)
    worker = await running_worker(db_session, monkeypatch, exchange)
    notices = []

    async def notify(_session, **kwargs):
        notices.append(kwargs["kind"])

    monkeypatch.setattr("app.services.notify_config.notify_event", notify)
    exchange.fill_id = tp.client_order_id
    exchange.fill_price = D("62000")
    if partial:
        exchange._resting[tp.client_order_id] = ("SELL", tp.qty / 2)
        original_read = exchange.get_order

        async def partial_read(symbol, client_id):
            result = await original_read(symbol, client_id)
            if client_id == tp.client_order_id and result.status == "FILLED":
                return replace(result, status="PARTIALLY_FILLED")
            return result

        monkeypatch.setattr(exchange, "get_order", partial_read)
    await worker.recover_once()
    assert (await protection.bot_service.status(db_session)).status == BotStatus.RUNNING
    assert trade.remaining_qty == (D("0.0032") if partial else D("0.0024"))
    active = await exchange.get_open_orders("BTCUSDT")
    assert len(active) == 1
    active_stop = await db_session.scalar(
        select(Order).where(Order.client_order_id == active[0].client_order_id)
    )
    assert active_stop.stop_price == (D("59000") if partial else D("60000"))
    if not partial:
        assert active_stop.qty == D("0.0024")
        assert exchange._orders[old_stop.client_order_id].status == "CANCELED"
    placed = len(exchange.placed)
    await worker.recover_once()
    assert len(exchange.placed) == placed
    assert notices == ([] if partial else ["tp1_filled"])


@pytest.mark.parametrize("qty", [D("0"), D("0.002"), D("-0.004")])
async def test_persistent_unexplained_mismatch_stays_safe_and_keeps_protection(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    qty: D,
    retry_waits: list[float],
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, _stop, _tp = await opened(db_session, exchange)
    worker = await running_worker(db_session, monkeypatch, exchange)
    before = list(exchange.placed)
    exchange._pos = qty
    await worker.recover_once()
    assert (await protection.bot_service.status(db_session)).status == BotStatus.SAFE_MODE
    assert trade.closed_at is None
    assert trade.remaining_qty == D("0.004")
    assert exchange.placed == before
    assert len(await exchange.get_open_orders("BTCUSDT")) == 2
    audit = await db_session.scalar(select(Event).where(Event.category == "reconciliation"))
    assert audit.payload_json["recovered"] is False
    assert audit.payload_json["attempts"] == 3
    assert all(D(s["actual_qty"]) == qty for s in audit.payload_json["snapshots"])
    assert retry_waits == [0.5, 0.5]
    # A later matching snapshot must not silently clear an established safe mode.
    exchange._pos = D("0.004")
    await worker.recover_once()
    assert (await protection.bot_service.status(db_session)).status == BotStatus.SAFE_MODE


async def test_verification_failure_enters_safe_mode_without_mutating_orders(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = FillDuringOrderRead(mark_price=D("60000"))
    _trade, stop, _tp = await opened(db_session, exchange)
    worker = await running_worker(db_session, monkeypatch, exchange)
    exchange.fill_id = stop.client_order_id
    before = list(exchange.placed)

    async def failed_retry(_seconds):
        async def unavailable(*args):
            raise BinanceError("verification unavailable", code=-1001)

        monkeypatch.setattr(exchange, "get_order", unavailable)

    monkeypatch.setattr(trade_sync, "sleep", failed_retry)
    with pytest.raises(BinanceError, match="verification unavailable"):
        await worker.recover_once()
    assert (await protection.bot_service.status(db_session)).status == BotStatus.SAFE_MODE
    assert exchange.placed == before
    event = await db_session.scalar(select(Event).where(Event.ref == "protection_recovery"))
    assert event.payload_json["error_type"] == "BinanceError"


async def test_position_snapshot_lag_recovers_on_last_attempt(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    retry_waits: list[float],
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, stop, _tp = await opened(db_session, exchange)
    worker = await running_worker(db_session, monkeypatch, exchange)
    exchange.fill_resting(stop.client_order_id, price=D("59000"))
    truth = exchange.get_position
    calls = 0

    async def lagged(symbol):
        nonlocal calls
        calls += 1
        # Initial pre-read, then two stale confirmations; third confirmation agrees.
        return Position(symbol, D("0.004"), D("60000")) if calls <= 3 else await truth(symbol)

    monkeypatch.setattr(exchange, "get_position", lagged)
    await worker.recover_once()
    assert (await protection.bot_service.status(db_session)).status == BotStatus.RUNNING
    assert trade.closed_at is not None
    assert retry_waits == [0.5, 0.5]


async def test_candle_close_uses_same_fill_confirmation_before_decision(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration.test_bot_lifecycle import _bull_candles

    exchange = FillDuringOrderRead(mark_price=D("60000"))
    trade, stop, _tp = await opened(db_session, exchange)
    await running_worker(db_session, monkeypatch, exchange)
    exchange.fill_id = stop.client_order_id
    actions = await protection.bot_service.evaluate_once(
        db_session,
        exchange,
        OrderManager(exchange, "BTCUSDT"),
        candles=_bull_candles(410),
        allow_new_entries=False,
    )
    await db_session.commit()
    assert "safe_mode" not in actions
    assert (await protection.bot_service.status(db_session)).status == BotStatus.RUNNING
    assert trade.closed_at is not None


async def test_matched_snapshot_does_not_wait_or_emit_retry_audit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    retry_waits: list[float],
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    await opened(db_session, exchange)
    worker = await running_worker(db_session, monkeypatch, exchange)
    await worker.recover_once()
    assert retry_waits == []
    assert not (
        await db_session.scalars(select(Event).where(Event.category == "reconciliation"))
    ).all()
