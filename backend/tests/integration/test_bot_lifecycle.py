"""Integration tests for the bot lifecycle + evaluate path (QA-5)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
import pytest
from app.bot.service import BotService
from app.bot.state import BotStatus
from app.db.models import Candle, EquitySnapshot, Event, Order, Trade
from app.execution.orders import (
    OrderManager,
    ProtectiveStopFailed,
    persist_emergency_exit,
)
from app.risk.sizing import SizingResult
from app.strategies.engine import add_indicators
from sqlalchemy import select
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
                symbol="BTCUSDT",
                interval="4h",
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
async def test_manual_start_baselines_latest_closed_candle_and_does_not_chase_it(
    db_session: AsyncSession,
) -> None:
    candles = _bull_candles(320)
    db_session.add_all(candles)
    await db_session.flush()
    svc = BotService()
    exchange = FakeExchange(mark_price=candles[-1].close)
    manager = OrderManager(exchange, symbol="BTCUSDT")

    run = await svc.start(db_session, exchange, by="owner")
    actions = await svc.evaluate_once(
        db_session,
        exchange,
        manager,
        candles=candles,
    )

    assert run.last_evaluated_candle_at == candles[-1].open_time
    assert actions == []
    assert (await exchange.get_position("BTCUSDT")).qty == 0


@pytest.mark.asyncio
async def test_missed_candle_gap_blocks_stale_entry_and_enters_safe_mode(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import notify_config

    notifications: list[str] = []

    async def capture(
        _session: AsyncSession,
        *,
        kind: str,
        payload: dict[str, object],
    ) -> str:
        notifications.append(kind)
        return "delivered"

    monkeypatch.setattr(notify_config, "notify_event", capture)
    candles = _bull_candles(320)
    svc = BotService()
    exchange = FakeExchange(mark_price=candles[-1].close)
    manager = OrderManager(exchange, symbol="BTCUSDT")
    run = await svc.start(db_session, exchange, by="owner")
    run.last_evaluated_candle_at = candles[-3].open_time

    actions = await svc.evaluate_once(
        db_session,
        exchange,
        manager,
        candles=candles,
    )

    assert actions == []
    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE
    assert (await exchange.get_position("BTCUSDT")).qty == 0
    assert run.last_evaluated_candle_at == candles[-1].open_time
    event = (
        await db_session.execute(
            select(Event).where(
                Event.message == "Missed closed-candle decision; stale entries blocked"
            )
        )
    ).scalar_one()
    assert event.payload_json["previous_candle"] == candles[-3].open_time.isoformat()
    assert notifications == ["bot_started", "error"]


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
    om = OrderManager(ex, symbol="BTCUSDT")
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    await ex.place_market("BTCUSDT", "BUY", D("0.05"), client_order_id="e")
    await svc.stop_and_close(db_session, ex, om)
    await db_session.commit()
    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    assert (await svc.status(db_session)).status == BotStatus.STOPPED


@pytest.mark.asyncio
async def test_kill_flattens_stops_run_and_notifies(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import notify_config

    kinds: list[str] = []

    async def capture(
        _session: AsyncSession,
        *,
        kind: str,
        payload: dict[str, object],
    ) -> str:
        kinds.append(kind)
        return "delivered"

    monkeypatch.setattr(notify_config, "notify_event", capture)
    svc = BotService()
    ex = FakeExchange()
    orders = OrderManager(ex, symbol="BTCUSDT")
    await svc.start(db_session, ex, by="owner")
    await ex.place_market("BTCUSDT", "SELL", D("0.05"), client_order_id="dust")

    await svc.kill(db_session, orders)

    assert (await ex.get_position("BTCUSDT")).qty == D("0")
    assert (await svc.status(db_session)).status == BotStatus.STOPPED
    assert kinds == ["bot_started", "kill_switch"]


@pytest.mark.asyncio
async def test_safe_mode_blocks_evaluate(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    om = OrderManager(ex, symbol="BTCUSDT")
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
    om = OrderManager(ex, symbol="BTCUSDT")
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
async def test_closed_candle_failure_notifies_owner_with_the_real_error(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: on 2026-07-30 and 2026-08-07 the real failure was silent.

    `_drive_bot` recorded `bot_drive_failed` but never notified, so the owner only
    learned four hours later from the missed-decision echo — with a message that
    named neither the rejection nor its cause.
    """
    import contextlib

    from app.bot.ingest import ingest_service
    from app.execution.binance_client import BinanceError
    from app.services import execution_service, notify_config
    from app.services.execution_service import ExecutionContext

    notifications: list[tuple[str, dict[str, object]]] = []

    async def capture(_session: AsyncSession, *, kind: str, payload: dict[str, object]) -> str:
        notifications.append((kind, payload))
        return "delivered"

    monkeypatch.setattr(notify_config, "notify_event", capture)

    svc = BotService()
    exchange = FakeExchange(mark_price=D("150"))

    async def reject_entry(*_args: object, **_kwargs: object) -> None:
        raise BinanceError("Margin is insufficient.", status=400, code=-2019)

    monkeypatch.setattr(exchange, "place_market", reject_entry)

    candles = _bull_candles(320)
    fresh = _fresh_regime_index(candles)
    for candle in candles[: fresh + 1]:
        db_session.add(candle)
    exchange.mark = Decimal(str(candles[fresh].close))
    await svc.start(db_session, exchange, by="o")
    run = await svc._current_run(db_session)
    assert run is not None
    run.last_evaluated_candle_at = None
    await db_session.commit()

    @contextlib.asynccontextmanager
    async def fake_context(_session: AsyncSession):  # type: ignore[no-untyped-def]
        yield ExecutionContext(
            environment="LIVE",
            market=__import__("app.strategies", fromlist=["get_strategy"])
            .get_strategy("trend_rider_v6_4h")
            .manifest.market,
            exchange=exchange,  # type: ignore[arg-type]
            orders=OrderManager(exchange, symbol="BTCUSDT"),
        )

    monkeypatch.setattr(execution_service, "execution_context", fake_context)

    await ingest_service._drive_bot(db_session, allow_new_entries=True)

    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE
    failure = (
        await db_session.execute(select(Event).where(Event.ref == "bot_drive_failed"))
    ).scalar_one()
    assert failure.payload_json["error"] == "Margin is insufficient."
    # The owner must be paged for the failure itself, carrying the real reason.
    assert [kind for kind, _ in notifications] == ["bot_started", "error"]
    assert "Margin is insufficient." in str(notifications[-1][1])


