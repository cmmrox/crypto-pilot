"""Trend Rider v5.1 on Binance USDT-M futures with realistic account rules:

- initial balance $1,000
- risk 1% of current equity per trade (position sized off the 2.5*ATR stop)
- leverage capped at 12x (notional never exceeds 12x equity)
- Binance BTCUSDT futures lot size: qty rounded DOWN to 0.001 BTC,
  min notional $100 (trade skipped if below)
- taker fee 0.05%/side on notional (worse than the 0.04% spot fee used
  in earlier reports -- honest for market orders on futures)
- 4% monthly circuit breaker (v5.1)
- at each month end, withdraw 10% of that month's profit (if positive);
  the rest compounds

Strategy logic is identical to circuit_breaker.managed_cb (v5.1):
regime filter, fresh-trend + pullback-resume entries, TP1 at 1R sell 50%
-> breakeven, 4*ATR trail, regime-death exit, conservative same-bar fills.

Funding rates are NOT modeled (see report note).
"""
import numpy as np
import pandas as pd

from backtest import add_indicators, load

FEE = 0.0005          # futures taker, per side, on notional
START_BALANCE = 1000.0
RISK_PCT = 0.01       # 1% of equity risked per trade
MAX_LEVERAGE = 12.0
QTY_STEP = 0.001      # BTCUSDT futures lot size
MIN_NOTIONAL = 100.0  # Binance futures minimum order notional
MONTH_LOSS_CAP = 0.04
WITHDRAW_FRAC = 0.10  # withdraw 10% of each positive month's profit
WITHDRAW_EVERY_MONTH = False  # if True: withdraw WITHDRAW_FRAC of balance every month

STOP_ATR, TP1_R, TP1_FRAC, TRAIL_ATR = 2.5, 1.0, 0.5, 4.0


def round_step(qty, step=QTY_STEP):
    return np.floor(qty / step) * step


