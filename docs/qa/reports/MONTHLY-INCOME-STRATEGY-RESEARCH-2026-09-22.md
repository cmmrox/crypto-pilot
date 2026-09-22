# Monthly-income strategy research with JEV — 22 September 2026

## Verdict

- **No tested strategy was profitable every month.** Directional BTCUSDT trading did not
  approach that target at any risk level tested. Only market-neutral funding carry came
  close (91% profitable months since mid-2020), and it currently pays about 0.2–0.5% a
  month before any leverage.
- **Best candidate found: "Atlas 7 Dual" (research name).** One position, long and short,
  entered either on an Atlas-style trend pullback or on a volatility-squeeze breakout, with a
  1 × ATR buffer around SMA200, a price stop on every position and a 3x leverage cap.
  Walk-forward (unseen) months were profitable **58–62%** of the time; over June 2020–September
  2026 it was profitable in 50 of 76 months at 2% risk and 49 of 76 at 4% risk. Expect roughly
  six profitable months in ten, not twelve in twelve.
- **Risk profile (owner choice, 2026-09-22): 4% risk per trade with 8% monthly breakers.**
  The breaker must be about twice the risk per trade. Keeping the current 4% breaker at 4% risk
  halts a side after a single stopped trade and tested worse than 2% risk on every measure
  (+207% versus +232%, 48.7% versus 65.8% profitable months). See "Risk per trade".
- **JEV (TypeSafe `jev-1.13.0`) did not improve trading decisions** on anonymised market
  state. Its direction answer had AUC 0.503; every JEV entry gate reduced walk-forward
  results. Keep JEV out of the trade decision path.
- **Why the live bot missed July–September:** 15% long risk sizing (up to 6x) with a 4%
  monthly breaker means one stopped long trips the breaker. It happened on August 11 and
  September 1, blocking the long book while BTC rose from about 62.9k to 86k.

Nothing was deployed, no order was placed, no setting or strategy was changed, and the
frozen `research/` tree was not modified. This is research evidence, not a release.

## What the live bot did in the last two months

From `.artifacts/strategy-audit-2026-09-22/` (read-only LIVE audit earlier today):

| Date (UTC) | LIVE event |
|---|---|
| Jul 30 12:00 | Long 0.006 filled; protective stop rejected (precision); emergency exit |
| Aug 1–4 | Four 0.002 shorts, each closed when deep-bear ended; all small losses |
| Aug 7 20:00 | Long entry rejected: margin insufficient |
| Aug 11 12:00–16:00 | Long 0.019 at 64,374; long breaker tripped at −7.1% of month equity |
| Aug 13–17 | Short 0.002, small loss |
| Sep 1 00:00–16:00 | Long 0.014 at 78,535.7; long breaker tripped at −4.46% |
| Sep 1 → now | Long book halted; 35 of 92 retained decisions would otherwise have been longs |

Account balance: 223.48 USDT at July 31 → 190.18 USDT now (−14.9%) while BTC rose about
37%. The same window replayed with the candidate below, starting from 223.48 USDT with
0.001 BTC lots: **249.56 USDT (+11.7%)** at 2% risk (the final September 18 long is marked
at the latest close, not realised).

## Data and protocol

- Public Binance USD-M data only, downloaded 2026-09-22 (`experiments/monthly_income_research/
  scripts/download.py`): BTCUSDT perpetual and spot 15m/1h/4h/1d from 2019-09-08 to
  2026-09-22 12:15 UTC, 7,708 funding events, and ETH/SOL/BNB/XRP perpetual 1h plus funding
  for cross-asset checks. The 4h series used for decisions is aggregated from 1h; it differs
  from Binance's native 4h klines in 4 of 15,424 bars (known exchange inconsistencies).
- Decisions on closed 4h candles only; entries and signal exits fill at the next 4h open.
  Stops and take-profits are checked on 1h bars (15m for grid simulation); if both could fill
  in one bar the stop is assumed first. Taker fee 0.05% plus 0.02% slippage per side, maker
  0.02% for take-profit limits, historical funding on every open position.
- Evaluation: 2020-06-01 to 2026-09-22 (76 months). Walk-forward selection trains on 24
  months and tests the next 6, rolled every 6 months: 52 unseen months, 2022-06 to 2026-09.
- Engine cross-check: with Atlas 5.2 rules at the live profile, the research engine
  reproduced 55 of the production replay's 59 long entries (Sep 2023–Sep 2026) and ended at
  1,056 USDT versus the production engine's 1,285 from 200. The research engine is the more
  conservative of the two, so it does not flatter the candidate.
