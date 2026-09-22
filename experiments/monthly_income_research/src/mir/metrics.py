"""Monthly-consistency metrics for engine results."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from mir.engine import REASONS, Result


def monthly_returns(equity: np.ndarray, index: pd.DatetimeIndex, init_eq: float) -> pd.Series:
    eq = pd.Series(equity, index=index)
    month_end = eq.groupby(eq.index.to_period("M")).last()
    prev = month_end.shift(1)
    prev.iloc[0] = init_eq
    return month_end / prev - 1.0


@dataclass
class Stats:
    start: str
    end: str
    months: int
    total_return: float
    cagr: float
    max_dd: float
    pos_months: int
    neg_months: int
    flat_months: int
    pct_pos: float
    worst_month: float
    best_month: float
    mean_month: float
    median_month: float
    monthly_sharpe: float
    trades: int
    trades_per_month: float
    win_rate: float
    profit_factor: float
    fees: float
    funding: float
    exposure: float

    def row(self) -> dict[str, object]:
        return asdict(self)


def window_stats(res: Result, init_eq: float, start: str | None = None,
                 end: str | None = None) -> tuple[Stats, pd.Series]:
    """Stats over [start, end) using the account marked at month ends.

    The window is evaluated on the continuous account (no reset), which is how a
    walk-forward out-of-sample stitch should be read.
    """
    idx = pd.DatetimeIndex(res.index)
    eq = pd.Series(res.equity, index=idx)
    mask = np.ones(len(idx), bool)
    if start is not None:
        mask &= idx >= pd.Timestamp(start, tz="UTC")
    if end is not None:
        mask &= idx < pd.Timestamp(end, tz="UTC")
    sub = eq[mask]
    before = eq[~mask & (idx < sub.index[0])]
    base = float(before.iloc[-1]) if len(before) else init_eq
    month_end = sub.groupby(sub.index.to_period("M")).last()
    prev = month_end.shift(1)
    prev.iloc[0] = base
    mret = month_end / prev - 1.0
    tot = float(sub.iloc[-1] / base - 1.0)
    years = (sub.index[-1] - sub.index[0]).total_seconds() / (365.2425 * 86400)
    cagr = (1 + tot) ** (1 / years) - 1 if years > 0 and tot > -1 else -1.0
    peak = np.maximum.accumulate(np.r_[base, sub.to_numpy()])
    dd = float(np.min(np.r_[base, sub.to_numpy()] / peak - 1.0))
    t = res.trades
    exit_time = idx[t["exit_i"]] if len(t["exit_i"]) else idx[:0]
    tmask = np.ones(len(t["exit_i"]), bool)
    if start is not None:
        tmask &= exit_time >= pd.Timestamp(start, tz="UTC")
    if end is not None:
        tmask &= exit_time < pd.Timestamp(end, tz="UTC")
    pnl = t["pnl"][tmask]
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    eps = 1e-9
    sd = float(mret.std(ddof=1)) if len(mret) > 1 else 0.0
    st = Stats(
        start=str(sub.index[0]), end=str(sub.index[-1]), months=len(mret),
        total_return=tot, cagr=cagr, max_dd=dd,
        pos_months=int((mret > eps).sum()), neg_months=int((mret < -eps).sum()),
        flat_months=int((mret.abs() <= eps).sum()),
        pct_pos=float((mret > eps).mean()) if len(mret) else 0.0,
        worst_month=float(mret.min()), best_month=float(mret.max()),
        mean_month=float(mret.mean()), median_month=float(mret.median()),
        monthly_sharpe=float(mret.mean() / sd * np.sqrt(12)) if sd > 0 else 0.0,
        trades=int(tmask.sum()), trades_per_month=float(tmask.sum() / max(len(mret), 1)),
        win_rate=float((pnl > 0).mean()) if len(pnl) else 0.0,
        profit_factor=float(wins / losses) if losses > 0 else float("inf"),
        fees=float(t["fee"][tmask].sum()), funding=float(t["funding"][tmask].sum()),
        exposure=float((np.abs(res.exposure[mask]) > 1e-9).mean()),
    )
    return st, mret


def trade_table(res: Result) -> pd.DataFrame:
    idx = pd.DatetimeIndex(res.index)
    t = res.trades
    if len(t["entry_i"]) == 0:
        return pd.DataFrame()
    df = pd.DataFrame({
        "entry_time": idx[t["entry_i"]],
        "exit_time": idx[t["exit_i"]],
        "side": np.where(t["side"] > 0, "LONG", "SHORT"),
        "entry_px": t["entry_px"], "exit_px": t["exit_px"], "qty": t["qty"],
        "pnl": t["pnl"], "fee": t["fee"], "funding": t["funding"],
        "reason": [REASONS.get(int(r), str(r)) for r in t["reason"]],
    })
    return df
