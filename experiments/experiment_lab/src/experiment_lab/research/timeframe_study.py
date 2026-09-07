"""Dated three-timeframe search, training-only selection and locked evaluation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from decimal import Decimal
from itertools import product
import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from strategy_runtime.parameters import validate_parameters

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.research.study import (
    END,
    ITERATION_25,
    SELECTION_END,
    START,
    code_hash,
    event,
)
from experiment_lab.research.timeframe_replay import Candidate, run_candidate

INTERVALS = ("30m", "1h", "4h")


def universe() -> list[Candidate]:
    candidates = []
    families: tuple[Literal["trend", "aligned"], ...] = ("trend", "aligned")
    exits: tuple[dict[str, str], ...] = (
        {},
        {"stop_atr": "2", "tp1_r": "1.5", "trail_atr": "5"},
        {"stop_atr": "3", "trail_atr": "4"},
    )
    for interval in INTERVALS:
        for family, profile, risk in product(
            families, exits, (("8", "4"), ("15", "6"))
        ):
            if family == "aligned" and interval == "4h":
                continue  # Same-timeframe confirmation would duplicate existing rules.
            candidates.append(
                Candidate(
                    interval,
                    family,
                    {**profile, "risk_pct": risk[0], "leverage_cap": risk[1]},
                )
            )
        candidates.append(Candidate(interval, "trend", ITERATION_25.copy()))
        for lookback, stop, risk in product(
            (20, 40), ("1.5", "2.5"), (("8", "4"), ("15", "6"))
        ):
            candidates.append(
                Candidate(
                    interval,
                    "breakout",
                    {
                        "stop_atr": stop,
                        "tp1_frac": "0.5",
                        "trail_atr": "4",
                        "risk_pct": risk[0],
                        "leverage_cap": risk[1],
                    },
                    lookback,
                )
            )
    return candidates


def refine(candidate: Candidate) -> list[Candidate]:
    values = validate_parameters(candidate.parameters)
    variants = []
    # Do not improve the score by turning up leverage/risk or loosening breakers.
    for key, delta in (("stop_atr", Decimal("0.5")), ("trail_atr", Decimal("0.5"))):
        for sign in (-1, 1):
            changed = {**values, key: str(Decimal(values[key]) + sign * delta)}
            validate_parameters(changed)
            variants.append(replace(candidate, parameters=changed))
    if candidate.family == "breakout":
        variants.extend(
            replace(candidate, breakout_lookback=candidate.breakout_lookback + delta)
            for delta in (-4, 4)
        )
    else:
        variants.extend(
            replace(
                candidate,
                parameters={
                    **values,
                    "tp1_frac": str(Decimal(values["tp1_frac"]) + delta),
                },
            )
            for delta in (Decimal("-0.1"), Decimal("0.1"))
        )
    return variants


def ranking(metrics: dict[str, Any]) -> tuple[bool, Decimal]:
    # Heterogeneous JSON metrics include numeric strings and monthly records.
    years = [
        sum(
            (Decimal(m["profit"]) for m in metrics["monthly"][offset : offset + 12]),
            Decimal(0),
        )
        for offset in (0, 12)
    ]
    qualified = (
        Decimal(metrics["net_profit"]) > 0
        and Decimal(metrics["max_drawdown"]) >= Decimal("-0.45")
        and Decimal(metrics["worst_month"]) >= Decimal("-0.15")
        and metrics["trade_count"] >= 30
        and all(value > 0 for value in years)
    )
    return qualified, Decimal(metrics["net_profit"])


def read_dataset(path: Path) -> dict[str, Any]:
    value = Artifacts(path.parent).get(path.stem)
    if not isinstance(value, dict):
        raise ValueError("Dataset must be an object")
    validate_dataset(value)
    if pd.Timestamp(value["start"]) > START or pd.Timestamp(value["end"]) < END:
        raise ValueError("Three complete years are required")
    return value


def compare_ohlc(small: dict[str, Any], large: dict[str, Any]) -> None:
    """Verify actual lower-timeframe bars aggregate to the reference market prices."""
    frames = []
    for data in (small, large):
        frame = pd.DataFrame(data["candles"])
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
        frame = frame[(frame["dt"] >= START) & (frame["dt"] < END)].set_index("dt")
        for column in ("open", "high", "low", "close"):
            frame[column] = frame[column].map(Decimal)
        frames.append(frame[["open", "high", "low", "close"]])
    aggregated = (
        frames[0]
        .resample(large["interval"])
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    )
    pd.testing.assert_frame_equal(aggregated, frames[1], check_freq=False)


def execute(paths: list[Path], output: Path) -> str:
    store = Artifacts(output)
    datasets = {
        data["interval"]: data for data in (read_dataset(path) for path in paths)
    }
    if set(datasets) != set(INTERVALS):
        raise ValueError("Provide exactly 30m, 1h and 4h datasets")
    compare_ohlc(datasets["30m"], datasets["1h"])
    compare_ohlc(datasets["30m"], datasets["4h"])
    provenance = {
        "datasets": {read_dataset(path)["interval"]: path.stem for path in paths},
        "code_hash": code_hash(),
    }
    protocol = store.put(
        {
            **provenance,
            "candidates": [asdict(c) for c in universe()],
            "selection": [START.isoformat(), SELECTION_END.isoformat()],
            "validation_end": END.isoformat(),
            "ranking": "Positive profit in both training years; >=30 trades; DD<=45%; worst month>=-15%; then maximize net profit",
            "refinement": "Six neighbors of global training winner, no risk/leverage increase; lock one winner per timeframe",
            "cost": "0.0006 per side, doubled in stress",
            "capital": "200, no withdrawals",
            "warning": "All history was exposed to earlier research; retrospective only. No liquidation model or activation.",
            "ohlc_aggregation_check": "PASS",
        }
    )
    event(
        "timeframe_protocol_saved",
        artifact_id=protocol,
        candidate_count=len(universe()),
    )
    trials: list[dict[str, Any]] = []

    def evaluate(candidate: Candidate, round_number: int) -> None:
        result = run_candidate(
            datasets[candidate.interval],
            datasets["4h"],
            candidate,
            START,
            SELECTION_END,
        )
        row = {
            "candidate": asdict(candidate),
            "metrics": result["metrics"],
            "round": round_number,
            "artifact_id": store.put({**provenance, **result}),
        }
        trials.append(row)
        event(
            "timeframe_training_finished",
            number=len(trials),
            candidate=asdict(candidate),
            profit=result["metrics"]["net_profit"],
            drawdown=result["metrics"]["max_drawdown"],
            qualified=ranking(result["metrics"])[0],
        )

    for candidate in universe():
        evaluate(candidate, 1)
    first_winner = max(trials, key=lambda row: ranking(row["metrics"]))
    for candidate in refine(Candidate(**first_winner["candidate"])):
        evaluate(candidate, 2)
    winners = {
        interval: max(
            (row for row in trials if row["candidate"]["interval"] == interval),
            key=lambda row: ranking(row["metrics"]),
        )
        for interval in INTERVALS
    }
    selection = store.put(
        {
            **provenance,
            "protocol": protocol,
            "trials": trials,
            "winners": winners,
            "first_winner": first_winner,
        }
    )
    event(
        "timeframe_selection_locked",
        artifact_id=selection,
        winners={k: v["candidate"] for k, v in winners.items()},
    )
    evaluations: dict[str, Any] = {}

    def validate(
        label: str,
        candidate: Candidate,
        begin: pd.Timestamp,
        cost: Decimal = Decimal("0.0006"),
    ) -> None:
        result = run_candidate(
            datasets[candidate.interval],
            datasets["4h"],
            candidate,
            begin,
            END,
            cost=cost,
            detailed=True,
        )
        evaluations[label] = {
            "candidate": asdict(candidate),
            "metrics": result["metrics"],
            "artifact_id": store.put({**provenance, **result}),
        }
        event(
            "timeframe_validation_finished",
            label=label,
            profit=result["metrics"]["net_profit"],
            drawdown=result["metrics"]["max_drawdown"],
        )

    for interval in INTERVALS:
        candidate = Candidate(**winners[interval]["candidate"])
        for suffix, begin, cost in (
            ("full", START, Decimal("0.0006")),
            ("full_stress", START, Decimal("0.0012")),
            ("later", SELECTION_END, Decimal("0.0006")),
            ("later_stress", SELECTION_END, Decimal("0.0012")),
        ):
            validate(f"winner_{interval}_{suffix}", candidate, begin, cost)
        for suffix, begin in (("full", START), ("later", SELECTION_END)):
            validate(
                f"live_parameters_{interval}_{suffix}",
                Candidate(interval, "trend", {}),
                begin,
            )
    report_id = store.put(
        {
            **provenance,
            "protocol": protocol,
            "selection": selection,
            "trial_count": len(trials),
            "winners": winners,
            "evaluations": evaluations,
            "suitable_for_live": False,
        }
    )
    event("timeframe_study_finished", artifact_id=report_id)
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    execute(args.dataset, args.output)
