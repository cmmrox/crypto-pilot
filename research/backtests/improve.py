"""Fine-tuning experiments on Trend Rider v5.1 (all fees included, conservative
fills, 4% monthly circuit breaker unless disabled).

Ideas under test (from trading research, 2026-07):
  A. TP ladder      - scale out level-by-level (e.g. 1R/2R/3R) instead of one TP1
  B. Time stop      - exit a trade that hasn't reached TP1 after N bars
  C. Early BE       - move stop to breakeven at 0.5-0.75R instead of at TP1
  D. Event blackout - no NEW entries within H hours before FOMC / CPI releases
  E. Combos of whatever survives out-of-sample

Validation protocol: in-sample 2023-06 .. 2025-06, out-of-sample 2025-07 .. now.
A change is accepted only if it helps (or at least doesn't hurt) BOTH windows.
"""
import numpy as np
import pandas as pd

from backtest import FEE, add_indicators, load, summarize

# ---------------------------------------------------------------- event dates
# FOMC decision days (2nd meeting day, statement 14:00 ET => 18/19:00 UTC)
FOMC = [
    "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]
# US CPI release days (08:30 ET => 12:30/13:30 UTC). 2025-10 delayed by
# shutdown (Oct 24), 2025-11 canceled, 2025-12 rescheduled to Dec 18.
CPI = [
    "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
    "2023-11-14", "2023-12-12",
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
    "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
    "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-24",
    "2025-12-18",
    "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", "2026-05-12",
    "2026-06-10", "2026-07-14",
]
FOMC_UTC = pd.to_datetime(FOMC, utc=True) + pd.Timedelta(hours=18, minutes=30)
CPI_UTC = pd.to_datetime(CPI, utc=True) + pd.Timedelta(hours=13)
ALL_EVENTS = FOMC_UTC.append(CPI_UTC).sort_values()


def hours_to_next_event(ts, events):
    idx = events.searchsorted(ts)
    if idx >= len(events):
        return np.inf
    return (events[idx] - ts).total_seconds() / 3600.0


# ---------------------------------------------------------------- the engine
def run(df, tp_levels=((1.0, 0.5),), trail_atr=4.0, stop_atr=2.5,
        be_at_r=None, time_stop_bars=None, time_stop_below_entry_only=True,
        blackout_hours=0, blackout_events=None, month_loss_cap=0.04,
        name="variant"):
    """v5.1 engine generalized.

    tp_levels: sequence of (r_multiple, fraction_of_ORIGINAL_position) profit
        levels. Stop moves to breakeven when the FIRST level fills (or earlier
        with be_at_r). After the LAST level fills the runner trails.
    be_at_r: if set, stop moves to entry once high >= entry + be_at_r * risk
        even before any TP fills.
    time_stop_bars: if set and no TP level has filled after N bars, exit at
        next open (only when close < entry if time_stop_below_entry_only).
    blackout_hours: skip NEW entries within H hours before each event.
    """
    events = blackout_events if blackout_events is not None else ALL_EVENTS
    equity, trades = [1.0], []
    cash, pos = 1.0, 0.0
    pos0 = 0.0                       # original size, for level fractions
    entry_px = sl = highest = entry_eq = 0.0
    risk_dist = 0.0
    levels_done = 0
    bars_in_trade = 0
    was_below = False
    reg_prev = False
    month_start_eq, cur_month, halted = 1.0, None, False

    n_levels = len(tp_levels)

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]
        m = (row["dt"].year, row["dt"].month)
        if m != cur_month:
            cur_month = m
            month_start_eq = cash + (pos * cl if pos > 0 else 0)
            halted = False

        if pos > 0:
            bars_in_trade += 1
            time_stop_hit = (time_stop_bars is not None and levels_done == 0
                             and bars_in_trade >= time_stop_bars
                             and (not time_stop_below_entry_only
                                  or prev["close"] < entry_px))
            if halted or not prev["regime"] or time_stop_hit:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            elif l <= sl:
                px = min(sl, o) if o < sl else sl
                cash += pos * px * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            else:
                # fill TP levels in order (conservative: one check per level)
                while levels_done < n_levels:
                    r_mult, frac = tp_levels[levels_done]
                    tp_px = entry_px + r_mult * risk_dist
                    if h >= tp_px:
                        fill = max(tp_px, o)
                        sell = min(pos, pos0 * frac)
                        cash += sell * fill * (1 - FEE)
                        pos -= sell
                        levels_done += 1
                        sl = max(sl, entry_px)      # BE after first level
                    else:
                        break
                if be_at_r is not None and levels_done == 0:
                    if h >= entry_px + be_at_r * risk_dist:
                        sl = max(sl, entry_px)
                highest = max(highest, h)
                if levels_done >= n_levels and pos > 0:
                    sl = max(sl, highest - trail_atr * row["atr"])
                if pos > 0 and pos < 1e-12:
                    pos = 0.0

        if pos == 0.0 and not halted and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not reg_prev
            resume = was_below and prev["close"] > prev["ema20"]
            blocked = (blackout_hours > 0 and
                       hours_to_next_event(row["dt"], events) <= blackout_hours)
            if (fresh or resume) and not blocked:
                entry_px = o
                risk_dist = stop_atr * prev["atr"]
                sl = entry_px - risk_dist
                highest = h
                levels_done = 0
                bars_in_trade = 0
                entry_eq = cash
                pos = cash * (1 - FEE) / entry_px
                pos0 = pos
                cash = 0.0
                if l <= sl:
                    cash = pos * sl * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq})
                was_below = False

        if row["close"] < row["ema20"]:
            was_below = True
        elif pos > 0:
            was_below = False
        reg_prev = bool(prev["regime"])

        eq = cash + (pos * cl if pos > 0 else 0.0)
        if month_loss_cap and eq < month_start_eq * (1 - month_loss_cap):
            halted = True
        equity.append(eq)

    if pos > 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize(name, equity, trades, df)


