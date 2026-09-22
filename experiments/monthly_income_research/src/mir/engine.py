"""Event-driven single-position engine on a 1h timeline (numba).

Decision points are the last 1h bar of each closed 4h candle. Orders decided there
fill at the next 1h open (= the next 4h open). Resting stop / take-profit orders are
checked on every 1h bar; when both could fill inside one bar the stop is assumed
first (conservative). Funding is charged on the open position at each funding hour.
Fees are charged on notional; ``taker`` already includes a slippage allowance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numba as nb
import numpy as np

from mir.data import Market

REASONS = {1: "signal", 2: "stop", 3: "take_profit", 4: "time", 5: "reverse", 6: "breaker",
           7: "end"}


@nb.njit(cache=True)
def _round_qty(qty: float, step: float) -> float:
    if step <= 0.0:
        return qty
    return np.floor(qty / step + 1e-9) * step


@nb.njit(cache=True)
def _simulate(o, h, l, c, fund, month_id, is_dec, el, es, xl, xs, sdl, sds, trl, trs, tpl,
              tps, sz, init_eq, risk_pct, lev_cap, taker, maker, max_hold, size_mode,
              notional_frac, tp_frac, be_after_tp, breaker_pct, breaker_flatten, qty_step,
              min_notional, trail_ref, trail_after_tp, month_target, month_stop):
    n = o.shape[0]
    equity = np.empty(n)
    exposure = np.zeros(n)
    max_tr = n // 2 + 10
    t_entry_i = np.zeros(max_tr, np.int64)
    t_exit_i = np.zeros(max_tr, np.int64)
    t_side = np.zeros(max_tr, np.int64)
    t_entry_px = np.zeros(max_tr)
    t_exit_px = np.zeros(max_tr)
    t_qty = np.zeros(max_tr)
    t_pnl = np.zeros(max_tr)
    t_fee = np.zeros(max_tr)
    t_fund = np.zeros(max_tr)
    t_reason = np.zeros(max_tr, np.int64)
    nt = 0
    skipped = 0

    cash = init_eq
    pos = 0.0
    entry_px = 0.0
    entry_i = -1
    stop = np.nan
    tp = np.nan
    tp_done = False
    hold = 0
    pos_fund = 0.0
    pos_fee = 0.0
    pend_exit = False
    pend_reason = 0
    pend_entry = 0
    pend_sd = np.nan
    pend_tp = np.nan
    pend_sz = 1.0
    hh = 0.0
    ll = 0.0

    cur_month = month_id[0]
    month_start_eq = init_eq
    long_mpnl = 0.0
    short_mpnl = 0.0
    halt_long = False
    halt_short = False
    halt_all = False
    last_eq = init_eq

    for i in range(n):
        # ---- month roll (at bar open) ----
        if month_id[i] != cur_month:
            cur_month = month_id[i]
            month_start_eq = last_eq
            long_mpnl = 0.0
            short_mpnl = 0.0
            # carried position: measure month P&L from the previous close, not from entry
            if i > 0 and pos > 0.0:
                long_mpnl = -pos * (c[i - 1] - entry_px)
            elif i > 0 and pos < 0.0:
                short_mpnl = -pos * (c[i - 1] - entry_px)
            halt_long = False
            halt_short = False
            halt_all = False

        # ---- pending orders at this open ----
        if pend_exit and pos != 0.0:
            side = 1 if pos > 0 else -1
            px = o[i]
            q = abs(pos)
            fee = q * px * taker
            pnl = pos * (px - entry_px)
            cash += pnl - fee
            t_entry_i[nt] = entry_i
            t_exit_i[nt] = i
            t_side[nt] = side
            t_entry_px[nt] = entry_px
            t_exit_px[nt] = px
            t_qty[nt] = q
            t_pnl[nt] = pnl - fee - pos_fee - pos_fund
            t_fee[nt] = fee + pos_fee
            t_fund[nt] = pos_fund
            t_reason[nt] = pend_reason
            nt += 1
            if side > 0:
                long_mpnl += pnl - fee
            else:
                short_mpnl += pnl - fee
            pos = 0.0
            pos_fund = 0.0
            pos_fee = 0.0
            stop = np.nan
            tp = np.nan
        pend_exit = False
        pend_reason = 0
        if pend_entry != 0 and pos == 0.0:
            px = o[i]
            eq_now = cash
            if size_mode == 0:
                if pend_sd > 0.0:
                    qty = risk_pct * eq_now / pend_sd
                else:
                    qty = 0.0
                cap = lev_cap * eq_now / px
                if qty > cap:
                    qty = cap
            else:
                qty = notional_frac * eq_now / px
                cap = lev_cap * eq_now / px
                if qty > cap:
                    qty = cap
            qty = qty * pend_sz
            qty = _round_qty(qty, qty_step)
            if qty > 0.0 and qty * px >= min_notional:
                fee = qty * px * taker
                cash -= fee
                pos = qty if pend_entry > 0 else -qty
                entry_px = px
                entry_i = i
                pos_fee = fee
                pos_fund = 0.0
                hold = 0
                tp_done = False
                hh = px
                ll = px
                if pend_entry > 0:
                    stop = px - pend_sd if pend_sd == pend_sd else np.nan
                    tp = px + pend_tp if pend_tp == pend_tp else np.nan
                    long_mpnl -= fee
                else:
                    stop = px + pend_sd if pend_sd == pend_sd else np.nan
                    tp = px - pend_tp if pend_tp == pend_tp else np.nan
                    short_mpnl -= fee
            else:
                skipped += 1
        pend_entry = 0

        # ---- funding at this hour ----
        if fund[i] != 0.0 and pos != 0.0:
            f = pos * o[i] * fund[i]
            cash -= f
            pos_fund += f
            if pos > 0:
                long_mpnl -= f
            else:
                short_mpnl -= f

        # ---- resting stop / take profit ----
        if pos != 0.0:
            if h[i] > hh:
                hh = h[i]
            if l[i] < ll:
                ll = l[i]
        if pos > 0.0:
            if stop == stop and l[i] <= stop:
                px = stop if o[i] > stop else o[i]
                q = pos
                fee = q * px * taker
                pnl = q * (px - entry_px)
                cash += pnl - fee
                long_mpnl += pnl - fee
                t_entry_i[nt] = entry_i
                t_exit_i[nt] = i
                t_side[nt] = 1
                t_entry_px[nt] = entry_px
                t_exit_px[nt] = px
                t_qty[nt] = q
                t_pnl[nt] = pnl - fee - pos_fee - pos_fund
                t_fee[nt] = fee + pos_fee
                t_fund[nt] = pos_fund
                t_reason[nt] = 2
                nt += 1
                pos = 0.0
                pos_fee = 0.0
                pos_fund = 0.0
                stop = np.nan
                tp = np.nan
            elif tp == tp and (not tp_done) and h[i] >= tp:
                px = tp if o[i] < tp else o[i]
                q = _round_qty(pos * tp_frac, qty_step)
                if q >= pos - 1e-12:
                    q = pos
                if q > 0.0:
                    fee = q * px * maker
                    pnl = q * (px - entry_px)
                    cash += pnl - fee
                    long_mpnl += pnl - fee
                    share = q / pos
                    t_entry_i[nt] = entry_i
                    t_exit_i[nt] = i
                    t_side[nt] = 1
                    t_entry_px[nt] = entry_px
                    t_exit_px[nt] = px
                    t_qty[nt] = q
                    t_pnl[nt] = pnl - fee - pos_fee * share - pos_fund * share
                    t_fee[nt] = fee + pos_fee * share
                    t_fund[nt] = pos_fund * share
                    t_reason[nt] = 3
                    nt += 1
                    pos_fee *= 1.0 - share
                    pos_fund *= 1.0 - share
                    pos -= q
                    if pos <= 1e-12:
                        pos = 0.0
                        stop = np.nan
                    elif be_after_tp == 1:
                        if stop != stop or stop < entry_px:
                            stop = entry_px
                tp_done = True
        elif pos < 0.0:
            if stop == stop and h[i] >= stop:
                px = stop if o[i] < stop else o[i]
                q = -pos
                fee = q * px * taker
                pnl = pos * (px - entry_px)
                cash += pnl - fee
                short_mpnl += pnl - fee
                t_entry_i[nt] = entry_i
                t_exit_i[nt] = i
                t_side[nt] = -1
                t_entry_px[nt] = entry_px
                t_exit_px[nt] = px
                t_qty[nt] = q
                t_pnl[nt] = pnl - fee - pos_fee - pos_fund
                t_fee[nt] = fee + pos_fee
                t_fund[nt] = pos_fund
                t_reason[nt] = 2
                nt += 1
                pos = 0.0
                pos_fee = 0.0
                pos_fund = 0.0
                stop = np.nan
                tp = np.nan
            elif tp == tp and (not tp_done) and l[i] <= tp:
                px = tp if o[i] > tp else o[i]
                q = _round_qty(-pos * tp_frac, qty_step)
                if q >= -pos - 1e-12:
                    q = -pos
                if q > 0.0:
                    fee = q * px * maker
                    pnl = -q * (px - entry_px)
                    cash += pnl - fee
                    short_mpnl += pnl - fee
                    share = q / (-pos)
                    t_entry_i[nt] = entry_i
                    t_exit_i[nt] = i
                    t_side[nt] = -1
                    t_entry_px[nt] = entry_px
                    t_exit_px[nt] = px
                    t_qty[nt] = q
                    t_pnl[nt] = pnl - fee - pos_fee * share - pos_fund * share
                    t_fee[nt] = fee + pos_fee * share
                    t_fund[nt] = pos_fund * share
                    t_reason[nt] = 3
                    nt += 1
                    pos_fee *= 1.0 - share
                    pos_fund *= 1.0 - share
                    pos += q
                    if pos >= -1e-12:
                        pos = 0.0
                        stop = np.nan
                    elif be_after_tp == 1:
                        if stop != stop or stop > entry_px:
                            stop = entry_px
                tp_done = True

        # ---- mark to market ----
        eq = cash + pos * (c[i] - entry_px)
        equity[i] = eq
        exposure[i] = pos * c[i] / eq if eq > 0 else 0.0
        last_eq = eq

        # ---- decision at closed 4h candle ----
        if is_dec[i]:
            if pos != 0.0:
                hold += 1
            # trailing stop ratchet (from close or from the extreme since entry)
            trail_on = trail_after_tp == 0 or tp_done
            if pos > 0.0 and trl[i] == trl[i] and trail_on:
                ref = hh if trail_ref == 1 else c[i]
                ns = ref - trl[i]
                if stop != stop or ns > stop:
                    stop = ns
            elif pos < 0.0 and trs[i] == trs[i] and trail_on:
                ref = ll if trail_ref == 1 else c[i]
                ns = ref + trs[i]
                if stop != stop or ns < stop:
                    stop = ns
            # monthly breakers (independent per side, marked incl. unrealized)
            if breaker_pct > 0.0 and month_start_eq > 0.0:
                ul = pos * (c[i] - entry_px) if pos > 0.0 else 0.0
                us = pos * (c[i] - entry_px) if pos < 0.0 else 0.0
                if (not halt_long) and long_mpnl + ul <= -breaker_pct * month_start_eq:
                    halt_long = True
                    if pos > 0.0 and breaker_flatten == 1:
                        pend_exit = True
                        pend_reason = 6
                if (not halt_short) and short_mpnl + us <= -breaker_pct * month_start_eq:
                    halt_short = True
                    if pos < 0.0 and breaker_flatten == 1:
                        pend_exit = True
                        pend_reason = 6
            # account-level monthly profit lock / loss stop (no new entries this month)
            if month_start_eq > 0.0 and not halt_all:
                mret = eq / month_start_eq - 1.0
                if month_target > 0.0 and mret >= month_target:
                    halt_all = True
                if month_stop > 0.0 and mret <= -month_stop:
                    halt_all = True
                    if pos != 0.0:
                        pend_exit = True
                        pend_reason = 6
            if not pend_exit:
                if pos > 0.0:
                    if es[i] and not halt_short:
                        pend_exit = True
                        pend_reason = 5
                    elif xl[i]:
                        pend_exit = True
                        pend_reason = 1
                    elif max_hold > 0 and hold >= max_hold:
                        pend_exit = True
                        pend_reason = 4
                elif pos < 0.0:
                    if el[i] and not halt_long:
                        pend_exit = True
                        pend_reason = 5
                    elif xs[i]:
                        pend_exit = True
                        pend_reason = 1
                    elif max_hold > 0 and hold >= max_hold:
                        pend_exit = True
                        pend_reason = 4
            flat_next = (pos == 0.0 or pend_exit) and not halt_all
            if flat_next:
                if el[i] and (not halt_long) and not (pos > 0.0):
                    pend_entry = 1
                    pend_sd = sdl[i]
                    pend_tp = tpl[i]
                    pend_sz = sz[i]
                elif es[i] and (not halt_short) and not (pos < 0.0):
                    pend_entry = -1
                    pend_sd = sds[i]
                    pend_tp = tps[i]
                    pend_sz = sz[i]

    # close any open position at the final close for accounting
    if pos != 0.0:
        px = c[n - 1]
        q = abs(pos)
        fee = q * px * taker
        pnl = pos * (px - entry_px)
        cash += pnl - fee
        t_entry_i[nt] = entry_i
        t_exit_i[nt] = n - 1
        t_side[nt] = 1 if pos > 0 else -1
        t_entry_px[nt] = entry_px
        t_exit_px[nt] = px
        t_qty[nt] = q
        t_pnl[nt] = pnl - fee - pos_fee - pos_fund
        t_fee[nt] = fee + pos_fee
        t_fund[nt] = pos_fund
        t_reason[nt] = 7
        nt += 1
        equity[n - 1] = cash
    return (equity, exposure, nt, skipped, t_entry_i[:nt], t_exit_i[:nt], t_side[:nt],
            t_entry_px[:nt], t_exit_px[:nt], t_qty[:nt], t_pnl[:nt], t_fee[:nt], t_fund[:nt],
            t_reason[:nt])


@dataclass
class Signals:
    """Per-4h-bar decision arrays (length = number of 4h bars)."""

    entry_long: np.ndarray
    entry_short: np.ndarray
    exit_long: np.ndarray | None = None
    exit_short: np.ndarray | None = None
    stop_long: np.ndarray | None = None  # price distance
    stop_short: np.ndarray | None = None
    trail_long: np.ndarray | None = None  # price distance
    trail_short: np.ndarray | None = None
    tp_long: np.ndarray | None = None
    tp_short: np.ndarray | None = None
    size: np.ndarray | None = None


@dataclass
class Config:
    init_eq: float = 1000.0
    risk_pct: float = 0.01
    lev_cap: float = 3.0
    taker: float = 0.0007  # 0.05% taker fee + 0.02% slippage allowance
    maker: float = 0.0002
    max_hold: int = 0  # in 4h decision bars
    size_mode: int = 0  # 0 = risk-based, 1 = notional fraction
    notional_frac: float = 1.0
    tp_frac: float = 1.0
    be_after_tp: bool = False
    breaker_pct: float = 0.0
    breaker_flatten: bool = True
    qty_step: float = 0.0
    min_notional: float = 0.0
    trail_ref: int = 0  # 0 = from decision close, 1 = from highest high / lowest low
    trail_after_tp: bool = False
    month_target: float = 0.0  # stop opening trades once the month is up this much
    month_stop: float = 0.0  # flatten and stop for the month once down this much


@dataclass
class Result:
    equity: np.ndarray
    exposure: np.ndarray
    trades: dict[str, np.ndarray]
    skipped: int
    index: object = field(repr=False, default=None)


def run(market: Market, sig: Signals, cfg: Config) -> Result:
    n4 = len(market.h4)

    def b(x: np.ndarray | None) -> np.ndarray:
        return market.to_h1(np.zeros(n4, bool) if x is None else np.asarray(x, bool), False)

    def f(x: np.ndarray | None, default: float = np.nan) -> np.ndarray:
        arr = np.full(n4, default) if x is None else np.asarray(x, float)
        return market.to_h1(arr, np.nan)

    h1 = market.h1
    is_dec = market.to_h1(np.ones(n4, bool), False)
    size = f(sig.size, 1.0)
    size = np.where(np.isnan(size), 1.0, size)
    out = _simulate(
        h1["open"].to_numpy(), h1["high"].to_numpy(), h1["low"].to_numpy(),
        h1["close"].to_numpy(), market.funding_h1, market.month_id_h1, is_dec,
        b(sig.entry_long), b(sig.entry_short), b(sig.exit_long), b(sig.exit_short),
        f(sig.stop_long), f(sig.stop_short), f(sig.trail_long), f(sig.trail_short),
        f(sig.tp_long), f(sig.tp_short), size,
        cfg.init_eq, cfg.risk_pct, cfg.lev_cap, cfg.taker, cfg.maker, cfg.max_hold,
        cfg.size_mode, cfg.notional_frac, cfg.tp_frac, int(cfg.be_after_tp), cfg.breaker_pct,
        int(cfg.breaker_flatten), cfg.qty_step, cfg.min_notional, cfg.trail_ref,
        int(cfg.trail_after_tp), cfg.month_target, cfg.month_stop,
    )
    keys = ["entry_i", "exit_i", "side", "entry_px", "exit_px", "qty", "pnl", "fee", "funding",
            "reason"]
    trades = dict(zip(keys, out[4:], strict=True))
    return Result(equity=out[0], exposure=out[1], trades=trades, skipped=int(out[3]),
                  index=h1.index)
