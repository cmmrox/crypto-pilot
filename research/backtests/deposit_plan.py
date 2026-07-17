"""Account plan sim: start small, deposit a fixed amount every month, grow it
with Trend Rider v5.2 at a chosen risk %. Realistic Binance USDT-M futures
constraints (0.001 BTC lot, $100 min notional, 0.05% taker fee, 12x cap).

No withdrawals in this mode -- deposits are for building the account.
"""
import numpy as np

from backtest import add_indicators, load

FEE = 0.0005
QTY_STEP = 0.001
MIN_NOTIONAL = 100.0
MAX_LEVERAGE = 12.0
STOP_ATR, TP1_R, TP1_FRAC, TRAIL_ATR = 2.5, 1.0, 0.4, 4.0   # v5.2


def round_step(q):
    return np.floor(q / QTY_STEP) * QTY_STEP


def run(df, start=100.0, deposit=50.0, risk=0.05, month_loss_cap=0.06):
    balance = start
    qty = 0.0
    entry_px = sl = tp1 = highest = entry_equity = 0.0
    pos0 = 0.0
    tp1_done = was_below = reg_prev = halted = False
    cur_month, month_start_eq = None, balance
    trades, months = [], []
    total_deposited = start
    contributions = start                 # cost basis for true P&L
    peak, max_dd = balance, 0.0
    skipped = 0
    max_lev = 0.0

    def equity(px):
        return balance + qty * (px - entry_px) if qty > 0 else balance

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]
        m = (row["dt"].year, row["dt"].month)

        if cur_month is None:
            cur_month = m
            month_start_eq = equity(o)
        elif m != cur_month:
            eq_now = equity(o)
            profit = eq_now - month_start_eq
            balance += deposit                       # <-- monthly top-up
            total_deposited += deposit
            contributions += deposit
            months.append((cur_month, month_start_eq, eq_now, profit,
                           deposit, eq_now + deposit))
            month_start_eq = eq_now + deposit
            cur_month = m
            halted = False

        # manage
        if qty > 0:
            if halted or not prev["regime"]:
                balance += qty * (o - entry_px) - qty * o * FEE
                trades.append({"pnl": balance - entry_equity}); qty = 0.0
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                balance += qty * (px - entry_px) - qty * px * FEE
                trades.append({"pnl": balance - entry_equity}); qty = 0.0
            else:
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o); sell = min(qty, round_step(pos0 * TP1_FRAC))
                    balance += sell * (fill - entry_px) - sell * fill * FEE
                    qty -= sell; tp1_done = True; sl = entry_px
                highest = max(highest, h)
                if tp1_done:
                    sl = max(sl, highest - TRAIL_ATR * row["atr"])

        # entry
        if qty == 0.0 and not halted and prev["regime"] and not np.isnan(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            if fresh or resume:
                eq = balance
                stop_dist = STOP_ATR * prev["atr"]
                q = round_step(min((risk * eq) / stop_dist, (MAX_LEVERAGE * eq) / o))
                if q * o < MIN_NOTIONAL or q <= 0:
                    skipped += 1
                else:
                    entry_px = o; sl = entry_px - stop_dist
                    tp1 = entry_px + TP1_R * stop_dist
                    highest = h; tp1_done = False; entry_equity = balance
                    qty = q; pos0 = q
                    balance -= qty * entry_px * FEE
                    max_lev = max(max_lev, qty * o / eq)
                    if l <= sl:
                        balance += qty * (sl - entry_px) - qty * sl * FEE
                        trades.append({"pnl": balance - entry_equity}); qty = 0.0
                was_below = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif qty > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = equity(cl)
        if month_loss_cap and eq < month_start_eq * (1 - month_loss_cap):
            halted = True
        peak = max(peak, eq); max_dd = min(max_dd, eq / peak - 1)

    if qty > 0:
        balance += qty * (cl - entry_px) - qty * cl * FEE
        trades.append({"pnl": balance - entry_equity})
    months.append((cur_month, month_start_eq, balance, balance - month_start_eq, 0.0, balance))

    return dict(balance=balance, months=months, trades=trades,
                total_deposited=total_deposited, max_dd=max_dd,
                skipped=skipped, max_lev=max_lev)


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    r = run(df, start=100.0, deposit=50.0, risk=0.05, month_loss_cap=0.06)

    print("Plan: $100 start + $50/month, 5% risk, v5.2, 6% monthly breaker\n")
    print(f"{'Month':<9}{'Start':>9}{'Traded to':>11}{'Trade P&L':>11}"
          f"{'+Deposit':>10}{'Balance':>10}")
    for (y, mo), s, e, p, dep, bal in r["months"]:
        print(f"{y}-{mo:02d}  {s:>8.2f}{e:>11.2f}{p:>+11.2f}{dep:>10.2f}{bal:>10.2f}")

    wins = [t for t in r["trades"] if t["pnl"] > 0]
    invested = r["total_deposited"]
    print(f"\nTotal you deposited over 3y:   ${invested:,.2f}")
    print(f"Final account balance:         ${r['balance']:,.2f}")
    print(f"Net trading profit:            ${r['balance'] - invested:,.2f} "
          f"({(r['balance']/invested - 1)*100:+.1f}% on money put in)")
    print(f"Trades taken: {len(r['trades'])}  win {len(wins)/max(1,len(r['trades']))*100:.0f}%   "
          f"skipped (under $100 min): {r['skipped']}")
    print(f"Worst drawdown: {r['max_dd']*100:.1f}%   max leverage used: {r['max_lev']:.2f}x")

    print("\n--- Sensitivity: same plan, other risk levels ---")
    for risk, cap in [(0.02, 0.04), (0.05, 0.06), (0.08, 0.10), (0.10, 0.12)]:
        rr = run(df, 100.0, 50.0, risk, cap)
        inv = rr["total_deposited"]
        print(f"risk {risk*100:>4.0f}%: deposited ${inv:,.0f} -> final ${rr['balance']:,.0f} "
              f"({(rr['balance']/inv-1)*100:+.0f}%)  maxDD {rr['max_dd']*100:.0f}%  "
              f"skipped {rr['skipped']}")