- Scale of search: about 2,400 BTC strategy configurations in nine families, 60 grid-bot
  configurations, 8 carry variants, 33 JEV-gated variants, and cross-asset replays. Searching
  this much creates selection bias; walk-forward testing, cross-asset testing with identical
  parameters, parameter-plateau checks and cost/delay stress tests are the mitigations.

## Baselines: the three installed releases (production replay engine)

Production `PluginReplayEngine`, fresh data, 200 USDT, live profile (15% risk, 6x, 4% breakers):

| Release | Sep 2023 → now | Max drawdown | Profitable months |
|---|---:|---:|---:|
| Atlas 5.2 · 4h | 1,285 USDT | −54.6% | 11 / 37 |
| Atlas 6 · 4h | 1,461 USDT | −46.9% | 14 / 37 |
| Atlas 6 Trail · 4h | 1,599 USDT | −46.0% | 14 / 37 |

Atlas 6 Trail from 2026-07-22 with 200 USDT: 160.53 (−19.7%). Over June 2020–September 2026
at 10,000 USDT: live profile +1,895% with a −50% month-end drawdown and 27/76 profitable
months; the same logic at 2% risk and 3x without breakers +197%, −9.4%, 42/76.

## Families tested (walk-forward, 52 unseen months, 1% risk per trade)

| Family | Idea | Profitable months | Sharpe | Worst month |
|---|---|---:|---:|---:|
| Trend rider (symmetric shorts with stops) | Atlas entries, stops both sides | 57.7% | 0.82 | −5.6% |
| Trend rider + chop filter | Efficiency-ratio gate | 44–58% | 0.79–1.39 | −3.5% |
| Squeeze breakout | Break of a tight range | 44.2% | 0.78 | −7.4% |
| Donchian breakout | Channel breakout | 46.2% | 0.45 | −4.3% |
| EMA trend, vol-targeted | Always in the trend side | 50.0% | 0.67 | −22.8% |
| Pullback mean reversion | RSI dips in trend | 23.1% | −1.11 | −2.0% |
| Range mean reversion | Fade z-score in chop | 50.0% | −0.04 | −5.1% |
| MAX/MIN (QuantPedia) | 10–20 day highs/lows | 46.2% | 0.03 | −4.7% |
| Dual (trend + squeeze) | One position, two triggers | 61.5% | 0.88 | −5.0% |
| **Dual + 1 ATR buffer** | Hysteresis around SMA200 | **57.7%** | **1.02** | **−3.0%** |

Neutral futures grid (15m fills, maker fees, ATR spacing): most variants lost after costs;
the few positive ones had −14% to −23% worst months and flipped sign with small parameter
changes. Regime-filtered grids lost money. Funding carry (spot long + perpetual short,
unlevered, 30-day trailing funding > 0): 91% profitable months, worst −0.26%, but 2025 +4.2%
and 2026 year-to-date +1.0%. Chop-filtered trend rider did not transfer to other coins
(ETH −2%, XRP −18% with BTC parameters); the squeeze breakout was profitable on all five coins.

Adding the carry overlay to the dual walk-forward portfolio raised profitable months to
61.5% and Sharpe to 1.5 (worst month −3.1%), but carry requires spot trading or Binance
multi-assets margin, which the bot does not support.

## Candidate specification: Atlas 7 Dual (research)

All on closed BTCUSDT 4h candles. ATR is ATR14 with an exponential (alpha 1/14) seed.

- Regime with buffer: bull = close > SMA200 + 1 ATR and EMA50 > EMA200; bear = close <
  SMA200 − 1 ATR and EMA50 < EMA200.
- Entry A, trend pullback: regime just began, or price closed back above EMA20 (below, for
  shorts) after closing on the other side during the current regime run.
- Entry B, squeeze breakout: the previous bar's 24-bar high-low width was at or below its
  35th percentile of the last 360 bars, and the close breaks the previous 24-bar high (low),
  beyond the buffered SMA200 line in the same direction.
- One position at a time; an opposite entry reverses the position.
- Protective stop 2.5 ATR from entry for every long and short. Size = risk % of equity ÷ stop
  distance, capped at 3x leverage, rounded down to 0.001 BTC with a 50 USDT minimum.
- Take 40% at 2R (limit), move the stop to breakeven, then trail at the highest high
  (lowest low) since entry ∓ 3 ATR at each 4h close.
- Exit when the close crosses the buffered SMA200 line against the position.
- Independent monthly long and short breakers, set to about twice the risk per trade
  (see "Risk per trade" below). The owner selected 4% risk with 8% breakers on
  2026-09-22; the research default was 2% risk with the existing 4% breakers.

This candidate deliberately puts a price stop on shorts, unlike Atlas 6's stop-free,
size-managed short sleeve. Atlas 6 itself is untouched; adopting stop-protected shorts in a
new release is an owner decision.

