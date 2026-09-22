"""Neutral futures grid with a regime switch (research simulation on 15m bars).

While active, resting limit orders sit one ``spacing`` apart around the activation
price: a fall to the next lower level buys one unit, a rise to the next upper level
sells one unit, so inventory = -(level index). Each completed buy/sell pair earns one
spacing minus two maker fees. The grid stops (market close, taker fee + slippage) when
price runs ``stop_extra`` levels beyond its outermost level, or at the next 4h open
after the regime switch turns off. Intrabar path: O-L-H-C on up bars, O-H-L-C on
down bars (a standard approximation; unknown true path).
"""

from __future__ import annotations

from dataclasses import dataclass

import numba as nb
import numpy as np
import pandas as pd

from mir.data import DATA


@dataclass
class Market15:
    m15: pd.DataFrame
    funding: np.ndarray
    dec_idx: np.ndarray  # last 15m bar of each 4h candle
    h4_index: pd.DatetimeIndex


def load_15m(symbol: str = "btcusdt") -> Market15:
    df = pd.read_csv(DATA / f"{symbol}_perp_15m.csv")
    df["dt"] = pd.to_datetime(df["dt"], utc=True)
    df = df.set_index("dt").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    start = df.index[0].ceil("4h")
    df = df.loc[start:]
    df = df.iloc[: (len(df) // 16) * 16]
    if not bool((df.index.to_series().diff().dropna() == pd.Timedelta("15min")).all()):
        raise ValueError("15m gaps")
    fund = pd.read_csv(DATA / f"{symbol}_funding.csv")
    fund["dt"] = pd.to_datetime(fund["dt"], utc=True, format="mixed")
    b = fund.groupby(fund["dt"].dt.floor("15min"))["funding_rate"].sum()
    f = np.zeros(len(df))
    pos = df.index.get_indexer(pd.DatetimeIndex(b.index))
    ok = pos >= 0
    f[pos[ok]] = b.to_numpy(float)[ok]
    return Market15(m15=df, funding=f, dec_idx=np.arange(15, len(df), 16),
                    h4_index=df.index[::16])


@nb.njit(cache=True)
def _cross(price_from, price_to, p0, g, j, n_lv, u, cash, fee_m):
    """Fill grid levels crossed while moving from price_from to price_to."""
    fills = 0
    if price_to < price_from:
        while j - 1 >= -n_lv and price_to <= p0 + (j - 1) * g:
            lv = p0 + (j - 1) * g
            cash -= u * lv + u * lv * fee_m
            j -= 1
            fills += 1
    else:
        while j + 1 <= n_lv and price_to >= p0 + (j + 1) * g:
            lv = p0 + (j + 1) * g
            cash += u * lv - u * lv * fee_m
            j += 1
            fills += 1
    return j, cash, fills


@nb.njit(cache=True)
def _grid(o, h, l, c, fund, is_dec, want_on, spacing, init_eq, n_lv, stop_extra, lev,
          fee_m, fee_t):
    n = o.shape[0]
    eq = np.empty(n)
    cash = init_eq
    active = False
    p0 = 0.0
    g = 0.0
    j = 0
    u = 0.0
    pend_on = False
    pend_off = False
    pend_g = 0.0
    fills_total = 0
    stops = 0
    for i in range(n):
        # scheduled activation / deactivation at this open
        if pend_off and active:
            k = -j
            cash += k * u * o[i] - abs(k) * u * o[i] * fee_t
            active = False
            j = 0
        pend_off = False
        if pend_on and not active:
            e_now = cash
            p0 = o[i]
            g = pend_g
            u = lev * e_now / (n_lv * p0)
            j = 0
            active = True
        pend_on = False
        if active:
            if fund[i] != 0.0:
                cash -= (-j) * u * o[i] * fund[i]
            # path through the bar
            if c[i] >= o[i]:
                pts = (o[i], l[i], h[i], c[i])
            else:
                pts = (o[i], h[i], l[i], c[i])
            prev = pts[0]
            stopped = False
            for q in range(1, 4):
                nxt = pts[q]
                j, cash, fl = _cross(prev, nxt, p0, g, j, n_lv, u, cash, fee_m)
                fills_total += fl
                lo_stop = p0 - (n_lv + stop_extra) * g
                hi_stop = p0 + (n_lv + stop_extra) * g
                if nxt <= lo_stop or nxt >= hi_stop:
                    px = lo_stop if nxt <= lo_stop else hi_stop
                    k = -j
                    cash += k * u * px - abs(k) * u * px * fee_t
                    active = False
                    j = 0
                    stops += 1
                    stopped = True
                    break
                prev = nxt
            if stopped:
                eq[i] = cash
                continue
        eq[i] = cash + (-j) * u * c[i] if active else cash
        if is_dec[i]:
            if active and not want_on[i]:
                pend_off = True
            elif (not active) and want_on[i] and spacing[i] == spacing[i] and spacing[i] > 0:
                pend_on = True
                pend_g = spacing[i]
    return eq, fills_total, stops


def run_grid(mk: Market15, want_on_4h: np.ndarray, spacing_4h: np.ndarray, *,
             init_eq: float = 10_000.0, n_lv: int = 5, stop_extra: int = 1, lev: float = 1.0,
             fee_m: float = 0.0002, fee_t: float = 0.0007) -> tuple[pd.Series, int, int]:
    n = len(mk.m15)
    is_dec = np.zeros(n, bool)
    is_dec[mk.dec_idx] = True
    want = np.zeros(n, bool)
    want[mk.dec_idx] = want_on_4h[: len(mk.dec_idx)]
    sp = np.full(n, np.nan)
    sp[mk.dec_idx] = spacing_4h[: len(mk.dec_idx)]
    eq, fills, stops = _grid(mk.m15["open"].to_numpy(), mk.m15["high"].to_numpy(),
                             mk.m15["low"].to_numpy(), mk.m15["close"].to_numpy(), mk.funding,
                             is_dec, want, sp, init_eq, n_lv, stop_extra, lev, fee_m, fee_t)
    return pd.Series(eq, index=mk.m15.index), int(fills), int(stops)
