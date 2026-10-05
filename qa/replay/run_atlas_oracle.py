"""Run the unchanged MIR oracle without publishing cached research results.

This isolated QA process replaces only numba's compiler decorator with an identity
decorator. The original strategy/engine source executes unchanged as plain Python;
numpy/pandas are already backend test dependencies. Results go to the test process,
not to committed fixtures. No credentials or network calls are used.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend/tests/fixtures"
sys.path.insert(0, str(ROOT / "experiments/monthly_income_research/src"))


def no_jit(**_options):
    return lambda function: function


# Process isolation prevents this QA-only compiler shim leaking into application
# imports or other tests. No engine expressions or execution rules are replaced.
compiler = ModuleType("numba")
compiler.njit = no_jit
sys.modules["numba"] = compiler

from mir.data import Market  # noqa: E402
from mir.engine import run  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402


def main() -> None:
    metadata = json.loads((FIXTURES / "atlas7_execution_oracle.json").read_text())
    h1 = pd.read_csv(
        FIXTURES / "atlas7_1h_2026.csv", index_col="dt", parse_dates=["dt"]
    )
    h4 = h1.resample("4h").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "quote_volume": "sum",
            "taker_buy_base": "sum",
        }
    )
    market = Market(
        h1,
        h4,
        h1.funding_rate.to_numpy(),
        np.arange(3, len(h1), 4),
        (h1.index.year * 12 + h1.index.month - 1).to_numpy(),
    )
    spec = dual(Feat(market), metadata["params"])
    spec.signals.entry_long[: metadata["warmup"]] = False
    spec.signals.entry_short[: metadata["warmup"]] = False
    result = run(market, spec.signals, replace(spec.config, **metadata["config"]))
    print(
        json.dumps(
            {
                "equity": result.equity.tolist(),
                "trades": {key: value.tolist() for key, value in result.trades.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
