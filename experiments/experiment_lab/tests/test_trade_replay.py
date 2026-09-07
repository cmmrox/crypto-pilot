"""Adversarial synthetic tapes prove ordering matters; they are not real data."""

from decimal import Decimal

import pandas as pd
import pytest

from strategy_runtime.contracts import EnterLong
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig
from strategy_runtime.trade_replay import TradeReplayEngine
from strategy_runtime.trend_rider import TrendRider


def engines(monkeypatch):
    timestamps = pd.date_range("2024-01-01", periods=401, freq="4h", tz="UTC")
    candles = pd.DataFrame(
        {
            "dt": timestamps,
            "open": 100,
            "high": 100,
            "low": 100,
            "close": 100,
            "volume": 1,
        }
    )
    candles.loc[400, ["high", "low"]] = [120, 80]
    funding = pd.DataFrame(columns=["dt", "funding_rate", "mark_price"])
    filters = SymbolFilters(
        Decimal("0.001"),
        Decimal("0.001"),
        Decimal("1000"),
        Decimal("0.1"),
        Decimal("1"),
    )
    monkeypatch.setattr(
        TrendRider,
        "on_prepared_frame",
        lambda self, frame, state: [EnterLong(10, ((1, 0.4),))],
    )
    config = ReplayConfig(initial_capital=Decimal("1000"))
    candle = PluginReplayEngine(candles, funding, filters, config, start=timestamps[-1])
    tape = TradeReplayEngine(candles, funding, filters, config, start=timestamps[-1])
    return candle, tape, timestamps[-1]


def test_actual_trade_order_can_differ_from_candle_stop_first(monkeypatch):
    candle, tape, start = engines(monkeypatch)
    tape.attach_trades(
        [
            (start, Decimal(100)),
            (start + pd.Timedelta(hours=1), Decimal(120)),
            (start + pd.Timedelta(hours=2), Decimal(80)),
            (start + pd.Timedelta(hours=3), Decimal(100)),
        ]
    )
    candle_result = candle.run()
    tape_result = tape.run()
    assert tape.actual_trade_count == 4
    assert tape_result.final_equity != candle_result.final_equity
    assert len(tape_result.trades) == 1
    assert Decimal(tape_result.trades.iloc[0]["fees"]) > 0


def test_trade_coverage_must_reconcile_with_every_candle(monkeypatch):
    _, tape, start = engines(monkeypatch)
    tape.attach_trades([(start, Decimal(100))])
    with pytest.raises(ValueError, match="does not reconcile"):
        tape.run()


def test_trade_replay_rejects_empty_tape(monkeypatch):
    _, tape, _ = engines(monkeypatch)
    tape.attach_trades([])
    with pytest.raises(ValueError, match="coverage"):
        tape.run()
