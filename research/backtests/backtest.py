"""Backtest BTCUSDT 4h strategies with the user's trade management:
enter -> ATR stop -> TP1 partial -> SL to breakeven -> ATR-trail the runner.

All tests include 0.04%/side fees. Equity compounds, full-equity positions,
partial scale-out at TP1. Intrabar fills are conservative: if a bar touches
both stop and target, the stop is assumed to fill first.
"""
import numpy as np
import pandas as pd

FEE = 0.0004  # per side


def load(path):
    return pd.read_csv(path, parse_dates=["dt"]).reset_index(drop=True)


def add_indicators(df):
    c = df["close"]
    df["sma200"] = c.rolling(200).mean()
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()
    tr = np.maximum(df["high"] - df["low"],
                    np.maximum((df["high"] - c.shift()).abs(),
                               (df["low"] - c.shift()).abs()))
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + up / dn)
    upm = df["high"].diff()
    dnm = -df["low"].diff()
    plus_dm = pd.Series(np.where((upm > dnm) & (upm > 0), upm, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dnm > upm) & (dnm > 0), dnm, 0.0), index=df.index)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / df["atr"]
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / df["atr"]
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    df["regime"] = (c > df["sma200"]) & (df["ema50"] > df["ema200"])
    return df


def summarize(name, equity_curve, trades, df):
    eq = pd.Series(equity_curve, index=df["dt"].iloc[: len(equity_curve)].values)
    ret = eq.iloc[-1] / eq.iloc[0] - 1
    daily = eq.resample("1D").last().pct_change().dropna()
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    wins = [t for t in trades if t["pnl"] > 0]
    gp = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    pf = gp / gl if gl > 0 else float("inf")
    monthly = eq.resample("ME").last().pct_change().dropna()
    return {
        "name": name, "return": ret, "sharpe": sharpe, "maxdd": dd,
        "trades": len(trades), "winrate": len(wins) / len(trades) if trades else 0,
        "pf": pf, "pos_months": int((monthly > 0).sum()), "n_months": len(monthly),
        "monthly": monthly, "equity": eq,
    }


def fmt(s):
    return (f"{s['name']:<46} ret {s['return']*100:+8.1f}%  shp {s['sharpe']:5.2f}  "
            f"dd {s['maxdd']*100:6.1f}%  n {s['trades']:4d}  wr {s['winrate']*100:5.1f}%  "
            f"pf {s['pf']:5.2f}  +months {s['pos_months']}/{s['n_months']}")


def buy_hold(df):
    eq = (df["close"] / df["close"].iloc[0]).tolist()
    return summarize("Buy & Hold", eq, [{"pnl": eq[-1] - 1}], df)


def regime_flip(df):
    """Validated baseline: long while regime True (signal acted on next open)."""
    equity, trades = [1.0], []
    eq, pos, entry_eq = 1.0, 0.0, 0.0
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        if pos == 0.0:
            if prev["regime"] and not pd.isna(prev["sma200"]):
                pos = eq * (1 - FEE) / row["open"]
                entry_eq = eq
            eq = pos * row["close"] if pos else eq
        else:
            if not prev["regime"]:
                eq = pos * row["open"] * (1 - FEE)
                trades.append({"pnl": eq - entry_eq})
                pos = 0.0
            else:
                eq = pos * row["close"]
        equity.append(eq)
    if pos > 0:
        trades.append({"pnl": eq - entry_eq})
    return summarize("Regime flip (validated v3 baseline)", equity, trades, df)


def managed(df, stop_atr=2.5, tp1_r=1.0, tp1_frac=0.5, trail_atr=3.0,
            adx_min=0, adx_max=100, name=None):
    """Regime-gated entries with the user's management rules.

    Entries (acted on next bar's open, all decided on closed-bar data):
      - regime turns on, or
      - while regime on and flat: close dipped below EMA20 then closes back above
        (pullback-resumption), optional ADX window on the signal bar.
    Management:
      - initial SL = entry - stop_atr*ATR
      - TP1 = entry + tp1_r * (stop distance); sell tp1_frac, SL -> breakeven
      - after TP1 the runner trails at highest_high - trail_atr*ATR (ratchet)
      - hard exit if regime flips off (next open)
    """
    equity, trades = [1.0], []
    eq, cash, pos = 1.0, 1.0, 0.0
    entry_px = sl = tp1 = highest = entry_eq = 0.0
    tp1_done = False
    was_below_ema20 = False
    regime_prev = False

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        o, h, l, cl = row["open"], row["high"], row["low"], row["close"]

        # --- manage open position ---
        if pos > 0:
            if not prev["regime"]:
                cash += pos * o * (1 - FEE)
                pos = 0.0
                trades.append({"pnl": cash - entry_eq})
            else:
                stop_px = min(sl, o) if o < sl else sl
                if l <= sl:
                    cash += pos * stop_px * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq})
                else:
                    if not tp1_done and h >= tp1:
                        fill = max(tp1, o)
                        sell = pos * tp1_frac
                        cash += sell * fill * (1 - FEE)
                        pos -= sell
                        tp1_done = True
                        sl = entry_px
                    highest = max(highest, h)
                    if tp1_done:
                        sl = max(sl, highest - trail_atr * row["atr"])

        # --- entries (flat only) ---
        if pos == 0.0 and prev["regime"] and not pd.isna(prev["sma200"]):
            fresh = not regime_prev
            resume = was_below_ema20 and prev["close"] > prev["ema20"]
            adx_ok = adx_min <= prev["adx"] <= adx_max
            if (fresh or resume) and adx_ok:
                entry_px = o
                stop_dist = stop_atr * prev["atr"]
                sl = entry_px - stop_dist
                tp1 = entry_px + tp1_r * stop_dist
                highest = h
                tp1_done = False
                entry_eq = cash
                pos = cash * (1 - FEE) / entry_px
                cash = 0.0
                if l <= sl:  # same-bar stop, conservative
                    cash = pos * sl * (1 - FEE)
                    pos = 0.0
                    trades.append({"pnl": cash - entry_eq})
                was_below_ema20 = False

        # --- pullback state (on closed bars) ---
        if row["close"] < row["ema20"]:
            was_below_ema20 = True
        elif pos > 0:
            was_below_ema20 = False
        regime_prev = bool(prev["regime"])

        eq = cash + pos * cl
        equity.append(eq)

    if pos > 0:
        trades.append({"pnl": eq - entry_eq})
    label = name or (f"Managed sl={stop_atr} tp1={tp1_r}R x{tp1_frac} "
                     f"trail={trail_atr} adx=[{adx_min},{adx_max}]")
    return summarize(label, equity, trades, df)


def monthly_table(s):
    m = s["monthly"]
    out = []
    for ts, v in m.items():
        out.append(f"  {ts.strftime('%Y-%m')}  {v*100:+7.2f}%")
    return "\n".join(out)


if __name__ == "__main__":
    df = add_indicators(load("btc_4h.csv"))
    print("Span:", df["dt"].iloc[0], "->", df["dt"].iloc[-1], "bars:", len(df))
    print(fmt(buy_hold(df)))
    print(fmt(regime_flip(df)))
    print(fmt(managed(df)))
