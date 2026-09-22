"""Run strategy grids once over the full history and walk-forward select on months."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from mir.data import Market
from mir.engine import Config, run
from mir.metrics import window_stats
from mir.strategies import FAMILIES, Feat, Spec

EVAL_START = "2020-06-01"  # after >= 200 days of 4h warm-up for the slowest indicator


def base_config(spec: Spec, risk_pct: float = 0.01, lev_cap: float = 3.0,
                init_eq: float = 10_000.0, taker: float = 0.0007) -> Config:
    return replace(spec.config, init_eq=init_eq, risk_pct=risk_pct,
                   lev_cap=max(lev_cap, spec.config.lev_cap) if spec.config.size_mode == 1
                   else lev_cap, taker=taker)


def monthly_from_equity(equity: np.ndarray, index: pd.DatetimeIndex, start: str,
                        init_eq: float) -> pd.Series:
    eq = pd.Series(equity, index=index)
    eq = eq[eq.index >= pd.Timestamp(start, tz="UTC")]
    me = eq.groupby(eq.index.tz_convert(None).to_period("M")).last()
    prev = me.shift(1)
    prev.iloc[0] = init_eq
    return me / prev - 1.0


def run_grid(market: Market, families: list[str] | None = None, taker: float = 0.0007,
             risk_pct: float = 0.01) -> tuple[pd.DataFrame, pd.DataFrame]:
    feat = Feat(market)
    months: dict[str, pd.Series] = {}
    rows = []
    for fam, (build, grid) in FAMILIES.items():
        if families and fam not in families:
            continue
        for params in grid():
            spec = build(feat, params)
            cfg = base_config(spec, risk_pct=risk_pct, taker=taker)
            # Flat until EVAL_START: mask entries before it so every config starts flat.
            start_k = int(np.searchsorted(market.h4.index, pd.Timestamp(EVAL_START, tz="UTC")))
            sig = spec.signals
            sig.entry_long = sig.entry_long.copy()
            sig.entry_short = sig.entry_short.copy()
            sig.entry_long[: max(start_k - 1, 0)] = False
            sig.entry_short[: max(start_k - 1, 0)] = False
            res = run(market, sig, cfg)
            label = spec.label()
            mret = monthly_from_equity(res.equity, market.h1.index, EVAL_START, cfg.init_eq)
            months[label] = mret
            st, _ = window_stats(res, cfg.init_eq, start=EVAL_START)
            rows.append({"label": label, "family": fam, **{"p_" + k: v for k, v in params.items()},
                         **st.row()})
    return pd.DataFrame(months), pd.DataFrame(rows)


def month_stats(m: pd.Series) -> dict[str, float]:
    m = m.dropna()
    sd = m.std(ddof=1)
    return {
        "months": len(m), "pct_pos": float((m > 1e-9).mean()), "mean": float(m.mean()),
        "worst": float(m.min()), "sharpe": float(m.mean() / sd * np.sqrt(12)) if sd > 0 else 0.0,
        "total": float((1 + m).prod() - 1),
    }


def folds(months: pd.PeriodIndex, train: int = 24, test: int = 6) -> list[tuple]:
    out = []
    i = train
    while i < len(months):
        out.append((months[i - train], months[i - 1], months[i],
                    months[min(i + test, len(months)) - 1]))
        i += test
    return out


def score(m: pd.Series, how: str = "sharpe", min_active: float = 0.5) -> float:
    m = m.dropna()
    if len(m) < 6:
        return -np.inf
    active = (m.abs() > 1e-9).mean()
    if active < min_active:
        return -np.inf
    sd = m.std(ddof=1)
    if how == "sharpe":
        return float(m.mean() / sd) if sd > 0 else -np.inf
    if how == "pct_pos":
        return float((m > 1e-9).mean() + 0.01 * m.mean() / (sd + 1e-9))
    if how == "sortino":
        dn = np.sqrt((np.minimum(m, 0) ** 2).mean())
        return float(m.mean() / dn) if dn > 0 else -np.inf
    raise ValueError(how)


def walk_forward(monthly: pd.DataFrame, cols: list[str] | None = None, how: str = "sharpe",
                 train: int = 24, test: int = 6, min_active: float = 0.5,
                 top_k: int = 1) -> tuple[pd.Series, list[dict]]:
    """Select the best config(s) on each training window; stitch the test months."""
    data = monthly if cols is None else monthly[cols]
    idx = data.index
    oos = []
    log = []
    for tr0, tr1, te0, te1 in folds(idx, train, test):
        tr = data.loc[tr0:tr1]
        scores = tr.apply(lambda s: score(s, how, min_active))
        best = scores.sort_values(ascending=False).index[:top_k]
        te = data.loc[te0:te1, best].mean(axis=1)
        oos.append(te)
        log.append({"train": f"{tr0}..{tr1}", "test": f"{te0}..{te1}", "picked": list(best),
                    "train_score": float(scores[best[0]]),
                    "test_mean": float(te.mean()), "test_pct_pos": float((te > 1e-9).mean())})
    return pd.concat(oos), log


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(df, indent=2, default=str))
    else:
        df.to_csv(path)
