"""Monthly breakers measure each book's loss including that book's own trading costs.

The validated model charges entry and exit costs to the book that trades. Every
decision's own orders must therefore reach the book's month-to-date P&L, and the
month-start base is the equity before the first decision of the month traded.
"""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from app.bot.service import BotService
from app.db.models import Candle, EquitySnapshot, Trade
from app.execution.orders import OrderManager
from app.services.settings_store import get_settings_row
from app.strategies import get_strategy
from app.strategies.base import Candle as StrategyCandle
from app.strategies.base import EnterLong, EnterShortStop, ExitAll, Intent, TradeState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "btcusdt_4h_2026.csv"
D = Decimal
COMMISSION = D("0.0004")
FOUR_HOURS = dt.timedelta(hours=4)
TP = ((1.0, 0.4),)


class _Scripted:
    """A registered release's manifest and risk, with intents scripted per decision."""

    def __init__(self, strategy_id: str, script: list[list[Intent]]) -> None:
        self.manifest = get_strategy(strategy_id).manifest
        self._script = script

    def on_candle(self, candles: list[StrategyCandle], state: TradeState) -> list[Intent]:
        return self._script.pop(0)


def _candles(count: int) -> list[Candle]:
    with FIXTURE.open() as handle:
        rows = list(csv.DictReader(handle))[:count]
    return [
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
        for row in rows
    ]


async def _bot(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    strategy_id: str,
    script: list[list[Intent]],
) -> tuple[BotService, FakeExchange, OrderManager, list[Candle]]:
    scripted = _Scripted(strategy_id, script)
    monkeypatch.setattr("app.bot.service.get_strategy", lambda _name: scripted)
    candles = _candles(40)  # all in March 2026: one month throughout
    session.add_all(candles)
    await session.flush()
    (await get_settings_row(session)).active_strategy = strategy_id
    exchange = FakeExchange(mark_price=D("60000"), balance=D("1000"), book_fills=True)
    orders = OrderManager(exchange, symbol="BTCUSDT")
    service = BotService()
    run = await service.start(session, exchange, by="qa")
    run.last_evaluated_candle_at = candles[19].open_time
    return service, exchange, orders, candles


async def _snapshot(session: AsyncSession, candle: Candle) -> EquitySnapshot:
    return (
        await session.execute(
            select(EquitySnapshot).where(EquitySnapshot.ts == candle.open_time + FOUR_HOURS)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_entry_and_exit_costs_count_toward_the_book(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, exchange, orders, candles = await _bot(
        db_session,
        monkeypatch,
        "trend_rider_v6_4h",
        [[EnterLong(stop_distance=1000.0, tp_levels=TP)], [ExitAll(reason="regime off")]],
    )

    assert await service.evaluate_once(db_session, exchange, orders, candles=candles[:21]) == [
        "open_long"
    ]
    trade = (await db_session.execute(select(Trade))).scalar_one()
    fee = trade.qty * trade.entry_px * COMMISSION
    assert (await _snapshot(db_session, candles[20])).month_to_date_pnl == -fee

    # Same mark: the round trip costs exactly its two commissions.
    assert await service.evaluate_once(db_session, exchange, orders, candles=candles[:22]) == [
        "exit_all"
    ]
    assert (await _snapshot(db_session, candles[21])).month_to_date_pnl == -2 * fee


@pytest.mark.asyncio
async def test_breaker_trips_on_the_loss_including_costs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 3.95% price loss plus the entry fee is past the 4% cap: the book must halt."""
    service, exchange, orders, candles = await _bot(
        db_session,
        monkeypatch,
        "trend_rider_v6_4h",
        [[EnterLong(stop_distance=1000.0, tp_levels=TP)], []],
    )
    await service.evaluate_once(db_session, exchange, orders, candles=candles[:21])
    trade = (await db_session.execute(select(Trade))).scalar_one()
    fee = trade.qty * trade.entry_px * COMMISSION
    price_loss = D("39.5")  # 3.95% of the 1000 month-start equity
    assert price_loss + fee > D("40")
    exchange.mark = D("60000") - price_loss / trade.qty

    actions = await service.evaluate_once(db_session, exchange, orders, candles=candles[:22])

    assert actions == ["halt_long", "breaker_exit_long"]


@pytest.mark.asyncio
async def test_reversal_charges_each_book_its_own_costs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, exchange, orders, candles = await _bot(
        db_session,
        monkeypatch,
        "atlas_dual_v1_4h",
        [
            [EnterLong(stop_distance=1000.0, tp_levels=TP)],
            [
                ExitAll(reason="reverse to short"),
                EnterShortStop(stop_distance=1000.0, tp_levels=TP),
            ],
        ],
    )
    await service.evaluate_once(db_session, exchange, orders, candles=candles[:21])
    await exchange.cancel_all("BTCUSDT")

    assert await service.evaluate_once(db_session, exchange, orders, candles=candles[:22]) == [
        "exit_all",
        "open_short",
    ]
    long_trade, short_trade = (await db_session.execute(select(Trade).order_by(Trade.id))).scalars()
    long_fees = 2 * long_trade.qty * long_trade.entry_px * COMMISSION
    short_fee = short_trade.qty * short_trade.entry_px * COMMISSION
    snapshot = await _snapshot(db_session, candles[21])
    assert snapshot.month_to_date_pnl == -long_fees
    assert snapshot.sleeve_month_pnl == -short_fee
