"""Parameter sweep + out-of-sample validation for the managed strategy."""
import itertools

import pandas as pd

from backtest import add_indicators, load, managed, regime_flip, buy_hold, fmt

df = add_indicators(load("btc_4h.csv"))

# In-sample: 2023-06 .. 2025-06 ; Out-of-sample: 2025-07 .. 2026-06
is_df = df[df["dt"] < "2025-07-01"].reset_index(drop=True)
oos_df = df[df["dt"] >= "2025-01-01"].reset_index(drop=True)  # warmup margin
oos_start = "2025-07-01"


def run_oos(**kw):
    s = managed(oos_df, **kw)
    eq = s["equity"][s["equity"].index >= oos_start]
    ret = eq.iloc[-1] / eq.iloc[0] - 1
    return ret


print("=== FULL PERIOD SWEEP (2023-06 .. 2026-06) ===")
rows = []
for stop_atr, tp1_r, tp1_frac, trail in itertools.product(
        [2.0, 2.5, 3.0], [1.0, 1.5, 2.0], [0.3, 0.5], [2.5, 3.0, 4.0]):
    s = managed(df, stop_atr=stop_atr, tp1_r=tp1_r, tp1_frac=tp1_frac, trail_atr=trail)
    rows.append({
        "stop": stop_atr, "tp1R": tp1_r, "frac": tp1_frac, "trail": trail,
        "ret": s["return"], "sharpe": s["sharpe"], "dd": s["maxdd"],
        "pf": s["pf"], "n": s["trades"], "wr": s["winrate"],
        "pos_m": s["pos_months"],
    })
t = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
print(t.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

print("\n=== ADX filter check on best region ===")
for amin, amax in [(0, 100), (15, 100), (20, 100), (0, 40), (20, 45)]:
    s = managed(df, stop_atr=2.5, tp1_r=1.5, tp1_frac=0.5, trail_atr=3.0,
                adx_min=amin, adx_max=amax)
    print(fmt(s))
