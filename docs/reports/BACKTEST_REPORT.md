# BTC Trend Rider v5.1 — Backtest Report

**Final headline (v5.1, fees included):** +130.8% over 3 years, Sharpe 1.49, max drawdown −12.4%, profit factor 1.81, 100 trades, 48% win rate, worst month −5.3%, vs buy & hold +118.9% with −53.4% drawdown.

**Data:** Real Binance BTCUSDT klines (data.binance.vision), 2023-06-01 → 2026-06-30 (3 years, 6,756 4h candles). Fees 0.04%/side included in every number. Conservative fills (if a bar touches both stop and target, the stop fills first).

## Why 4h and not 15m

Your original 5-confluence 15m indicator was replicated exactly on real data in earlier sessions and re-confirmed: **it loses money as written** (−14 to −16%, profit factor ~0.9, ~450 trades). Even the best filtered version (ADX>30 + trailing exit) was only marginal and fell apart out-of-sample (PF 0.69). 15m signals on BTC have no reliable edge once fees are paid — this was tested thoroughly twice. The edge that survives every test is **trend-regime participation on the 4h chart**.

## The system (BTC_Trend_Rider_v5.pine)

- **Regime filter (the edge):** long only while `close > SMA200` AND `EMA50 > EMA200` on 4h. No shorts — shorting BTC lost money in every test.
- **Entries:** when the regime turns on, and pullback-resumptions (price dips below EMA20, then closes back above it while the regime holds).
- **Your management rules, validated:** initial stop 2.5×ATR(14) → at 1R sell 50% and move stop to entry (breakeven) → trail the rest at highest-high − 4×ATR → exit everything if the regime dies.
- **Monthly circuit-breaker (v5.1):** if equity drops 4% within a calendar month, close everything and stand aside until the next month. Validated in-sample (Sharpe 1.77→1.97, PF 2.01→2.30) *and* out-of-sample (−1.7% vs −3.2%, smaller DD). It cuts the worst month from −7.6% to −5.3% and *raises* total return (skipping post-loss chop avoids bad re-entries).

## Results (3 years, fees included)

| Strategy | Return | Sharpe | Max DD | Trades | Win rate | PF | +Months |
|---|---|---|---|---|---|---|---|
| Buy & Hold | +118.9% | 0.78 | −53.4% | — | — | — | 20/36 |
| Regime flip only (v3) | +157.7% | 1.14 | −28.6% | 61 | 15% | 1.95 | 16/36 |
| Trend Rider v5 | +112.5% | 1.31 | −16.2% | 106 | 47% | 1.62 | 18/36 |
| **Trend Rider v5.1 (final, +breaker)** | **+130.8%** | **1.49** | **−12.4%** | 100 | 48% | 1.81 | 17/36 |

Your partial-profit management trades some total return for a much smoother ride: highest Sharpe, drawdown cut to −16% (vs −53% holding), and win rate 47% (the breakeven stop turns many would-be losers into scratches, exactly as you intended).

### Out-of-sample test (2025-07 → 2026-06, the bear year)
- Buy & hold: **−45.3%**
- Trend Rider v5: **−3.2%** (max DD −12.5%)
- Trend Rider v5.1: **−1.7%** (max DD −11.6%)

This is the honest picture: in a bear year the system's value is *not losing*. It sat mostly flat while the market halved.

### Robustness (not curve-fit)
All neighboring parameters stay profitable: regime SMA 150–250 and EMA 40/180–60/220 all give +75% to +117% (Sharpe 1.0–1.35); every stop/TP1/trail combination in the sweep (54 configs) was profitable, Sharpe 0.79–1.31. The chosen config sits in the middle of a broad plateau, not on a spike.

## Why long-only? Shorts were tested exhaustively (`short_sweep.py`, `combined.py`)

The obvious idea — "profit in bear markets too by shorting" — was tested four ways:

1. **Rally-fade shorts** (short when price fails at EMA20 in a bear regime): lose money in almost every configuration (PF 0.9-1.1). Bear-market rallies are too violent.
2. **Fresh-bear shorts in isolation** (short once when the regime flips bearish): profitable standalone (+13% to +47% over 3y, all 18 configs green) — a real but small edge, mostly earned in one bear leg.
3. **Combined with the long system (v5.2 candidate):** return drops (+131% → +89-101%), Sharpe drops (1.49 → 1.1-1.2), drawdown worsens (−12% → −18-21%), and red months *increase* (12 → 13-14).
4. **The decisive test — the out-of-sample bear year itself:** long-only lost −1.7%; adding shorts lost **−8.4%**. Even in the market shorts are meant for, they hurt.

