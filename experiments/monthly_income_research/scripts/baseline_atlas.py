"""Replay the three installed Atlas releases through the production replay engine.

Uses the shared ``strategy_runtime`` PluginReplayEngine (production strategy, sizing
and filter code) on freshly downloaded public 4h candles and funding. Research only:
no account access, no orders.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "strategy_runtime" / "src"))

from strategy_runtime.contracts import EnterShort, ResizeShort  # noqa: E402
from strategy_runtime.filters import SymbolFilters  # noqa: E402
from strategy_runtime.parameters import TrendRiderParameters  # noqa: E402
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig  # noqa: E402
from strategy_runtime.trend_rider import TrendRider  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parents[1] / "results" / "baseline"
FILTERS = SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"),
                        max_qty=Decimal("120"), tick_size=Decimal("0.10"),
                        min_notional=Decimal("50"))


class LongOnly(TrendRider):
    def on_prepared_frame(self, df, state):  # type: ignore[no-untyped-def]
        return [i for i in super().on_prepared_frame(df, state)
                if not isinstance(i, EnterShort | ResizeShort)]


def replay(name: str, params: TrendRiderParameters, start: str, capital: str,
           breakers: bool = True, long_only: bool = False,
           risk: str | None = None, lev: str | None = None) -> dict[str, object]:
    candles = pd.read_csv(DATA / "btcusdt_perp_4h.csv")
    candles = candles[["dt", "open", "high", "low", "close", "volume"]]
    funding = pd.read_csv(DATA / "btcusdt_funding.csv")
    cfg = ReplayConfig(parameters=params, initial_capital=Decimal(capital),
                       monthly_breakers_enabled=breakers)
    if risk is not None:
        cfg = replace(cfg, risk_pct=Decimal(risk))
    if lev is not None:
        cfg = replace(cfg, leverage_cap=Decimal(lev))
    eng = PluginReplayEngine(candles, funding, FILTERS, cfg, start=pd.Timestamp(start, tz="UTC"))
    if long_only:
        eng.strategy = LongOnly(params, "4h")
    res = eng.run()
    eq = res.equity.copy()
    eq["dt"] = pd.to_datetime(eq["dt"], utc=True)
    eq = eq.set_index("dt")["equity"].astype(float)
    month_end = eq.groupby(eq.index.tz_convert(None).to_period("M")).last()
    prev = month_end.shift(1)
    prev.iloc[0] = float(capital)
    mret = (month_end / prev - 1.0)
    trades = res.trades.copy()
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT / f"{name}_trades.csv", index=False)
    mret.to_csv(OUT / f"{name}_monthly.csv")
    return {
        "name": name, "start": start, "capital": capital,
        "final_equity": float(res.final_equity), "total_return": float(res.total_return),
        "max_dd": float(res.max_drawdown), "months": len(mret),
        "pos_months": int((mret > 1e-9).sum()), "neg_months": int((mret < -1e-9).sum()),
        "flat_months": int((mret.abs() <= 1e-9).sum()),
        "worst_month": float(mret.min()), "best_month": float(mret.max()),
        "trades": len(trades), "long_breaker_trips": res.long_breaker_trips,
        "short_breaker_trips": res.short_breaker_trips,
        "skipped_long": res.skipped_long_entries, "skipped_short": res.skipped_short_entries,
        "last_months": {str(k): round(float(v) * 100, 2) for k, v in mret.tail(6).items()},
    }


def main() -> None:
    runs = []
    v6 = TrendRiderParameters()
    trail = TrendRiderParameters(trail_atr=4.5)
    for start in ("2023-09-01", "2020-06-01"):
        runs.append(replay(f"atlas52_{start[:4]}", v6, start, "200", long_only=True))
        runs.append(replay(f"atlas6_{start[:4]}", v6, start, "200"))
        runs.append(replay(f"atlas6trail_{start[:4]}", trail, start, "200"))
        runs.append(replay(f"atlas6_nobreaker_{start[:4]}", v6, start, "200", breakers=False))
    # Last-two-months window from a fresh flat $200 account (July 22 onward).
    runs.append(replay("atlas6trail_recent", trail, "2026-07-22", "200"))
    runs.append(replay("atlas6trail_recent_nobreaker", trail, "2026-07-22", "200",
                       breakers=False))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(runs, indent=2))
    cols = ["name", "final_equity", "total_return", "max_dd", "months", "pos_months",
            "neg_months", "flat_months", "worst_month", "trades", "long_breaker_trips",
            "short_breaker_trips"]
    print(pd.DataFrame(runs)[cols].round(4).to_string(index=False))
    for r in runs:
        print(r["name"], r["last_months"])


if __name__ == "__main__":
    main()
