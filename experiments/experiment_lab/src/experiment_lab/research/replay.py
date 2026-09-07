"""Research-only adapter to the existing Decimal account and exchange-filter model."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
from strategy_runtime.contracts import EnterLong, ExitAll, MoveStop
from strategy_runtime.replay import PluginReplayEngine, ReplayResult

from experiment_lab.adapters.replay import records
from experiment_lab.research.regime_long import RegimeLong


class ResearchReplay(PluginReplayEngine):
    def attach(self, hypothesis: RegimeLong) -> None:
        self.hypothesis = hypothesis
        self.df = hypothesis.prepare(self.df)

    # Heterogeneous rows follow the existing replay adapter's boundary type.
    def _process_open(self, i: int, row: pd.Series[Any], prev: pd.Series[Any]) -> None:
        price, timestamp = Decimal(str(row["open"])), pd.Timestamp(row["dt"])
        if self.position is not None and self.halted_long:
            self._close_position(price, timestamp, "monthly_breaker")
        intents = self.hypothesis.decide(prev, self._plugin_state(i, prev))
        self.intent_trace.append(
            {"dt": timestamp, "intents": [type(x).__name__ for x in intents]}
        )
        for intent in intents:
            if isinstance(intent, ExitAll) and self.position is not None:
                self._close_position(price, timestamp, intent.reason)
            elif isinstance(intent, MoveStop) and self.position is not None:
                self.position.stop = max(
                    self.position.stop or Decimal(0), Decimal(str(intent.price))
                )
            elif (
                isinstance(intent, EnterLong)
                and self.position is None
                and not self.halted_long
            ):
                self._open_long_from_intent(intent, price, timestamp)


def summarize(
    engine: PluginReplayEngine, result: ReplayResult, end: pd.Timestamp
) -> dict[str, Any]:
    # JSON evidence mixes monthly records, strings, counts and nullable positions.
    capital = result.config.initial_capital
    prior = peak = capital
    drawdown = Decimal(0)
    for value in result.equity["equity"]:
        current = Decimal(str(value))
        peak = max(peak, current)
        drawdown = min(drawdown, current / peak - 1)
    monthly = []
    times = pd.to_datetime(result.equity["dt"], utc=True)
    for month, group in result.equity.groupby(times.dt.strftime("%Y-%m"), sort=True):
        equity = Decimal(str(group.iloc[-1]["equity"]))
        month_start = pd.Timestamp(f"{month}-01", tz="UTC")
        full = (
            engine.start <= month_start
            and end >= month_start + pd.offsets.MonthBegin(1)
        )
        monthly.append(
            {
                "month": month,
                "profit": str(equity - prior),
                "return": str(equity / prior - 1),
                "full": full,
            }
        )
        prior = equity
    complete = [m for m in monthly if m["full"]]
    trades = records(result.trades)
    pnls = [Decimal(t["net_pnl"]) for t in trades]
    wins = sum((p for p in pnls if p > 0), Decimal(0))
    losses = -sum((p for p in pnls if p < 0), Decimal(0))
    fees = sum((Decimal(t["fees"]) for t in trades), Decimal(0))
    funding = sum((Decimal(t["funding"]) for t in trades), Decimal(0))
    open_net = Decimal(0)
    if engine.position is not None:
        p = engine.position
        unrealized = (result.latest_close - p.entry_price) * p.qty
        if p.side == "SHORT":
            unrealized = -unrealized
        open_net = p.realized_partial + unrealized + p.funding - p.fees
        fees += p.fees
        funding += p.funding
    delta = result.profit - sum(pnls, Decimal(0)) - open_net
    if abs(delta) > Decimal("0.00000001"):
        raise ValueError("Account reconciliation failed")
    return {
        "initial_capital": str(capital),
        "final_equity": str(result.final_equity),
        "net_profit": str(result.profit),
        "return": str(result.total_return),
        "max_drawdown": str(drawdown),
        "sharpe_4h": str(result.sharpe),
        "profitable_months": sum(Decimal(str(m["profit"])) > 0 for m in complete),
        "full_months": len(complete),
        "monthly": monthly,
        "worst_month": min((m["return"] for m in complete), key=Decimal, default="0"),
        "trade_count": len(trades),
        "wins": sum(p > 0 for p in pnls),
        "losses": sum(p < 0 for p in pnls),
        "profit_factor": str(wins / losses) if losses else None,
        "fees_and_slippage": str(fees),
        "funding": str(funding),
        "reconciliation_delta": str(delta),
        "open_position": result.open_position,
        "open_net_pnl": str(open_net),
        "funding_mark_fallbacks": result.funding_mark_fallbacks,
        "skipped_entries": result.skipped_long_entries + result.skipped_short_entries,
    }