Why: BTC's bear regimes flip on and off many times in chop, so "fresh bear" entries fire at local bottoms as often as at tops, and each whipsaw pays fees and misses the long re-entry. Bitcoin's long-run upward drift means the profitable side of a bear market is *cash*, not shorts. **In a bear market this system "profits" by not losing: −1.7% vs −45.3% for holders — a 43-point edge — and re-enters longs the moment the trend returns.**

## About "profit every month" — read this

**No honest strategy on one asset delivers a profit every single month, and anyone selling you one is lying.** Verified monthly distribution over 36 months (v5.1):

- 17 positive months, 12 negative, 7 flat (no trades — regime off or breaker)
- Best months: +21.5%, +17.0%, +12.4% (trend months)
- Worst months: −5.3%, −4.4%, −4.2% — losses capped by your breakeven rule + the monthly breaker
- Longest flat/negative stretch: the 2025-26 bear (system mostly flat, preserving capital)

That asymmetry — small capped losing months, big winning months, flat when there's no trend — is what a real edge looks like. Demanding "every month green" forces overfitting, which is exactly how the 15m system fooled us before real-data testing.

### Monthly-consistency experiments (what was actually tried)

The "every month green" goal was pushed as far as the data allows (`consistency.py`, all fees included):

| Variant | Return | Sharpe | Max DD | Worst month | Neg months |
|---|---|---|---|---|---|
| v5 long-only (final) | +112.5% | 1.31 | −16.2% | −7.6% | 12/36 |
| + bear-regime shorts | +99.6% | 0.92 | −30.1% | −10.5% | 16/36 |
| Long+short, half size | +45.9% | 0.92 | −15.2% | −5.2% | 16/36 |
| **Long-only, half size** | +48.3% | 1.30 | **−8.4%** | **−3.9%** | **10/36** |

- **Shorting BTC in bear regimes makes months *less* consistent**, not more (bear chop stops shorts out repeatedly). Tested with three management variants — all worse.
- **Position size is the real consistency knob.** Trading 50% of equity (set "Order size" to 50% in the strategy's Properties tab) cuts the worst month to −3.9% and negative months to 10/36 while keeping the same Sharpe. Scale to taste: consistency and total return trade off linearly.
- **Monthly circuit-breaker (v5.1):** halting the month after a 4% equity loss improved *everything* — validated out-of-sample. In the final code, default on.
- **Diversification (4-coin portfolio, `portfolio.py`):** running the same system on BTC+ETH+SOL+BNB with equal capital gives 16 green/14 red months — *worse* than BTC alone. Crypto is one correlated trade; altcoins run the strategy weaker (ETH Sharpe 0.67, BNB 0.33 vs BTC 1.49). Diversifying within crypto does not buy monthly consistency.
- After 70+ tested configurations (management grid, ADX filters, shorts, sizing, circuit-breaker, multi-coin portfolio): **the maximum honestly achievable is ~2 green months for every red one, with red months 2-4× smaller than green ones.** 36/36 green months does not exist on this asset class — that profile is only produced by overfit backtests or fraud.

## Monthly returns (v5.1, full 3y, fees included)

```
2023: Jul -1.3  Aug 0.0  Sep -0.2  Oct +6.6  Nov +9.1  Dec +4.5
2024: Jan +10.4 Feb +17.0 Mar +9.1 Apr -5.3  May +0.2  Jun +0.1
      Jul +4.4  Aug -3.5  Sep +4.2 Oct +12.4 Nov +21.5 Dec +3.1
2025: Jan -4.2  Feb -3.5  Mar 0.0  Apr +6.8  May +5.0  Jun -4.4
      Jul +4.8  Aug -0.2  Sep -2.8 Oct -0.6  Nov 0.0   Dec 0.0
2026: Jan -4.2  Feb 0.0   Mar +1.0 Apr +3.6  May -3.1  Jun 0.0
```

## How to use

1. TradingView → BTCUSDT (Binance) → **4h chart**.
2. Pine Editor → paste `BTC_Trend_Rider_v5.pine` → Add to chart.
3. Check Strategy Tester to see the backtest on TradingView's own data.
4. Create alert → condition: this strategy → "Order fills and alert() function calls". You'll get BUY, TP1, trail-stop and regime-exit alerts with instructions.
5. Risk: the backtest compounds 100% of equity per trade with a 2.5×ATR stop (~5-8% risk per trade). If trading real money, start smaller.

## Files

- `BTC_Trend_Rider_v5.pine` — the TradingView strategy, v5.1 (backtest + alerts + circuit breaker)
- `download_data.py` — pulls real Binance data
- `backtest.py`, `sweep.py`, `validate.py`, `consistency.py`, `circuit_breaker.py` — full reproducible pipeline
- `btc_4h.csv`, `btc_15m.csv`, `btc_1d.csv` — raw data
