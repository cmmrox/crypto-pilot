"""Trend Rider v6 composite engine — faithful port of the validated research
engine (research/backtests/final_composite.py + backtest.py + research_ls.py +
short_lab.py). The parity gate (tests/parity) proves this reproduces the research
engine bar-for-bar.

Composite per-bar return: r = r_long + w * r_short_breaker, w = 0.75.
  - r_long: v5.2 managed long engine with 4% monthly breaker (fees 0.04%/side)
  - r_short: deep-bear vol-targeted sleeve (cost 0.05%/side) + 4% monthly breaker

Decisions use float64 (identical to the research engine). Money becomes Decimal
at the execution boundary (Stage 4), not here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Costs (identical to research)
FEE = 0.0004  # long engine, per side
COST = 0.0005  # short sleeve, per side (fee + slippage)
BARS_PER_YEAR = 2190

# Validated defaults (do not tune — the parity gate pins these)
STOP_ATR = 2.5
TP1_R = 1.0
TP1_FRAC = 0.4
TRAIL_ATR = 4.0
LONG_MONTH_CAP = 0.04
SLEEVE_DEPTH_ATR = 0.5
SLEEVE_VOL_TARGET = 0.40
SLEEVE_VOL_SPAN = 48
SLEEVE_WEIGHT = 0.75
SLEEVE_MONTH_CAP = 0.04


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach SMA200, EMA20/50/200, ATR14 and the bull regime flag.

    Identical to research backtest.add_indicators (the columns the engine uses).
    """
    df = df.copy()
    c = df["close"]
    df["sma200"] = c.rolling(200).mean()
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum((df["high"] - c.shift()).abs(), (df["low"] - c.shift()).abs()),
    )
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    df["regime"] = (c > df["sma200"]) & (df["ema50"] > df["ema200"])
    df["ret"] = c.pct_change().fillna(0.0)
    return df


def long_equity(df: pd.DataFrame) -> tuple[pd.Series, list[dict[str, object]]]:
    """v5.2 managed long engine + 4% monthly breaker. Returns (equity, trades).

    Line-for-line port of research circuit_breaker.managed_cb with the chosen
    params (tp1_frac=0.4, trail_atr=4.0, month_loss_cap=0.04).
    """
    equity: list[float] = [1.0]
    trades: list[dict[str, object]] = []
    cash, pos = 1.0, 0.0
    entry_px = sl = tp1 = highest = entry_eq = 0.0
    tp1_done = False
    was_below = False
    reg_prev = False
    month_start_eq = 1.0
    cur_month: tuple[int, int] | None = None
    halted = False

    rows = df.to_dict("records")
    for i in range(1, len(rows)):
        row, prev = rows[i], rows[i - 1]
        o, h, low, cl = row["open"], row["high"], row["low"], row["close"]
        dt_i = row["dt"]
        m = (dt_i.year, dt_i.month)
        if m != cur_month:
            cur_month = m
            month_start_eq = cash + (pos * cl if pos > 0 else 0.0)
            halted = False

        if pos > 0:
            if halted or not prev["regime"]:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq, "exit_i": i, "reason": "regime/halt"})
            elif low <= sl:
                px = min(sl, o) if o < sl else sl
                cash += pos * px * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq, "exit_i": i, "reason": "stop"})
            else:
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o)
                    sell = pos * TP1_FRAC
                    cash += sell * fill * (1 - FEE)
                    pos -= sell
                    tp1_done = True
                    sl = entry_px
                highest = max(highest, h)
                if tp1_done:
                    sl = max(sl, highest - TRAIL_ATR * row["atr"])

        if pos == 0.0 and not halted and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            if fresh or resume:
                entry_px = o
                d = STOP_ATR * prev["atr"]
                sl, tp1 = entry_px - d, entry_px + TP1_R * d
                highest, tp1_done, entry_eq = h, False, cash
                pos = cash * (1 - FEE) / entry_px
                cash = 0.0
                if low <= sl:
                    cash = pos * sl * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq, "exit_i": i, "reason": "same_bar_stop"})
                was_below = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = cash + (pos * cl if pos > 0 else 0.0)
        if eq < month_start_eq * (1 - LONG_MONTH_CAP):
            halted = True
        equity.append(eq)

    idx = pd.to_datetime(df["dt"].to_numpy(), utc=True)
    return pd.Series(equity, index=idx[: len(equity)]), trades


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    c = df["close"]
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum((df["high"] - c.shift()).abs(), (df["low"] - c.shift()).abs()),
    )
    return pd.Series(tr.ewm(alpha=1 / n, adjust=False).mean())


