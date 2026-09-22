"""Final evaluation of the recommended dual-engine configuration."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.engine import Signals, run  # noqa: E402
from mir.metrics import trade_table  # noqa: E402
from mir.portfolio import summarize  # noqa: E402
from mir.search import base_config, monthly_from_equity  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "final"
PARAMS = dict(fast=20, slow=200, stop_t=2.5, stop_b=2.5, tp_r=2.0, trail=3.0, n=24, look=360,
              q=0.35, er=0.0, er_n=84, short=1, hyst=1.0)


def shifted(sig: Signals, k: int) -> Signals:
    def sh(x: np.ndarray | None, fill: object) -> np.ndarray | None:
        if x is None:
            return None
        return np.r_[np.full(k, fill, dtype=x.dtype), x[:-k]]

    return Signals(entry_long=sh(sig.entry_long, False), entry_short=sh(sig.entry_short, False),
                   exit_long=sh(sig.exit_long, False), exit_short=sh(sig.exit_short, False),
                   stop_long=sig.stop_long, stop_short=sig.stop_short,
                   trail_long=sig.trail_long, trail_short=sig.trail_short,
                   tp_long=sig.tp_long, tp_short=sig.tp_short)


def evaluate(m, start: str, *, risk: float, init_eq: float, lot: bool = False,
             taker: float = 0.0007, delay: int = 0, lev: float = 3.0):
    f = Feat(m)
    spec = dual(f, PARAMS)
    sig = shifted(spec.signals, delay) if delay else spec.signals
    sk = int(np.searchsorted(m.h4.index, pd.Timestamp(start, tz="UTC")))
    sig.entry_long = sig.entry_long.copy()
    sig.entry_short = sig.entry_short.copy()
    sig.entry_long[: max(sk - 1, 0)] = False
    sig.entry_short[: max(sk - 1, 0)] = False
    cfg = replace(base_config(spec, risk_pct=risk, lev_cap=lev, init_eq=init_eq, taker=taker),
                  qty_step=0.001 if lot else 0.0, min_notional=50.0 if lot else 0.0)
    r = run(m, sig, cfg)
    mr = monthly_from_equity(r.equity, m.h1.index, start, init_eq)
    eq = pd.Series(r.equity, index=m.h1.index)
    eq = eq[eq.index >= pd.Timestamp(start, tz="UTC")]
    dd = float((eq / eq.cummax() - 1).min())
    return r, mr, dd


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m = load_market()
    rows = []
    monthly = {}
    for label, kw in {
        "risk 1% (continuous)": dict(risk=0.01, init_eq=10_000),
        "risk 1.5% (continuous)": dict(risk=0.015, init_eq=10_000),
        "risk 2% (continuous)": dict(risk=0.02, init_eq=10_000),
        "risk 3% (continuous)": dict(risk=0.03, init_eq=10_000),
        "risk 2%, double costs": dict(risk=0.02, init_eq=10_000, taker=0.0014),
        "risk 2%, 4h late execution": dict(risk=0.02, init_eq=10_000, delay=1),
    }.items():
        r, mr, dd = evaluate(m, "2020-06-01", **kw)
        monthly[label] = mr
        rows.append({"run": label, **summarize(mr), "intrabar_maxDD%": round(dd * 100, 1),
                     "trades": len(r.trades["pnl"]), "skipped": r.skipped})
    for start in ("2023-09-01", "2026-07-22"):
        for risk in (0.02, 0.03):
            r, mr, dd = evaluate(m, start, risk=risk, init_eq=190.0, lot=True)
            label = f"$190 real lots, risk {risk:.0%}, from {start}"
            monthly[label] = mr
            rows.append({"run": label, **summarize(mr), "intrabar_maxDD%": round(dd * 100, 1),
                         "trades": len(r.trades["pnl"]), "skipped": r.skipped,
                         "final_$": round(float(r.equity[-1]), 2)})
            if start == "2026-07-22" and risk == 0.02:
                tt = trade_table(r)
                tt.to_csv(OUT / "trades_recent_190.csv", index=False)
    summary = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(summary.to_string(index=False))
    summary.to_csv(OUT / "summary.csv", index=False)
    mdf = pd.DataFrame(monthly)
    mdf.to_csv(OUT / "monthly.csv")
    # year x month table for the 2% continuous run
    base = monthly["risk 2% (continuous)"]
    tab = pd.DataFrame({"year": base.index.year, "month": base.index.month, "ret": base.values})
    grid = tab.pivot(index="year", columns="month", values="ret") * 100
    grid["year_total%"] = [((1 + base[base.index.year == y]).prod() - 1) * 100 for y in grid.index]
    grid.round(2).to_csv(OUT / "year_month_2pct.csv")
    print(grid.round(1).to_string())
    # full trade list (2% continuous) and recent trades
    r, _, _ = evaluate(m, "2020-06-01", risk=0.02, init_eq=10_000)
    tt = trade_table(r)
    tt.to_csv(OUT / "trades_2pct.csv", index=False)
    recent = tt[tt["exit_time"] >= "2026-06-01"].copy()
    recent["pnl_%eq"] = recent["pnl"] / 100
    print(recent[["entry_time", "exit_time", "side", "entry_px", "exit_px", "pnl_%eq", "reason"]]
          .round(2).to_string(index=False))
    long_ = tt[tt.side == "LONG"]
    short_ = tt[tt.side == "SHORT"]
    stats = {"params": PARAMS, "long_trades": len(long_), "short_trades": len(short_),
             "long_pnl": float(long_.pnl.sum()), "short_pnl": float(short_.pnl.sum()),
             "win_rate": float((tt.pnl > 0).mean()), "fees": float(tt.fee.sum()),
             "funding": float(tt.funding.sum())}
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
