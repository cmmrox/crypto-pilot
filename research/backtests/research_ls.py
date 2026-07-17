"""Long/short equity-curve research engine (vectorized).

Goal: find a BTCUSDT strategy whose equity curve grinds UP with small
pullbacks, including the 2025-07 -> 2026-07 bear year, trading both sides.

Engine: target exposure per bar in [-cap, +cap] decided on bar close i,
applied to the close(i) -> close(i+1) return. Costs charged on turnover:
|pos_i - pos_{i-1}| * COST (fee + slippage per side).

Honesty rules:
- costs 0.05%/side (0.04% taker fee + 0.01% slippage) on every change
- signals use shift(1) inside the engine: no look-ahead
- in-sample = 2023-06 .. 2025-06, out-of-sample = 2025-07 .. end (bear year)
- a config is only a candidate if it works in BOTH windows
"""
import numpy as np
import pandas as pd

COST = 0.0005          # per side: fee + slippage
BARS_PER_YEAR = 2190   # 4h bars

OOS_START = "2025-07-01"


def load(path="btc_4h.csv"):
    df = pd.read_csv(path, parse_dates=["dt"]).set_index("dt")
    df["ret"] = df["close"].pct_change().fillna(0.0)
    return df


# ---------------------------------------------------------------- indicators
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    c = df["close"]
    tr = np.maximum(df["high"] - df["low"],
                    np.maximum((df["high"] - c.shift()).abs(),
                               (df["low"] - c.shift()).abs()))
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def realized_vol(df, span=48):
    """Annualized EWMA vol of 4h returns."""
    return df["ret"].ewm(span=span, adjust=False).std() * np.sqrt(BARS_PER_YEAR)


# ---------------------------------------------------------------- signals
# Each returns a Series of target exposure BEFORE vol scaling, in [-1, 1].

def sig_regime(df, sma=200, f=50, s=200, short_scale=1.0):
    c = df["close"]
    sma_ = c.rolling(sma).mean()
    bull = (c > sma_) & (ema(c, f) > ema(c, s))
    bear = (c < sma_) & (ema(c, f) < ema(c, s))
    return bull.astype(float) - short_scale * bear.astype(float)


def sig_tsmom(df, n):
    return np.sign(df["close"].pct_change(n)).fillna(0.0)


def sig_tsmom_ens(df, lookbacks=(42, 84, 168, 336, 672), short_scale=1.0):
    sigs = pd.concat([sig_tsmom(df, n) for n in lookbacks], axis=1).mean(axis=1)
    return sigs.where(sigs > 0, sigs * short_scale)


def sig_macross(df, f, s, short_scale=1.0):
    d = np.sign(ema(df["close"], f) - ema(df["close"], s))
    return d.where(d > 0, d * short_scale)


def sig_donchian(df, n, exit_mid=True, short_scale=1.0):
    hi = df["high"].rolling(n).max().shift(1)
    lo = df["low"].rolling(n).min().shift(1)
    mid = (hi + lo) / 2
    pos = np.zeros(len(df))
    c = df["close"].values
    hi_v, lo_v, mid_v = hi.values, lo.values, mid.values
    p = 0.0
    for i in range(len(df)):
        if np.isnan(hi_v[i]):
            pos[i] = 0.0
            continue
        if p == 0.0:
            if c[i] > hi_v[i]:
                p = 1.0
            elif c[i] < lo_v[i]:
                p = -1.0
        elif p > 0:
            if c[i] < (mid_v[i] if exit_mid else lo_v[i]):
                p = -1.0 if c[i] < lo_v[i] else 0.0
        else:
            if c[i] > (mid_v[i] if exit_mid else hi_v[i]):
                p = 1.0 if c[i] > hi_v[i] else 0.0
        pos[i] = p
    pos = pd.Series(pos, index=df.index)
    return pos.where(pos > 0, pos * short_scale)


# ---------------------------------------------------------------- engine
def backtest(df, target, vol_target=None, cap=1.0, vol_span=48, name=""):
    """target: Series of desired exposure (pre vol-scaling). Returns metrics."""
    pos = target.copy().fillna(0.0)
    if vol_target is not None:
        rv = realized_vol(df, vol_span).replace(0, np.nan)
        scale = (vol_target / rv).clip(upper=cap).fillna(0.0)
        pos = pos * scale
    pos = pos.clip(-cap, cap)
    pos_l = pos.shift(1).fillna(0.0)              # exposure held during bar
    gross = pos_l * df["ret"]
    costs = (pos.diff().abs().fillna(pos.abs())) * COST
    net = gross - costs.shift(1).fillna(0.0)
    eq = (1 + net).cumprod()
    return metrics(name, eq, pos_l)


