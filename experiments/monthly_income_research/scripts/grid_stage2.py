"""Stage 2: squeeze breakout and chop-filtered trend rider; merge with stage-1 months."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.search import month_stats, run_grid, walk_forward  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    t0 = time.time()
    market = load_market()
    monthly, stats = run_grid(market, families=["squeeze", "trend_rider_f"])
    out = RES / "stage2"
    out.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out / "monthly.csv")
    stats.to_csv(out / "stats.csv", index=False)
    print(f"{monthly.shape[1]} configs in {time.time() - t0:.1f}s")
    pd.set_option("display.width", 250)
    cols = ["label", "total_return", "max_dd", "pct_pos", "worst_month", "monthly_sharpe",
            "trades_per_month", "win_rate", "profit_factor"]
    for fam, g in stats.groupby("family"):
        print(f"\\n== {fam}: {len(g)} configs; top 8 by full-period monthly Sharpe (in-sample!)")
        print(g.sort_values("monthly_sharpe", ascending=False)[cols].head(8).round(3)
              .to_string(index=False))
    m1 = pd.read_csv(RES / "stage1" / "monthly.csv", index_col=0)
    s1 = pd.read_csv(RES / "stage1" / "stats.csv")
    m1.index = pd.PeriodIndex(m1.index, freq="M")
    allm = pd.concat([m1, monthly], axis=1)
    alls = pd.concat([s1, stats])
    allm.to_csv(RES / "all_monthly.csv")
    alls.to_csv(RES / "all_stats.csv", index=False)
    print("\\n== Walk-forward (train 24m, test 6m), by training monthly Sharpe")
    rows = []
    for fam, g in alls.groupby("family"):
        for how in ("sharpe", "pct_pos"):
            oos, _ = walk_forward(allm, list(g["label"]), how=how)
            rows.append({"family": fam, "select": how, **month_stats(oos),
                         "last3": [round(x * 100, 2) for x in oos.tail(3)]})
    print(pd.DataFrame(rows).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
