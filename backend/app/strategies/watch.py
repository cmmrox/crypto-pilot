"""Read-only owner projection of Trend Rider v6's latest closed-candle state.

This module uses the validated indicator functions but never emits intents and is
never imported by the trading path. It exists only to explain what the strategy is
watching on the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.strategies import engine
from app.strategies.base import Candle


@dataclass(frozen=True)
class StrategyWatch:
    last_closed_open_time_ms: int
    close: float
    ema20: float
    ema50: float
    ema200: float
    sma200: float
    atr14: float
    deep_bear_threshold: float
    long_regime: bool
    pullback_resume: bool
    deep_bear: bool


def inspect_strategy_watch(candles: list[Candle]) -> StrategyWatch | None:
    """Return the latest explainability snapshot after the 200-bar warmup."""
    if len(candles) < 200:
        return None

    frame = engine.add_indicators(_to_frame(candles))
    current = frame.iloc[-1]
    close = float(current["close"])
    sma200 = float(current["sma200"])
    ema50 = float(current["ema50"])
    ema200 = float(current["ema200"])
    atr14 = float(current["atr"])
    deep_bear_threshold = sma200 - engine.SLEEVE_DEPTH_ATR * atr14
    long_regime = bool(current["regime"])
    deep_bear = close < sma200 and ema50 < ema200 and close < deep_bear_threshold

    return StrategyWatch(
        last_closed_open_time_ms=candles[-1].open_time_ms,
        close=close,
        ema20=float(current["ema20"]),
        ema50=ema50,
        ema200=ema200,
        sma200=sma200,
        atr14=atr14,
        deep_bear_threshold=deep_bear_threshold,
        long_regime=long_regime,
        pullback_resume=_was_below_then_back(frame),
        deep_bear=deep_bear,
    )


def _to_frame(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dt": pd.to_datetime([c.open_time_ms for c in candles], unit="ms", utc=True),
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )


def _was_below_then_back(frame: pd.DataFrame) -> bool:
    """Match the live plugin's pullback-resumption state for the latest close."""
    previous = frame.iloc[-2]
    if not (float(previous["close"]) > float(previous["ema20"])):
        return False
    below = frame["close"] < frame["ema20"]
    regime = frame["regime"].to_numpy()
    for index in range(len(frame) - 2, 0, -1):
        if not regime[index]:
            break
        if bool(below.iloc[index]):
            return True
    return False
