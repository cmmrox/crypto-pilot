"""Dedicated SHORT-side investigation, shorts ONLY (no longs), so the short
edge (if any) is visible in isolation.

Bear regime: close < SMA200 AND EMA50 < EMA200 (mirror of the long regime).
Entry styles:
  fresh  - bear regime turns on
  fade   - in bear regime: price rallies above EMA20, then closes back below
  both   - either
Management mirrors the long side: stop above, TP1 below (sell-to-cover half,
stop -> breakeven), then trail at lowest-low + trail*ATR. Exit if bear dies.
Fees 0.04%/side.
"""
import itertools

import pandas as pd

from backtest import FEE, add_indicators, load, summarize


def shorts_only(df, entry="both", stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5,
                trail_atr=3.0, name=None):
    df = df.copy()
    df["bear"] = (df["close"] < df["sma200"]) & (df["ema50"] < df["ema200"])
    equity, trades = [1.0], []
    cash, units = 1.0, 0.0          # short size in BTC units (positive number)
    entry_px = sl = tp1 = lowest = entry_eq = 0.0
    tp1_done = False
    was_above = False
    bear_prev = False

    def cover(px, frac=1.0):
        nonlocal cash, units
        amt = units * frac
        cash += amt * (2 * entry_px - px) * (1 - FEE)
        units -= amt

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]

        if units > 0:
            if not prev["bear"]:
                cover(o)
                trades.append({"pnl": cash - entry_eq})
            elif h >= sl:
                px = max(sl, o) if o > sl else sl
                cover(px)
                trades.append({"pnl": cash - entry_eq})
            else:
                if not tp1_done and l <= tp1:
                    fill = min(tp1, o)
                    cover(fill, tp1_frac)
                    tp1_done = True
                    sl = entry_px
                lowest = min(lowest, l)
                if tp1_done:
                    sl = min(sl, lowest + trail_atr * row["atr"])

        if units == 0.0 and prev["bear"] and not pd.isna(prev["sma200"]):
            fresh = not bear_prev
            fade = was_above and prev["close"] < prev["ema20"]
            trig = (entry in ("fresh", "both") and fresh) or (entry in ("fade", "both") and fade)
            if trig:
                entry_px = o
                d = stop_atr * prev["atr"]
                sl, tp1 = entry_px + d, entry_px - tp1_r * d
                lowest, tp1_done, entry_eq = l, False, cash
                units = cash * (1 - FEE) / entry_px
                cash = 0.0
                if h >= sl:
                    cover(sl)
                    trades.append({"pnl": cash - entry_eq})
                was_above = False

        if row["close"] > row["ema20"]:
            was_above = True
        elif units > 0:
            was_above = False
        bear_prev = bool(prev["bear"])

        eq = cash + (units * (2 * entry_px - cl) if units > 0 else 0.0)
        equity.append(eq)

    if units > 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize(name or "shorts", equity, trades, df)


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    bear_bars = ((df["close"] < df["sma200"]) & (df["ema50"] < df["ema200"])).sum()
    print(f"bear-regime bars: {bear_bars}/{len(df)} ({bear_bars/len(df)*100:.0f}% of time)")
    print(f"{'entry':<6} {'stop':>4} {'tp1R':>4} {'trail':>5} | {'ret':>8} {'pf':>5} {'n':>4} {'wr':>5} {'maxdd':>7}")
    rows = []
    for entry, stop, tp1r, trail in itertools.product(
            ["fresh", "fade", "both"], [2.0, 2.5, 3.0], [1.0, 1.5], [2.5, 3.0, 4.0]):
        s = shorts_only(df, entry=entry, stop_atr=stop, tp1_r=tp1r, trail_atr=trail)
        rows.append((entry, stop, tp1r, trail, s))
        print(f"{entry:<6} {stop:>4} {tp1r:>4} {trail:>5} | {s['return']*100:+7.1f}% {s['pf']:5.2f} {s['trades']:4d} {s['winrate']*100:4.0f}% {s['maxdd']*100:6.1f}%")
    best = max(rows, key=lambda r: r[4]["return"])
    print("\nBest short config:", best[:4], f"ret {best[4]['return']*100:+.1f}%  pf {best[4]['pf']:.2f}")
