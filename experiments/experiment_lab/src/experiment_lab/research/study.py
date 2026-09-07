"""Bounded two-round search. Selection never reads the later validation results."""

import argparse
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from itertools import product
import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from strategy_runtime.filters import SymbolFilters
from strategy_runtime.parameters import TrendRiderParameters
from strategy_runtime.replay import PluginReplayEngine, ReplayConfig, config_dict

from experiment_lab.adapters.artifacts import Artifacts, canonical
from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.adapters.provenance import evaluator_hash
from experiment_lab.adapters.replay import records
from experiment_lab.research.regime_long import Parameters, RegimeLong
from experiment_lab.research.replay import ResearchReplay, summarize

LOGGER = logging.getLogger(__name__)
START = pd.Timestamp("2023-09-01", tz="UTC")
SELECTION_END = pd.Timestamp("2025-09-01", tz="UTC")
END = pd.Timestamp("2026-09-01", tz="UTC")
BASE_COST = Decimal("0.0006")  # 4bp fee + 2bp adverse-execution allowance per side.
ITERATION_25 = dict(
    risk_pct="8",
    leverage_cap="4",
    long_month_cap="0.02",
    stop_atr="2",
    tp1_frac="0.5",
    trail_atr="3.5",
)


def event(name: str, **fields: object) -> None:
    LOGGER.info(
        canonical({"ts": datetime.now(UTC).isoformat(), "event": name, **fields})
    )


def code_hash() -> str:
    digest = hashlib.sha256(evaluator_hash().encode())
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_dataset(path: Path) -> dict[str, Any]:
    # Immutable Lab JSON contains nested records of heterogeneous values.
    data = Artifacts(path.parent).get(path.stem)
    if not isinstance(data, dict):
        raise ValueError("Dataset artifact must be an object")
    validate_dataset(data)
    if data["interval"] != "4h":
        raise ValueError("This hypothesis uses closed 4h candles only")
    return data


def run_case(
    data: dict[str, Any],
    start: pd.Timestamp,
    end: pd.Timestamp,
    candidate: Parameters | str,
    cost: Decimal = BASE_COST,
    capital: Decimal = Decimal("200"),
) -> dict[str, Any]:
    frame = pd.DataFrame(data["candles"])
    times = pd.to_datetime(frame["dt"], utc=True)
    if times.min() > start - pd.Timedelta(
        hours=4 * 200
    ) or times.max() < end - pd.Timedelta(hours=4):
        raise ValueError("Dataset does not cover evaluation plus warmup")
    frame = frame[times < end]
    funding = pd.DataFrame(data["funding"])
    funding_times = pd.to_datetime(funding["dt"], utc=True, format="mixed")
    funding = funding[(funding_times >= start) & (funding_times < end)].copy()
    funding["mark_price"] = funding["mark_price"].map(
        lambda x: "NaN" if x is None or str(x).strip() == "" else x
    )
    filters = SymbolFilters(**{k: Decimal(v) for k, v in data["filters"].items()})
    parameters = TrendRiderParameters.from_values(
        ITERATION_25 if candidate == "iteration_25" else {}
    )
    config = ReplayConfig(
        parameters=parameters,
        initial_capital=capital,
        long_fee_rate=cost,
        short_cost_rate=cost,
    )
    if candidate == "iteration_25":
        config = replace(
            config,
            risk_pct=Decimal("8"),
            leverage_cap=Decimal("4"),
            long_breaker_cap=Decimal("0.02"),
        )
    if candidate == "live_low_risk":
        config = replace(config, risk_pct=Decimal("1.5"), leverage_cap=Decimal("1"))
    engine: PluginReplayEngine
    if isinstance(candidate, Parameters):
        config = replace(
            config,
            parameters=replace(parameters, tp1_frac=0.5),
            risk_pct=Decimal("1.5"),
            leverage_cap=Decimal("1"),
            long_breaker_cap=Decimal("0.04"),
        )
        engine = ResearchReplay(frame, funding, filters, config, start=start)
        engine.attach(RegimeLong(candidate))
    else:
        if candidate not in {"live_baseline", "iteration_25", "live_low_risk"}:
            raise ValueError("Unknown comparison strategy")
        engine = PluginReplayEngine(frame, funding, filters, config, start=start)
    result = engine.run()
    return {
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "cost_per_side": str(cost),
        "account_config": config_dict(config),
        "parameters": asdict(candidate)
        if isinstance(candidate, Parameters)
        else candidate,
        "metrics": summarize(engine, result, end),
        "trades": records(result.trades),
        "equity": records(result.equity),
        "intent_trace": records(pd.DataFrame(engine.intent_trace)),
    }


