# Monthly-consistency strategy research — 6 September 2026

## Decision

**No strategy found in this bounded study meets the requested >60% profitable-month
target. Do not promote the new candidate to LIVE or describe it as passive income.**
The new long/flat breakout variant reduced simulated losses but did not establish
reliable monthly income or dominate the existing strategy on every measure.

Thirty distinct parameter configurations were tested: 24 initial candidates and six
neighbors of the training leader. Repeated verification runs used the same candidate
set, not additional optimization trials. This was deterministic mathematical search;
no new real-LLM advisor iterations, login, credit reset or production changes occurred.

## Research that informed the hypothesis

- [Le and Ruthbah, Monash: Trend-following Strategies for Crypto Investors](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf)
  reports historical trend-following results and substantial transaction-cost impact.
  It motivated testing a simple trend rule and explicitly stressing costs. Its results
  are not evidence that our BTC perpetual strategy works.
- [r/algotrading: Problem with overfitting](https://www.reddit.com/r/algotrading/comments/1t70xws/problem_with_overfitting/)
  discusses parameter sensitivity, repeated holdout exposure and research logs. These
  community suggestions motivated a small grid and one-coordinate refinement. They
  are practitioner anecdotes, not independently verified profitable strategies.
- [QuantConnect community: Rebalancing Premium in Mean-reverting Cryptocurrencies](https://www.quantconnect.com/forum/discussion/13540/share-rebalancing-premium-in-mean-reverting-cryptocurrencies/p1)
  contains follow-up reports of large downturn losses, regime-filter suggestions, and
  universe/warmup issues. This supported testing a risk-off condition, not copying the
  old FTX multi-asset system or accepting its reported performance as proof.

Our inference: seeking more frequent profits by buying every dip can add losses and
costs. A simple regime filter is worth testing, but cannot manufacture profitable
months. Risk control and evidence quality matter as much as the entry indicator.

## Protocol and data

- Market: Binance USD-M BTCUSDT perpetual, closed 4h candles.
- Training/selection: 2023-09-01 00:00 UTC to 2025-09-01 00:00 UTC, end exclusive.
- Later validation: 2025-09-01 to 2026-09-01, end exclusive. Separate $200 flat start.
- Continuous three-year account: 2023-09-01 to 2026-09-01. $200, no withdrawals.
- Recent comparison: 2026-06-06 04:00 UTC to 2026-09-06 04:00 UTC. Separate $200
  flat start, profits retained. June and September are partial months; July/August
  are the two complete months inside this rolling three-month window.
- Authentic previously downloaded Binance candles/funding were integrity-checked,
  with 400 warmup candles. These are public market observations, not actual account
  fills or raw-trade replay. No fabricated market data is used for reported results.
- Per-side cost assumption: 0.06% (0.04% fee + 0.02% execution allowance), identical
  across comparisons. Stress: 0.12%. These are assumptions, not a verified account
  fee tier. Funding rates are historical observations.
- Current exchange filters applied historically. For the selected three-year result,
  23 funding events used the existing candle-price fallback because historical mark
  prices were absent. Later-year and recent candidate runs had zero such fallbacks.
- Monthly P/L includes marked equity. Flat months are not profitable. No daily/monthly
  withdrawals, income smoothing, fabricated cash interest or martingale sizing.

Selection first prefers positive net profit, drawdown <=15%, worst month >=-5% and
at least 30 closed trades; then profitable-month frequency and return relative to
drawdown. The data has been exposed to previous research, so even the later partition
is retrospective validation, **not untouched out-of-sample or forward evidence**.

## Selected new hypothesis

`regime_long_research_4h_v1`, breakout variant:

1. A closed candle must be above EMA200, with EMA200 higher than six bars earlier.
2. Its close must exceed the highest high of the preceding 40 closed candles.
3. Enter at the following candle open. Planned risk 1.5% of current equity, exposure
   capped at 1x and rounded down through Binance quantity filters.
4. Initial long stop 1.5 × ATR14. Take 50% at 1R when quantity precision permits.
5. Ratchet a 4.5 × ATR trailing stop; after partial profit, also protect entry price.
6. Exit when the bullish regime ends. A 4% monthly loss breaker stands aside after
   triggering. This is not a guaranteed maximum loss: gaps and delayed checks matter.
7. No shorts, averaging down, live orders or automatic activation.

Round 1 leader: 40-bar breakout, 1.5 ATR stop, 4 ATR trail. Training profit **$44.20**,
14/24 profitable months, 8.90% drawdown. Round 2 changed the trail to 4.5 ATR:
training profit **$50.17**, still 14/24 profitable months, drawdown **9.58%**. More
profit came with slightly more drawdown and no monthly-frequency improvement. All
16 tested pullback candidates lost money during training; they were not promoted.

## Results for the new candidate

| Evaluation | Start → end equity | Net P/L | Profitable full months | Max drawdown | Worst full month | Closed trades / PF |
|---|---:|---:|---:|---:|---:|---:|
| Selection, 24 months | $200 → $250.17 | +$50.17 | 14/24 (58.3%) | 9.58% | -3.72% | 45 / 1.88 |
| Later year, fresh $200 | $200 → $205.55 | +$5.55 | 5/12 (41.7%) | 6.64% | -2.22% | 15 / 1.36 |
| Later year, double cost | $200 → $203.30 | +$3.30 | 5/12 (41.7%) | 7.58% | -2.40% | 15 / 1.20 |
| Continuous three years | $200 → $243.53 | +$43.53 | 17/36 (47.2%) | 9.58% | -3.72% | 64 / 1.49 |
| Three years, double cost | $200 → $230.03 | +$30.03 | 16/36 (44.4%) | 11.27% | -3.27% | 64 / 1.33 |
| Recent rolling three months | $200 → $202.57 | +$2.57 | 1/2 complete months | 3.14% | -2.24% | 5 / 1.34 |

All these candidate runs ended flat. Three-year fee/slippage allowance totaled $11.76;
funding was -$6.53. Four-hour return Sharpe was 0.80, not a forward income forecast.
Recent monthly dollar P/L: June partial $0; July -$4.48; August +$8.75; September
partial -$1.70. The recent gain came from only one winning trade and four losing trades.

## Same recent window and common cost assumptions

| Strategy/configuration | Ending equity | Net P/L | Max drawdown | Closed trades | Ending position |
|---|---:|---:|---:|---:|---|
| Live v6 settings, 15% risk / 6x cap | $149.62 | -$50.38 | 25.22% | 10 | Flat |
| Iteration #25, 8% risk / 4x cap | $160.53 | -$39.47 | 19.76% | 10 | Flat |
| Existing v6, 1.5% long risk / 1x cap | $182.94 | -$17.06 | 14.18% | 11 | Long 0.001 BTC |
| New breakout, 1.5% risk / 1x cap | $202.57 | +$2.57 | 3.14% | 5 | Flat |

The low-risk v6 comparison retains its original short sleeve; only long risk and
leverage cap are matched. Its ending equity includes $11.23 open net P/L, before any
future closing cost. Much of the loss reduction versus LIVE comes from less exposure.
The new rules helped in this recent sample, but do not dominate over all history:
low-risk v6 ended the full three years at **$279.23**, with **12.77%** drawdown,
**18/36** profitable months and a **-7.91%** worst month, versus the new strategy's
$243.53, 9.58%, 17/36 and -3.72%. Low-risk v6 includes $9.86 open net P/L and had
78 historical funding mark-price fallbacks. Neither reaches the monthly target.

These v6 and #25 figures differ from the earlier exact-settings comparison because
this study adds a common, more conservative execution-cost allowance. Costs can
change breaker timing and subsequent trades, so P/L is not simply the old result
minus an extra fee. No live parameters or positions were changed to run these tests.

## Small-account sensitivity: a material warning

The new candidate's later year returned +2.77% from a fresh $200, but only +0.06%
from $160 and **-2.60% from $240**. Carrying its training balance of $250.165992 into
that year produced **-$6.64**, ending at $243.529693, exactly reconciling the continuous
three-year result. BTC lot rounding changes partial-profit eligibility and therefore
breakeven management and later entries. Returns must not be scaled linearly from one
starting balance. This fragility is another reason to reject LIVE promotion.

## QA and evidence

- 11 new tests: parameter guards, regime/entry/exit rules, breaker and reentry guards,
  causal indicator preparation, bounded neighbor search, monthly ranking, next-open
  execution and deterministic Decimal reconciliation.
- The existing production parity suite passed: 4 tests, one existing timezone warning.
- Combined Lab and backtesting regression suite passed: 55 tests, one existing
  Starlette/httpx deprecation warning.
- Strict mypy passed for all four new Python modules. Ruff lint/format passed.
- The later-year replay repeated exactly; every run reconciled closed plus open P/L.
- No frontend or deployment code changed; Browser order-lifecycle/live QA was not
  claimed for an offline strategy. This hypothesis is not installed in the live bot.

Final machine-readable report:
`.lab-data/monthly-consistency/2026-09-06/artifacts/8d7f8d75fc630ad865ae05f75b733fee2f968fc02178abb9e2a9b4b5a3902842.json`.
It links the protocol, all training trials, selected parameters, full trade/equity
ledgers, comparisons, stress tests and capital sensitivities.
Code/evaluator hash: `146af1a98e9bb52901af0eca79f844a307f18280c6f591e991ba3749c0107195`.

## Next decision, not an automatic deployment

Keep this candidate as a research benchmark, not an income strategy. A subsequent
study should first address small-account partial-fill realism and missing historical
mark prices, then predeclare a genuinely different hypothesis and test forward without
repeatedly optimizing the same evaluation months. Raw-trade/order lifecycle checks,
liquidation and intrabar drawdown modeling, forward paper performance, implementation
parity and explicit approval remain gates. Lower losses are useful, but neither a
60% monthly hit rate nor a smooth historical chart guarantees positive future income.
