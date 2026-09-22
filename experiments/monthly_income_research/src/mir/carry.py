"""Delta-neutral funding carry: long spot + short perpetual (research simulation).

The hedge is evaluated once per day at 00:00 UTC from *past* funding only. While on,
the account holds ``gross`` notional in each leg per unit of equity and receives the
perpetual funding (shorts receive positive funding). Leg-price differences (basis)
are marked from the actual spot and perpetual closes. Every switch pays spot and
perp taker fees plus a slippage allowance on both legs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mir.data import Market


def simulate_carry(market: Market, *, lookback_days: int = 7, on_threshold: float = 0.0,
                   gross: float = 0.5, spot_fee: float = 0.001, perp_fee: float = 0.0005,
                   slip: float = 0.0002, start: str = "2020-06-01") -> pd.Series:
    """Return the hourly equity curve (starting at 1.0) of the carry sleeve.

    gross = notional per leg / equity. 0.5 means half the equity buys spot and the
    other half margins a 1x short of the same notional (no leverage).
    """
    h1 = market.h1
    spot = market.spot_h1["close"].to_numpy()
    perp = h1["close"].to_numpy()
    fund = market.funding_h1
    idx = h1.index
    # trailing mean of funding events over lookback_days, known at each hour
    f_series = pd.Series(np.where(fund != 0, fund, np.nan), index=idx)
    trailing = f_series.rolling(f"{lookback_days}D").mean().to_numpy()
    start_i = int(np.searchsorted(idx, pd.Timestamp(start, tz="UTC")))
    eq = np.ones(len(idx))
    equity = 1.0
    on = False
    q_spot = 0.0
    q_perp = 0.0
    e_spot = 0.0
    e_perp = 0.0
    cash = 1.0
    for i in range(len(idx)):
        if i < start_i:
            eq[i] = 1.0
            continue
        # funding received by the short perp leg at this hour (applied at the open)
        if on and fund[i] != 0.0:
            cash += q_perp * perp[i - 1] * fund[i]
        # daily decision at 00:00 using data up to the previous hour
        if idx[i].hour == 0 and i > 0:
            want = bool(trailing[i - 1] > on_threshold) if np.isfinite(trailing[i - 1]) else False
            px_s, px_p = spot[i - 1], perp[i - 1]
            mark = cash + q_spot * (px_s - e_spot) - q_perp * (px_p - e_perp)
            if want and not on:
                notional = gross * mark
                q_spot = notional / px_s
                q_perp = notional / px_p
                e_spot, e_perp = px_s, px_p
                cash = mark - notional * (spot_fee + perp_fee + 2 * slip)
                on = True
            elif on and not want:
                fees = q_spot * px_s * (spot_fee + slip) + q_perp * px_p * (perp_fee + slip)
                cash = mark - fees
                q_spot = q_perp = 0.0
                on = False
        equity = cash + q_spot * (spot[i] - e_spot) - q_perp * (perp[i] - e_perp)
        eq[i] = equity
    return pd.Series(eq, index=idx)
