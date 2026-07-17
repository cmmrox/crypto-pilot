"""Monthly loss circuit-breaker test: after the equity drops X% within a
calendar month, close everything and stay flat until the next month.
Directly targets worst-month size. Honest question: does it help or does it
just lock in losses before rebounds?
"""
import pandas as pd

from backtest import FEE, add_indicators, load, managed, summarize, fmt


def managed_cb(df, stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5, trail_atr=4.0,
               month_loss_cap=0.05, name=None):
    equity, trades = [1.0], []
    cash, pos = 1.0, 0.0
    entry_px = sl = tp1 = highest = entry_eq = 0.0
    tp1_done = False
    was_below = False
    reg_prev = False
    month_start_eq = 1.0
    cur_month = None
    halted = False

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
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o)
                    sell = pos * tp1_frac
                    cash += sell * fill * (1 - FEE)
                    pos -= sell
                    tp1_done = True
                    sl = entry_px
                highest = max(highest, h)
                if tp1_done:
                    sl = max(sl, highest - trail_atr * row["atr"])

        if pos == 0.0 and not halted and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            if fresh or resume:
                entry_px = o
                d = stop_atr * prev["atr"]
                sl, tp1 = entry_px - d, entry_px + tp1_r * d
                highest, tp1_done, entry_eq = h, False, cash
                pos = cash * (1 - FEE) / entry_px
                cash = 0.0
                if l <= sl:
                    cash = pos * sl * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq})
                was_below = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = cash + (pos * cl if pos > 0 else 0.0)
        if eq < month_start_eq * (1 - month_loss_cap):
            halted = True
        equity.append(eq)

    if pos > 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize(name or f"CB{month_loss_cap}", equity, trades, df)


def report(s):
    mo = s["monthly"]
    worst = mo.min() * 100 if len(mo) else 0
    neg = (mo < -0.001).sum()
    print(fmt(s) + f"  worst_m {worst:+.1f}%  neg {neg}")


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    report(managed(df, trail_atr=4.0, name="v5 (no breaker)"))
    for cap in (0.03, 0.04, 0.05, 0.07):
        report(managed_cb(df, month_loss_cap=cap, name=f"v5 + {cap*100:.0f}% monthly breaker"))
