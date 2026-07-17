"""Out-of-sample validation + monthly breakdown for the chosen config."""
import pandas as pd

from backtest import add_indicators, load, managed, regime_flip, buy_hold, fmt, monthly_table

CFG = dict(stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5, trail_atr=4.0)

df = add_indicators(load("btc_4h.csv"))

print("=== FULL 3Y (2023-06 .. 2026-06) ===")
bh = buy_hold(df)
rf = regime_flip(df)
mg = managed(df, **CFG, name="FINAL: sl2.5 tp1@1R x50% BE trail4ATR")
for s in (bh, rf, mg):
    print(fmt(s))

# --- IS / OOS split ---
is_df = df[df["dt"] < "2025-07-01"].reset_index(drop=True)
print("\n=== IN-SAMPLE (2023-06 .. 2025-06) ===")
print(fmt(buy_hold(is_df)))
print(fmt(managed(is_df, **CFG, name="FINAL config IS")))

# OOS with warm-up: feed data from 2024-07 so indicators are formed by 2025-07,
# then slice stats to the OOS window only.
warm = df[df["dt"] >= "2024-07-01"].reset_index(drop=True)
s = managed(warm, **CFG, name="warm")
eq = s["equity"][s["equity"].index >= "2025-07-01"]
oos_ret = eq.iloc[-1] / eq.iloc[0] - 1
oos_dd = (eq / eq.cummax() - 1).min()
bh_oos = df[df["dt"] >= "2025-07-01"]
bh_ret = bh_oos["close"].iloc[-1] / bh_oos["close"].iloc[0] - 1
m = eq.resample("ME").last().pct_change().dropna()
print("\n=== OUT-OF-SAMPLE (2025-07 .. 2026-06) ===")
print(f"Buy&Hold OOS: {bh_ret*100:+.1f}%")
print(f"FINAL   OOS: {oos_ret*100:+.1f}%  maxDD {oos_dd*100:.1f}%  +months {(m>0).sum()}/{len(m)}")

print("\n=== FINAL config: monthly returns, full 3y ===")
print(monthly_table(mg))

print("\n=== Robustness: regime-parameter sweep with FINAL management ===")
import backtest as B
import numpy as np
base = load("btc_4h.csv")
for sma, e_fast, e_slow in [(150, 50, 200), (200, 50, 200), (250, 50, 200),
                            (200, 40, 180), (200, 60, 220)]:
    d2 = base.copy()
    c = d2["close"]
    d2 = add_indicators(d2)
    d2["sma200"] = c.rolling(sma).mean()
    d2["regime"] = (c > d2["sma200"]) & (
        c.ewm(span=e_fast, adjust=False).mean() > c.ewm(span=e_slow, adjust=False).mean())
    s = managed(d2, **CFG, name=f"regime SMA{sma}/EMA{e_fast}-{e_slow}")
    print(fmt(s))
