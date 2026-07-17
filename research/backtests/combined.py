"""v5.2 candidate: v5.1 longs (regime + pullback, breaker) + FRESH-BEAR shorts
(short once when the bear regime turns on, mirror management).
Validation: full period, IS/OOS split, robustness across short params.
"""
import pandas as pd

from backtest import FEE, add_indicators, load, summarize, fmt


def v52(df, l_stop=2.5, l_tp1=1.0, l_frac=0.5, l_trail=4.0,
        s_stop=2.5, s_tp1=1.5, s_frac=0.5, s_trail=3.0,
        cap=0.04, do_short=True, name=None):
    df = df.copy()
    df["bear"] = (df["close"] < df["sma200"]) & (df["ema50"] < df["ema200"])
    equity, trades = [1.0], []
    cash, pos = 1.0, 0.0          # pos>0 long units; pos<0 short units
    entry_px = sl = tp1 = extreme = entry_eq = 0.0
    tp1_done = False
    was_below = False
    reg_prev = bear_prev = False
    month_start_eq, cur_month, halted = 1.0, None, False

    def mark(cl):
        if pos > 0:
            return cash + pos * cl
        if pos < 0:
            return cash + (-pos) * (2 * entry_px - cl)
        return cash

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]
        m = (row["dt"].year, row["dt"].month)
        if m != cur_month:
            cur_month = m
            month_start_eq = mark(cl)
            halted = False

        # ---- manage long ----
        if pos > 0:
            if halted or not prev["regime"]:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq, "side": "L"})
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                cash += pos * px * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq, "side": "L"})
            else:
                if not tp1_done and h >= tp1:
                    fill = max(tp1, o)
                    sell = pos * l_frac
                    cash += sell * fill * (1 - FEE)
                    pos -= sell
                    tp1_done = True
                    sl = entry_px
                extreme = max(extreme, h)
                if tp1_done:
                    sl = max(sl, extreme - l_trail * row["atr"])
        # ---- manage short ----
        elif pos < 0:
            units = -pos
            def cover(px, frac=1.0):
                nonlocal cash, pos
                amt = units * frac
                cash += amt * (2 * entry_px - px) * (1 - FEE)
                pos += amt
            if halted or not prev["bear"]:
                cover(o)
                trades.append({"pnl": cash - entry_eq, "side": "S"})
            elif h >= sl:
                px = max(sl, o) if o > sl else sl
                cover(px)
                trades.append({"pnl": cash - entry_eq, "side": "S"})
            else:
                if not tp1_done and l <= tp1:
                    fill = min(tp1, o)
                    cover(fill, s_frac)
                    units = -pos
                    tp1_done = True
                    sl = entry_px
                extreme = min(extreme, l)
                if tp1_done:
                    sl = min(sl, extreme + s_trail * row["atr"])

        # ---- entries ----
        if pos == 0.0 and not halted and not pd.isna(prev["sma200"]):
            if prev["regime"]:
                fresh = not reg_prev
                resume = was_below and prev["close"] > prev["ema20"]
                if fresh or resume:
                    entry_px = o
                    d = l_stop * prev["atr"]
                    sl, tp1 = entry_px - d, entry_px + l_tp1 * d
                    extreme, tp1_done, entry_eq = h, False, cash
                    pos = cash * (1 - FEE) / entry_px
                    cash = 0.0
                    if l <= sl:
                        cash = pos * sl * (1 - FEE)
                        pos = 0.0
                        trades.append({"pnl": cash - entry_eq, "side": "L"})
                    was_below = False
            elif do_short and prev["bear"] and not bear_prev:
                entry_px = o
                d = s_stop * prev["atr"]
                sl, tp1 = entry_px + d, entry_px - s_tp1 * d
                extreme, tp1_done, entry_eq = l, False, cash
                units = cash * (1 - FEE) / entry_px
                pos = -units
                cash = 0.0
                if h >= sl:
                    cash = units * (2 * entry_px - sl) * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq, "side": "S"})

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        reg_prev, bear_prev = bool(prev["regime"]), bool(prev["bear"])

        eq = mark(cl)
        if eq < month_start_eq * (1 - cap):
            if not halted:
                halted = True
        equity.append(eq)

    if pos != 0:
        trades.append({"pnl": mark(df["close"].iloc[-1]) - entry_eq, "side": "L" if pos > 0 else "S"})
    s = summarize(name or "v5.2", equity, trades, df)
    s["trades_list"] = trades
    return s


def report(s):
    m = s["monthly"]
    worst = m.min() * 100 if len(m) else 0
    neg = (m < -0.001).sum()
    extra = ""
    if "trades_list" in s:
        ls = [t for t in s["trades_list"] if t["side"] == "S"]
        sp = sum(t["pnl"] for t in ls)
        extra = f"  shorts n={len(ls)} pnl_sum={sp:+.2f}"
    print(fmt(s) + f"  worst_m {worst:+.1f}%  neg {neg}" + extra)


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    print("== FULL PERIOD ==")
    report(v52(df, do_short=False, name="v5.1 long-only (baseline)"))
    report(v52(df, do_short=True, name="v5.2 = v5.1 + fresh-bear shorts"))

    print("\n== IN-SAMPLE (2023-06..2025-06, bull+corrections) ==")
    is_df = df[df["dt"] < "2025-07-01"].reset_index(drop=True)
    report(v52(is_df, do_short=False, name="long-only IS"))
    report(v52(is_df, do_short=True, name="v5.2 IS"))

    print("\n== OUT-OF-SAMPLE (2025-07..2026-06, the bear) ==")
    warm = df[df["dt"] >= "2024-07-01"].reset_index(drop=True)
    for label, kw in [("long-only OOS", dict(do_short=False)), ("v5.2 OOS", dict(do_short=True))]:
        s = v52(warm, **kw, name="w")
        eq = s["equity"][s["equity"].index >= "2025-07-01"]
        mm = eq.resample("ME").last().pct_change().dropna()
        print(f"{label:<16} ret {(eq.iloc[-1]/eq.iloc[0]-1)*100:+6.1f}%  dd {(eq/eq.cummax()-1).min()*100:6.1f}%  "
              f"worst_m {mm.min()*100:+.1f}%  green {(mm>0.001).sum()}/{len(mm)}")

    print("\n== SHORT-PARAM ROBUSTNESS (full period, v5.2) ==")
    for ss, st, tr in [(2.0, 1.0, 2.5), (2.5, 1.0, 2.5), (2.5, 1.5, 3.0), (3.0, 1.0, 3.0), (3.0, 1.5, 2.5)]:
        report(v52(df, s_stop=ss, s_tp1=st, s_trail=tr, name=f"v5.2 s_stop={ss} s_tp1={st} s_trail={tr}"))