def run(df):
    balance = START_BALANCE      # realized cash
    qty = 0.0                    # open position size in BTC
    entry_px = sl = tp1 = highest = 0.0
    entry_equity = 0.0
    tp1_done = False
    was_below = False
    reg_prev = False

    cur_month = None
    month_start_eq = balance
    halted = False

    trades = []
    months = []                  # (month, start_eq, end_eq, profit, withdrawn, balance_after)
    total_withdrawn = 0.0
    peak_eq, max_dd = balance, 0.0
    max_notional_ratio = 0.0
    skipped_min_notional = 0

    def equity(price):
        return balance + qty * (price - entry_px) if qty > 0 else balance

    def close_month(month, eq_now):
        nonlocal balance, month_start_eq, total_withdrawn
        profit = eq_now - month_start_eq
        if WITHDRAW_EVERY_MONTH:
            wd = WITHDRAW_FRAC * eq_now          # 5% of balance, profit or loss
        else:
            wd = WITHDRAW_FRAC * profit if profit > 0 else 0.0
        balance -= wd
        total_withdrawn += wd
        months.append((month, month_start_eq, eq_now, profit, wd, eq_now - wd))
        return eq_now - wd

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]
        m = (row["dt"].year, row["dt"].month)

        if cur_month is None:
            cur_month = m
            month_start_eq = equity(o)
        elif m != cur_month:
            month_start_eq = close_month(cur_month, equity(o))
            cur_month = m
            halted = False

        # --- manage open position ---
        if qty > 0:
            if halted or not prev["regime"]:
                px = o
                balance += qty * (px - entry_px) - qty * px * FEE
                trades.append({"pnl": balance - entry_equity})
                qty = 0.0
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                balance += qty * (px - entry_px) - qty * px * FEE
                trades.append({"pnl": balance - entry_equity})
                qty = 0.0
            else:
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o)
                    sell = round_step(qty * TP1_FRAC)
                    balance += sell * (fill - entry_px) - sell * fill * FEE
                    qty -= sell
                    tp1_done = True
                    sl = entry_px
                highest = max(highest, h)
                if tp1_done:
                    sl = max(sl, highest - TRAIL_ATR * row["atr"])

        # --- entries (flat only) ---
        if qty == 0.0 and not halted and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            if fresh or resume:
                eq = balance
                stop_dist = STOP_ATR * prev["atr"]
                want_qty = (RISK_PCT * eq) / stop_dist
                cap_qty = (MAX_LEVERAGE * eq) / o
                q = round_step(min(want_qty, cap_qty))
                if q * o < MIN_NOTIONAL or q <= 0:
                    skipped_min_notional += 1
                else:
                    entry_px = o
                    sl = entry_px - stop_dist
                    tp1 = entry_px + TP1_R * stop_dist
                    highest = h
                    tp1_done = False
                    entry_equity = balance
                    qty = q
                    balance -= qty * entry_px * FEE
                    max_notional_ratio = max(max_notional_ratio, qty * o / eq)
                    if l <= sl:  # conservative same-bar stop
                        balance += qty * (sl - entry_px) - qty * sl * FEE
                        trades.append({"pnl": balance - entry_equity})
                        qty = 0.0
                was_below = False

        # --- pullback state ---
        if row["close"] < row["ema20"]:
            was_below = True
        elif qty > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = equity(cl)
        if eq < month_start_eq * (1 - MONTH_LOSS_CAP):
            halted = True
        peak_eq = max(peak_eq, eq + total_withdrawn)
        max_dd = min(max_dd, (eq + total_withdrawn) / peak_eq - 1)

    # close final open position at last close, close final month
    if qty > 0:
        balance += qty * (cl - entry_px) - qty * cl * FEE
        trades.append({"pnl": balance - entry_equity})
        qty = 0.0
    close_month(cur_month, balance)

    return dict(balance=balance, months=months, trades=trades,
                total_withdrawn=total_withdrawn, max_dd=max_dd,
                max_notional_ratio=max_notional_ratio,
                skipped=skipped_min_notional)


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    print(f"Data: {df['dt'].iloc[0]} -> {df['dt'].iloc[-1]}  ({len(df)} bars)\n")
    r = run(df)

    print(f"{'Month':<9}{'Start eq':>10}{'End eq':>10}{'Profit':>10}"
          f"{'Withdrawn':>11}{'After wd':>10}")
    for (y, mo), s, e, p, w, a in r["months"]:
        print(f"{y}-{mo:02d}  {s:>9.2f} {e:>9.2f} {p:>+9.2f} {w:>10.2f} {a:>9.2f}")

    wins = [t for t in r["trades"] if t["pnl"] > 0]
    gl = -sum(t["pnl"] for t in r["trades"] if t["pnl"] <= 0)
    gp = sum(t["pnl"] for t in wins)
    wd_months = [w for *_x, w, _a in r["months"] if w > 0]
    print(f"\nFinal account balance:   ${r['balance']:,.2f}")
    print(f"Total withdrawn:         ${r['total_withdrawn']:,.2f}")
    print(f"Total made (bal+wd-1k):  ${r['balance'] + r['total_withdrawn'] - START_BALANCE:,.2f}")
    print(f"Months: {len(r['months'])}  positive: {sum(1 for m in r['months'] if m[3] > 0)}  "
          f"negative: {sum(1 for m in r['months'] if m[3] < -0.005 * START_BALANCE)}")
    print(f"Avg withdrawal (when >0): ${np.mean(wd_months):,.2f}  "
          f"median ${np.median(wd_months):,.2f}  max ${max(wd_months):,.2f}")
    print(f"Trades: {len(r['trades'])}  winrate {len(wins)/len(r['trades'])*100:.0f}%  "
          f"PF {gp/gl:.2f}")
    print(f"Max drawdown (incl. withdrawals as banked): {r['max_dd']*100:.1f}%")
    print(f"Max notional used: {r['max_notional_ratio']:.2f}x equity "
          f"(12x cap {'NEVER' if r['max_notional_ratio'] < 12 else 'WAS'} binding)")
    print(f"Entries skipped (below $100 min notional): {r['skipped']}")
