"""Existing Atlas 6 Trail logic under saner risk profiles (production replay engine)."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_atlas import DATA, FILTERS  # noqa: E402
from strategy_runtime.parameters import TrendRiderParameters  # noqa: E402
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig  # noqa: E402


def run(risk: str, lev: str, sleeve: float, cap: float | None, start: str = "2023-09-01",
        capital: str = "200") -> dict:
    candles = pd.read_csv(DATA / "btcusdt_perp_4h.csv")[["dt", "open", "high", "low", "close", "volume"]]
    funding = pd.read_csv(DATA / "btcusdt_funding.csv")
    params = TrendRiderParameters(trail_atr=4.5, sleeve_weight=sleeve, risk_pct=float(risk),
                                  leverage_cap=float(lev),
                                  long_month_cap=cap or 0.04, sleeve_month_cap=cap or 0.04)
    cfg = ReplayConfig(parameters=params, initial_capital=Decimal(capital), risk_pct=Decimal(risk),
                       leverage_cap=Decimal(lev), monthly_breakers_enabled=cap is not None,
                       long_breaker_cap=Decimal(str(cap or 0.04)),
                       short_breaker_cap=Decimal(str(cap or 0.04)))
    res = PluginReplayEngine(candles, funding, FILTERS, cfg, start=pd.Timestamp(start, tz="UTC")).run()
    eq = res.equity.copy()
    eq["dt"] = pd.to_datetime(eq["dt"], utc=True)
    eq = eq.set_index("dt")["equity"].astype(float)
    me = eq.groupby(eq.index.tz_convert(None).to_period("M")).last()
    prev = me.shift(1)
    prev.iloc[0] = float(capital)
    mr = me / prev - 1
    return {"risk%": risk, "lev": lev, "sleeve": sleeve, "breaker": cap, "final": round(float(res.final_equity), 1),
            "maxDD%": round(float(res.max_drawdown) * 100, 1), "pos": int((mr > 1e-9).sum()),
            "neg": int((mr < -1e-9).sum()), "months": len(mr), "worst%": round(mr.min() * 100, 1),
            "last3%": [round(x * 100, 1) for x in mr.tail(3)], "trades": len(res.trades),
            "skipped_long": res.skipped_long_entries}


if __name__ == "__main__":
    rows = [run("15", "6", 0.75, 0.04)]
    for risk, lev, sleeve in [("2", "2", 0.25), ("3", "3", 0.35), ("5", "3", 0.5)]:
        for cap in (0.04, 0.08, None):
            rows.append(run(risk, lev, sleeve, cap))
    pd.set_option("display.width", 220)
    print(pd.DataFrame(rows).to_string(index=False))
