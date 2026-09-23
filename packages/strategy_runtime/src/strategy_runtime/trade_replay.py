"""Actual-trade-price replay using the same closed-bar strategy and accounting.

Actual prints establish event ordering, not queue position or guaranteed fills.
No price stop is introduced for the short sleeve. Liquidation is not modeled.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import Any

import pandas as pd

from strategy_runtime.parameters import INTERVAL_MINUTES
from strategy_runtime.replay import PluginReplayEngine


class TradeReplayEngine(PluginReplayEngine):
    def attach_trades(self, trades: Iterable[tuple[pd.Timestamp, Decimal]]) -> None:
        self._ticks: Iterator[tuple[pd.Timestamp, Decimal]] = iter(trades)
        self._next_tick = next(self._ticks, None)
        self._bar_ticks: list[tuple[pd.Timestamp, Decimal]] = []
        self._funding_cursor = 0
        self._funding_rows = list(self.funding.sort_values("dt").to_dict("records"))
        self.actual_trade_count = 0

    def _apply_funding_at_open(self, timestamp: pd.Timestamp, fallback_price: Decimal) -> None:
        self._apply_funding_until(timestamp, fallback_price)

    def _apply_funding_until(self, timestamp: pd.Timestamp, fallback_price: Decimal) -> None:
        while self._funding_cursor < len(self._funding_rows):
            row = self._funding_rows[self._funding_cursor]
            if row["dt"] > timestamp:
                break
            self._funding_cursor += 1
            if row["dt"] < self.start or self.position is None:
                continue
            mark = row["mark_price"]
            if not mark.is_finite() or mark <= 0:
                raise ValueError("Trade replay requires actual funding mark prices")
            notional = self.position.qty * mark
            payment = notional * row["funding_rate"] * (-1 if self.position.side == "LONG" else 1)
            self.cash += payment
            self.position.funding += payment
            self.funding_events_applied += 1

    def _process_open(self, i: int, row: pd.Series[Any], prev: pd.Series[Any]) -> None:
        start = pd.Timestamp(row["dt"])
        end = start + pd.Timedelta(minutes=INTERVAL_MINUTES[self.config.interval])
        # Keep only one candle's real prints in memory; whole-history archives stream.
        self._bar_ticks = []
        while self._next_tick is not None and self._next_tick[0] < end:
            if self._next_tick[0] < start:
                raise ValueError("Trade stream precedes requested replay window")
            self._bar_ticks.append(self._next_tick)
            self._next_tick = next(self._ticks, None)
        if not self._bar_ticks:
            raise ValueError("Trade replay has a candle without actual trade coverage")
        prices = [tick[1] for tick in self._bar_ticks]
        observed = (prices[0], max(prices), min(prices), prices[-1])
        expected = tuple(Decimal(str(row[key])) for key in ("open", "high", "low", "close"))
        if observed != expected:
            raise ValueError("Actual trade OHLC does not reconcile with Binance candle")
        timestamp, price = self._bar_ticks[0]
        self._apply_funding_until(timestamp, price)
        execution = row.copy()
        execution["open"] = str(price)
        execution["dt"] = timestamp
        super()._process_open(i, execution, prev)

    def _process_intrabar(self, i: int, row: pd.Series[Any]) -> None:
        for timestamp, price in self._bar_ticks:
            self._apply_funding_until(timestamp, price)
            tick = pd.Series({"dt": timestamp, "open": price, "high": price, "low": price})
            super()._process_intrabar(i, tick)
            self.actual_trade_count += 1
        end = pd.Timestamp(row["dt"]) + pd.Timedelta(minutes=INTERVAL_MINUTES[self.config.interval])
        self._apply_funding_until(end - pd.Timedelta(milliseconds=1), Decimal(str(row["close"])))
