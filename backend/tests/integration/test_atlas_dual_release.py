"""Atlas 7 Dual release QA: the real bot loop replayed over real closed 4h candles.

Drives BotService.evaluate_once, the production OrderManager and the production risk
engine against a FakeExchange seeded with committed BTCUSDT candles (March-September
2026). Decisions are taken at each closed candle and executed at the next open, and
resting stop/take-profit orders are resolved against the following candle's range
(stop first when both could fill). This is execution-contract evidence, not a
profitability claim: fills are simulated and funding, latency and liquidity are absent.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from app.bot.service import BotService
from app.db.models import Candle, Event, Order, Trade
from app.execution.orders import OrderManager
from app.services.settings_store import get_settings_row
from app.strategies import get_strategy
from app.strategies.base import Candle as StrategyCandle
from app.strategies.base import EnterLong, EnterShortStop, TradeState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

STRATEGY = "atlas_dual_v1_4h"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "btcusdt_4h_2026.csv"
D = Decimal
WARMUP = 400  # AtlasDual manifest warmup_bars; asserted below


def _load_candles(limit: int | None = None) -> list[Candle]:
    rows: list[Candle] = []
    with FIXTURE.open() as handle:
        for row in csv.DictReader(handle):
            rows.append(
                Candle(
                    symbol="BTCUSDT",
                    interval="4h",
                    open_time=dt.datetime.fromisoformat(row["dt"]),
                    open=D(row["open"]),
                    high=D(row["high"]),
                    low=D(row["low"]),
                    close=D(row["close"]),
                    volume=D(row["volume"]),
                    closed=True,
                )
            )
    return rows[:limit] if limit else rows


@dataclass
class ReplayResult:
    actions: list[tuple[str, str]]  # (candle iso, action)
    entries: list[tuple[str, str]]  # (candle iso, LONG|SHORT)
    naked_bars: list[str]  # bars where a position had no active stop
    breaker_halts: int


async def _resolve_resting(exchange: FakeExchange, candle: Candle) -> None:
    """Fill resting stop/TP orders against one candle; the stop wins a tie."""
    while True:
        stop_hit: str | None = None
        tp_hit: str | None = None
        for client_order_id, (side, _qty) in list(exchange._resting.items()):
            price = exchange.price_by_order[client_order_id]
            is_stop = client_order_id.startswith(("CPS-", "CPSR-"))
            if is_stop:
                touched = candle.low <= price if side == "SELL" else candle.high >= price
                if touched:
                    stop_hit = client_order_id
            else:
                touched = candle.high >= price if side == "SELL" else candle.low <= price
                if touched:
                    tp_hit = client_order_id
        chosen = stop_hit or tp_hit
        if chosen is None:
            return
        exchange.fill_resting(chosen, price=exchange.price_by_order[chosen])
        if chosen == stop_hit:
            # A stop closes the position: nothing else may fill for this trade.
            await exchange.cancel_all("BTCUSDT")
            return


async def _replay(session: AsyncSession, *, bars: int, balance: str = "1000") -> ReplayResult:
    candles = _load_candles(bars)
    session.add_all(candles)
    await session.flush()
    (await get_settings_row(session)).active_strategy = STRATEGY
    service = BotService()
    exchange = FakeExchange(mark_price=candles[WARMUP].open, balance=D(balance))
    orders = OrderManager(exchange, symbol="BTCUSDT")
    run = await service.start(session, exchange, by="qa")
    # start() parks the cursor on the newest stored candle; rewind it to the end of
    # the warm-up so the replay evaluates every later candle exactly once.
    run.last_evaluated_candle_at = candles[WARMUP - 1].open_time

    result = ReplayResult(actions=[], entries=[], naked_bars=[], breaker_halts=0)
    for index in range(WARMUP, len(candles) - 1):
        execution_candle = candles[index + 1]
        exchange.mark = execution_candle.open  # decisions execute at the next open
        actions = await service.evaluate_once(
            session, exchange, orders, candles=candles[: index + 1]
        )
        stamp = candles[index].open_time.isoformat()
        for action in actions:
            result.actions.append((stamp, action))
            if action == "open_long":
                result.entries.append((stamp, "LONG"))
            elif action == "open_short":
                result.entries.append((stamp, "SHORT"))
            elif action == "breaker_exit_long" or action == "breaker_exit_short":
                result.breaker_halts += 1
        # Every open position must carry an active protective stop before the
        # market moves again.
        position = await exchange.get_position("BTCUSDT")
        if position.qty != 0:
            open_trade = await session.scalar(
                select(Trade).where(Trade.closed_at.is_(None)).order_by(Trade.id.desc()).limit(1)
            )
            active_stop = None
            if open_trade is not None:
                active_stop = await session.scalar(
                    select(Order.id).where(
                        Order.trade_id == open_trade.id,
                        Order.type == "STOP_MARKET",
                        Order.status.in_(("NEW", "PARTIALLY_FILLED")),
                    )
                )
            if active_stop is None:
                result.naked_bars.append(stamp)
        exchange.mark = execution_candle.close
        await _resolve_resting(exchange, execution_candle)
    await session.flush()
    return result


@pytest.mark.asyncio
async def test_manifest_warmup_matches_this_harness() -> None:
    assert get_strategy(STRATEGY).manifest.market.warmup_bars == WARMUP


@pytest.mark.asyncio
async def test_replay_trades_both_sides_with_a_stop_on_every_position(
    db_session: AsyncSession,
) -> None:
    result = await _replay(db_session, bars=1233)
    trades = (await db_session.execute(select(Trade).order_by(Trade.id))).scalars().all()
    assert trades, "the replay produced no trades"
    sides = {trade.side for trade in trades}
    assert sides == {"LONG", "SHORT"}, f"expected both books to trade, saw {sides}"
    assert result.naked_bars == [], f"position without an active stop at {result.naked_bars[:3]}"
    for trade in trades:
        stop_orders = (
            (
                await db_session.execute(
                    select(Order).where(Order.trade_id == trade.id, Order.type == "STOP_MARKET")
                )
            )
            .scalars()
            .all()
        )
        assert stop_orders, f"trade {trade.id} ({trade.side}) opened without a protective stop"
        limit_orders = (
            (
                await db_session.execute(
                    select(Order).where(Order.trade_id == trade.id, Order.type == "LIMIT")
                )
            )
            .scalars()
            .all()
        )
        assert limit_orders, f"trade {trade.id} opened without its take-profit"


@pytest.mark.asyncio
async def test_replay_matches_the_pure_strategy_decisions(db_session: AsyncSession) -> None:
    """Every bot entry happened on a candle where the strategy asked for it."""
    candles = _load_candles(700)
    result = await _replay(db_session, bars=700)
    strategy = get_strategy(STRATEGY)
    entry_stamps = {stamp for stamp, _side in result.entries}
    wanted: set[str] = set()
    for index in range(WARMUP, len(candles) - 1):
        window = [
            StrategyCandle(
                int(c.open_time.timestamp() * 1000),
                float(c.open),
                float(c.high),
                float(c.low),
                float(c.close),
                float(c.volume),
            )
            for c in candles[: index + 1]
        ]
        intents = strategy.on_candle(window, TradeState(equity=1000.0))
        if any(isinstance(i, EnterLong | EnterShortStop) for i in intents):
            wanted.add(candles[index].open_time.isoformat())
    assert entry_stamps, "no entries were taken"
    # The bot never invents an entry the flat-state strategy would not ask for.
    assert entry_stamps <= wanted, sorted(entry_stamps - wanted)[:5]


@pytest.mark.asyncio
async def test_replay_stops_ratchet_one_way_only(db_session: AsyncSession) -> None:
    await _replay(db_session, bars=1233)
    trades = (await db_session.execute(select(Trade).order_by(Trade.id))).scalars().all()
    checked = 0
    for trade in trades:
        stops = (
            (
                await db_session.execute(
                    select(Order)
                    .where(Order.trade_id == trade.id, Order.type == "STOP_MARKET")
                    .order_by(Order.id)
                )
            )
            .scalars()
            .all()
        )
        prices = [order.stop_price for order in stops if order.stop_price is not None]
        if len(prices) < 2:
            continue
        checked += 1
        if trade.side == "LONG":
            assert prices == sorted(prices), f"long stop moved down on trade {trade.id}"
        else:
            assert prices == sorted(prices, reverse=True), f"short stop rose on trade {trade.id}"
    assert checked > 0, "no trade ratcheted its stop; the trail was never exercised"


@pytest.mark.asyncio
async def test_replay_records_a_decision_for_every_closed_candle(
    db_session: AsyncSession,
) -> None:
    bars = 500
    await _replay(db_session, bars=bars)
    observations = (
        (
            await db_session.execute(
                select(Event).where(Event.category == "strategy", Event.ref.like("decision:%"))
            )
        )
        .scalars()
        .all()
    )
    assert len(observations) == bars - WARMUP - 1
    payload = observations[-1].payload_json
    assert payload["strategy_id"] == STRATEGY
    assert payload["interval"] == "4h"
    assert payload["state"]["equity"]


@pytest.mark.asyncio
async def test_monthly_breaker_halts_the_losing_book(db_session: AsyncSession) -> None:
    """An 8% monthly loss must stop that side until the month rolls over."""
    from app.risk.breakers import evaluate_breaker

    risk = get_strategy(STRATEGY).manifest.risk
    assert risk.long_monthly_loss_cap == D("0.08") == risk.short_monthly_loss_cap
    tripped = evaluate_breaker(
        month_start_equity=D("1000"), month_to_date_pnl=D("-81"), cap=risk.long_monthly_loss_cap
    )
    held = evaluate_breaker(
        month_start_equity=D("1000"), month_to_date_pnl=D("-79"), cap=risk.long_monthly_loss_cap
    )
    assert tripped.tripped and tripped.threshold == D("-80.00")
    assert not held.tripped
    # One stopped trade at 4% risk must not halt a side: that pairing is what
    # froze the live bot in August and September 2026.
    single_loss = evaluate_breaker(
        month_start_equity=D("1000"),
        month_to_date_pnl=D("-40") - D("1"),  # 4% risk plus costs
        cap=risk.long_monthly_loss_cap,
    )
    assert not single_loss.tripped


@pytest.mark.asyncio
async def test_reversal_closes_and_flips_in_one_decision(db_session: AsyncSession) -> None:
    result = await _replay(db_session, bars=1233)
    stamps = [stamp for stamp, action in result.actions]
    by_stamp: dict[str, list[str]] = {}
    for stamp, action in result.actions:
        by_stamp.setdefault(stamp, []).append(action)
    reversals = [
        stamp
        for stamp, actions in by_stamp.items()
        if "exit_all" in actions and ("open_long" in actions or "open_short" in actions)
    ]
    assert stamps, "no actions recorded"
    assert reversals, "the replay never exercised a same-decision reversal"
    for stamp in reversals:
        assert by_stamp[stamp].index("exit_all") < max(
            by_stamp[stamp].index(action)
            for action in by_stamp[stamp]
            if action in {"open_long", "open_short"}
        ), f"reversal at {stamp} opened before flattening"


@pytest.mark.asyncio
async def test_intent_vocabulary_is_stop_protected(db_session: AsyncSession) -> None:
    """This release must never emit the stop-free sleeve intents."""
    candles = _load_candles(900)
    strategy = get_strategy(STRATEGY)
    seen: set[str] = set()
    for index in range(WARMUP, len(candles), 7):
        window = [
            StrategyCandle(
                int(c.open_time.timestamp() * 1000),
                float(c.open),
                float(c.high),
                float(c.low),
                float(c.close),
                float(c.volume),
            )
            for c in candles[: index + 1]
        ]
        for state in (
            TradeState(equity=1000.0),
            TradeState(
                equity=1000.0,
                long_position=True,
                long_entry=60000.0,
                long_stop=58000.0,
                tp1_done=True,
                highest_high=70000.0,
            ),
            TradeState(
                equity=1000.0,
                short_position=True,
                short_entry=60000.0,
                short_stop=62000.0,
                tp1_done=True,
                lowest_low=55000.0,
            ),
        ):
            for intent in strategy.on_candle(window, state):
                seen.add(type(intent).__name__)
    assert "EnterShort" not in seen and "ResizeShort" not in seen
    assert seen <= {"EnterLong", "EnterShortStop", "ExitAll", "MoveStop"}
    assert {"EnterLong", "EnterShortStop"} & seen


@pytest.mark.asyncio
async def test_overview_breaker_meter_uses_this_release_cap(db_session: AsyncSession) -> None:
    """The console must show the release's own monthly cap, not a hardcoded 4%."""
    import datetime as dt

    from app.services.overview_service import _breaker_progress, _breaker_snapshots

    risk = get_strategy(STRATEGY).manifest.risk
    (await get_settings_row(db_session)).active_strategy = STRATEGY
    breakers, _realized = await _breaker_snapshots(
        db_session, dt.datetime.now(dt.UTC), D("1000"), risk
    )
    assert [row.cap_pct for row in breakers] == ["8.0", "8.0"]
    # Half of an 8% cap is a half-full meter, not a full one.
    assert _breaker_progress(D("-0.04"), risk.long_monthly_loss_cap) == "50.00"
    assert _breaker_progress(D("-0.08"), risk.long_monthly_loss_cap) == "100.00"


@pytest.mark.asyncio
async def test_decision_state_reports_each_stop_on_its_own_side(
    db_session: AsyncSession,
) -> None:
    """The strategy must never read a short's stop through ``long_stop`` (or vice versa)."""
    await _replay(db_session, bars=1233)
    payloads = (
        (
            await db_session.execute(
                select(Event.payload_json).where(
                    Event.category == "strategy", Event.ref.like("decision:%")
                )
            )
        )
        .scalars()
        .all()
    )
    states = [payload["state"] for payload in payloads]
    in_long = [state for state in states if state["long_position"]]
    in_short = [state for state in states if state["short_position"]]
    assert in_long and in_short, "the replay must hold both books at some point"
    assert all(s["long_stop"] is not None and s["short_stop"] is None for s in in_long)
    assert all(s["short_stop"] is not None and s["long_stop"] is None for s in in_short)
