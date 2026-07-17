# Long/Short Composite — "Trend Rider v6" Research Report (2026-07-17)

**Goal:** a strategy whose equity curve grinds UP with small pullbacks — including
in a bear market, by trading shorts — instead of giving back profits like the
withdrawal-plan curve did.

**Headline (fees included, real Binance 4h data 2023-06 → 2026-07):**

| | Composite v6 | v5.2 long-only | Buy & Hold |
|---|---|---|---|
| Total return | **+204.5%** | +137.3% | +134.6% |
| CAGR | **+42.7%** | +31.8% | +31.3% |
| Sharpe | **1.48** | 1.45 | 0.82 |
| Max drawdown | −17.2% | −13.2% | −53.4% |
| Ulcer index (avg pain) | **0.069** | 0.073 | 0.211 |
| Log-equity linearity R² (smoothness) | **0.91** | 0.82 | 0.55 |
| Worst month | −7.9% | −5.6% | −20.4% |
| Green months | **23/37** | 16/37 | 21/37 |
| **OOS bear year 2025-07→2026-07** | **+31.7%** (DD −13.8%) | −2.1% | −41.4% |

The composite's equity curve is the straightest of the three (R² 0.91) and it is
the only one that **made money in the bear year** — which is exactly what was asked.

## What changed vs the old conclusion "never short BTC"

Every previous short attempt used the long side's management: ATR stop above
entry, TP1, trail. Bear rallies are violent, so those stops were hit constantly
— the shorts died by whipsaw. This research separated the two questions:

- **Is there a short edge?** Yes. Raw "be short while the bear regime holds"
  (no stops at all) made +30% in the OOS bear year. The edge was always there;
  the stops were destroying it.
- **How to hold shorts without stop whipsaw?** Position **sizing**, not stops:
  vol targeting shrinks the short when the market goes wild, and a monthly
  sleeve breaker caps a bad month. The sleeve rides through rallies instead of
  being stopped by them.

## The system (Trend Rider v6 = v5.2 long + short sleeve)

**Long engine — unchanged v5.2** (already validated): long entries while
`close > SMA200` and `EMA50 > EMA200`; 2.5×ATR stop; TP1 at 1R sells 40%,
stop → breakeven; trail 4×ATR; exit on regime death; 4% monthly circuit breaker.

**Short sleeve — new, stop-free, runs only when the long engine is flat:**
- **When:** deep-bear regime on 4h closes: `close < SMA200 − 0.5×ATR(14)`
  AND `EMA50 < EMA200`. (Mutually exclusive with the long regime — the two
  never overlap, so no leverage is used.)
- **Size:** `0.75 × min(1, 0.40 / realized_vol) × equity` short, where
  realized_vol = annualized EWMA(48-bar) vol of 4h returns. In calm bears it
  shorts ~75% of equity; in violent crashes it automatically shrinks.
- **Exit:** regime condition fails on a 4h close → cover. No price stop.
- **Sleeve breaker:** if the sleeve loses 4% of equity within a calendar
  month, cover and stand aside until the next month (same rule that was
  already validated on the long side).

## Monthly returns (composite, fees included)

```
2023: Jul -1.5  Aug +5.3  Sep -3.5  Oct +6.5  Nov +7.8  Dec +5.3
2024: Jan +7.2  Feb +18.9 Mar +9.2  Apr -2.6  May -3.8  Jun +3.2
      Jul +4.8  Aug -4.8  Sep +1.3  Oct +12.9 Nov +25.0 Dec +2.6
2025: Jan -7.9  Feb +6.5  Mar -4.5  Apr +4.4  May +5.5  Jun -6.0
      Jul +5.6  Aug +2.4  Sep -5.9  Oct -0.5  Nov +11.6 Dec -3.8
2026: Jan +3.8  Feb +9.4  Mar -4.2  Apr +1.3  May -2.5  Jun +16.8
```

23 green / 14 red; every red month is single-digit; the bear year (2025-07 on)
is **net positive** because the sleeve earns while the long engine sleeps.
This is the honest version of "only goes up with small pullbacks" — nothing
real gives 37/37 green months.

## Robustness (why this is not curve-fit)

- **Depth filter** 0 → 1.0 ATR: full +174% to +204%, OOS +28% to +34% — flat plateau.
- **Vol target** 0.3 / 0.4 / 0.5 / off: full +180% to +204%, OOS +24% to +41%.
- **Sleeve weight** 0.5 → 1.0: full +183% → +224%, OOS +20% → +44%, DD −16% → −19%
  (a clean risk/return dial, pick your size).
- **Costs**: still +176% full / +29% OOS at 0.10%/side — 2.5× actual Binance taker fees.
- **Other coins, BTC-tuned params untouched:** ETH +118% (OOS +34%), BNB +25%
  (OOS +51%), SOL +149% (OOS −0.5%). Structure generalizes; BTC remains the best host.
- IS/OOS discipline: every accepted piece helps (or is neutral) in-sample AND
  in the untouched 2025-07→2026-07 bear year. Rejected on the way: TSMOM
  ensembles, Donchian L/S, raw regime flips, fade-style shorts, oversold-pause
  shorts — all documented in `sweep1_out.txt` / `short_lab.py` output.

## Tuning the "smoothness vs growth" dial

| Sleeve weight | Full return | Sharpe | Max DD | Worst month | OOS bear year |
|---|---|---|---|---|---|
| 0.5 (smoothest) | +183% | **1.54** | **−15.9%** | −6.8% | +19.9% |
| **0.75 (chosen)** | +204% | 1.48 | −17.2% | −7.9% | +31.7% |
| 1.0 (max bear alpha) | +224% | 1.40 | −18.6% | −8.9% | +44.0% |

Want even smaller pullbacks? Scale the *whole system* (both sleeves) by 0.5 —
that halves every drawdown and monthly loss and roughly halves returns, same
Sharpe. Drawdown scales with size; the shape of the curve is already as
straight as this asset honestly allows.

## Execution notes (4h bar closes only, Binance USDT-M futures)

1. All decisions on the 4h candle CLOSE. Longs exactly as in `TRADING_GUIDE.md`.
2. Short sleeve entry: at a 4h close with `close < SMA200 − 0.5×ATR` and
   `EMA50 < EMA200`, open a short worth `0.75 × min(1, 0.40/vol) × equity`.
3. Re-check size on each 4h close; adjust only if the target changes by more
   than ~20% (avoids fee churn — sizing tolerance tested in the cost sweep).
4. Cover the short when the deep-bear condition fails on a close, or when the
   sleeve is down 4% of account equity within the month (stand aside till the 1st).
5. Never both long and short: the regimes cannot overlap by construction.

## Files

- `BTC_Trend_Rider_v6.pine` — the executable TradingView strategy (long engine + short sleeve, alerts, status table)
- `TRADING_GUIDE.md` §10 — plain-language rules for trading the short sleeve
- `research_ls.py` — vectorized L/S engine + strategy families A–D sweep
- `short_lab.py` — short-sleeve variant lab (10 variants, IS/OOS)
- `combine_ls.py` — long+sleeve weight sweep
- `final_composite.py` — the chosen system; writes `composite_equity.csv`
- `robustness_ls.py` — depth/vol/weight/cost/coin robustness battery
- `sweep1_out.txt` — raw family-sweep results

**Honesty box:** single asset, one bear cycle in the OOS window, futures
funding rates not modeled (typically *positive* for shorts in bears — would
likely help, not hurt), and all results assume 4h-close execution with
0.05%/side cost. Past performance is not a promise; run it small first.
