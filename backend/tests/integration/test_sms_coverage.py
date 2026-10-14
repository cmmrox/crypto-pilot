"""Every owner-facing trading event sends its SMS (BSD FR-06, §8, §10).

Regression for the 2026-10-07 LIVE stop-out: a trade closed by its exchange-resident
stop was recorded but never reported. Each test asserts the SMS a real path sends,
rendered through the production template so placeholders cannot silently go blank.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.bot import deadman_monitor
from app.bot.service import BotService
from app.db.models import BotRun, Order, Trade
from app.execution.orders import OrderManager
from app.execution.trade_sync import sync_open_trade
from app.notifier.templates import render
from app.risk.sizing import SizingResult
from app.strategies.base import EnterShort, Halt, ResizeShort
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange
from tests.integration.test_atlas_recovery import opened
from tests.integration.test_breaker_cost_accounting import _bot

D = Decimal


@pytest.fixture
def sms(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    from app.services import notify_config

    sent: list[tuple[str, dict[str, object]]] = []

    async def capture(_session: AsyncSession, *, kind: str, payload: dict[str, object]) -> str:
        sent.append((kind, payload))
        return "delivered"

    monkeypatch.setattr(notify_config, "notify_event", capture)
    return sent


def _of(sent: list[tuple[str, dict[str, object]]], kind: str) -> list[str]:
    """Rendered messages of one kind, exactly as the owner's phone would show them."""
    return [render(k, payload) for k, payload in sent if k == kind]


async def _run(session: AsyncSession, *, safe: bool = False) -> BotRun:
    run = BotRun(
        started_at=dt.datetime.now(dt.UTC),
        environment="DEMO",
        strategy="atlas_dual_v1_4h",
        stop_reason="safe_mode" if safe else None,
    )
    session.add(run)
    await session.commit()
    return run