def metrics(name, eq, pos=None):
    daily = eq.resample("1D").last().pct_change().dropna()
    n_years = len(eq) / BARS_PER_YEAR
    cagr = eq.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else 0
    dd_series = eq / eq.cummax() - 1
    maxdd = dd_series.min()
    ulcer = np.sqrt((dd_series ** 2).mean())
    monthly = eq.resample("ME").last().pct_change().dropna()
    mar = cagr / abs(maxdd) if maxdd < 0 else np.inf
    # linearity of log-equity: R^2 vs straight line (smooth-up score)
    y = np.log(eq.values)
    x = np.arange(len(y))
    r2 = np.corrcoef(x, y)[0, 1] ** 2 if y.std() > 0 else 0
    return {
        "name": name, "ret": eq.iloc[-1] - 1, "cagr": cagr, "sharpe": sharpe,
        "maxdd": maxdd, "ulcer": ulcer, "mar": mar, "r2": r2,
        "worst_m": monthly.min() if len(monthly) else 0,
        "pos_m": int((monthly > 0.001).sum()), "n_m": len(monthly),
        "monthly": monthly, "equity": eq,
        "turnover": float(pos.diff().abs().sum()) if pos is not None else 0,
    }


def fmt(s):
    return (f"{s['name']:<42} ret {s['ret']*100:+8.1f}%  cagr {s['cagr']*100:+6.1f}%  "
            f"shp {s['sharpe']:5.2f}  dd {s['maxdd']*100:6.1f}%  mar {min(s['mar'],99):5.2f}  "
            f"worstM {s['worst_m']*100:+5.1f}%  +m {s['pos_m']}/{s['n_m']}")


def split(df):
    return df.loc[:OOS_START].iloc[:-1], df.loc[OOS_START:]


def run_both(df, sig_fn, name, **bt_kw):
    """Compute signal on FULL data (indicators warm), then slice windows."""
    target = sig_fn(df)
    full = backtest(df, target, name=name + " FULL", **bt_kw)
    is_, oos = split(df)
    s_is = backtest(is_, target.loc[is_.index], name=name + " IS", **bt_kw)
    s_oos = backtest(oos, target.loc[oos.index], name=name + " OOS", **bt_kw)
    return full, s_is, s_oos


if __name__ == "__main__":
    df = load()
    print("Span:", df.index[0], "->", df.index[-1], "bars:", len(df))
    is_, oos = split(df)
    print(f"IS bars {len(is_)}  OOS bars {len(oos)} (bear year)")

    print("\n--- Baselines ---")
    bh = metrics("Buy&Hold FULL", (1 + df["ret"]).cumprod())
    print(fmt(bh))
    bh_oos = metrics("Buy&Hold OOS", (1 + oos["ret"]).cumprod())
    print(fmt(bh_oos))

    print("\n--- Family A: regime long/short, short_scale sweep ---")
    for ss in (1.0, 0.5, 0.25, 0.0):
        for r in run_both(df, lambda d, ss=ss: sig_regime(d, short_scale=ss),
                          f"regime ss={ss}"):
            print(fmt(r))
        print()

    print("--- Family B: TSMOM ensemble ---")
    for ss in (1.0, 0.5, 0.25):
        for r in run_both(df, lambda d, ss=ss: sig_tsmom_ens(d, short_scale=ss),
                          f"tsmom-ens ss={ss}"):
            print(fmt(r))
        print()

    print("--- Family C: Donchian ---")
    for n in (60, 120, 240):
        for ss in (1.0, 0.5):
            for r in run_both(df, lambda d, n=n, ss=ss: sig_donchian(d, n, short_scale=ss),
                              f"donch n={n} ss={ss}"):
                print(fmt(r))
            print()

    print("--- Family D: vol-targeted regime L/S ---")
    for vt in (0.3, 0.5, 0.8):
        for ss in (1.0, 0.5, 0.25):
            for r in run_both(df, lambda d, ss=ss: sig_regime(d, short_scale=ss),
                              f"regime ss={ss} volT={vt}", vol_target=vt, cap=1.0):
                print(fmt(r))
            print()