def coarse_candidates() -> list[Parameters]:
    families: tuple[Literal["pullback", "breakout"], ...] = ("pullback", "breakout")
    return [
        Parameters(family, lookback, entry, stop, trail)
        for family in families
        for lookback, entry, stop, trail in product(
            (20, 40),
            (0.5, 1.0) if family == "pullback" else (0.0,),
            (1.5, 2.5),
            (2.0, 4.0),
        )
    ]


def neighbors(p: Parameters) -> list[Parameters]:
    variants = []
    for name, distance in (("lookback", 4), ("stop_atr", 0.25), ("trail_atr", 0.5)):
        for sign in (-1, 1):
            variants.append(replace(p, **{name: getattr(p, name) + sign * distance}))
    if p.family == "pullback":
        variants.extend(
            replace(p, entry_atr=p.entry_atr + sign * 0.25) for sign in (-1, 1)
        )
    return variants


def ranking(metrics: dict[str, Any]) -> tuple[bool, Decimal, Decimal]:
    profit = Decimal(metrics["net_profit"])
    drawdown = abs(Decimal(metrics["max_drawdown"]))
    ratio = Decimal(metrics["profitable_months"]) / max(1, metrics["full_months"])
    prudent = (
        profit > 0
        and drawdown <= Decimal("0.15")
        and Decimal(metrics["worst_month"]) >= Decimal("-0.05")
        and metrics["trade_count"] >= 30
    )
    return prudent, ratio, profit / max(Decimal(1), Decimal(200) * drawdown)


