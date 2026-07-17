"""Short-sleeve laboratory: stop-free bear-regime shorts, tested in isolation.

Finding from sweep1: the raw 'short while bear regime' exposure made +15.6%
in the OOS bear year -- the old managed shorts failed because ATR stops got
whipsawed by bear rallies, not because the short edge is absent. Here we
refine the SLEEVE (exposure-based, no stops) and validate IS/OOS.
"""
import numpy as np
import pandas as pd

from research_ls import (COST, BARS_PER_YEAR, OOS_START, load, ema, atr,
                         realized_vol, backtest, metrics, fmt, split)


def bear_regime(df, sma=200, f=50, s=200):
    c = df["close"]
    sma_ = c.rolling(sma).mean()
    return (c < sma_) & (ema(c, f) < ema(c, s))


def rsi(df, n=14):
    d = df["close"].diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


# ---------------- sleeve variants: return target exposure in [-1, 0] --------
def s_plain(df):
    return -bear_regime(df).astype(float)


def s_confirm(df, k=6):
    b = bear_regime(df)
    return -(b.rolling(k).sum() == k).astype(float)


def s_deep(df, mult=1.0):
    c = df["close"]
    sma_ = c.rolling(200).mean()
    deep = bear_regime(df) & (c < sma_ - mult * atr(df))
    return -deep.astype(float)


def s_no_oversold(df, lo=27, hi=45):
    """Bear short, but step aside when RSI is oversold (crash exhaustion),
    re-enter when RSI recovers above hi."""
    b = bear_regime(df).values
    r = rsi(df).values
    out = np.zeros(len(df))
    active = True
    for i in range(len(df)):
        if not b[i]:
            active = True
            out[i] = 0.0
            continue
        if active and r[i] < lo:
            active = False
        elif not active and r[i] > hi:
            active = True
        out[i] = -1.0 if active else 0.0
    return pd.Series(out, index=df.index)


def s_fade(df):
    """In bear regime: short only while close < EMA20 (ride legs down, stand
    aside during rallies above EMA20). No stops."""
    b = bear_regime(df)
    below = df["close"] < ema(df["close"], 20)
    return -(b & below).astype(float)


def s_fade_sticky(df):
    """Enter short when close crosses below EMA20 in bear; cover only when
    close > EMA50 (wider exit to avoid churn)."""
    b = bear_regime(df).values
    c = df["close"].values
    e20 = ema(df["close"], 20).values
    e50 = ema(df["close"], 50).values
    out = np.zeros(len(df))
    p = 0.0
    for i in range(len(df)):
        if not b[i]:
            p = 0.0
        elif p == 0.0 and c[i] < e20[i]:
            p = -1.0
        elif p < 0 and c[i] > e50[i]:
            p = 0.0
        out[i] = p
    return pd.Series(out, index=df.index)


VARIANTS = {
    "plain bear": s_plain,
    "confirm k=6": lambda d: s_confirm(d, 6),
    "confirm k=12": lambda d: s_confirm(d, 12),
    "deep 0.5atr": lambda d: s_deep(d, 0.5),
    "deep 1atr": lambda d: s_deep(d, 1.0),
    "deep 2atr": lambda d: s_deep(d, 2.0),
    "no-oversold 27/45": s_no_oversold,
    "no-oversold 22/40": lambda d: s_no_oversold(d, 22, 40),
    "fade ema20": s_fade,
    "fade sticky 20/50": s_fade_sticky,
}

if __name__ == "__main__":
    df = load()
    print("SHORT SLEEVES IN ISOLATION (full size, no vol targeting)")
    for name, fn in VARIANTS.items():
        tgt = fn(df)
        is_, oos = split(df)
        s_full = backtest(df, tgt, name=f"{name} FULL")
        s_is = backtest(is_, tgt.loc[is_.index], name=f"{name} IS")
        s_oos = backtest(oos, tgt.loc[oos.index], name=f"{name} OOS")
        for s in (s_full, s_is, s_oos):
            print(fmt(s))
        print()

    print("\nWITH VOL TARGET 0.4 (short sleeve)")
    for name, fn in VARIANTS.items():
        tgt = fn(df)
        is_, oos = split(df)
        s_full = backtest(df, tgt, vol_target=0.4, name=f"{name} vt40 FULL")
        s_oos = backtest(oos, tgt.loc[oos.index], vol_target=0.4, name=f"{name} vt40 OOS")
        print(fmt(s_full))
        print(fmt(s_oos))
        print()
