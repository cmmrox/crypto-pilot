"""Parity gate (QA-3, BSD G1): the production Trend Rider v6 engine must
reproduce the validated research engine (research/backtests/final_composite.py)
bar-for-bar over the full 3-year history.

The research engine is the source of truth. This test imports it directly, runs
both engines on the same candles, and asserts zero decision mismatches plus a
composite equity match to floating-point tolerance.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[3]
RESEARCH = REPO / "research" / "backtests"
CSV = REPO / "research" / "data" / "btc_4h.csv"

pytestmark = pytest.mark.parity


@contextlib.contextmanager
def _in_research_dir():
    """Run with research/backtests on sys.path and as CWD (for its CSV symlinks)."""
    old_cwd = os.getcwd()
    os.chdir(RESEARCH)
    sys.path.insert(0, str(RESEARCH))
    try:
        yield
    finally:
        os.chdir(old_cwd)
        with contextlib.suppress(ValueError):
            sys.path.remove(str(RESEARCH))


def _reference_composite() -> pd.Series:
    """Run the research engine's CHOSEN config → reference composite equity."""
    with _in_research_dir():
        import backtest as bt
        from circuit_breaker import managed_cb
        from final_composite import apply_month_breaker
        from research_ls import backtest as vec_bt
        from research_ls import load as rl_load
        from short_lab import s_deep

        df_bt = bt.add_indicators(bt.load("btc_4h.csv"))
        long_eq = managed_cb(df_bt, tp1_frac=0.4, trail_atr=4.0, month_loss_cap=0.04)["equity"]
        long_eq.index = pd.to_datetime(long_eq.index, utc=True)
        r_long = long_eq.pct_change().fillna(0.0)

        df_rl = rl_load("btc_4h.csv")
        r_long.index = df_rl.index[: len(r_long)]
        tgt = s_deep(df_rl, 0.5)
        r_short = vec_bt(df_rl, tgt, vol_target=0.4)["equity"].pct_change().fillna(0.0)
        r_short = apply_month_breaker(r_short, 0.04)

        r = r_long.add(0.75 * r_short, fill_value=0.0)
        return (1 + r).cumprod()


def _production_composite() -> pd.Series:
    from app.strategies.engine import run_composite

    df = pd.read_csv(CSV, parse_dates=["dt"]).reset_index(drop=True)
    return run_composite(df).equity


def test_composite_equity_matches_research_bar_for_bar() -> None:
    ref = _reference_composite().to_numpy()
    prod = _production_composite().to_numpy()
    assert len(ref) == len(prod), f"length mismatch: ref {len(ref)} vs prod {len(prod)}"
    # Same float64 operations → agreement to well within 1e-9 relative.
    max_abs = float(np.max(np.abs(ref - prod)))
    max_rel = float(np.max(np.abs(ref - prod) / np.maximum(np.abs(ref), 1e-12)))
    assert max_rel < 1e-9, f"composite equity drift too large: rel {max_rel:.2e} abs {max_abs:.2e}"


def test_long_in_market_decisions_match() -> None:
    """The long engine's in-market bars must match the research engine exactly."""
    with _in_research_dir():
        import backtest as bt
        from circuit_breaker import managed_cb

        df_bt = bt.add_indicators(bt.load("btc_4h.csv"))
        ref_eq = managed_cb(df_bt, tp1_frac=0.4, trail_atr=4.0, month_loss_cap=0.04)["equity"]
        ref_r = ref_eq.pct_change().fillna(0.0).to_numpy()

    from app.strategies.engine import add_indicators, long_equity

    df = pd.read_csv(CSV, parse_dates=["dt"]).reset_index(drop=True)
    prod_eq = long_equity(add_indicators(df))[0]
    prod_r = prod_eq.pct_change().fillna(0.0).to_numpy()

    assert len(ref_r) == len(prod_r)
    assert float(np.max(np.abs(ref_r - prod_r))) < 1e-12


def test_short_exposure_sign_matches() -> None:
    """Bars with a short position must match the research sleeve exactly."""
    with _in_research_dir():
        from research_ls import load as rl_load
        from short_lab import s_deep

        df_rl = rl_load("btc_4h.csv")
        ref_target = s_deep(df_rl, 0.5).to_numpy()

    from app.strategies.engine import add_indicators, short_target

    df = pd.read_csv(CSV, parse_dates=["dt"]).reset_index(drop=True)
    prod_target = short_target(add_indicators(df)).to_numpy()

    # s_deep is the raw target (pre vol-scale); a bar is "short" iff target == -1.
    ref_short = ref_target < 0
    prod_short = prod_target < 0
    mismatches = int(np.sum(ref_short != prod_short))
    assert mismatches == 0, f"{mismatches} short-decision mismatches vs research"