## Candidate results (research engine)

June 2020–September 2026, 10,000 USDT, 2% risk, 3x cap, 4% breakers: **+232%**, 50/76
profitable months, worst month −8.5%, month-end drawdown −16.4%, intrabar drawdown −20.6%,
monthly Sharpe 1.17, 321 trades.

| Year | 2020 (Jun–Dec) | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Candidate, 2% risk | +18.5% | +31.8% | +2.7% | +15.3% | +34.4% | +14.9% | +16.4% |
| Atlas 6 Trail, live profile | +99.4% | +42.6% | −41.0% | +198.2% | +171.9% | +84.5% | −20.5% |
| Atlas 6 Trail, 2% risk | +38.2% | +7.8% | −6.2% | +36.8% | +38.7% | +8.4% | +3.4% |

Atlas rows are production-engine replays; the candidate row is the research engine.

Robustness (no breakers unless noted):

- Risk 1% / 2% / 3%: +86% / +222% / +423%; profitable months 66% / 66% / 65%; worst
  month −5.6% / −10.9% / −16.0%.
- Double trading costs (0.14% per side): +171%, 64.5% profitable months, Sharpe 0.93.
- Every order one 4h bar late: +152%, 61.8% profitable months, Sharpe 0.90.
- Breaker choice at 2% risk: none −10.9% worst month; per-side 4% −8.5% (Sharpe 1.17);
  account −8% monthly stop −9.5%. The 4% breaker helps once risk per trade is 2%.
- Same parameters on other coins, monthly Sharpe: BTC 1.09, ETH 0.93, SOL 0.73, BNB 0.55.
- All 768 dual configurations tested were profitable on BTC; the 1 ATR buffer raised the
  average full-period, last-24-month and cross-asset Sharpe.
- 190 USDT with 0.001 BTC lots, September 2023 → now: 355.08 USDT (+87%), 24/37 profitable
  months, worst −8.8%, intrabar drawdown −12.8%; 24 entries skipped because the minimum lot
  exceeded the 2% risk budget.

## Risk per trade — added 2026-09-22 at the owner's request

`scripts/risk_sweep.py`, same rules, June 2020–September 2026, 10,000 USDT, continuous sizing.
**The breaker must scale with the risk per trade.** A 4% per-side breaker with 4% risk halts a
side after one stopped trade — the exact failure mode seen on LIVE in August and September.

| Risk | Breaker | Total | Profitable months | Worst month | Max drawdown | Sharpe | Breaker exits |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1% | any | +86% | 65.8% | −5.6% | −9.3% | 1.09 | 0 |
| 2% | 4% | +232% | 65.8% | −8.5% | −20.6% | 1.17 | 3 |
| 3% | 8% | +486% | 64.5% | −14.5% | −22.2% | 1.17 | 2 |
| 4% | **4%** | **+207%** | **48.7%** | −9.1% | −29.7% | **0.68** | 15 |
| 4% | 8% | +734% | 64.5% | −16.5% | −38.0% | 1.13 | 6 |
| 4% | 10% | +833% | 64.5% | −18.6% | −28.5% | 1.17 | 3 |
| 5% | 8% | +1,013% | 63.2% | −18.9% | −43.6% | 1.13 | 13 |

At 4% risk with 8% breakers the median month is +3.2%, winning months average +9.0%, losing
months −7.0%, six months lost more than 10%, and the longest losing streak is 3 months. Yearly:
2020 (Jun–Dec) +37.4%, 2021 +69.3%, 2022 +2.1%, 2023 +24.5%, 2024 +73.3%, 2025 +26.7%,
2026 YTD +28.3%. Stress: double costs +518% (Sharpe 0.99), all orders 4h late +524%
(Sharpe 1.01).

On a 190 USDT account with real 0.001 BTC lots (September 2023 → now): 2% risk / 4% breaker
355.08 USDT with 24 entries skipped for minimum lot size; **4% risk / 8% breaker 576.82 USDT
(+204%), 25/37 profitable months, worst month −16.5%, intrabar drawdown −25.5%, no skipped
entries**. Lot granularity is why the smaller account tolerates the higher risk setting: at
2% risk a 0.001 BTC minimum already exceeds the risk budget in about one entry in six.

Same window as the live account (2026-08-01 from 223.48 USDT, real lots): 2% risk 249.56 USDT
(+11.7%); 4% risk with 8% breakers 265.56 USDT (+18.8%); 4% risk with 4% breakers 193.24 USDT
(−13.5%). The live account itself ended at 190.18 USDT (−14.9%).

