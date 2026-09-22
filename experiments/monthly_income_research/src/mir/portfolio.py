"""Walk-forward portfolio of strategy sleeves using only training-window information."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mir.search import folds, score


def wf_portfolio(sleeves: dict[str, pd.DataFrame], *, train: int = 24, test: int = 6,
                 target_vol: float | None = 0.02, max_scale: float = 3.0,
                 how: str = "sharpe", weighting: str = "inv_vol",
                 min_active: float = 0.3) -> tuple[pd.Series, list[dict]]:
    """Each fold: pick each sleeve's best config on train, weight sleeves by inverse
    training volatility, scale to ``target_vol`` monthly (train estimate), apply to test."""
    idx = None
    for df in sleeves.values():
        idx = df.index if idx is None else idx.intersection(df.index)
    assert idx is not None
    out = []
    log = []
    for tr0, tr1, te0, te1 in folds(idx, train, test):
        picks = {}
        for name, df in sleeves.items():
            tr = df.loc[tr0:tr1]
            sc = tr.apply(lambda s: score(s, how, min_active))
            best = sc.idxmax()
            if not np.isfinite(sc[best]):
                continue
            picks[name] = best
        if not picks:
            continue
        tr_ret = pd.DataFrame({n: sleeves[n].loc[tr0:tr1, c] for n, c in picks.items()})
        te_ret = pd.DataFrame({n: sleeves[n].loc[te0:te1, c] for n, c in picks.items()})
        vol = tr_ret.std(ddof=1).replace(0, np.nan)
        if weighting == "inv_vol":
            w = (1 / vol).fillna(0)
        else:
            w = pd.Series(1.0, index=tr_ret.columns)
        w = w / w.sum()
        port_tr = tr_ret.mul(w, axis=1).sum(axis=1)
        scale = 1.0
        if target_vol:
            sd = port_tr.std(ddof=1)
            scale = min(max_scale, target_vol / sd) if sd > 0 else 1.0
        port_te = te_ret.mul(w, axis=1).sum(axis=1) * scale
        out.append(port_te)
        log.append({"test": f"{te0}..{te1}", "picks": picks, "weights": w.round(3).to_dict(),
                    "scale": round(scale, 2)})
    return pd.concat(out), log


def summarize(m: pd.Series) -> dict[str, float]:
    m = m.dropna()
    sd = m.std(ddof=1)
    eq = (1 + m).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    return {"months": len(m), "pct_pos": round(float((m > 1e-9).mean()), 3),
            "mean%": round(float(m.mean() * 100), 2), "worst%": round(float(m.min() * 100), 2),
            "best%": round(float(m.max() * 100), 2),
            "sharpe": round(float(m.mean() / sd * np.sqrt(12)), 2) if sd > 0 else 0.0,
            "total%": round(float((eq.iloc[-1] - 1) * 100), 1),
            "maxDD_monthly%": round(dd * 100, 1)}
