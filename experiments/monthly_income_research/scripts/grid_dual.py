"""Stage 3: dual-engine strategy grid on BTC, walk-forward, plus cross-asset check."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.engine import run  # noqa: E402
from mir.portfolio import summarize  # noqa: E402
from mir.search import base_config, monthly_from_equity, run_grid, walk_forward  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    m = load_market()
    monthly, stats = run_grid(m, families=["dual"])
    out = RES / "stage3"
    out.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out / "monthly.csv")
    stats.to_csv(out / "stats.csv", index=False)
    pd.set_option("display.width", 250)
    cols = ["label", "total_return", "max_dd", "pct_pos", "worst_month", "monthly_sharpe",
            "trades_per_month", "win_rate", "profit_factor"]
    print(stats.sort_values("monthly_sharpe", ascending=False)[cols].head(10).round(3)
          .to_string(index=False))
    for how in ("sharpe", "pct_pos"):
        oos, log = walk_forward(monthly, how=how)
        print(f"WF dual ({how}):", summarize(oos), [round(x * 100, 2) for x in oos.tail(3)])
    # cross-asset check of the in-sample top 5 BTC configs with identical parameters
    top = stats.sort_values("monthly_sharpe", ascending=False).head(5)
    pcols = [c for c in stats.columns if c.startswith("p_")]
    for _, row in top.iterrows():
        params = {c[2:]: row[c] for c in pcols if pd.notna(row[c])}
        for k in ("fast", "slow", "n", "look", "er_n", "short"):
            params[k] = int(params[k])
        res = {}
        for sym in ("btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt"):
            mk = load_market(sym)
            f = Feat(mk)
            start = "2021-03-01" if sym == "solusdt" else "2020-06-01"
            sk = int(np.searchsorted(mk.h4.index, pd.Timestamp(start, tz="UTC")))
            spec = dual(f, params)
            spec.signals.entry_long[: sk - 1] = False
            spec.signals.entry_short[: sk - 1] = False
            cfg = base_config(spec)
            r = run(mk, spec.signals, cfg)
            mr = monthly_from_equity(r.equity, mk.h1.index, start, cfg.init_eq)
            res[sym] = mr
        df = pd.DataFrame(res).loc["2021-03":]
        port = df.mean(axis=1)
        print(row["label"])
        print("   per-asset sharpe:", {k: round(v.mean() / v.std() * np.sqrt(12), 2)
                                       for k, v in df.items()},
              "| 5-coin portfolio:", summarize(port))


if __name__ == "__main__":
    main()
