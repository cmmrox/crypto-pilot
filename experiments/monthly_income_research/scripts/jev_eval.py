"""Evaluate whether cached JEV judgments add information and improve strategies.

1. Predictive check: do JEV answers rank forward returns / forward chop better than
   chance and better than a simple code baseline built from the same features?
2. Gating check: apply a small, pre-declared set of JEV entry gates to the candidate
   strategies; select the gate threshold on training folds only (walk-forward).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mir.data import load_market  # noqa: E402
from mir.engine import run  # noqa: E402
from mir.jev import answers_frame, build_states  # noqa: E402
from mir.portfolio import summarize  # noqa: E402
from mir.search import EVAL_START, base_config, monthly_from_equity, walk_forward  # noqa: E402
from mir.strategies import Feat, squeeze, trend_rider, trend_rider_f  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results" / "jev"


def auc(score: np.ndarray, label: np.ndarray) -> float:
    ok = np.isfinite(score) & np.isfinite(label)
    s, y = score[ok], label[ok].astype(bool)
    if y.all() or (~y).all():
        return np.nan
    ranks = pd.Series(s).rank().to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    m = load_market()
    f = Feat(m)
    states = build_states(m)
    ans = answers_frame(m, states)
    ans.to_csv(RES / "answers_4h.csv")
    have = ans["p_up"].notna()
    print(f"answers for {int(have.sum())}/{len(ans)} bars; phase counts:",
          ans["phase"].value_counts().to_dict())

    # ---------- 1. predictive checks (18 bars = 3 days ahead)
    c = m.h4["close"]
    fwd = (c.shift(-18) / c - 1).to_numpy()
    fwd_abs_eff = pd.Series(f.er(18)).shift(-18).to_numpy()  # future path efficiency
    up = (fwd > 0).astype(float)
    up[~np.isfinite(fwd)] = np.nan
    base_mom = (c / c.shift(42) - 1).to_numpy()  # 7-day momentum, the obvious baseline
    rows = []
    for period, mask in {"all": have.to_numpy(),
                         "2020-2023": have.to_numpy() & (m.h4.index < "2024-01-01"),
                         "2024-2026": have.to_numpy() & (m.h4.index >= "2024-01-01")}.items():
        rows.append({
            "period": period, "n": int(mask.sum()),
            "AUC up_next -> up in 3d": auc(ans["up_next"].to_numpy()[mask], up[mask]),
            "AUC p_up-p_down -> up in 3d": auc((ans["p_up"] - ans["p_down"]).to_numpy()[mask],
                                               up[mask]),
            "AUC 7d momentum -> up in 3d": auc(base_mom[mask], up[mask]),
            "corr chop vs future efficiency": float(pd.Series(ans["chop"].to_numpy()[mask])
                                                    .corr(pd.Series(fwd_abs_eff[mask]))),
            "corr past-ER vs future efficiency": float(pd.Series(f.er(42)[mask])
                                                       .corr(pd.Series(fwd_abs_eff[mask]))),
        })
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    # ---------- 2. gating on strategies (walk-forward over gate choices)
    start_k = int(np.searchsorted(m.h4.index, pd.Timestamp(EVAL_START, tz="UTC")))
    p_up = ans["p_up"].to_numpy()
    p_dn = ans["p_down"].to_numpy()
    chop = ans["chop"].to_numpy()
    strength = ans["strength"].to_numpy()
    nxt = ans["up_next"].to_numpy()
    sq = ans["squeeze"].to_numpy()
    ext = ans["overextended"].to_numpy()

    def ge(x: np.ndarray, t: float) -> np.ndarray:
        return np.where(np.isfinite(x), x >= t, False)

    def le(x: np.ndarray, t: float) -> np.ndarray:
        return np.where(np.isfinite(x), x <= t, False)

    gates = {"none": (None, None)}
    for t in (0.5, 0.8):
        gates[f"phase>={t}"] = (ge(p_up, t), ge(p_dn, t))
    for t in (0.3, 0.5):
        gates[f"chop<={t}"] = (le(chop, t), le(chop, t))
    for t in (1.5, 2.5):
        gates[f"strength>={t}"] = (ge(strength, t), ge(strength, t))
    for t in (0.5, 0.55):
        gates[f"up_next {t}"] = (ge(nxt, t), le(nxt, 1 - t))
    gates["not_overextended<0.6"] = (le(ext, 0.6), le(ext, 0.6))
    prev_sq = np.r_[np.nan, sq[:-1]]
    for t in (0.3,):
        gates[f"squeeze_prev>={t}"] = (ge(prev_sq, t), ge(prev_sq, t))

    bases = {
        "trend_rider": lambda: trend_rider(f, dict(fast=30, med=50, slow=200, stop=2.5, tp_r=1.0,
                                                    tp_frac=0.4, trail=3.0, short=1)),
        "trend_rider_f": lambda: trend_rider_f(f, dict(fast=20, med=50, slow=200, stop=2.5,
                                                        tp_r=1.0, tp_frac=0.4, trail=3.0,
                                                        short=1, er=0.15, er_n=84, deep=1)),
        "squeeze": lambda: squeeze(f, dict(n=24, look=360, q=0.35, stop=1.5, tp_r=2.0,
                                           trail=5.0, filt=200, short=1)),
    }
    monthly = {}
    rows = []
    for bname, build in bases.items():
        for gname, (gl, gs) in gates.items():
            spec = build()
            sig = spec.signals
            el, es = sig.entry_long.copy(), sig.entry_short.copy()
            if gl is not None:
                el &= gl
                es &= gs
            el[: start_k - 1] = False
            es[: start_k - 1] = False
            sig.entry_long, sig.entry_short = el, es
            cfg = base_config(spec)
            r = run(m, sig, cfg)
            mr = monthly_from_equity(r.equity, m.h1.index, EVAL_START, cfg.init_eq)
            label = f"{bname}|{gname}"
            monthly[label] = mr
            rows.append({"strategy": bname, "gate": gname, **summarize(mr),
                         "oos_pct_pos": round(float((mr["2022-06":] > 1e-9).mean()), 3),
                         "last3": [round(x * 100, 2) for x in mr.tail(3)]})
    mdf = pd.DataFrame(monthly)
    mdf.index = pd.PeriodIndex(mdf.index, freq="M")
    mdf.to_csv(RES / "gated_monthly.csv")
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nWalk-forward gate selection (train 24m / test 6m) per strategy:")
    for bname in bases:
        cols = [c for c in mdf.columns if c.startswith(bname + "|")]
        oos, log = walk_forward(mdf, cols)
        none_oos, _ = walk_forward(mdf, [f"{bname}|none"])
        print(bname, "JEV-gated WF:", summarize(oos), "| ungated:", summarize(none_oos))
        print("   picks:", [l["picked"][0].split("|")[1] for l in log])


if __name__ == "__main__":
    main()