@pytest.mark.asyncio
async def test_long_entry_submits_tick_aligned_stop_and_take_profit(
    db_session: AsyncSession,
) -> None:
    """Regression: the 2026-07-30 LIVE long (Binance -1111).

    `stop_distance` is a float, so `mark - stop_distance` lands on sub-tick
    precision. The protective stop and TP1 must be rounded to `tick_size` before
    they reach the exchange, or the stop is rejected and the long is stranded.
    """
    svc = BotService()
    ex = FakeExchange(mark_price=D("150"))
    om = OrderManager(ex, symbol="BTCUSDT")
    await svc.start(db_session, ex, by="o")
    await db_session.commit()

    candles = _bull_candles(320)
    fresh = _fresh_regime_index(candles)
    # An off-tick mark guarantees an off-tick raw stop/TP (tick size is 0.10).
    ex.mark = Decimal("150.07")
    actions = await svc.evaluate_once(db_session, ex, om, candles=candles[: fresh + 1])
    await db_session.commit()

    assert "open_long" in actions
    tick = (await ex.get_filters("BTCUSDT")).tick_size
    assert ex.price_by_order, "no protective orders were submitted"
    for client_order_id, price in ex.price_by_order.items():
        assert price % tick == 0, f"{client_order_id} price {price} is not tick-aligned"


