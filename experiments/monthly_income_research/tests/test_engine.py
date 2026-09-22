"""Deterministic checks for the research engine and the recommended signals."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import Market  # noqa: E402
from mir.engine import Config, Signals, run  # noqa: E402
from mir.strategies import Feat, dual  # noqa: E402

PARAMS = dict(fast=20, slow=200, stop_t=2.5, stop_b=2.5, tp_r=2.0, trail=3.0, n=24, look=360,
              q=0.35, er=0.0, er_n=84, short=1, hyst=1.0)


def synthetic_market(n4: int = 900, seed: int = 7, funding: float = 0.0001) -> Market:
    rng = np.random.default_rng(seed)
    n1 = n4 * 4
    idx = pd.date_range("2024-01-01", periods=n1, freq="1h", tz="UTC")
    steps = rng.normal(0, 0.004, n1) + 0.0002 * np.sin(np.arange(n1) / 400)
    close = 50_000 * np.exp(np.cumsum(steps))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n1))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n1))
    h1 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 1.0, "quote_volume": 1.0, "taker_buy_base": 0.5}, index=idx)
    groups = np.arange(n1) // 4
    h4 = h1.groupby(groups).agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                 "volume": "sum", "quote_volume": "sum",
                                 "taker_buy_base": "sum"})
    h4.index = idx[::4]
    fund = np.zeros(n1)
    fund[(idx.hour % 8) == 0] = funding
    month = (idx.year * 12 + idx.month - 1).to_numpy()
    return Market(h1=h1, h4=h4, funding_h1=fund, dec_idx_h1=np.arange(3, n1, 4),
                  month_id_h1=month)


def test_equity_change_equals_sum_of_trade_pnl() -> None:
    m = synthetic_market()
    spec = dual(Feat(m), PARAMS)
    cfg = replace(spec.config, init_eq=10_000.0, risk_pct=0.02, lev_cap=3.0)
    res = run(m, spec.signals, cfg)
    assert len(res.trades["pnl"]) > 5
    assert res.equity[-1] - cfg.init_eq == pytest.approx(res.trades["pnl"].sum(), abs=1e-6)


def test_buy_and_hold_pays_funding_and_fees() -> None:
    m = synthetic_market(funding=0.0001)
    n4 = len(m.h4)
    el = np.zeros(n4, bool)
    el[0] = True
    res = run(m, Signals(entry_long=el, entry_short=np.zeros(n4, bool)),
              Config(init_eq=1_000.0, size_mode=1, notional_frac=1.0, lev_cap=1.0))
    t = res.trades
    assert len(t["pnl"]) == 1
    gross = t["qty"][0] * (t["exit_px"][0] - t["entry_px"][0])
    assert t["funding"][0] > 0
    assert t["pnl"][0] == pytest.approx(gross - t["fee"][0] - t["funding"][0], rel=1e-9)


def test_signals_are_causal() -> None:
    """Changing future candles must not change any earlier decision."""
    m = synthetic_market()
    base = dual(Feat(m), PARAMS).signals
    cut = 700
    h1 = m.h1.copy()
    h1.iloc[(cut + 1) * 4:, :4] *= 1.25  # rewrite everything after 4h bar `cut`
    h4 = m.h4.copy()
    h4.iloc[cut + 1:, :4] *= 1.25
    changed = Market(h1=h1, h4=h4, funding_h1=m.funding_h1, dec_idx_h1=m.dec_idx_h1,
                     month_id_h1=m.month_id_h1)
    alt = dual(Feat(changed), PARAMS).signals
    for name in ("entry_long", "entry_short", "exit_long", "exit_short"):
        a, b = getattr(base, name)[: cut + 1], getattr(alt, name)[: cut + 1]
        assert np.array_equal(a, b), name
    np.testing.assert_allclose(base.stop_long[: cut + 1], alt.stop_long[: cut + 1])


def test_lot_rounding_and_min_notional() -> None:
    m = synthetic_market()
    spec = dual(Feat(m), PARAMS)
    cfg = replace(spec.config, init_eq=190.0, risk_pct=0.02, lev_cap=3.0, qty_step=0.001,
                  min_notional=50.0)
    res = run(m, spec.signals, cfg)
    q = res.trades["qty"]
    assert len(q) > 0
    assert np.allclose(np.round(q / 0.001), q / 0.001, atol=1e-6)
    assert (q >= 0.001 - 1e-12).all()
    # every opening fill met the exchange minimum notional
    opened = {}
    for e, qty, px in zip(res.trades["entry_i"], q, res.trades["entry_px"], strict=True):
        opened[e] = opened.get(e, 0.0) + qty * px
    assert min(opened.values()) >= 50.0 - 1e-9


def test_monthly_breaker_blocks_same_side_entries() -> None:
    m = synthetic_market()
    spec = dual(Feat(m), PARAMS)
    base = replace(spec.config, init_eq=10_000.0, risk_pct=0.05, lev_cap=3.0)
    free = run(m, spec.signals, base)
    capped = run(m, spec.signals, replace(base, breaker_pct=0.02))
    assert len(capped.trades["pnl"]) <= len(free.trades["pnl"])
