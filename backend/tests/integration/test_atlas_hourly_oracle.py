"""Real production bot/order/risk replay versus independently generated MIR oracle.

One-hour historical traded-price ranges execute stops first on ambiguous bars.
The engine files and committed input are hash pinned; fixtures contain no secrets.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from app.bot.service import BotService
from app.db.models import Candle
from app.execution.exchange import FundingIncome
from app.execution.orders import OrderManager
from app.execution.trade_sync import sync_open_trade
from app.services.settings_store import get_settings_row
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeExchange

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


async def test_production_execution_matches_independent_hourly_research(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = json.loads((FIXTURES / "atlas7_execution_oracle.json").read_text())
    for relative, checksum in metadata["hashes"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == checksum
    reference = subprocess.run(
        [sys.executable, str(ROOT / "qa/replay/run_atlas_oracle.py")],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    expected = json.loads(reference.stdout, parse_float=D)
    rows = list(csv.DictReader((FIXTURES / "atlas7_1h_2026.csv").open()))
    frame = pd.DataFrame(rows)
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
    frame = frame.set_index("dt")
    for key in ["open", "high", "low", "close", "volume"]:
        frame[key] = frame[key].astype(float)
    h4 = frame.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    candles = [
        Candle(
            symbol="BTCUSDT",
            interval="4h",
            closed=True,
            open_time=stamp.to_pydatetime(),
            **{k: D(str(row[k])) for k in ["open", "high", "low", "close", "volume"]},
        )
        for stamp, row in h4.iterrows()
    ]
    now = dt.datetime.fromisoformat(rows[0]["dt"])

    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:
            return now

    monkeypatch.setattr("app.execution.orders.dt", SimpleNamespace(datetime=Clock, UTC=dt.UTC))
    exchange = FakeExchange(
        mark_price=D(rows[0]["open"]),
        balance=D("1000"),
        book_fills=True,
        taker_fee=D("0.0007"),
        maker_fee=D("0.0002"),
        clock=lambda: now,
    )
    original_filters = await exchange.get_filters("BTCUSDT")

    # The oracle does continuous trigger-price arithmetic; 1e-8 ticks isolate rule
    # parity. Actual 0.1-tick rounding has separate contract tests.
    async def filters(_symbol: str):
        return replace(original_filters, tick_size=D("0.00000001"))

    monkeypatch.setattr(exchange, "get_filters", filters)
    settings = await get_settings_row(db_session)
    settings.active_strategy = "atlas_dual_v1_4h"
    service = BotService()
    orders = OrderManager(exchange, "BTCUSDT")
    run = await service.start(db_session, exchange, by="hourly-oracle")
    run.last_evaluated_candle_at = candles[399].open_time
    observed_reductions: list[tuple[int, str, D, D]] = []
    seen_reductions: set[str] = set()
    for hour, row in enumerate(rows):
        now = dt.datetime.fromisoformat(row["dt"])
        exchange.mark = D(row["open"])
        if hour >= 1604 and hour % 4 == 0:
            await service.evaluate_once(db_session, exchange, orders, candles=candles[: hour // 4])
        if exchange._pos != 0 and D(row["funding_rate"]) != 0:
            amount = -exchange._pos * exchange.mark * D(row["funding_rate"])
            exchange._balance += amount
            exchange._funding.append(FundingIncome(str(hour), amount, now))
        # Historical stop-first rule; only one category fills in a one-hour bar.
        candidates: list[tuple[bool, str, D]] = []
        for client_id, (side, _qty) in list(exchange._resting.items()):
            price = exchange.price_by_order[client_id]
            stop = client_id.startswith(("CPS-", "CPSR-"))
            touched = (
                (D(row["low"]) <= price if side == "SELL" else D(row["high"]) >= price)
                if stop
                else (D(row["high"]) >= price if side == "SELL" else D(row["low"]) <= price)
            )
            if touched:
                fill_px = (
                    (min(price, exchange.mark) if side == "SELL" else max(price, exchange.mark))
                    if stop
                    else (
                        max(price, exchange.mark) if side == "SELL" else min(price, exchange.mark)
                    )
                )
                candidates.append((stop, client_id, fill_px))
        if candidates:
            stop, client_id, price = sorted(candidates, key=lambda item: not item[0])[0]
            exchange.fill_resting(client_id, price=price)
            if stop:
                await exchange.cancel_all("BTCUSDT")
        exchange.mark = D(row["close"])
        await sync_open_trade(db_session, exchange, environment="DEMO", symbol="BTCUSDT")
        if hour == len(rows) - 1 and exchange._pos != 0:
            await orders.flatten(
                db_session,
                side="LONG" if exchange._pos > 0 else "SHORT",
                qty=abs(exchange._pos),
                reason="oracle final close",
            )
        account = await exchange.get_account()
        equity = account.balance + account.unrealized_pnl
        assert abs(equity - D(str(expected["equity"][hour]))) <= D("0.00001"), (
            hour,
            str(now),
            str(equity),
            expected["equity"][hour],
        )
        for order_id, fills in exchange._fills.items():
            if order_id in seen_reductions:
                continue
            for fill in fills:
                if fill.realized_pnl != 0:
                    observed_reductions.append((hour, fill.side, fill.qty, fill.price))
                    seen_reductions.add(order_id)
    assert len(observed_reductions) == len(expected["trades"]["exit_i"])
    for index, (hour, side, qty, price) in enumerate(observed_reductions):
        assert hour == expected["trades"]["exit_i"][index]
        assert side == ("SELL" if expected["trades"]["side"][index] > 0 else "BUY")
        assert abs(qty - D(str(expected["trades"]["qty"][index]))) <= D("0.00000001")
        assert abs(price - D(str(expected["trades"]["exit_px"][index]))) <= D("0.00000001")
