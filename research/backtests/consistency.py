"""Experiments aimed at maximizing MONTHLY consistency:
1. Bear-regime SHORT module (same management, mirrored) — can down months become green?
2. Fractional position sizing — do smaller positions raise the +month count?
3. Combined long+short with reduced size.
Reports +months / worst month / return / Sharpe for each.
"""
import numpy as np
import pandas as pd

from backtest import FEE, add_indicators, load, managed, summarize, fmt


def managed_ls(df, stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5, trail_atr=4.0,  # v5 defaults

               size_frac=1.0, do_short=True, name=None):
    """Long module (as v5) + optional mirrored short module in bear regime.
    size_frac = fraction of equity deployed per trade (rest held in cash).
    """
    c = df["close"]
    df = df.copy()
    df["bear"] = (c < df["sma200"]) & (df["ema50"] < df["ema200"])

    equity, trades = [1.0], []
    cash, pos = 1.0, 0.0          # pos>0 long units, pos<0 short units
    entry_px = sl = tp1 = extreme = entry_eq = 0.0
    tp1_done = False
    was_below = was_above = False
    reg_prev = bear_prev = False

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]

        # ---- manage long ----
        if pos > 0:
            if not prev["regime"]:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                cash += pos * px * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            else:
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o)
                    sell = pos * tp1_frac
                    cash += sell * fill * (1 - FEE)
                    pos -= sell
                    tp1_done = True
                    sl = entry_px
                extreme = max(extreme, h)
                if tp1_done:
                    sl = max(sl, extreme - trail_atr * row["atr"])
        # ---- manage short ----
        elif pos < 0:
            def close_short(px):
                nonlocal cash, pos
                cash += (-pos) * (2 * entry_px - px) * (1 - FEE)  # short pnl mapping
                pos = 0.0
            if not prev["bear"]:
                close_short(o)
                trades.append({"pnl": cash - entry_eq})
            elif h >= sl:
                px = max(sl, o) if o > sl else sl
                close_short(px)
                trades.append({"pnl": cash - entry_eq})
            else:
                if not tp1_done and l <= tp1:
                    fill = min(tp1, o)
                    cover = (-pos) * tp1_frac
                    cash += cover * (2 * entry_px - fill) * (1 - FEE)
                    pos += cover
                    tp1_done = True
                    sl = entry_px
                extreme = min(extreme, l)
                if tp1_done:
                    sl = min(sl, extreme + trail_atr * row["atr"])

        # ---- entries ----
        if pos == 0.0 and not pd.isna(prev["sma200"]):
            if prev["regime"]:
                fresh = not reg_prev
                resume = was_below and prev["close"] > prev["ema20"]
                if fresh or resume:
                    entry_px = o
                    d = stop_atr * prev["atr"]
                    sl, tp1 = entry_px - d, entry_px + tp1_r * d
                    extreme, tp1_done, entry_eq = h, False, cash
                    alloc = cash * size_frac
                    units = alloc * (1 - FEE) / entry_px
                    pos = units
                    cash -= alloc
                    if l <= sl:
                        cash += pos * sl * (1 - FEE)
                        pos = 0.0
                        trades.append({"pnl": cash - entry_eq})
                    was_below = False
            elif do_short and prev["bear"]:
                fresh = not bear_prev
                resume = was_above and prev["close"] < prev["ema20"]
                if fresh or resume:
                    entry_px = o
                    d = stop_atr * prev["atr"]
                    sl, tp1 = entry_px + d, entry_px - tp1_r * d
                    extreme, tp1_done, entry_eq = l, False, cash
                    alloc = cash * size_frac
                    units = alloc * (1 - FEE) / entry_px
                    pos = -units
                    cash -= alloc
                    if h >= sl:
                        cash += units * (2 * entry_px - sl) * (1 - FEE)
                        pos = 0.0
                        trades.append({"pnl": cash - entry_eq})
                    was_above = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        if row["close"] > row["ema20"]:
            was_above = True
        elif pos < 0:
            was_above = False
        reg_prev, bear_prev = bool(prev["regime"]), bool(prev["bear"])

        if pos > 0:
            eq = cash + pos * cl
        elif pos < 0:
            eq = cash + (-pos) * (2 * entry_px - cl)
        else:
            eq = cash
        equity.append(eq)

    if pos != 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize(name or "LS", equity, trades, df)


def report(s):
    m = s["monthly"]
    worst = m.min() * 100 if len(m) else 0
    neg = (m < -0.001).sum()
    flat = ((m >= -0.001) & (m <= 0.001)).sum()
    print(fmt(s) + f"  worst_m {worst:+.1f}%  neg {neg}  flat {flat}")


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    print("--- monthly-consistency experiments (full 3y, fees incl.) ---")
    report(managed(df, trail_atr=4.0, name="v5 long-only (current)"))
    report(managed_ls(df, do_short=False, name="LS engine long-only (sanity)"))
    report(managed_ls(df, do_short=True, name="v5 + bear-regime shorts"))
    for f in (0.5, 0.75):
        report(managed_ls(df, do_short=True, size_frac=f, name=f"long+short size={f}"))
        report(managed_ls(df, do_short=False, size_frac=f, name=f"long-only size={f}"))
    # tighter short management (shorts in crypto need quicker profit-taking)
    report(managed_ls(df, do_short=True, stop_atr=2.0, tp1_r=1.0, tp1_frac=0.7,
                      trail_atr=2.5, name="L/S tighter shorts mgmt"))
