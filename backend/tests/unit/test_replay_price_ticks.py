"""Regression: offline protective prices must obey the live exchange adapter."""

from decimal import Decimal

import pandas as pd
from strategy_runtime.contracts import EnterLong
from strategy_runtime.filters import SymbolFilters, round_price
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig


def test_replay_stop_and_profit_target_use_live_tick_rounding() -> None:
    dates = pd.date_range("2024-01-01", periods=220, freq="4h", tz="UTC")
    candles = pd.DataFrame(
        {"dt": dates, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}
    )
    filters = SymbolFilters(
        Decimal("0.001"), Decimal("0.001"), Decimal("120"), Decimal("0.1"), Decimal("1")
    )
    replay = PluginReplayEngine(candles, pd.DataFrame(), filters, ReplayConfig(), start=dates[200])
    price, distance = Decimal("100.07"), Decimal("2.234")
    replay._open_long_from_intent(EnterLong(float(distance), ((1.0, 0.4),)), price, dates[200])
    assert replay.position is not None
    assert replay.position.stop == round_price(price - distance, filters.tick_size)
    assert replay.position.tp1 == round_price(price + distance, filters.tick_size)
