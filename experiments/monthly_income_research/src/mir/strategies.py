"""Strategy families expressed as per-4h-bar signals (all causal, closed-bar)."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

from mir import indicators as ind
from mir.data import Market
from mir.engine import Config, Signals


class Feat:
    """Indicator access on the 4h frame, memoised per instance."""

    def __init__(self, market: Market) -> None:
        self.m = market
        self.df = market.h4
        self.close = self.df["close"]
        self.c = self.close.to_numpy()
        self.n = len(self.df)
        self._memo: dict[tuple[str, int], np.ndarray] = {}

    def _get(self, name: str, n: int, build: Callable[[], np.ndarray]) -> np.ndarray:
        key = (name, n)
        if key not in self._memo:
            self._memo[key] = build()
        return self._memo[key]

    def sma(self, n: int) -> np.ndarray:
        return self._get("sma", n, lambda: ind.sma(self.close, n).to_numpy())

    def ema(self, n: int) -> np.ndarray:
        return self._get("ema", n, lambda: ind.ema(self.close, n).to_numpy())

    def atr(self, n: int = 14) -> np.ndarray:
        return self._get("atr", n, lambda: ind.atr(self.df, n).to_numpy())

    def rsi(self, n: int) -> np.ndarray:
        return self._get("rsi", n, lambda: ind.rsi(self.close, n).to_numpy())

    def z(self, n: int) -> np.ndarray:
        return self._get("z", n, lambda: ind.zscore(self.close, n).to_numpy())

    def dhigh(self, n: int) -> np.ndarray:
        return self._get("dhigh", n, lambda: ind.donchian_high(self.df, n).to_numpy())

    def dlow(self, n: int) -> np.ndarray:
        return self._get("dlow", n, lambda: ind.donchian_low(self.df, n).to_numpy())

    def er(self, n: int) -> np.ndarray:
        return self._get("er", n, lambda: ind.efficiency_ratio(self.close, n).to_numpy())

    def adx(self, n: int = 14) -> np.ndarray:
        return self._get("adx", n, lambda: ind.adx(self.df, n).to_numpy())

    def rvol(self, n: int) -> np.ndarray:
        # annualised realised volatility of 4h log returns
        return self._get("rvol", n, lambda: (ind.realized_vol(self.close, n)
                                             * np.sqrt(6 * 365)).to_numpy())

    def ret(self, n: int) -> np.ndarray:
        return self._get("ret", n, lambda: (self.close / self.close.shift(n) - 1.0).to_numpy())


@dataclass
class Spec:
    family: str
    params: dict[str, float]
    signals: Signals
    config: Config

    def label(self) -> str:
        args = ",".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}"
                        for k, v in self.params.items())
        return f"{self.family}({args})"


def _nan_to_false(x: np.ndarray) -> np.ndarray:
    return np.where(np.isnan(x.astype(float)), False, x).astype(bool)


# ---------------------------------------------------------------- trend rider
def trend_rider(f: Feat, p: dict) -> Spec:
    """Atlas-style regime + EMA pullback resumption; optional symmetric short side.

    p: fast, med, slow, stop, tp_r, tp_frac, trail, short (0 none / 1 mirror)
    """
    c = f.c
    sma_s, ema_f, ema_m, ema_s = f.sma(p["slow"]), f.ema(p["fast"]), f.ema(p["med"]), f.ema(p["slow"])
    a = f.atr(14)
    bull = (c > sma_s) & (ema_m > ema_s)
    bear = (c < sma_s) & (ema_m < ema_s)
    fresh_bull = bull & ~np.r_[False, bull[:-1]]
    fresh_bear = bear & ~np.r_[False, bear[:-1]]
    below = c < ema_f
    above = c > ema_f
    # "was below EMA_fast since the regime began" memory, reset on each new regime run
    resume_long = np.zeros(f.n, bool)
    resume_short = np.zeros(f.n, bool)
    armed_l = False
    armed_s = False
    for i in range(1, f.n):
        if not bull[i]:
            armed_l = False
        elif below[i - 1]:
            armed_l = True
        if armed_l and bull[i] and above[i]:
            resume_long[i] = True
            armed_l = False
        if not bear[i]:
            armed_s = False
        elif above[i - 1]:
            armed_s = True
        if armed_s and bear[i] and below[i]:
            resume_short[i] = True
            armed_s = False
    el = bull & (fresh_bull | resume_long)
    es = (bear & (fresh_bear | resume_short)) if p.get("short", 0) else np.zeros(f.n, bool)
    sig = Signals(
        entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
        exit_long=~bull, exit_short=~bear,
        stop_long=p["stop"] * a, stop_short=p["stop"] * a,
        trail_long=p["trail"] * a, trail_short=p["trail"] * a,
        tp_long=p["tp_r"] * p["stop"] * a, tp_short=p["tp_r"] * p["stop"] * a,
    )
    cfg = Config(tp_frac=p["tp_frac"], be_after_tp=True, trail_ref=1, trail_after_tp=True)
    return Spec("trend_rider", p, sig, cfg)


def trend_rider_grid() -> list[dict]:
    out = []
    for fast, stop, trail, tp_r, short in product((20, 30), (2.0, 2.5, 3.0), (3.0, 4.0, 5.0),
                                                  (1.0, 2.0), (0, 1)):
        out.append(dict(fast=fast, med=50, slow=200, stop=stop, tp_r=tp_r, tp_frac=0.4,
                        trail=trail, short=short))
    return out


# ---------------------------------------------------------------- donchian breakout
def donchian(f: Feat, p: dict) -> Spec:
    """Channel breakout both ways; exit on the opposite shorter channel or ATR trail.

    p: n (entry bars), m (exit bars), stop (ATR), trail (ATR, 0 = channel exit only),
       filt (0 none, else SMA length for direction filter)
    """
    c = f.c
    hi, lo = f.dhigh(p["n"]), f.dlow(p["n"])
    xhi, xlo = f.dhigh(p["m"]), f.dlow(p["m"])
    a = f.atr(14)
    el = c > hi
    es = c < lo
    if p["filt"]:
        s = f.sma(p["filt"])
        el &= c > s
        es &= c < s
    trail = p["trail"] * a if p["trail"] else None
    sig = Signals(entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
                  exit_long=_nan_to_false(c < xlo), exit_short=_nan_to_false(c > xhi),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a,
                  trail_long=trail, trail_short=trail)
    return Spec("donchian", p, sig, Config(trail_ref=1))


def donchian_grid() -> list[dict]:
    out = []
    for n, m, stop, trail, filt in product((30, 60, 120, 180), (10, 20, 40), (2.0, 3.0, 4.0),
                                           (0.0, 4.0), (0, 300, 900)):
        if m >= n:
            continue
        out.append(dict(n=n, m=m, stop=stop, trail=trail, filt=filt))
    return out


# ---------------------------------------------------------------- EMA / TSMOM with vol target
def ema_trend(f: Feat, p: dict) -> Spec:
    """Hold the side of the fast/slow EMA spread (with a no-trade band), vol-targeted.

    p: fast, slow, band (ATR multiple), tvol (annual vol target), stop (ATR catastrophe stop)
    """
    spread = f.ema(p["fast"]) - f.ema(p["slow"])
    a = f.atr(14)
    band = p["band"] * a
    up = spread > band
    dn = spread < -band
    rv = f.rvol(42)
    size = np.clip(p["tvol"] / np.where(rv > 0, rv, np.nan), 0.0, 3.0)
    sig = Signals(entry_long=_nan_to_false(up), entry_short=_nan_to_false(dn),
                  exit_long=_nan_to_false(~up), exit_short=_nan_to_false(~dn),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a, size=size)
    return Spec("ema_trend", p, sig, Config(size_mode=1, notional_frac=1.0, lev_cap=3.0))


def ema_trend_grid() -> list[dict]:
    out = []
    for fast, slow, band, stop in product((12, 24, 48, 96), (96, 192, 384, 720), (0.0, 0.5, 1.0),
                                          (4.0, 8.0)):
        if fast * 3 > slow:
            continue
        out.append(dict(fast=fast, slow=slow, band=band, tvol=0.4, stop=stop))
    return out


# ---------------------------------------------------------------- pullback mean reversion
def pullback_mr(f: Feat, p: dict) -> Spec:
    """Buy short-term oversold dips in an uptrend; sell overbought rallies in a downtrend.

    p: rsi (period), lo, hi (thresholds), trend (SMA len), exit (0 = close crosses SMA5,
       1 = RSI crosses 50), stop (ATR), hold (max bars), both (1 = trade shorts too)
    """
    c = f.c
    r = f.rsi(p["rsi"])
    t = f.sma(p["trend"])
    a = f.atr(14)
    up = c > t
    dn = c < t
    el = up & (r < p["lo"])
    es = dn & (r > p["hi"]) if p["both"] else np.zeros(f.n, bool)
    if p["exit"] == 0:
        s5 = f.sma(5)
        xl, xs = c > s5, c < s5
    else:
        xl, xs = r > 50, r < 50
    sig = Signals(entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
                  exit_long=_nan_to_false(xl), exit_short=_nan_to_false(xs),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a)
    return Spec("pullback_mr", p, sig, Config(max_hold=int(p["hold"])))


def pullback_mr_grid() -> list[dict]:
    out = []
    for rsi, lo, trend, ex, stop, hold, both in product(
            (2, 3, 5), (5, 10, 20), (100, 300, 600), (0, 1), (2.0, 3.0), (12, 30), (1,)):
        out.append(dict(rsi=rsi, lo=lo, hi=100 - lo, trend=trend, exit=ex, stop=stop,
                        hold=hold, both=both))
    return out


# ---------------------------------------------------------------- range mean reversion
def range_mr(f: Feat, p: dict) -> Spec:
    """Fade band extremes only while the market is choppy (low efficiency ratio).

    p: win (z-score window), ez (entry z), er_n, er_max, stop (ATR), hold
    """
    z = f.z(p["win"])
    er = f.er(p["er_n"])
    a = f.atr(14)
    chop = er < p["er_max"]
    el = chop & (z < -p["ez"])
    es = chop & (z > p["ez"])
    sig = Signals(entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
                  exit_long=_nan_to_false(z > 0), exit_short=_nan_to_false(z < 0),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a)
    return Spec("range_mr", p, sig, Config(max_hold=int(p["hold"])))


def range_mr_grid() -> list[dict]:
    out = []
    for win, ez, er_n, er_max, stop, hold in product((20, 42, 84), (1.5, 2.0, 2.5), (30, 60),
                                                      (0.2, 0.3, 0.45), (2.0, 3.0), (12, 30)):
        out.append(dict(win=win, ez=ez, er_n=er_n, er_max=er_max, stop=stop, hold=hold))
    return out


# ---------------------------------------------------------------- MAX / MIN (QuantPedia)
def maxmin(f: Feat, p: dict) -> Spec:
    """Long at N-day high (trend) and/or N-day low (reversion); short at N-day low if trend.

    p: n (4h bars), hold (bars), mode (0 = max only, 1 = min only, 2 = both longs,
       3 = trend both sides: long at max, short at min), stop (ATR)
    """
    hh = f.dhigh(p["n"])
    ll = f.dlow(p["n"])
    a = f.atr(14)
    at_max = f.df["high"].to_numpy() >= hh
    at_min = f.df["low"].to_numpy() <= ll
    zero = np.zeros(f.n, bool)
    mode = p["mode"]
    if mode == 0:
        el, es = at_max, zero
    elif mode == 1:
        el, es = at_min, zero
    elif mode == 2:
        el, es = at_max | at_min, zero
    else:
        el, es = at_max, at_min
    sig = Signals(entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a)
    return Spec("maxmin", p, sig, Config(max_hold=int(p["hold"])))


def maxmin_grid() -> list[dict]:
    out = []
    for n, hold, mode, stop in product((30, 60, 120), (6, 12, 30), (0, 1, 2, 3), (3.0, 5.0)):
        out.append(dict(n=n, hold=hold, mode=mode, stop=stop))
    return out


FAMILIES: dict[str, tuple[Callable[[Feat, dict], Spec], Callable[[], list[dict]]]] = {
    "trend_rider": (trend_rider, trend_rider_grid),
    "donchian": (donchian, donchian_grid),
    "ema_trend": (ema_trend, ema_trend_grid),
    "pullback_mr": (pullback_mr, pullback_mr_grid),
    "range_mr": (range_mr, range_mr_grid),
    "maxmin": (maxmin, maxmin_grid),
}


# ---------------------------------------------------------------- volatility squeeze breakout
def squeeze(f: Feat, p: dict) -> Spec:
    """Trade the break of a tight (low-volatility) range in either direction.

    p: n (range bars), look (bars for the width percentile), q (width quantile that counts
       as a squeeze), stop (ATR), tp_r (R multiple for a partial, 0 = none), trail (ATR from
       the extreme since entry), filt (0 = both sides freely, else SMA length: longs only
       above / shorts only below), short (0/1)
    """
    c = f.c
    hi, lo = f.dhigh(p["n"]), f.dlow(p["n"])
    width = (hi - lo) / c
    w = pd.Series(width)
    thr = w.rolling(p["look"], min_periods=p["look"]).quantile(p["q"]).to_numpy()
    tight = width <= thr
    was_tight = np.r_[False, tight[:-1]]  # the range before this bar was tight
    a = f.atr(14)
    el = was_tight & (c > hi)
    es = was_tight & (c < lo) if p.get("short", 1) else np.zeros(f.n, bool)
    if p["filt"]:
        s = f.sma(p["filt"])
        el &= c > s
        es &= c < s
    tp = p["tp_r"] * p["stop"] * a if p["tp_r"] else None
    sig = Signals(entry_long=_nan_to_false(el), entry_short=_nan_to_false(es),
                  stop_long=p["stop"] * a, stop_short=p["stop"] * a,
                  trail_long=p["trail"] * a, trail_short=p["trail"] * a,
                  tp_long=tp, tp_short=tp)
    cfg = Config(tp_frac=0.4, be_after_tp=bool(p["tp_r"]), trail_ref=1,
                 trail_after_tp=False, max_hold=int(p.get("hold", 0)))
    return Spec("squeeze", p, sig, cfg)


def squeeze_grid() -> list[dict]:
    out = []
    for n, look, q, stop, tp_r, trail, filt in product(
            (12, 24, 48), (180, 360), (0.2, 0.35, 0.5), (1.5, 2.5), (0.0, 1.0, 2.0),
            (3.0, 5.0), (0, 200)):
        out.append(dict(n=n, look=look, q=q, stop=stop, tp_r=tp_r, trail=trail, filt=filt,
                        short=1))
    return out


# ---------------------------------------------------------------- trend rider + chop filter
def trend_rider_f(f: Feat, p: dict) -> Spec:
    """trend_rider with entries allowed only when the market is directional.

    p (extra): er (min efficiency ratio over er_n bars, 0 = off), er_n,
               deep (1 = shorts only in the Atlas 'deep bear' state: close < SMA - 0.5 ATR)
    """
    spec = trend_rider(f, p)
    ok = np.ones(f.n, bool)
    if p.get("er", 0):
        ok &= _nan_to_false(f.er(int(p["er_n"])) >= p["er"])
    spec.signals.entry_long = spec.signals.entry_long & ok
    es = spec.signals.entry_short & ok
    if p.get("deep", 0):
        es &= _nan_to_false(f.c < f.sma(p["slow"]) - 0.5 * f.atr(14))
    spec.signals.entry_short = es
    spec.family = "trend_rider_f"
    return spec


def trend_rider_f_grid() -> list[dict]:
    out = []
    for fast, stop, trail, tp_r, er, er_n, deep in product(
            (20, 30), (2.5, 3.0), (3.0, 4.0), (1.0, 2.0), (0.0, 0.15, 0.25, 0.35), (42, 84),
            (0, 1)):
        if er == 0.0 and er_n == 84:
            continue
        out.append(dict(fast=fast, med=50, slow=200, stop=stop, tp_r=tp_r, tp_frac=0.4,
                        trail=trail, short=1, er=er, er_n=er_n, deep=deep))
    return out


FAMILIES["squeeze"] = (squeeze, squeeze_grid)
FAMILIES["trend_rider_f"] = (trend_rider_f, trend_rider_f_grid)


# ---------------------------------------------------------------- union: trend pullback + squeeze
def dual(f: Feat, p: dict) -> Spec:
    """One position; enter on either a trend-pullback resumption or a squeeze breakout.

    Direction filter for both engines: longs only above SMA(slow), shorts only below.
    Exits: protective stop (per entry type), partial take-profit at tp_r R, trail from the
    extreme after the partial, and a regime exit when close crosses SMA(slow) against the
    position. p: fast, slow, stop_t, stop_b, tp_r, trail, n, look, q, er, er_n, short
    """
    c = f.c
    a = f.atr(14)
    sma_s = f.sma(p["slow"])
    hb = p.get("hyst", 0.0) * a  # hysteresis buffer around the slow average
    up_line, dn_line = sma_s + hb, sma_s - hb
    ema_f, ema_m, ema_s = f.ema(p["fast"]), f.ema(50), f.ema(p["slow"])
    bull = (c > up_line) & (ema_m > ema_s)
    bear = (c < dn_line) & (ema_m < ema_s)
    below, above = c < ema_f, c > ema_f
    res_l = np.zeros(f.n, bool)
    res_s = np.zeros(f.n, bool)
    al = as_ = False
    for i in range(1, f.n):
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
    if p.get("er", 0):
        ok = _nan_to_false(f.er(int(p["er_n"])) >= p["er"])
        trend_l &= ok
        trend_s &= ok
    hi, lo = f.dhigh(p["n"]), f.dlow(p["n"])
    width = (hi - lo) / c
    thr = pd.Series(width).rolling(p["look"], min_periods=p["look"]).quantile(p["q"]).to_numpy()
    was_tight = np.r_[False, (width <= thr)[:-1]]
    brk_l = was_tight & (c > hi) & (c > up_line)
    brk_s = was_tight & (c < lo) & (c < dn_line)
    el = _nan_to_false(trend_l | brk_l)
    es = _nan_to_false(trend_s | brk_s) if p.get("short", 1) else np.zeros(f.n, bool)
    stop = np.where(_nan_to_false(brk_l | brk_s) & ~_nan_to_false(trend_l | trend_s),
                    p["stop_b"] * a, p["stop_t"] * a)
    sig = Signals(entry_long=el, entry_short=es,
                  exit_long=_nan_to_false(c < dn_line), exit_short=_nan_to_false(c > up_line),
                  stop_long=stop, stop_short=stop,
                  trail_long=p["trail"] * a, trail_short=p["trail"] * a,
                  tp_long=p["tp_r"] * stop, tp_short=p["tp_r"] * stop)
    cfg = Config(tp_frac=0.4, be_after_tp=True, trail_ref=1, trail_after_tp=True)
    return Spec("dual", p, sig, cfg)


def dual_grid(hysts: tuple[float, ...] = (0.0,)) -> list[dict]:
    out = []
    for fast, stop_t, stop_b, tp_r, trail, n, q, er, hyst in product(
            (20, 30), (2.5, 3.0), (1.5, 2.5), (1.0, 2.0), (3.0, 4.5), (24, 48), (0.2, 0.35),
            (0.0, 0.15), hysts):
        d = dict(fast=fast, slow=200, stop_t=stop_t, stop_b=stop_b, tp_r=tp_r,
                 trail=trail, n=n, look=360, q=q, er=er, er_n=84, short=1)
        if hyst:
            d["hyst"] = hyst
        out.append(d)
    return out


def dual_h_grid() -> list[dict]:
    return dual_grid((0.0, 0.5, 1.0))


def dual_h(f: Feat, p: dict) -> Spec:
    spec = dual(f, p)
    spec.family = "dual_h"
    return spec


FAMILIES["dual"] = (dual, dual_grid)
FAMILIES["dual_h"] = (dual_h, dual_h_grid)


def monthly_frame(results: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.DataFrame(results)
