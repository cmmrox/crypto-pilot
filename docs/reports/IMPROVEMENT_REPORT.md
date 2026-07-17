# Trend Rider v5.2 — Improvement Research Report (2026-07-17)

**Goal:** research how successful traders improve profit / cut losing trades,
test an economic-calendar filter, fine-tune the strategy (up to 20% risk),
and deliver an honest, validated recommendation.

**Method:** every idea was backtested on real Binance BTCUSDT 4h data
(2023-06 → 2026-07-17, fees included, conservative fills), then validated
out-of-sample on the 2025-07 → 2026-07 bear year. A change was accepted only
if it helped (or didn't hurt) BOTH windows. Scripts: `improve.py`,
`pyramid.py`, `leverage_backtest.py`.

## What the research says successful traders do

1. **Risk 1–2% per trade** — the near-universal professional rule.
2. **Scale out to smooth the curve** — partial exits improve Sharpe, not
   total return; the runner is where trend profits come from.
3. **Cut losses mechanically, let winners run** — win rates below 50% are
   normal for profitable trend followers; discipline on exits is the edge
   (Turtle Traders evidence).
4. **Time stops** reduce time-in-market cheaply.
5. **Macro events:** BTC's *direction* on CPI days is statistically random;
   Fed (FOMC) decisions matter more, and volatility stays elevated for hours
   after — but that's a volatility fact, not a directional edge.

v5.1 already embodied #1–#3. The open questions were tested one by one.

## Experiment results (full period / validated OOS)

| Idea | Result | Verdict |
|---|---|---|
| **TP1 size 50% → 40%** (keep more runner) | +130.8% → **+137.3%**, PF 1.81→1.84, DD −12.4→−13.2%; OOS unchanged (−4.1% vs −4.4%) | **ACCEPTED → v5.2** |
| TP1 size 30% | +145.5%, DD −14.0%, Sharpe 1.43 | optional aggressive setting |
| Multi-level TP ladders (1R/2R, 1R/2R/3R…) | all −35 to −70pp worse — selling more of the runner early kills the big winners | rejected |
| Time stops (48–168h if below entry) | all worse (−7 to −48pp), no worst-month benefit | rejected |
| Earlier breakeven (0.5R / 0.75R) | much worse (+37% / +105%) — noise stops you out | rejected |
| Pyramiding (Turtle adds at +0.5/1/1.5R) | all worse (+23% to +106%) — account already fully invested; adds dilute the base | rejected |
| Entry filters (RSI>70 skip, >25%/35% above SMA200 skip) | filters almost never fire on real signals; no effect or worse | rejected |
| **FOMC/CPI entry blackout (12–48h)** | −7 to −28pp worse; skipped entries cost more than event risk | rejected |

The 2026 verdict matches the 2025 sweeps: **v5's structure sits at a broad
optimum. The only honest lever left for "more profit" is position size.**

## Sizing (the real decision) — $1,000, 12x cap, 10% monthly-profit withdrawals

Full period, v5.2 (tp1 40%):

| Risk/trade | Total made (3y) | Max DD | Worst month | Started at bear top instead: max DD |
|---|---|---|---|---|
| 1% | +$320 | −5.3% | −1.8% | −5.7% |
| 2% | +$716 | −12.0% | −4.4% | −12.7% |
| **5%** | **+$1,348** | **−23.8%** | −8.5% | −20.1% |
| 10% | +$3,152 | −41.1% | −16.8% | −44.2% |
| 20% | +$16,077* | −53.4% | −10.3%* | **−60.4%** |

\* The 20% row is **sequencing luck, not skill**. The same backtest contains a
6-trade losing streak; at 20%/trade that streak alone turns $1,000 into $262.
Started one bear-cycle later, the same settings drew down −60% before
recovering. Kelly math on the measured edge (48% win rate, 2:1 win/loss)
puts full Kelly at ≈ 22% — i.e. 20% risk is betting *full Kelly* on an edge
that just spent an entire OOS year underwater (PF 0.88). Full Kelly with an
uncertain edge is how accounts die; professionals bet a quarter to half of
it. **Recommendation: 3–5% risk per trade** (≈ quarter Kelly), which also
means the 12x leverage cap is never stressed (max ~3.4x used) and liquidation
is a non-issue.

Note: the 4% monthly circuit-breaker was validated at ~5%/trade risk. If you
trade above that, scale the breaker roughly with risk (e.g. 10% risk → 12%
monthly cap) or it halts on every normal stop-out.

## Economic calendar — how to actually use it

- **Don't skip trades around events** — tested, it only costs money.
- **Never override an exit because an event is coming.** The stop, TP1, trail
  and regime rules already handle event moves.
- What the calendar IS for: **expectation management**. On FOMC days
  (14:00 ET) and CPI days (08:30 ET), 4h candles will be violent; wick-throughs
  of your stop are normal, not a malfunction. Don't panic-close the runner
  mid-candle, and don't market-buy into the spike — the system only acts on
  candle CLOSES anyway.
- FOMC decision dates and CPI release dates for the current year:
  federalreserve.gov/monetarypolicy/fomccalendars.htm and
  bls.gov/schedule/news_release/cpi.htm.

## Final: Trend Rider v5.2

Identical to v5.1 except **TP1 sells 40%** of the position (Pine input
default updated). Full period 2023-06 → 2026-07: **+137.3%, Sharpe 1.45,
max DD −13.2%, PF 1.84, 100 trades, 48% win rate**, worst month −5.6%,
vs buy & hold ≈ +115% with −53% drawdown. OOS bear year: −4.1% vs −45% B&H.

Everything else in `TRADING_GUIDE.md` stands. The system's profit engine is
unchanged: small capped losses, half the trades are scratches, and a handful
of +8–20% runners a year pay for everything — now with 10% more runner.
