"""Export production-engine Atlas 6 Trail monthly returns for the report (2020-06 onward)."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_atlas import DATA, FILTERS  # noqa: E402
from strategy_runtime.parameters import TrendRiderParameters  # noqa: E402
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "final"


def monthly(risk: str, lev: str, sleeve: float, breakers: bool) -> dict[str, float]:
    candles = pd.read_csv(DATA / "btcusdt_perp_4h.csv")[["dt", "open", "high", "low", "close",
                                                          "volume"]]
    funding = pd.read_csv(DATA / "btcusdt_funding.csv")
    params = TrendRiderParameters(trail_atr=4.5, sleeve_weight=sleeve, risk_pct=float(risk),
                                  leverage_cap=float(lev))
    cfg = ReplayConfig(parameters=params, initial_capital=Decimal("10000"),
                       risk_pct=Decimal(risk), leverage_cap=Decimal(lev),
                       monthly_breakers_enabled=breakers)
    res = PluginReplayEngine(candles, funding, FILTERS, cfg,
                             start=pd.Timestamp("2020-06-01", tz="UTC")).run()
    eq = res.equity.copy()
    eq["dt"] = pd.to_datetime(eq["dt"], utc=True)
    eq = eq.set_index("dt")["equity"].astype(float)
    me = eq.groupby(eq.index.tz_convert(None).to_period("M")).last()
    prev = me.shift(1)
    prev.iloc[0] = 10000.0
    return {str(k): round(float(v) * 100, 3) for k, v in (me / prev - 1).items()}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "atlas6trail_live_15pct_6x_breaker4": monthly("15", "6", 0.75, True),
        "atlas6trail_2pct_3x_nobreaker": monthly("2", "3", 0.25, False),
    }
    (OUT / "atlas_monthly.json").write_text(json.dumps(data, indent=1))
    for k, v in data.items():
        s = pd.Series(v) / 100
        print(k, "months", len(s), "pos", int((s > 1e-9).sum()), "total%",
              round(((1 + s).prod() - 1) * 100, 1))
