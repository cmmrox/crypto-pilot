"""Robustness battery for the chosen composite:
  long  = v5.2 managed + 4% monthly breaker
  short = deep-bear sleeve (SMA200 - d*ATR, bear EMAs), vol-target vt,
          sleeve 4% monthly breaker, weight w
Checks: parameter neighborhoods, cost sensitivity, other coins.
"""
import numpy as np
import pandas as pd

import backtest as bt
import research_ls
from circuit_breaker import managed_cb
from research_ls import OOS_START, backtest as vec_bt, metrics, fmt
from short_lab import s_deep
from final_composite import apply_month_breaker


def build(csv, depth=0.5, vt=0.4, w=0.75, cb=0.04, tp1_frac=0.4):
    dfi = bt.add_indicators(bt.load(csv))
    s = managed_cb(dfi, tp1_frac=tp1_frac, trail_atr=4.0, month_loss_cap=0.04)
    r_long = s["equity"].pct_change().fillna(0.0)
    df = research_ls.load(csv)
    r_long.index = df.index[: len(r_long)]
    tgt = s_deep(df, depth)
    r_short = vec_bt(df, tgt, vol_target=vt, name="s")["equity"].pct_change().fillna(0.0)
    if cb:
        r_short = apply_month_breaker(r_short, cb)
    r = r_long.add(w * r_short, fill_value=0.0)
    eq = (1 + r).cumprod()
    return eq, r


def line(name, eq, r):
    full = metrics(name + " FULL", eq)
    oos = metrics(name + " OOS", (1 + r.loc[OOS_START:]).cumprod())
    print(fmt(full))
    print(fmt(oos))


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    print("=== depth neighborhood (vt=0.4 w=0.75 cb=4%) ===")
    for d in (0.0, 0.25, 0.5, 0.75, 1.0):
        eq, r = build("btc_4h.csv", depth=d)
        line(f"depth={d}", eq, r)

    print("\n=== vol-target neighborhood (depth=0.5 w=0.75) ===")
    for vt in (0.3, 0.4, 0.5, None):
        eq, r = build("btc_4h.csv", vt=vt)
        line(f"vt={vt}", eq, r)

    print("\n=== weight neighborhood ===")
    for w in (0.5, 0.6, 0.75, 0.9, 1.0):
        eq, r = build("btc_4h.csv", w=w)
        line(f"w={w}", eq, r)

    print("\n=== cost sensitivity (whole system re-run at higher costs) ===")
    for cost in (0.0004, 0.0005, 0.00075, 0.001):
        research_ls.COST = cost
        bt.FEE = cost
        eq, r = build("btc_4h.csv")
        line(f"cost={cost*100:.3f}%/side", eq, r)
    research_ls.COST = 0.0005
    bt.FEE = 0.0004

    print("\n=== other coins (same structure, BTC-tuned params) ===")
    for csv in ("eth_4h.csv", "sol_4h.csv", "bnb_4h.csv"):
        eq, r = build(csv)
        line(csv.split("_")[0].upper(), eq, r)