Risk-adjusted quality is flat between 2% and 4% (Sharpe 1.17 versus 1.13): 4% is 2% scaled up,
roughly doubling both the average month and the drawdown. 3% with an 8% breaker keeps the 1.17
Sharpe with a −22% drawdown and is the balanced middle. No setting removes losing months.

## JEV (TypeSafe System One)

Jev is a structured-decision model: text state plus typed Choice/Score/Noul questions in,
calibrated probabilities out. Its documentation warns it is weak at arithmetic, numbers and
dates, so the test kept all arithmetic in code and gave Jev named buckets.

- State: 14 anonymised descriptors per closed 4h candle (trend versus 33-day average and its
  slope, 1/7/30-day change, range position, distance from 90-day high, volatility rank, path
  efficiency, crossings, candle direction count, funding, volume). No dates, prices or asset
  name, so the model cannot recall later price history.
- Questions: market phase (uptrend/downtrend/sideways), chop, trend strength, overextension,
  volatility squeeze, and "higher in three days".
- Scale: 14,767 unique requests, 12.1M input tokens, about $0.51, pinned `jev-1.13.0`, all
  answers cached for deterministic replay.
- Prediction: AUC for "higher in three days" 0.503 overall (0.517 in 2020–2023, 0.481 in
  2024–2026); phase-based direction 0.514 (0.482 recently); chop answers correlated 0.05
  with realised future path efficiency.
- Gating: every phase, chop, strength, direction and squeeze gate reduced profitable months
  or Sharpe in walk-forward selection (for example, chop-filtered trend 63.5% → 40.4%;
  squeeze 53.8% → 48.1%). Only "not overextended" was roughly neutral.

Where Jev fits instead: classifying unstructured text, such as a news-event risk guard
(exchange hacks, regulatory actions, macro surprises) that blocks new entries for a few
hours, or routing unfamiliar exchange errors. That would need a forward DEMO test, since no
multi-year headline archive exists, and an owner-approved deviation because the news module
is isolated from trading by design.

## Limits

- Simulated fills on public candles; not order-book or account replay. Slippage is an
  allowance; liquidation is not modelled; intrabar path within an hour is unknown.
- The final configuration was chosen using data through today; its 66% profitable months is
  partly in-sample. The walk-forward 57.7–61.5% is the fairer expectation.
- Small accounts are lumpy: at about 190 USDT a 0.001 BTC lot already risks about 1.5% with
  a 2.5 ATR stop, so realised risk per trade varies between roughly 1.5% and 3%.
- Past behaviour does not guarantee future profit; this is not financial advice.

## Validation

- `experiments/monthly_income_research/tests`: 5 passed (equity equals summed trade P&L,
  funding and fee accounting, causality under changed future candles, lot rounding and
  minimum notional, breaker blocking).
- Production baselines ran through `strategy_runtime.replay.PluginReplayEngine` unchanged.
- The TradingView script `tradingview/atlas_7_dual_strategy.pine` has not been compiled in
  TradingView yet; its emulator will not match the research engine exactly.
- No backend, frontend, deployment or production code changed, so backend, parity and
  Playwright suites were not re-run for this research.

## Next decisions for the owner

1. Whether to build the candidate as a new plugin (for example display name
   `Atlas 7 Dual · 4h`) with parity, chronological replay and bot-integration tests, then
   run it on DEMO before any LIVE use. The owner selected the 4% risk / 8% breaker profile;
   both numbers are inside the existing parameter ranges (`risk_pct` ≤ 15, monthly caps
   0.01–0.10), so no schema change is needed, but the release must pin them explicitly.
   A −38% drawdown is part of that choice; 3% risk with 8% breakers halves it (−22%).
2. Whether a stop-protected short book is acceptable in a new release.
3. Whether to forward-test a Jev news-event guard in DEMO (architecture deviation).
4. Whether to pursue funding carry, which needs spot or multi-assets margin support.
5. Rotate the TypeSafe API key: it was shared in a chat message. It was only ever read
   from the `TYPESAFE_API_KEY` environment variable and is not stored in the repository.

## Reproduce

```sh
cd experiments/monthly_income_research
../../backend/.venv/bin/python scripts/download.py --symbols BTCUSDT --intervals 15m,1h,4h,1d --spot
../../backend/.venv/bin/python scripts/download.py --symbols ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT --intervals 1h
../../backend/.venv/bin/python scripts/baseline_atlas.py
../../backend/.venv/bin/python scripts/export_atlas_monthly.py
# research engine (needs numba; see README)
python scripts/grid_stage1.py && python scripts/grid_stage2.py && python scripts/grid_dual.py
python scripts/select_dual.py && python scripts/final_eval.py
python scripts/risk_sweep.py   # risk per trade vs monthly breaker
TYPESAFE_API_KEY=... python scripts/jev_eval.py   # uses cached answers when present
```