@pytest.mark.asyncio
async def test_every_close_reconciliation_blocks_new_risk(
    db_session: AsyncSession,
) -> None:
    svc = BotService()
    ex = FakeExchange()
    om = OrderManager(ex, symbol="BTCUSDT")
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    await ex.place_market("BTCUSDT", "BUY", D("0.05"), client_order_id="out-of-band")

    actions = await svc.evaluate_once(db_session, ex, om, candles=_bull_candles())
    await db_session.commit()

    assert actions == ["safe_mode"]
    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE


def _regime_flip_candles(
    flat_bars: int, trend_bars: int = 200, *, direction: int = 1
) -> list[Candle]:
    """Drift against the trend for `flat_bars`, then trend — the regime flips *after* warm-up.

    Releases declare different warm-up windows, so tests that need a fresh regime
    build the flip past the longest one instead of assuming a fixed history.
    """
    out: list[Candle] = []
    base = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    price = 100.0
    for i in range(flat_bars + trend_bars):
        if i < flat_bars:
            price *= 1 - 0.001 * direction
            shown = price * (1.003 if i % 2 else 0.997)
        else:
            price *= 1 + 0.006 * direction
            shown = price
        out.append(
            Candle(
                symbol="BTCUSDT",
                interval="4h",
                open_time=base + dt.timedelta(hours=4 * i),
                open=Decimal(str(round(shown * 0.999, 2))),
                high=Decimal(str(round(shown * 1.004, 2))),
                low=Decimal(str(round(shown * 0.996, 2))),
                close=Decimal(str(round(shown, 2))),
                volume=Decimal("10"),
            )
        )
    return out


def _first_entry_index(strategy_id: str, candles: list[Candle], *, side: str = "LONG") -> int:
    """First bar at which *this* release asks to open `side` from a flat account."""
    from app.strategies import EnterLong, EnterShort, EnterShortStop, get_strategy
    from app.strategies.base import Candle as StrategyCandle
    from app.strategies.base import TradeState

    wanted = (EnterLong,) if side == "LONG" else (EnterShort, EnterShortStop)
    strategy = get_strategy(strategy_id)
    window = [
        StrategyCandle(
            int(c.open_time.timestamp() * 1000),
            float(c.open),
            float(c.high),
            float(c.low),
            float(c.close),
            float(c.volume),
        )
        for c in candles
    ]
    for index in range(strategy.manifest.market.warmup_bars, len(window)):
        intents = strategy.on_candle(window[: index + 1], TradeState(equity=10_000.0))
        if any(isinstance(intent, wanted) for intent in intents):
            return index
    raise AssertionError(f"{strategy_id} produced no {side} entry over {len(window)} candles")


def _fresh_regime_index(candles: list[Candle]) -> int:
    """First bar where the trend regime flips on (so on_candle emits EnterLong)."""
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
    return next(i for i in range(1, len(regime)) if regime[i] and not regime[i - 1])


@pytest.mark.asyncio
async def test_protective_stop_failure_enters_safe_mode_and_records_fills(
    db_session: AsyncSession,
) -> None:
    """When the protective stop can't be placed, the closed-candle path enters safe
    mode AND durably records the entry + emergency-exit fills (audit trail survives
    the rollback), leaving a reconcilable flat position."""

    class StopFailingExchange(FakeExchange):
        async def place_stop_market(
            self, symbol, side, qty, stop_price, *, client_order_id, reduce_only=True
        ):
            raise RuntimeError("would immediately trigger")

    svc = BotService()
    ex = StopFailingExchange(mark_price=D("150"))
    om = OrderManager(ex, symbol="BTCUSDT")
    await svc.start(db_session, ex, by="o")
    await db_session.commit()

    candles = _bull_candles(320)
    fresh = _fresh_regime_index(candles)
    ex.mark = Decimal(str(candles[fresh].close))

    # The strategy emits EnterLong; the entry fills but the protective stop fails,
    # so open_long emergency-flattens and raises ProtectiveStopFailed.
    with pytest.raises(ProtectiveStopFailed) as excinfo:
        await svc.evaluate_once(db_session, ex, om, candles=candles[: fresh + 1])

    # Emulate _drive_bot's handler: roll back, enter safe mode, durably record, commit.
    await db_session.rollback()
    await svc.enter_safe_mode(db_session, reason="protective stop failed at candle close")
    await persist_emergency_exit(db_session, excinfo.value.record)
    await db_session.commit()

    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE
    assert (await ex.get_position("BTCUSDT")).qty == D("0")  # flattened on the exchange

    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert len(trades) == 1
    assert trades[0].closed_at is not None  # net-flat round trip recorded
    # Expected position stays consistent with the flat exchange → reconciles clean.
    assert await svc._expected_position(db_session) == D("0")

    failure_events = (
        (await db_session.execute(select(Event).where(Event.ref == f"trade:{trades[0].id}")))
        .scalars()
        .all()
    )
    assert len(failure_events) == 1
    assert failure_events[0].payload_json["stop_error"] == "would immediately trigger"