# ------------------------------------------------------------------ reporting
def line(s):
    mo = s["monthly"]
    worst = mo.min() * 100 if len(mo) else 0
    return (f"{s['name']:<44} ret {s['return']*100:+7.1f}%  shp {s['sharpe']:5.2f}  "
            f"dd {s['maxdd']*100:6.1f}%  n {s['trades']:3d}  wr {s['winrate']*100:4.0f}%  "
            f"pf {s['pf']:4.2f}  worst_m {worst:+5.1f}%")


def is_oos(df, split="2025-07-01", **kw):
    dfi = df[df["dt"] < pd.Timestamp(split, tz="UTC")].reset_index(drop=True)
    dfo = df[df["dt"] >= pd.Timestamp(split, tz="UTC") - pd.Timedelta(days=60)].reset_index(drop=True)
    # OOS gets a 60-day warmup for indicators; trades only judged on the window
    si = run(dfi, **kw)
    so = run(dfo, **{**kw, "name": kw.get("name", "variant") + " [OOS]"})
    return si, so


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    base = dict(tp_levels=((1.0, 0.5),), trail_atr=4.0)

    print("=== FULL PERIOD baseline ===")
    print(line(run(df, **base, name="v5.1 baseline")))

    print("\n=== A. TP ladders (full period) ===")
    for levels, nm in [
        (((1.0, 0.5),), "1R x50 (v5.1)"),
        (((1.0, 0.33), (2.0, 0.33)), "1R/2R x33/33"),
        (((1.0, 0.25), (2.0, 0.25), (3.0, 0.25)), "1R/2R/3R x25 each"),
        (((0.75, 0.33), (1.5, 0.33)), "0.75R/1.5R x33/33"),
        (((1.5, 0.5),), "1.5R x50"),
        (((2.0, 0.5),), "2R x50"),
        (((1.0, 0.4), (2.5, 0.3)), "1R x40 / 2.5R x30"),
    ]:
        print(line(run(df, tp_levels=levels, name=f"ladder {nm}")))

    print("\n=== B. Time stops (bars of 4h; full period) ===")
    for n in (12, 18, 24, 30, 42):
        print(line(run(df, **base, time_stop_bars=n,
                       name=f"time-stop {n} bars ({n*4}h) if <entry")))
    print(line(run(df, **base, time_stop_bars=24, time_stop_below_entry_only=False,
                   name="time-stop 24 bars unconditional")))

    print("\n=== C. Early breakeven (full period) ===")
    for r in (0.5, 0.75):
        print(line(run(df, **base, be_at_r=r, name=f"BE at {r}R")))

    print("\n=== D. Event blackout before FOMC+CPI (full period) ===")
    for hrs, ev, nm in [(12, ALL_EVENTS, "12h FOMC+CPI"),
                        (24, ALL_EVENTS, "24h FOMC+CPI"),
                        (24, FOMC_UTC, "24h FOMC only"),
                        (48, FOMC_UTC, "48h FOMC only")]:
        print(line(run(df, **base, blackout_hours=hrs, blackout_events=ev,
                       name=f"blackout {nm}")))
