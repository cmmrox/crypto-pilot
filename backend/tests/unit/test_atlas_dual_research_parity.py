"""Atlas 7 Dual's entry decisions equal the validated research signals on every candle.

The oracle below reproduces ``strategies.dual`` from experiments/monthly_income_research
(the backtest behind this release) with its chosen parameters, using pandas instead of
the research engine's numba runtime. It is independent of the plugin's own code.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from strategy_runtime.atlas_dual import AtlasDual, AtlasDualParameters, add_indicators

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "btcusdt_4h_2026.csv"
# final_eval.PARAMS: fast=20, slow=200, stop 2.5, tp 2R, trail 3, n=24, look=360, q=0.35, hyst=1.0
FAST, SLOW, N, LOOK, Q, HYST = 20, 200, 24, 360, 0.35, 1.0


def _frame() -> pd.DataFrame:
    with FIXTURE.open() as handle:
        rows = list(csv.DictReader(handle))
    return pd.DataFrame(
        {
            "dt": [dt.datetime.fromisoformat(r["dt"]) for r in rows],
            **{k: [float(r[k]) for r in rows] for k in ("open", "high", "low", "close", "volume")},
        }
    )


def _ema(frame: pd.DataFrame, span: int) -> np.ndarray:
    return frame["close"].ewm(span=span, adjust=False, min_periods=span).mean().to_numpy()


def _no_nan(values: np.ndarray) -> np.ndarray:
    return np.where(np.isnan(values.astype(float)), False, values).astype(bool)


def _research_signals(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """strategies.dual(f, PARAMS).signals.entry_long / entry_short, line for line."""
    c = df["close"].to_numpy()
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    a = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().to_numpy()
    sma_s = df["close"].rolling(SLOW, min_periods=SLOW).mean().to_numpy()
    ema_f, ema_m, ema_s = _ema(df, FAST), _ema(df, 50), _ema(df, SLOW)
    up_line, dn_line = sma_s + HYST * a, sma_s - HYST * a
    bull = (c > up_line) & (ema_m > ema_s)
    bear = (c < dn_line) & (ema_m < ema_s)
    below, above = c < ema_f, c > ema_f
    res_l = np.zeros(len(c), bool)
    res_s = np.zeros(len(c), bool)
    al = as_ = False
    for i in range(1, len(c)):
        al = False if not bull[i] else (al or below[i - 1])
        if al and above[i]:
            res_l[i] = True
            al = False
        as_ = False if not bear[i] else (as_ or above[i - 1])
        if as_ and below[i]:
            res_s[i] = True
            as_ = False
    fresh_l = bull & ~np.r_[False, bull[:-1]]
    fresh_s = bear & ~np.r_[False, bear[:-1]]
    trend_l = bull & (fresh_l | res_l)
    trend_s = bear & (fresh_s | res_s)
    hi = df["high"].rolling(N, min_periods=N).max().shift(1).to_numpy()
    lo = df["low"].rolling(N, min_periods=N).min().shift(1).to_numpy()
    width = (hi - lo) / c
    thr = pd.Series(width).rolling(LOOK, min_periods=LOOK).quantile(Q).to_numpy()
    was_tight = np.r_[False, (width <= thr)[:-1]]
    brk_l = was_tight & (c > hi) & (c > up_line)
    brk_s = was_tight & (c < lo) & (c < dn_line)
    return _no_nan(trend_l | brk_l), _no_nan(trend_s | brk_s)


def test_every_entry_decision_matches_the_research_signals() -> None:
    frame = _frame()
    research_long, research_short = _research_signals(frame)
    strategy = AtlasDual()
    assert strategy.parameters == AtlasDualParameters()  # the pinned release parameters
    prepared = add_indicators(frame, strategy.parameters)
    warmup = strategy.manifest.market.warmup_bars
    checked = long_hits = short_hits = 0
    mismatches: list[tuple[str, bool, bool, bool, bool]] = []
    for i in range(warmup, len(frame)):
        window = prepared.iloc[: i + 1]
        long_signal = strategy._entry(window, bullish=True)[0]
        short_signal = strategy._entry(window, bullish=False)[0]
        checked += 1
        long_hits += long_signal
        short_hits += short_signal
        expected = (bool(research_long[i]), bool(research_short[i]))
        if (long_signal, short_signal) != expected:
            mismatches.append(
                (str(frame["dt"].iloc[i]), long_signal, expected[0], short_signal, expected[1])
            )
    assert checked == len(frame) - warmup
    assert long_hits and short_hits, "the fixture must exercise both sides"
    assert mismatches == [], f"{len(mismatches)} mismatches, first: {mismatches[:3]}"
