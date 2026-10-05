"""Prepare public market input and hash/config metadata for the MIR oracle.

Run in a QA-only venv with numba, numpy and pandas; no credentials or network.
Backend tests calculate expected results at runtime; research results stay local.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MIR = ROOT / "experiments/monthly_income_research"
sys.path.insert(0, str(MIR / "src"))
from mir.data import Market  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402

PARAMS = dict(
    fast=20,
    slow=200,
    stop_t=2.5,
    stop_b=2.5,
    tp_r=2.0,
    trail=3.0,
    n=24,
    look=360,
    q=0.35,
    er=0.0,
    er_n=84,
    short=1,
    hyst=1.0,
)
FIXTURES = ROOT / "backend/tests/fixtures"


def main() -> None:
    raw = pd.read_csv(MIR / "data/btcusdt_perp_1h.csv")
    raw["dt"] = pd.to_datetime(raw["dt"], utc=True)
    h1 = raw.set_index("dt").loc["2026-03-01":"2026-09-21 23:00:00"].copy()
    assert (h1.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()
    columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base",
    ]
    h1 = h1[columns].astype(float)
    funding = pd.read_csv(MIR / "data/btcusdt_funding.csv")
    funding["dt"] = pd.to_datetime(funding["dt"], utc=True, format="mixed")
    rates = (
        funding.groupby(funding["dt"].dt.floor("1h"))["funding_rate"]
        .sum()
        .reindex(h1.index, fill_value=0)
    )
    saved = h1.copy()
    saved["funding_rate"] = rates
    path = FIXTURES / "atlas7_1h_2026.csv"
    saved.to_csv(path, index_label="dt", float_format="%.12g")
    # Re-read the exact committed decimal strings before building the oracle.
    h1 = pd.read_csv(path, index_col="dt", parse_dates=["dt"])
    h4 = h1.resample("4h").agg(
        dict(
            open="first",
            high="max",
            low="min",
            close="last",
            volume="sum",
            quote_volume="sum",
            taker_buy_base="sum",
        )
    )
    m = Market(
        h1,
        h4,
        h1.funding_rate.to_numpy(),
        np.arange(3, len(h1), 4),
        (h1.index.year * 12 + h1.index.month - 1).to_numpy(),
    )
    spec = dual(Feat(m), PARAMS)
    spec.signals.entry_long[:400] = False
    spec.signals.entry_short[:400] = False
    cfg = replace(
        spec.config,
        init_eq=1000.0,
        risk_pct=0.04,
        lev_cap=3.0,
        taker=0.0007,
        maker=0.0002,
        breaker_pct=0.08,
        qty_step=0.0001,
        min_notional=50.0,
    )
    source_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            MIR / "src/mir/engine.py",
            MIR / "src/mir/strategies.py",
            MIR / "src/mir/indicators.py",
            MIR / "src/mir/data.py",
            path,
        ]
    }
    payload = dict(
        reference="MIR dual / final_eval.PARAMS",
        hashes=source_hashes,
        params=PARAMS,
        config=vars(cfg),
        warmup=400,
    )
    (FIXTURES / "atlas7_execution_oracle.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(
        json.dumps(
            dict(
                hours=len(h1),
                decisions=len(h4),
            )
        )
    )


if __name__ == "__main__":
    main()