def study(dataset: Path, recent: Path, output: Path) -> str:
    artifacts = Artifacts(output)
    data, recent_data = load_dataset(dataset), load_dataset(recent)
    provenance = {
        "code_hash": code_hash(),
        "dataset": dataset.stem,
        "recent_dataset": recent.stem,
    }
    protocol_id = artifacts.put(
        {
            **provenance,
            "coarse_candidates": [asdict(p) for p in coarse_candidates()],
            "selection_start": START.isoformat(),
            "selection_end": SELECTION_END.isoformat(),
            "validation_end": END.isoformat(),
            "ranking": "positive net, DD<=15%, worst month>=-5%, >=30 trades; then profitable-month ratio; then net profit / max(1, 200*DD)",
            "refinement": "one coordinate at a time around training leader; no validation feedback",
            "monthly_target": ">60% of all complete months (flat months count against target)",
            "risk_pct": "1.5",
            "leverage_cap": "1",
            "breaker": "0.04",
            "capital": "200",
            "base_cost_per_side": str(BASE_COST),
            "fidelity": "actual Binance public candles and funding, simulated OHLC fills; no raw-trade replay",
            "validation_warning": "Retrospective validation: these dates were exposed to previous strategy research. No untouched or forward-live claim.",
        }
    )
    event("research_protocol_saved", artifact_id=protocol_id)
    trials = []

    def evaluate(candidates: list[Parameters], round_number: int) -> None:
        for candidate in candidates:
            result = run_case(data, START, SELECTION_END, candidate)
            artifact_id = artifacts.put({**provenance, **result})
            row = {
                "round": round_number,
                "parameters": asdict(candidate),
                "artifact_id": artifact_id,
                "metrics": result["metrics"],
            }
            trials.append(row)
            event(
                "research_candidate_finished",
                number=len(trials),
                round=round_number,
                artifact_id=artifact_id,
                parameters=asdict(candidate),
                metrics=result["metrics"],
            )

    evaluate(coarse_candidates(), 1)
    coarse = max(trials, key=lambda x: ranking(x["metrics"]))
    evaluate(neighbors(Parameters(**coarse["parameters"])), 2)
    winner = max(trials, key=lambda x: ranking(x["metrics"]))
    candidate = Parameters(**winner["parameters"])
    selection_id = artifacts.put(
        {
            **provenance,
            "protocol": protocol_id,
            "trials": trials,
            "winner": winner,
            "coarse_winner": coarse,
        }
    )
    event(
        "research_selection_locked",
        artifact_id=selection_id,
        parameters=asdict(candidate),
    )
    evaluations = {}
    recent_start, recent_end = (
        pd.Timestamp(recent_data["start"]),
        pd.Timestamp(recent_data["end"]),
    )
    for label, source, begin, end, parameters, cost in (
        ("winner_validation", data, SELECTION_END, END, candidate, BASE_COST),
        (
            "winner_validation_stress",
            data,
            SELECTION_END,
            END,
            candidate,
            BASE_COST * 2,
        ),
        ("winner_full", data, START, END, candidate, BASE_COST),
        ("winner_full_stress", data, START, END, candidate, BASE_COST * 2),
        ("winner_recent", recent_data, recent_start, recent_end, candidate, BASE_COST),
        ("live_low_risk_full", data, START, END, "live_low_risk", BASE_COST),
        (
            "live_low_risk_validation",
            data,
            SELECTION_END,
            END,
            "live_low_risk",
            BASE_COST,
        ),
        (
            "live_low_risk_recent",
            recent_data,
            recent_start,
            recent_end,
            "live_low_risk",
            BASE_COST,
        ),
        (
            "live_recent",
            recent_data,
            recent_start,
            recent_end,
            "live_baseline",
            BASE_COST,
        ),
        (
            "iteration_25_recent",
            recent_data,
            recent_start,
            recent_end,
            "iteration_25",
            BASE_COST,
        ),
    ):
        result = run_case(source, begin, end, parameters, cost)
        evaluations[label] = {
            "artifact_id": artifacts.put({**provenance, **result}),
            "metrics": result["metrics"],
        }
        event("research_validation_finished", label=label, **evaluations[label])
    verification = run_case(data, SELECTION_END, END, candidate)
    if verification["metrics"] != evaluations["winner_validation"]["metrics"]:
        raise ValueError("Deterministic repeat failed")
    # BTC lot-size thresholds matter for small accounts. Diagnostics only: these
    # results cannot change selection or establish scale-invariant returns.
    for capital in (
        Decimal("160"),
        Decimal("240"),
        Decimal(winner["metrics"]["final_equity"]),
    ):
        result = run_case(data, SELECTION_END, END, candidate, capital=capital)
        label = f"winner_validation_capital_{capital}"
        evaluations[label] = {
            "artifact_id": artifacts.put({**provenance, **result}),
            "metrics": result["metrics"],
        }
        event(
            "research_capital_sensitivity_finished", label=label, **evaluations[label]
        )
    report = {
        **provenance,
        "protocol": protocol_id,
        "selection": selection_id,
        "winner": winner,
        "coarse_winner": coarse,
        "trial_count": len(trials),
        "evaluations": evaluations,
        "deterministic_repeat": "PASS",
        "suitable_for_live": False,
        "limitations": [
            "Repeated historical research is not untouched validation",
            "Current exchange filters applied historically",
            "No order-book/liquidation replay; slippage is a cost allowance",
            "Month-end marked equity, not withdrawals",
            "4h close drawdown understates possible intrabar drawdown",
            "No monthly-profit or passive-income guarantee",
        ],
    }
    report_id = artifacts.put(report)
    event("research_study_finished", artifact_id=report_id)
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--recent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    study(args.dataset, args.recent, args.output)
