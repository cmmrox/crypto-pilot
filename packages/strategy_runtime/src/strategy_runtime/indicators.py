"""Pure indicator calculations; legacy column names preserve v6 compatibility."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_runtime.parameters import TrendRiderParameters


def add_indicators(
    df: pd.DataFrame, params: TrendRiderParameters = TrendRiderParameters()
) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    df["sma200"] = close.rolling(params.slow_period).mean()
    df["ema20"] = close.ewm(span=params.fast_period, adjust=False).mean()
    df["ema50"] = close.ewm(span=params.medium_period, adjust=False).mean()
    df["ema200"] = close.ewm(span=params.slow_period, adjust=False).mean()
    true_range = np.maximum(
        df["high"] - df["low"],
        np.maximum((df["high"] - close.shift()).abs(), (df["low"] - close.shift()).abs()),
    )
    df["atr"] = true_range.ewm(alpha=1 / params.atr_period, adjust=False).mean()
    df["regime"] = (close > df["sma200"]) & (df["ema50"] > df["ema200"])
    df["ret"] = close.pct_change().fillna(0.0)
    return df
