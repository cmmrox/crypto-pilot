"""Production-engine Atlas 6 Trail at matched risk over the same 2020-06 -> now window."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_risk_profiles import run  # noqa: E402

if __name__ == "__main__":
    rows = []
    out = {}
    for risk, lev, sleeve in [("15", "6", 0.75), ("2", "3", 0.25), ("3", "3", 0.35)]:
        cap = 0.04 if risk == "15" else None
        r = run(risk, lev, sleeve, cap, start="2020-06-01", capital="10000")
        rows.append(r)
    pd.set_option("display.width", 220)
    print(pd.DataFrame(rows).to_string(index=False))