def short_target(df: pd.DataFrame) -> pd.Series:
    """s_deep(0.5): -1 while (close<SMA200 and EMA50<EMA200 and close<SMA200-0.5*ATR)."""
    c = df["close"]
    sma_ = c.rolling(200).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    ema200 = c.ewm(span=200, adjust=False).mean()
    bear = (c < sma_) & (ema50 < ema200)
    deep = bear & (c < sma_ - SLEEVE_DEPTH_ATR * _atr(df))
    return -deep.astype(float)


def _sleeve_raw_returns(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Vectorized sleeve returns (pre monthly breaker) and per-bar held exposure.

    Port of research_ls.backtest with vol_target=0.4, cap=1.0, vol_span=48.
    """
    ret = df["close"].pct_change().fillna(0.0)
    target = short_target(df)
    rv = (ret.ewm(span=SLEEVE_VOL_SPAN, adjust=False).std() * np.sqrt(BARS_PER_YEAR)).replace(
        0, np.nan
    )
    scale = (SLEEVE_VOL_TARGET / rv).clip(upper=1.0).fillna(0.0)
    pos = (target * scale).clip(-1.0, 1.0)
    pos_l = pos.shift(1).fillna(0.0)  # exposure held during the bar
    gross = pos_l * ret
    costs = pos.diff().abs().fillna(pos.abs()) * COST
    net = gross - costs.shift(1).fillna(0.0)
    eq = (1 + net).cumprod()
    return eq.pct_change().fillna(0.0), pos_l


def apply_month_breaker(
    r: pd.Series, cap: float = SLEEVE_MONTH_CAP, cost: float = COST
) -> pd.Series:
    """Zero out the rest of a month once the stream loses `cap` within it."""
    out = r.to_numpy(copy=True)
    idx = pd.DatetimeIndex(r.index)
    # tz-naive month grouping (same wall-clock months; avoids a tz-drop warning).
    month = idx.tz_localize(None).to_period("M")
    cum = 1.0
    cur = None
    halted = False
    for i in range(len(out)):
        if month[i] != cur:
            cur = month[i]
            cum, halted = 1.0, False
        if halted:
            out[i] = 0.0
            continue
        cum *= 1 + out[i]
        if cum < 1 - cap:
            halted = True
            out[i] -= cost
    return pd.Series(out, index=idx)


@dataclass
class CompositeResult:
    equity: pd.Series
    r_long: pd.Series
    r_short: pd.Series  # after breaker, before weighting
    short_exposure: pd.Series  # per-bar held short exposure (negative)
    trades: list[dict[str, object]]


def run_composite(df: pd.DataFrame, weight: float = SLEEVE_WEIGHT) -> CompositeResult:
    """Reproduce final_composite.py's CHOSEN config bar-for-bar."""
    df = add_indicators(df)
    long_eq, trades = long_equity(df)
    r_long = long_eq.pct_change().fillna(0.0)

    r_short_raw, exposure = _sleeve_raw_returns(df)
    r_short_raw.index = long_eq.index[: len(r_short_raw)]
    exposure.index = long_eq.index[: len(exposure)]
    r_short = apply_month_breaker(r_short_raw)

    r = r_long.add(weight * r_short, fill_value=0.0)
    eq = (1 + r).cumprod()
    return CompositeResult(
        equity=eq,
        r_long=r_long,
        r_short=r_short,
        short_exposure=exposure,
        trades=trades,
    )
