"""Training-only exit refinement at the original LIVE risk, never higher exposure."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from decimal import Decimal
from itertools import product
import logging
from pathlib import Path
from typing import Any

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.research.study import END, SELECTION_END, START, code_hash, event
from experiment_lab.research.timeframe_replay import Candidate, run_candidate
from experiment_lab.research.timeframe_study import read_dataset


def execute(dataset: Path, output: Path) -> str:
    store, data = Artifacts(output), read_dataset(dataset)
    if data["interval"] != "4h":
        raise ValueError("The supplementary hypothesis is 4h exit refinement")
    base = Candidate("4h", "trend", {})
    candidates = [
        replace(base, parameters={"stop_atr": stop, "tp1_frac": fraction})
        for stop, fraction in product(("2", "2.5", "3"), ("0.2", "0.3", "0.4", "0.5"))
    ]
    provenance = {"dataset": dataset.stem, "code_hash": code_hash()}
    protocol = store.put(
        {
            **provenance,
            "candidates": [asdict(c) for c in candidates],
            "hypothesis": "Keep more of winning trades without increasing the existing live risk of 15% or leverage cap of 6x",
            "selection_end": SELECTION_END.isoformat(),
            "ranking": "Maximize training profit subject to drawdown no worse than live baseline; risk and breakers unchanged",
            "refinement": "Then four neighbors: trail +/-0.5 ATR, first target +/-0.2R; select before later-year evaluation",
            "warning": "Additional research after timeframe study; historical periods already exposed. Not untouched validation.",
        }
    )
    baseline = run_candidate(data, data, base, START, SELECTION_END)
    baseline_drawdown = Decimal(baseline["metrics"]["max_drawdown"])
    trials: list[dict[str, Any]] = []  # Heterogeneous artifact metrics/parameters.

    def rank(row: dict[str, Any]) -> tuple[bool, Decimal]:
        metrics = row["metrics"]
        return Decimal(metrics["max_drawdown"]) >= baseline_drawdown, Decimal(
            metrics["net_profit"]
        )

    def run(candidate: Candidate, round_number: int) -> None:
        result = run_candidate(data, data, candidate, START, SELECTION_END)
        row = {
            "candidate": asdict(candidate),
            "metrics": result["metrics"],
            "round": round_number,
            "artifact_id": store.put({**provenance, **result}),
        }
        trials.append(row)
        event(
            "profit_refinement_trial",
            number=len(trials),
            candidate=asdict(candidate),
            profit=result["metrics"]["net_profit"],
            drawdown=result["metrics"]["max_drawdown"],
        )

    for candidate in candidates:
        run(candidate, 1)
    coarse = max(trials, key=rank)
    chosen = Candidate(**coarse["candidate"])
    for key, value in (
        ("trail_atr", "3.5"),
        ("trail_atr", "4.5"),
        ("tp1_r", "0.8"),
        ("tp1_r", "1.2"),
    ):
        run(replace(chosen, parameters={**chosen.parameters, key: value}), 2)
    winner = max(trials, key=rank)
    chosen = Candidate(**winner["candidate"])
    selection = store.put(
        {
            **provenance,
            "protocol": protocol,
            "baseline_training": baseline["metrics"],
            "trials": trials,
            "winner": winner,
        }
    )
    event("profit_refinement_locked", artifact_id=selection, candidate=asdict(chosen))
    evaluations = {}
    for label, start, cost in (
        ("full", START, Decimal("0.0006")),
        ("later", SELECTION_END, Decimal("0.0006")),
        ("full_stress", START, Decimal("0.0012")),
        ("later_stress", SELECTION_END, Decimal("0.0012")),
    ):
        result = run_candidate(data, data, chosen, start, END, cost=cost, detailed=True)
        evaluations[label] = {
            "metrics": result["metrics"],
            "artifact_id": store.put({**provenance, **result}),
        }
        event(
            "profit_refinement_evaluated",
            label=label,
            profit=result["metrics"]["net_profit"],
            drawdown=result["metrics"]["max_drawdown"],
        )
    repeat = run_candidate(data, data, chosen, START, END)
    if repeat["metrics"] != evaluations["full"]["metrics"]:
        raise ValueError("Replay did not repeat exactly")
    report = store.put(
        {
            **provenance,
            "protocol": protocol,
            "selection": selection,
            "winner": winner,
            "evaluations": evaluations,
            "trial_count": len(trials),
            "deterministic_repeat": "PASS",
            "suitable_for_live": False,
        }
    )
    event("profit_refinement_finished", artifact_id=report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    execute(args.dataset, args.output)