@pytest.mark.asyncio
async def test_restart_resume_detects_open_run(db_session: AsyncSession) -> None:
    svc = BotService()
    ex = FakeExchange()
    await svc.start(db_session, ex, by="o")
    await db_session.commit()
    # A fresh service instance (simulating restart) sees the open run as running.
    fresh = BotService()
    assert (await fresh.status(db_session)).status == BotStatus.RUNNING


@pytest.mark.asyncio
async def test_safe_mode_continues_tp_sync_and_stop_management(
    db_session: AsyncSession,
) -> None:
    svc = BotService()
    exchange = FakeExchange(mark_price=D("150"), balance=D("5000"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    await svc.start(db_session, exchange, by="owner")
    trade = await manager.open_long(
        db_session,
        sizing=SizingResult(D("1"), D("150"), D("0.03"), True, "ok"),
        stop_price=D("100"),
        tp1_price=D("160"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    tp = (
        await db_session.execute(
            select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
        )
    ).scalar_one()
    exchange.fill_resting(tp.client_order_id, price=D("160"))
    await svc.enter_safe_mode(db_session, reason="test management")

    candles = _bull_candles(320)
    exchange.mark = candles[-1].close
    actions = await svc.evaluate_once(
        db_session,
        exchange,
        manager,
        candles=candles,
    )

    assert "move_stop" in actions
    assert trade.remaining_qty == D("0.6")
    assert (await svc.status(db_session)).status == BotStatus.SAFE_MODE


@pytest.mark.asyncio
async def test_long_monthly_breaker_flattens_and_persists_halt(
    db_session: AsyncSession,
) -> None:
    svc = BotService()
    exchange = FakeExchange(mark_price=D("150"), balance=D("100"))
    manager = OrderManager(exchange, symbol="BTCUSDT")
    await svc.start(db_session, exchange, by="owner")
    trade = await manager.open_long(
        db_session,
        sizing=SizingResult(D("0.1"), D("15"), D("0.15"), True, "ok"),
        stop_price=D("90"),
        tp1_price=D("210"),
        tp1_fraction=D("0.4"),
        strategy="trend_rider_v6_4h",
        strategy_release="6.0",
        strategy_interval="4h",
    )
    candles = _bull_candles(320)
    current_close = candles[-1].open_time + dt.timedelta(hours=4)
    db_session.add(
        EquitySnapshot(
            ts=current_close - dt.timedelta(hours=4),
            environment="DEMO",
            balance=D("100"),
            unrealized_pnl=D("0"),
            month_to_date_pnl=D("0"),
            sleeve_month_pnl=D("0"),
        )
    )
    exchange.mark = D("100")  # -$5 unrealized = -5% of month-start equity

    actions = await svc.evaluate_once(
        db_session,
        exchange,
        manager,
        candles=candles,
    )

    assert actions == ["halt_long", "breaker_exit_long"]
    assert (await exchange.get_position("BTCUSDT")).qty == 0
    assert trade.closed_at is not None
    breaker = (
        await db_session.execute(select(Event).where(Event.ref == "breaker:LONG:2024-02"))
    ).scalar_one()
    assert D(breaker.payload_json["month_to_date_pnl"]) == D("-5")