async def test_exchange_stop_fill_sends_trade_closed_sms_once(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, stop, _tp = await opened(db_session, exchange)

    exchange.fill_resting(stop.client_order_id, price=D("58950"))
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")

    closed = _of(sms, "trade_closed")
    assert trade.closed_at is not None and trade.exit_reason == "protective_stop"
    assert len(closed) == 1
    assert "LONG closed @ 58950" in closed[0]
    assert "(stop loss)" in closed[0]
    net = trade.realized_pnl - trade.fees + trade.funding
    assert f"P&L {net:+.2f} USDT net" in closed[0]
    assert "(DEMO)" in closed[0] and "—" not in closed[0]


async def test_tp1_fill_sends_one_sms_with_breakeven_protection(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    _trade, _stop, tp = await opened(db_session, exchange)

    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")

    [message] = _of(sms, "tp1_filled")
    assert "LONG TP1 filled 0.0016 BTC @ 62000" in message
    assert "Remaining 0.0024 BTC protected by stop 60000" in message
    assert _of(sms, "trade_closed") == []


async def test_stop_after_tp1_is_reported_as_trailing_stop(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, _stop, tp = await opened(db_session, exchange)
    exchange.fill_resting(tp.client_order_id, price=D("62000"))
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
    breakeven = await db_session.scalar(
        select(Order).where(
            Order.trade_id == trade.id, Order.type == "STOP_MARKET", Order.status == "NEW"
        )
    )
    assert breakeven is not None

    exchange.fill_resting(breakeven.client_order_id, price=D("60000"))
    await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")

    [message] = _of(sms, "trade_closed")
    assert "(trailing/breakeven stop after TP1)" in message


async def test_open_with_target_below_one_lot_still_sends_trade_opened(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    await OrderManager(exchange, "BTCUSDT").open_long(
        db_session,
        sizing=SizingResult(D("0.0002"), D("12"), D("0.2"), True, "ok"),
        stop_price=D("59000"),
        tp1_price=D("62000"),
        tp1_fraction=D("0.4"),
        stop_distance=D("1000"),
        tp1_r=D("2"),
        strategy="atlas_dual_v1_4h",
        strategy_release="1.2",
        strategy_interval="4h",
    )

    [message] = _of(sms, "trade_opened")
    assert "LONG opened 0.0002 BTC @ 60000" in message
    assert "below one lot" in message


async def test_bot_initiated_close_reports_net_pnl_and_month(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    trade, _stop, _tp = await opened(db_session, exchange)
    exchange.mark = D("61000")

    await OrderManager(exchange, "BTCUSDT").flatten(
        db_session, side="LONG", qty=D("0.004"), reason="regime exit"
    )

    [message] = _of(sms, "trade_closed")
    net = trade.realized_pnl - trade.fees + trade.funding
    assert "LONG closed @ 61000 (regime exit)" in message
    assert f"P&L {net:+.2f} USDT net" in message
    assert f"Month closed P&L: {net:+.2f} USDT" in message


async def test_safe_mode_pages_once_per_transition(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    await _run(db_session)
    svc = BotService()

    await svc.enter_safe_mode(db_session, reason="every-close reconciliation: mismatch")
    await svc.enter_safe_mode(db_session, reason="every-close reconciliation: mismatch")

    [message] = _of(sms, "safe_mode")
    assert "SAFE MODE (every-close reconciliation: mismatch)" in message


async def test_safe_mode_callers_with_their_own_alert_do_not_double_page(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    await _run(db_session)

    await BotService().enter_safe_mode(db_session, reason="evaluation failed", alert=False)

    assert sms == []


async def test_stop_sms_warns_that_an_open_position_is_unwatched(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"))
    await opened(db_session, exchange)
    await _run(db_session)

    await BotService().stop(db_session, reason="user")

    [message] = _of(sms, "bot_stopped")
    assert "Open LONG 0.004" in message
    assert "not tracked or alerted until the bot is started again" in message


async def test_start_sms_reports_equity_and_safe_mode(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    exchange = FakeExchange(mark_price=D("60000"), balance=D("190.18"))
    await exchange.place_market("BTCUSDT", "BUY", D("0.001"), client_order_id="CP-untracked")

    await BotService().start(db_session, exchange, by="owner")

    [message] = _of(sms, "bot_started")
    assert "equity 190.18 USDT" in message
    assert "SAFE MODE: position mismatch" in message


async def test_breaker_sms_names_the_book_and_its_cap(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    run = await _run(db_session)

    await BotService()._trip_breaker(
        db_session,
        run=run,
        book="LONG",
        month="2026-10",
        pnl=D("-16.40"),
        month_start_equity=D("200"),
        cap=D("0.08"),
    )

    [message] = _of(sms, "breaker")
    assert "LONG monthly loss cap hit (-16.40 USDT, -8.2% of month-start equity; cap -8%)" in (
        message
    )
    assert "-4%" not in message


async def test_short_sleeve_resize_sends_sms(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    sms: list[tuple[str, dict[str, object]]],
) -> None:
    service, exchange, orders, candles = await _bot(
        db_session,
        monkeypatch,
        "trend_rider_v6_4h",
        [[EnterShort(weight=0.3, vol_target=0.4)], [ResizeShort(target_weight=0.6)]],
    )
    await service.evaluate_once(db_session, exchange, orders, candles=candles[:21])
    await service.evaluate_once(db_session, exchange, orders, candles=candles[:22])

    [message] = _of(sms, "short_resized")
    assert "SHORT sleeve resized" in message
    assert "(60% of equity, vol drift)" in message


async def test_strategy_halt_sends_one_sms_per_halt(
    db_session: AsyncSession, sms: list[tuple[str, dict[str, object]]]
) -> None:
    decision = SimpleNamespace(session=db_session, actions=[])
    svc = BotService()

    await svc._halt(decision, Halt(until="2026-11"))  # type: ignore[arg-type]
    await db_session.flush()
    await svc._halt(decision, Halt(until="2026-11"))  # type: ignore[arg-type]

    assert _of(sms, "strategy_halt") == ["CryptoPilot: strategy halted new entries until 2026-11."]


async def test_independent_deadman_alert_and_recovery_name_the_problem(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import asynccontextmanager

    sent: list[str] = []

    async def capture(_session: AsyncSession, *, kind: str, payload: dict[str, object]) -> str:
        sent.append(render(kind, payload))
        return "delivered"

    @asynccontextmanager
    async def sessions():  # type: ignore[no-untyped-def]
        yield db_session

    monkeypatch.setattr(deadman_monitor, "notify_event", capture)
    monkeypatch.setattr(deadman_monitor, "get_sessionmaker", lambda: sessions)

    await deadman_monitor._alert(recovered=False, failures=3)
    await deadman_monitor._alert(recovered=True, failures=3)

    assert sent[0] == (
        "CryptoPilot ALERT: backend health check failed 3 times in a row; the bot may not "
        "be trading. Check the VPS and dashboard."
    )
    assert "recovered" in sent[1]
    assert all("—" not in message for message in sent)


async def test_closed_trade_month_total_excludes_other_environments(
    db_session: AsyncSession,
) -> None:
    from app.services.trade_alerts import month_closed_net_pnl

    now = dt.datetime.now(dt.UTC)

    def closed(environment: str, pnl: str) -> Trade:
        return Trade(
            opened_at=now,
            closed_at=now,
            side="LONG",
            entry_px=D("60000"),
            exit_px=D("60000"),
            qty=D("0.001"),
            fees=D("0.10"),
            funding=D("0"),
            realized_pnl=D(pnl),
            strategy="atlas_dual_v1_4h",
            environment=environment,
        )

    current = closed("LIVE", "5")
    db_session.add_all([closed("LIVE", "-2"), closed("DEMO", "100"), current])
    await db_session.flush()

    assert await month_closed_net_pnl(db_session, current) == D("2.80")


async def test_unrepaired_candle_gap_pages_when_a_decision_is_skipped(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    sms: list[tuple[str, dict[str, object]]],
) -> None:
    from contextlib import asynccontextmanager

    from app.bot import ingest

    @asynccontextmanager
    async def sessions():  # type: ignore[no-untyped-def]
        yield db_session

    class _Client:
        def __init__(self, _environment: str) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    async def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    async def one_gap(*_args: object, **_kwargs: object) -> list[object]:
        return [object()]

    monkeypatch.setattr(ingest, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr(ingest, "BinanceClient", _Client)
    monkeypatch.setattr(ingest.candle_svc, "backfill", nothing)
    monkeypatch.setattr(ingest.candle_svc, "repair_gaps", nothing)
    monkeypatch.setattr(ingest.candle_svc, "detect_gaps", one_gap)

    await ingest.CandleIngestService()._ingest_once(reason="candle_close")

    [message] = _of(sms, "health")
    assert "1 candle gap(s) could not be repaired" in message
    assert "trading decision was skipped" in message
