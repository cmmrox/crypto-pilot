"""Replay adapter: shared strategy runtime, exact accounting and immutable evidence."""

from dataclasses import replace
from decimal import Decimal
from importlib.metadata import version

from typing import cast

import pandas as pd
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig
from strategy_runtime.trade_replay import TradeReplayEngine

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.adapters.trade_archive import TradeArchive
from experiment_lab.adapters.provenance import evaluator_hash, runtime_hash
from experiment_lab.domain.policy import POLICY_VERSION, eligibility


def records(frame: pd.DataFrame) -> list[dict]:
    return [
        {
            key: value.isoformat() if isinstance(value, pd.Timestamp) else str(value)
            for key, value in row.items()
        }
        for row in frame.to_dict("records")
    ]


class Replay:
    def __init__(self, artifacts: Artifacts):
        self.artifacts = artifacts

    def run(self, context: dict) -> dict:
        study = context["study"]["config"]
        if study["runtime_hash"] != runtime_hash():
            raise ValueError("Runtime changed after study creation")
        if (
            study.get("evaluator_hash") is not None
            and study["evaluator_hash"] != evaluator_hash()
        ):
            raise ValueError("Replay evaluator changed after study creation")
        iteration = context["iteration"]
        dataset = self.artifacts.get(study["dataset_id"])
        validate_dataset(dataset)
        if dataset["interval"] != study["interval"]:
            raise ValueError("Dataset interval does not match study")
        parameters = TrendRiderParameters.from_values(iteration["parameters"])
        config = ReplayConfig(
            parameters=parameters,
            interval=study["interval"],
            initial_capital=Decimal(study["initial_capital"]),
            risk_pct=Decimal(iteration["parameters"]["risk_pct"]),
            leverage_cap=Decimal(iteration["parameters"]["leverage_cap"]),
            long_breaker_cap=Decimal(iteration["parameters"]["long_month_cap"]),
            short_breaker_cap=Decimal(iteration["parameters"]["sleeve_month_cap"]),
        )
        frame = pd.DataFrame(dataset["candles"])
        frame = frame[
            pd.to_datetime(frame["dt"], utc=True) < pd.Timestamp(study["end"])
        ]
        funding = pd.DataFrame(dataset["funding"])
        funding_times = pd.to_datetime(funding["dt"], utc=True, format="ISO8601")
        funding = funding[
            (funding_times >= pd.Timestamp(study["start"]))
            & (funding_times < pd.Timestamp(study["end"]))
        ].copy()
        missing_marks = funding["mark_price"].map(
            lambda value: value is None or str(value).strip() == ""
        )
        if study.get("fidelity") == "TRADE_REPLAY" and missing_marks.any():
            raise ValueError(
                "Trade replay requires funding mark-price coverage; Binance returned missing marks"
            )
        # Legacy candle approximation is explicitly counted by the shared replay.
        # Preserve the immutable raw dataset; never invent a historical mark price.
        funding.loc[missing_marks, "mark_price"] = "NaN"
        filters = SymbolFilters(
            **{key: Decimal(value) for key, value in dataset["filters"].items()}
        )
        trade_mode = study.get("fidelity") == "TRADE_REPLAY"
        engine_type = TradeReplayEngine if trade_mode else PluginReplayEngine
        engine = engine_type(
            frame, funding, filters, config, start=pd.Timestamp(study["start"])
        )
        archive = TradeArchive(self.artifacts.root.parent / "trade-archives")
        if isinstance(engine, TradeReplayEngine):
            engine.attach_trades(
                archive.trades(pd.Timestamp(study["start"]), pd.Timestamp(study["end"]))
            )
        result = engine.run()
        stressed = engine_type(
            frame,
            funding,
            filters,
            replace(
                config,
                long_fee_rate=config.long_fee_rate * 2,
                short_cost_rate=config.short_cost_rate * 2,
            ),
            start=pd.Timestamp(study["start"]),
        )
        if isinstance(stressed, TradeReplayEngine):
            stressed.attach_trades(
                archive.trades(pd.Timestamp(study["start"]), pd.Timestamp(study["end"]))
            )
        stressed_result = stressed.run()
        capital = config.initial_capital
        peak = capital
        drawdown = Decimal(0)
        monthly = []
        prior = capital
        equity = result.equity.copy()
        times = pd.to_datetime(equity["dt"], utc=True)
        for value in equity["equity"]:
            current = Decimal(str(value))
            peak = max(peak, current)
            drawdown = min(drawdown, current / peak - 1)
        for month, group in equity.groupby(times.dt.strftime("%Y-%m"), sort=True):
            end_equity = Decimal(str(group.iloc[-1]["equity"]))
            start_month = pd.Timestamp(f"{month}-01", tz="UTC")
            end_month = start_month + pd.offsets.MonthBegin(1)
            full = (
                pd.Timestamp(study["start"]) <= start_month
                and pd.Timestamp(study["end"]) >= end_month
            )
            monthly.append(
                {
                    "month": month,
                    "profit": str(end_equity - prior),
                    "return": str(end_equity / prior - 1) if prior > 0 else "-1",
                    "full": full,
                }
            )
            prior = end_equity
        full_months = [row for row in monthly if row["full"]]
        trades = records(result.trades)
        closed_net = sum((Decimal(row["net_pnl"]) for row in trades), Decimal(0))
        fees = sum((Decimal(row["fees"]) for row in trades), Decimal(0))
        funding_paid = sum((Decimal(row["funding"]) for row in trades), Decimal(0))
        open_net = Decimal(0)
        if engine.position is not None:
            position = engine.position
            fees += position.fees
            funding_paid += position.funding
            unrealized = (result.latest_close - position.entry_price) * position.qty
            if position.side == "SHORT":
                unrealized = -unrealized
            open_net = (
                position.realized_partial
                + unrealized
                + position.funding
                - position.fees
            )
        reconciliation_delta = result.final_equity - capital - closed_net - open_net
        if abs(reconciliation_delta) > Decimal("0.00000001"):
            raise ValueError("Replay accounting does not reconcile")
        wins = sum(
            (Decimal(row["net_pnl"]) for row in trades if Decimal(row["net_pnl"]) > 0),
            Decimal(0),
        )
        losses = -sum(
            (Decimal(row["net_pnl"]) for row in trades if Decimal(row["net_pnl"]) < 0),
            Decimal(0),
        )
        metrics = {
            "initial_capital": str(capital),
            "final_equity": str(result.final_equity),
            "net_profit": str(result.final_equity - capital),
            "max_drawdown": str(drawdown),
            "worst_month": str(
                min(
                    (Decimal(cast(str, row["return"])) for row in full_months),
                    default=Decimal(0),
                )
            ),
            "full_months": len(full_months),
            "profitable_month_ratio": str(
                Decimal(
                    sum(Decimal(cast(str, row["profit"])) > 0 for row in full_months)
                )
                / len(full_months)
            )
            if full_months
            else "0",
            "trade_count": len(trades),
            "winning_trades": sum(Decimal(row["net_pnl"]) > 0 for row in trades),
            "losing_trades": sum(Decimal(row["net_pnl"]) < 0 for row in trades),
            "profit_factor": str(wins / losses) if losses else None,
            "total_fees": str(fees),
            "total_funding": str(funding_paid),
            "closed_net_pnl": str(closed_net),
            "open_net_pnl": str(open_net),
            "reconciliation_delta": str(reconciliation_delta),
            "stressed_net_profit": str(stressed_result.profit),
            "monthly": monthly,
            "open_position": result.open_position,
            "funding_events": result.funding_events_applied,
            "funding_mark_fallbacks": result.funding_mark_fallbacks,
            "skipped_entries": result.skipped_long_entries
            + result.skipped_short_entries,
            "fidelity": "TRADE_REPLAY" if trade_mode else "CANDLE_REPLAY",
            "policy_version": POLICY_VERSION,
        }
        metrics["ineligibility_reasons"] = eligibility(metrics)
        metrics["suitable_for_live"] = False
        artifact = self.artifacts.put(
            {
                "schema_version": 1,
                "runtime_version": version("cryptopilot-strategy-runtime"),
                "runtime_hash": runtime_hash(),
                "study": study,
                "parameters": iteration["parameters"],
                "metrics": metrics,
                "trades": trades,
                "trade_partitions": archive.provenance,
                "equity": [
                    {
                        "dt": study["start"],
                        "equity": str(capital),
                        "kind": "INITIAL_CAPITAL",
                    },
                    *records(equity),
                ],
                "intent_trace": [
                    {
                        "dt": cast(pd.Timestamp, row["dt"]).isoformat(),
                        "intents": row["intents"],
                    }
                    for row in engine.intent_trace
                ],
                "assumptions": [
                    "Stop-first when candle touches stop and target",
                    "Current exchange filters applied historically",
                    "Liquidation/order-book liquidity not modeled",
                    "All fills simulated; actual Binance candles and funding",
                    "No guarantee of profitable months",
                ],
            }
        )
        return {"artifact_id": artifact, "metrics": metrics}
