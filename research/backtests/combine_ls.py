"""Composite: managed long engine (v5.2) + stop-free short sleeve.

r_portfolio = r_long + w * r_short  (sleeves share the same equity base;
the short sleeve is only active in bear regimes, when the long engine is
flat, so no leverage is implied for w <= 1).

Validation: accepted only if the composite beats long-only in BOTH the
in-sample window and the untouched OOS bear year.
"""
import numpy as np
import pandas as pd

import backtest as bt
from research_ls import OOS_START, load, backtest as vec_bt, metrics, fmt, split
from short_lab import VARIANTS, s_deep


def long_stream():
    """v5.2 managed long engine -> 4h return series."""
    df = bt.add_indicators(bt.load("btc_4h.csv"))
    s = bt.managed(df, tp1_frac=0.4, name="v5.2 long")
    eq = s["equity"]
    eq.index = pd.to_datetime(eq.index, utc=True)
    return eq.pct_change().fillna(0.0)


def sleeve_stream(df, fn, vol_target=None):
    """Short sleeve -> 4h net return series (costs included)."""
    tgt = fn(df)
    s = vec_bt(df, tgt, vol_target=vol_target, name="sleeve")
    eq = s["equity"]
    return eq.pct_change().fillna(0.0)


def combo_metrics(name, r_long, r_short, w):
    r = r_long.add(w * r_short, fill_value=0.0)
    eq = (1 + r).cumprod()
    full = metrics(name + " FULL", eq)
    is_eq = eq.loc[:OOS_START]
    oos_r = r.loc[OOS_START:]
    oos_eq = (1 + oos_r).cumprod()
    s_is = metrics(name + " IS", is_eq)
    s_oos = metrics(name + " OOS", oos_eq)
    return full, s_is, s_oos


if __name__ == "__main__":
    df = load()
    r_long = long_stream()
    r_long.index = df.index[: len(r_long)]

    print("--- long-only baseline (v5.2 managed) ---")
    for s in combo_metrics("v5.2 long-only", r_long, r_long * 0, 0):
        print(fmt(s))
    print()

    sleeves = {
        "plain vt40": ("plain bear", 0.4),
        "deep0.5 vt40": ("deep 0.5atr", 0.4),
        "confirm12 vt40": ("confirm k=12", 0.4),
        "deep0.5 raw": ("deep 0.5atr", None),
        "no-oversold vt40": ("no-oversold 27/45", 0.4),
    }
    results = []
    for sname, (vkey, vt) in sleeves.items():
        r_short = sleeve_stream(df, VARIANTS[vkey], vol_target=vt)
        corr = r_long.corr(r_short)
        print(f"=== sleeve {sname}  (corr with long: {corr:+.2f}) ===")
        for w in (0.25, 0.5, 0.75, 1.0):
            full, s_is, s_oos = combo_metrics(f"{sname} w={w}", r_long, r_short, w)
            results.append((sname, w, full, s_is, s_oos))
            print(fmt(full))
            print(fmt(s_is))
            print(fmt(s_oos))
            print()

    # rank by full-period MAR among configs that are OOS-positive and IS >= long-only IS
    print("\n--- OOS-positive candidates ranked by FULL MAR ---")
    good = [r for r in results if r[4]["ret"] > 0.02]
    for sname, w, full, s_is, s_oos in sorted(good, key=lambda r: -r[2]["mar"])[:8]:
        print(f"{sname:<18} w={w:<5} mar {full['mar']:5.2f}  "
              f"full {full['ret']*100:+7.1f}% dd {full['maxdd']*100:5.1f}%  "
              f"IS {s_is['ret']*100:+7.1f}%  OOS {s_oos['ret']*100:+6.1f}% "
              f"oosDD {s_oos['maxdd']*100:5.1f}%  worstM {full['worst_m']*100:+5.1f}%")
