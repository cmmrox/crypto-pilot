"""Pick a deployable dual config by robustness, not by the single best backtest.

Score = mean rank over (a) BTC full-period monthly Sharpe, (b) BTC last-24-month
Sharpe, (c) mean Sharpe on ETH/SOL/BNB with identical parameters, (d) BTC share of
profitable months. Uses only data up to today; no later information exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.engine import run  # noqa: E402
from mir.search import base_config, monthly_from_equity  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402
from mir.strategies import dual_h_grid as dual_grid

RES = Path(__file__).resolve().parents[1] / "results" / "stage4"


def sharpe(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(12)) if x.std() > 0 else 0.0


def main() -> None:
    markets = {s: load_market(s) for s in ("btcusdt", "ethusdt", "solusdt", "bnbusdt")}
    feats = {s: Feat(mk) for s, mk in markets.items()}
    rows = []
    for p in dual_grid():
        rec = {"label": dual(feats["btcusdt"], p).label(), **p}
        for s, mk in markets.items():
            start = "2021-03-01" if s == "solusdt" else "2020-06-01"
            sk = int(np.searchsorted(mk.h4.index, pd.Timestamp(start, tz="UTC")))
            spec = dual(feats[s], p)
            spec.signals.entry_long[: sk - 1] = False
            spec.signals.entry_short[: sk - 1] = False
            cfg = base_config(spec)
            r = run(mk, spec.signals, cfg)
            mr = monthly_from_equity(r.equity, mk.h1.index, start, cfg.init_eq)
            if s == "btcusdt":
                rec["btc_sharpe"] = sharpe(mr)
                rec["btc_last24_sharpe"] = sharpe(mr.iloc[-25:-1])
                rec["btc_pct_pos"] = float((mr > 1e-9).mean())
                rec["btc_total"] = float((1 + mr).prod() - 1)
            else:
                rec[f"{s}_sharpe"] = sharpe(mr)
        rec["alt_sharpe"] = np.mean([rec[f"{s}_sharpe"] for s in ("ethusdt", "solusdt", "bnbusdt")])
        rows.append(rec)
    df = pd.DataFrame(rows)
    keys = ["btc_sharpe", "btc_last24_sharpe", "alt_sharpe", "btc_pct_pos"]
    df["robust_rank"] = df[keys].rank(ascending=False).mean(axis=1)
    df = df.sort_values("robust_rank")
    df.to_csv(RES / "robust_selection.csv", index=False)
    pd.set_option("display.width", 250)
    show = ["label", "robust_rank", *keys, "btc_total", "ethusdt_sharpe", "solusdt_sharpe",
            "bnbusdt_sharpe"]
    print(df[show].head(12).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
