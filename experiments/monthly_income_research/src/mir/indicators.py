"""Causal indicators on closed bars (value at bar k uses bars <= k only)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(x: pd.Series, n: int) -> pd.Series:
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(up.notna())


def zscore(x: pd.Series, n: int) -> pd.Series:
    m = x.rolling(n, min_periods=n).mean()
    s = x.rolling(n, min_periods=n).std(ddof=0)
    return (x - m) / s


def donchian_high(df: pd.DataFrame, n: int) -> pd.Series:
    """Highest high of the n bars *before* the current bar."""
    return df["high"].rolling(n, min_periods=n).max().shift(1)


def donchian_low(df: pd.DataFrame, n: int) -> pd.Series:
    return df["low"].rolling(n, min_periods=n).min().shift(1)


def efficiency_ratio(x: pd.Series, n: int) -> pd.Series:
    """Kaufman efficiency ratio: |net move| / sum(|moves|), 0 = chop, 1 = straight line."""
    net = (x - x.shift(n)).abs()
    path = x.diff().abs().rolling(n, min_periods=n).sum()
    return net / path.replace(0, np.nan)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def realized_vol(x: pd.Series, n: int) -> pd.Series:
    return np.log(x).diff().rolling(n, min_periods=n).std(ddof=0)
