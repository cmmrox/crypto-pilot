"""Portfolio test: Trend Rider v5.1 run independently on BTC/ETH/SOL/BNB 4h,
equal capital per coin (25%), monthly returns combined. Does diversification
raise the count of green months? All fees included.
"""
import pandas as pd

from backtest import add_indicators, load, fmt
from circuit_breaker import managed_cb

symbols = {"BTC": "btc_4h.csv", "ETH": "eth_4h.csv",
           "SOL": "sol_4h.csv", "BNB": "bnb_4h.csv"}

monthlies = {}
equities = {}
for sym, path in symbols.items():
    df = add_indicators(load(path))
    s = managed_cb(df, month_loss_cap=0.04, name=f"{sym} v5.1")
    print(fmt(s) + f"  worst_m {s['monthly'].min()*100:+.1f}%")
    monthlies[sym] = s["monthly"]
    equities[sym] = s["equity"]

m = pd.DataFrame(monthlies).dropna()
port = m.mean(axis=1)  # equal-weight, rebalanced monthly
eq = (1 + port).cumprod()
ret = eq.iloc[-1] - 1
dd = (eq / eq.cummax() - 1).min()
pos = (port > 0.001).sum()
neg = (port < -0.001).sum()
flat = len(port) - pos - neg
sharpe = port.mean() / port.std() * (12 ** 0.5)

print(f"\nPORTFOLIO (equal-weight 4 coins, monthly rebalance)")
print(f"ret {ret*100:+.1f}%  monthly-Sharpe {sharpe:.2f}  maxDD(monthly) {dd*100:.1f}%")
print(f"green {pos}/{len(port)}  red {neg}  flat {flat}  worst {port.min()*100:+.2f}%  best {port.max()*100:+.2f}%")
print("\nMonthly:")
for ts, v in port.items():
    tag = "+" if v > 0.001 else ("-" if v < -0.001 else "0")
    print(f"  {ts.strftime('%Y-%m')}  {v*100:+7.2f}%  {tag}")
