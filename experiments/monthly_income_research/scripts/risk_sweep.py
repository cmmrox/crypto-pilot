"""Atlas 7 Dual at different risk-per-trade levels and monthly-breaker settings.

Same pinned rules as final_eval.py; only sizing and the breaker change.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from final_eval import PARAMS  # noqa: E402
from mir.data import load_market  # noqa: E402
from mir.engine import run  # noqa: E402
from mir.metrics import trade_table  # noqa: E402
from mir.portfolio import summarize  # noqa: E402
from mir.search import base_config, monthly_from_equity  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "risk"


def evaluate(m, f, start: str, *, risk: float, init_eq: float, breaker: float, lot: bool,
             taker: float = 0.0007, delay: int = 0):
    spec = dual(f, PARAMS)
    sig = spec.signals
    if delay:
        for name in ("entry_long", "entry_short", "exit_long", "exit_short"):
            arr = getattr(sig, name)
            setattr(sig, name, np.r_[np.zeros(delay, dtype=arr.dtype), arr[:-delay]])
    sk = int(np.searchsorted(m.h4.index, pd.Timestamp(start, tz="UTC")))
    sig.entry_long = sig.entry_long.copy()
    sig.entry_short = sig.entry_short.copy()
    sig.entry_long[: max(sk - 1, 0)] = False
    sig.entry_short[: max(sk - 1, 0)] = False
    cfg = replace(base_config(spec, risk_pct=risk, lev_cap=3.0, init_eq=init_eq, taker=taker),
                  breaker_pct=breaker, qty_step=0.001 if lot else 0.0,
                  min_notional=50.0 if lot else 0.0)
    res = run(m, sig, cfg)
    mret = monthly_from_equity(res.equity, m.h1.index, start, init_eq)
    eq = pd.Series(res.equity, index=m.h1.index)
    eq = eq[eq.index >= pd.Timestamp(start, tz="UTC")]
    dd = float((eq / eq.cummax() - 1).min())
    halted = int((res.trades["reason"] == 6).sum())
    return res, mret, dd, halted


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m = load_market()
    f = Feat(m)
    rows = []
    monthly = {}
    for risk in (0.01, 0.02, 0.03, 0.04, 0.05):
        for breaker in (0.04, 0.08, 0.10, 0.0):
            res, mret, dd, halted = evaluate(m, f, "2020-06-01", risk=risk, init_eq=10_000,
                                             breaker=breaker, lot=False)
            label = f"risk {risk:.0%} · breaker {('off' if not breaker else f'{breaker:.0%}')}"
            monthly[label] = mret
            rows.append({"risk": f"{risk:.0%}",
                         "breaker": "off" if not breaker else f"{breaker:.0%}",
                         **summarize(mret), "maxDD%": round(dd * 100, 1),
                         "trades": len(res.trades["pnl"]), "breaker_exits": halted})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print("=== Jun 2020 – Sep 2026, $10,000, continuous sizing ===")
    print(df.to_string(index=False))
    df.to_csv(OUT / "sweep_full.csv", index=False)
    pd.DataFrame(monthly).to_csv(OUT / "sweep_monthly.csv")

    print("\n=== Your account: $190 with real 0.001 BTC lots, Sep 2023 → now ===")
    rows2 = []
    for risk in (0.02, 0.03, 0.04, 0.05):
        for breaker in (0.04, 0.08, 0.10, 0.0):
            res, mret, dd, halted = evaluate(m, f, "2023-09-01", risk=risk, init_eq=190.0,
                                             breaker=breaker, lot=True)
            rows2.append({"risk": f"{risk:.0%}",
                          "breaker": "off" if not breaker else f"{breaker:.0%}",
                          "final_$": round(float(res.equity[-1]), 2), **summarize(mret),
                          "maxDD%": round(dd * 100, 1), "trades": len(res.trades["pnl"]),
                          "skipped": res.skipped, "breaker_exits": halted})
    df2 = pd.DataFrame(rows2)
    print(df2.to_string(index=False))
    df2.to_csv(OUT / "sweep_190.csv", index=False)

    print("\n=== Last two months: from the live account's $223.48 on Aug 1 ===")
    rows3 = []
    for risk in (0.02, 0.04):
        for breaker in (0.04, 0.08, 0.0):
            res, mret, dd, _ = evaluate(m, f, "2026-08-01", risk=risk, init_eq=223.48,
                                        breaker=breaker, lot=True)
            rows3.append({"risk": f"{risk:.0%}",
                          "breaker": "off" if not breaker else f"{breaker:.0%}",
                          "final_$": round(float(res.equity[-1]), 2),
                          "return%": round((float(res.equity[-1]) / 223.48 - 1) * 100, 1),
                          "maxDD%": round(dd * 100, 1), "trades": len(res.trades["pnl"])})
    print(pd.DataFrame(rows3).to_string(index=False))

    print("\n=== 4% risk, breaker 8%: stress tests (full period, $10,000) ===")
    rows4 = []
    for name, kw in {"base": {}, "double costs": {"taker": 0.0014},
                     "4h late execution": {"delay": 1}}.items():
        res, mret, dd, _ = evaluate(m, f, "2020-06-01", risk=0.04, init_eq=10_000,
                                    breaker=0.08, lot=False, **kw)
        rows4.append({"run": name, **summarize(mret), "maxDD%": round(dd * 100, 1)})
    print(pd.DataFrame(rows4).to_string(index=False))

    # yearly + monthly detail for the 4% / 8% choice
    res, mret, dd, _ = evaluate(m, f, "2020-06-01", risk=0.04, init_eq=10_000, breaker=0.08,
                                lot=False)
    years = {}
    for k, v in mret.items():
        years.setdefault(str(k)[:4], []).append(v)
    yearly = {y: round((np.prod([1 + x for x in vs]) - 1) * 100, 1) for y, vs in years.items()}
    print("\nYear by year at 4% risk / 8% breaker:", yearly)
    losses = sorted(v * 100 for v in mret if v < 0)[:5]
    print("Five worst months:", [round(x, 1) for x in losses])
    trade_table(res).to_csv(OUT / "trades_4pct.csv", index=False)
    (OUT / "monthly_4pct.json").write_text(json.dumps(
        {"monthly": {str(k): round(float(v) * 100, 2) for k, v in mret.items()},
         "yearly": yearly, "summary": summarize(mret), "maxDD%": round(dd * 100, 1)}, indent=1))


if __name__ == "__main__":
    main()
