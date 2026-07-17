"""Pyramiding tests (Turtle-style adding to winners) + TP1 fraction sweep.

Variants on the v5.1 engine:
  - tp1_frac sweep: how much of the position to sell at 1R (v5.1 = 50%)
  - pyramid: when price reaches entry + add_r * risk, ADD add_frac * original
    size at that level; stop for the whole position moves to original entry.
    TP1 (if any) then applies at tp1_r from ORIGINAL entry as usual, sized on
    the original position; the combined rest trails at 4*ATR.

All with fees, conservative fills, 4% monthly breaker. IS/OOS validated.
"""
import numpy as np
import pandas as pd

from backtest import FEE, add_indicators, load, summarize


def run(df, stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5, trail_atr=4.0,
        add_r=None, add_frac=0.5, month_loss_cap=0.04, name="variant"):
    equity, trades = [1.0], []
    cash, pos = 1.0, 0.0
    pos0 = 0.0
    entry_px = sl = highest = entry_eq = 0.0
    risk_dist = 0.0
    tp1_done = added = False
    was_below = False
    reg_prev = False
    month_start_eq, cur_month, halted = 1.0, None, False

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]
        m = (row["dt"].year, row["dt"].month)
        if m != cur_month:
            cur_month = m
            month_start_eq = cash + (pos * cl if pos > 0 else 0)
            halted = False

        if pos > 0:
            if halted or not prev["regime"]:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                cash += pos * px * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            else:
                # pyramid add (before TP1; conservative: uses cash only)
                if add_r is not None and not added:
                    add_px = entry_px + add_r * risk_dist
                    if h >= add_px and cash > 0:
                        fill = max(add_px, o)
                        spend = min(cash, pos0 * add_frac * fill)
                        pos += spend * (1 - FEE) / fill
                        cash -= spend
                        added = True
                        sl = max(sl, entry_px)      # whole position BE
                if tp1_r is not None and not tp1_done:
                    tp_px = entry_px + tp1_r * risk_dist
                    if h >= tp_px:
                        fill = max(tp_px, o)
                        sell = min(pos, pos0 * tp1_frac)
                        cash += sell * fill * (1 - FEE)
                        pos -= sell
                        tp1_done = True
                        sl = max(sl, entry_px)
                highest = max(highest, h)
                trail_on = tp1_done if tp1_r is not None else (added or add_r is None)
                if trail_on and pos > 0:
                    sl = max(sl, highest - trail_atr * row["atr"])

        if pos == 0.0 and not halted and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            if fresh or resume:
                entry_px = o
                risk_dist = stop_atr * prev["atr"]
                sl = entry_px - risk_dist
                highest = h
                tp1_done = added = False
                entry_eq = cash
                if add_r is not None:
                    frac_in = 1.0 / (1.0 + add_frac)   # reserve cash for the add
                else:
                    frac_in = 1.0
                spend = cash * frac_in
                pos = spend * (1 - FEE) / entry_px
                pos0 = pos
                cash -= spend
                if l <= sl:
                    cash += pos * sl * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq})
                was_below = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = cash + (pos * cl if pos > 0 else 0.0)
        if month_loss_cap and eq < month_start_eq * (1 - month_loss_cap):
            halted = True
        equity.append(eq)

    if pos > 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize(name, equity, trades, df)


def line(s):
    mo = s["monthly"]
    worst = mo.min() * 100 if len(mo) else 0
    return (f"{s['name']:<44} ret {s['return']*100:+7.1f}%  shp {s['sharpe']:5.2f}  "
            f"dd {s['maxdd']*100:6.1f}%  n {s['trades']:3d}  wr {s['winrate']*100:4.0f}%  "
            f"pf {s['pf']:4.2f}  worst_m {worst:+5.1f}%")


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))

    print("=== TP1 fraction sweep (sell less, keep more runner) ===")
    print(line(run(df, name="v5.1 baseline (tp1 50%)")))
    for f in (0.3, 0.4, 0.6, 0.7):
        print(line(run(df, tp1_frac=f, name=f"tp1 sell {int(f*100)}%")))
    print(line(run(df, tp1_r=None, name="no TP1: trail-only after entry")))

    print("\n=== Pyramiding (add to winners at +addR) ===")
    for ar, af in [(1.0, 0.5), (1.0, 1.0), (0.5, 0.5), (1.5, 0.5)]:
        print(line(run(df, add_r=ar, add_frac=af,
                       name=f"pyramid add {int(af*100)}% at +{ar}R, tp1 50%")))
    for ar, af in [(1.0, 0.5), (1.0, 1.0)]:
        print(line(run(df, add_r=ar, add_frac=af, tp1_r=None,
                       name=f"pyramid {int(af*100)}% at +{ar}R, no TP1 (turtle)")))
