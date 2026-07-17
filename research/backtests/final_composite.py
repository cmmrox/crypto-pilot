"""Final composite: v5.2 long engine (with 4% monthly breaker) + deep-bear
short sleeve (vol-targeted, optional sleeve-level monthly breaker).

Portfolio return per 4h bar: r = r_long + w * r_short.
"""
import numpy as np
import pandas as pd

import backtest as bt
from circuit_breaker import managed_cb
from research_ls import OOS_START, load, backtest as vec_bt, metrics, fmt
from short_lab import s_deep


def long_stream():
    df = bt.add_indicators(bt.load("btc_4h.csv"))
    s = managed_cb(df, tp1_frac=0.4, trail_atr=4.0, month_loss_cap=0.04,
                   name="v5.2 long+CB")
    eq = s["equity"]
    eq.index = pd.to_datetime(eq.index, utc=True)
    return eq.pct_change().fillna(0.0)


def sleeve_returns(df, vol_target=0.4):
    tgt = s_deep(df, 0.5)
    s = vec_bt(df, tgt, vol_target=vol_target, name="sleeve")
    return s["equity"].pct_change().fillna(0.0)


def apply_month_breaker(r, cap=0.04, cost=0.0005):
    """Zero out the rest of a month once the stream loses `cap` within it."""
    out = r.to_numpy(copy=True)
    idx = r.index
    month = idx.to_period("M")
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
            out[i] -= cost  # cost of closing the sleeve
    return pd.Series(out, index=idx)


def combo(name, r_long, r_short, w):
    r = r_long.add(w * r_short, fill_value=0.0)
    eq = (1 + r).cumprod()
    full = metrics(name + " FULL", eq)
    s_is = metrics(name + " IS", eq.loc[:OOS_START])
    oos_r = r.loc[OOS_START:]
    s_oos = metrics(name + " OOS", (1 + oos_r).cumprod())
    return full, s_is, s_oos, eq


if __name__ == "__main__":
    df = load()
    r_long = long_stream()
    r_long.index = df.index[: len(r_long)]
    r_short = sleeve_returns(df)

    print("--- long-only v5.2 + 4% breaker ---")
    for s in combo("long-only v5.2CB", r_long, r_short * 0, 0)[:3]:
        print(fmt(s))
    print()

    best_eq = None
    for cb in (None, 0.03, 0.04):
        rs = r_short if cb is None else apply_month_breaker(r_short, cb)
        tag = "noCB" if cb is None else f"CB{int(cb*100)}"
        for w in (0.5, 0.75, 1.0):
            full, s_is, s_oos, eq = combo(f"deep0.5vt40 {tag} w={w}", r_long, rs, w)
            print(fmt(full))
            print(fmt(s_is))
            print(fmt(s_oos))
            print()
            if cb == 0.04 and w == 0.75:
                best_eq = eq

    # monthly table + equity export for the chosen config
    full, s_is, s_oos, eq = combo("CHOSEN deep0.5vt40 CB4 w=0.75",
                                  r_long, apply_month_breaker(r_short, 0.04), 0.75)
    print("=== CHOSEN monthly returns ===")
    for ts, v in full["monthly"].items():
        print(f"  {ts.strftime('%Y-%m')}  {v*100:+7.2f}%")
    eq.to_frame("composite").join(
        (1 + r_long).cumprod().rename("long_only")).join(
        (1 + df["ret"]).cumprod().rename("buy_hold")).to_csv("composite_equity.csv")
    print("saved composite_equity.csv")
