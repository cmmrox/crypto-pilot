"""Stage 1: every family grid over the full history, then per-family walk-forward."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.search import month_stats, run_grid, walk_forward  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "stage1"


def main() -> None:
    t0 = time.time()
    market = load_market()
    monthly, stats = run_grid(market)
    OUT.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(OUT / "monthly.csv")
    stats.to_csv(OUT / "stats.csv", index=False)
    print(f"{monthly.shape[1]} configs in {time.time() - t0:.1f}s; months {len(monthly)}")
    pd.set_option("display.width", 220)
    cols = ["label", "total_return", "max_dd", "pct_pos", "worst_month", "monthly_sharpe",
            "trades_per_month", "win_rate", "profit_factor"]
    for fam, g in stats.groupby("family"):
        print(f"\n== {fam}: {len(g)} configs; top 5 by full-period monthly Sharpe (in-sample!)")
        print(g.sort_values("monthly_sharpe", ascending=False)[cols].head(5).round(3)
              .to_string(index=False))
    print("\n== Walk-forward (train 24m, test 6m), selection by training monthly Sharpe")
    rows = []
    for fam, g in stats.groupby("family"):
        oos, log = walk_forward(monthly, list(g["label"]))
        rows.append({"family": fam, **month_stats(oos), "first": str(oos.index[0]),
                     "last": str(oos.index[-1])})
    allfam, _ = walk_forward(monthly)
    rows.append({"family": "ALL (pick best of any family)", **month_stats(allfam),
                 "first": str(allfam.index[0]), "last": str(allfam.index[-1])})
    print(pd.DataFrame(rows).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
