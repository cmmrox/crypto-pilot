# BTCUSDT 30-minute and 1-hour strategy research — 2026-07-29

## Decision

**Do not replace Trend Rider v6 with any tested 30-minute or 1-hour candidate.**

Every winner selected on older data failed a later evaluation window. The later-window
1x breaker diagnostics returned only **+12.10% at 30 minutes** and **+10.34% at 1
hour**, versus **+74.69%** for the 1x-cap Trend Rider v6 control. They also had
materially worse drawdowns and more losing months. No production plugin, scheduler
change, account connection, or order was created.

The work exceeded the requested 2,000 trials. It evaluated 43,728 planned
candidate/sleeve/composite configurations across five search phases, then repeated
16,364 trend configurations to add a strict 1x comparison:

- Initial 30-minute train/validation/holdout search: 3,000 candidates.
- 30-minute all-family asymmetric search: 6,998 sleeves + 5,184 composites.
- 30-minute trend-only asymmetric search: 2,998 sleeves + 5,184 composites.
- 1-hour all-family asymmetric search: 6,998 sleeves + 5,184 composites.
- 1-hour trend-only asymmetric search: 2,998 sleeves + 5,184 composites.

## Phase 1: initial 30-minute search

- Public Binance USD-M BTCUSDT 30-minute candles, closed bars only.
- Exact three-year evaluation window:
  `2023-07-29 04:30 UTC` through `2026-07-29 04:30 UTC`.
- 2,100 pre-period warm-up bars.
- 1,500 broad candidates plus 1,500 non-overlapping local refinements:
  **3,000 unique candidates**.
- Families: EMA trend, time-series momentum, Donchian breakout, ATR channel,
  regime-gated mean reversion, and multi-horizon momentum ensemble.
- First year = training; second year = validation; final year = locked holdout.
- Signal at a closed 30-minute candle; fill at the next 30-minute open.
- One-times-notional exposure, 0.05% cost per unit of turnover, and actual public
  historical funding.
- Deterministic seed `20260729`.
- Candle SHA-256:
  `aea93521c523cb1f07e6280faee268112c38b86b06785d1c9b1e370b64b98fb7`.
- Funding SHA-256:
  `bb2f925607a69d33da4dad51f925c4917a6687b38d653da1aac2edfe72adefa8`.

Binance's official API defines 30-minute USD-M klines and identifies bars by open time;
the funding-history endpoint supplies funding time, rate, and associated mark price:

- [Binance USD-M kline and funding API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

## Locked development winner

`mean_reversion(entry_z=2.0, exit_z=0.75, regime=672, window=240)`

Rules on closed 30-minute candles:

1. Compute a 240-bar rolling mean and standard deviation (five days), producing the
   close-price z-score.
2. Compute EMA(672), representing 14 days.
3. While flat, enter long when z-score is at or below -2.0 and close is at or above
   EMA(672).
4. While flat, enter short when z-score is at or above +2.0 and close is at or below
   EMA(672).
5. Exit a long when z-score rises to -0.75; exit a short when it falls to +0.75.
6. Execute every transition at the next 30-minute open.

This is the best *development* candidate, not an approved strategy.

| Window/control | Return | Sharpe | Max DD | Green/red/flat months | Worst month |
|---|---:|---:|---:|---:|---:|
| Train year | +15.07% | 1.99 | -4.72% | 9/1/3 | -0.88% |
| Validation year | +10.21% | 1.88 | -4.40% | 6/1/6 | -0.84% |
| **Untouched holdout year** | **-0.23%** | **0.00** | **-7.88%** | **6/3/4** | **-4.14%** |
| Full three years | +26.53% | 1.22 | -7.88% | 21/5/11 | -4.14% |
| Double-cost stress | +21.69% | 1.04 | -8.09% | 21/5/11 | -4.24% |
| One-extra-bar delay | +25.83% | 1.28 | -6.57% | 20/5/12 | -3.26% |
| Full with 4% monthly breaker | +20.34% | 1.03 | -5.62% | 21/5/11 | -4.26% |

Both sleeves made money over the full sample, but not enough to rescue the holdout:

- Long-only: +19.18%, -6.60% max drawdown, 27 entries.
- Short-only: +6.16%, -4.11% max drawdown, 12 entries.

The monthly breaker reduced drawdown but also cut total return because it crystallized
intramonth losses before later recoveries. It did not make every month profitable.

## Phases 2–5: older-three-year selection, latest-three-year evaluation

To test whether separate bull and bear sleeves generalized, the next searches used
approximately six years of history. The older three years (`2020-07-29` to
`2023-07-29`) selected long and short rules independently across three annual folds.
Only the locked composite was then evaluated from `2023-07-29` to `2026-07-29`.

Each timeframe was searched twice: all six signal families, then trend-only after the
all-family winner exposed a regime-dependent mean-reversion failure.

| Timeframe/family winner | Older-data return | Latest 3y return | Sharpe | Max DD | Green/red/flat |
|---|---:|---:|---:|---:|---:|
| 30m all-family mean reversion | +132.24% | **-12.35%** | -0.11 | -32.07% | 19/12/6 |
| 30m trend, Donchian long + momentum short | +407.60% | **-2.70%** | 0.19 | -49.34% | 18/19/0 |
| 1h all-family mean reversion | +82.90% | **-4.04%** | -0.01 | -23.36% | 18/11/8 |
| 1h trend, Donchian long + momentum short | +623.27% | **-27.74%** | 0.03 | -64.93% | 14/21/2 |

The large older-data trend returns used up to 2x notional and did not persist. A 4%
monthly breaker made the later trend windows positive, but that is a post-selection
diagnostic, not a newly untouched strategy. At a fair 1x exposure cap:

| Locked trend diagnostic | Latest 3y return | Sharpe | Max DD | Green/red/flat |
|---|---:|---:|---:|---:|
| 30m base | -0.52% | 0.12 | -30.96% | 19/18/0 |
| 30m + 4% breaker | +12.10% | 0.28 | -28.15% | 14/22/1 |
| 1h base | -31.32% | -0.15 | -48.09% | 15/21/1 |
| 1h + 4% breaker | +10.34% | 0.26 | -30.86% | 12/24/1 |

Neither timeframe produced a strategy that was profitable every month. The short
sleeves were especially unstable in the recent evaluation window, so neither candidate
demonstrated reliable bear-market execution after costs and funding.

## Trend Rider comparison

The current production-plugin replay was refreshed through `2026-07-29 00:00 UTC`,
with public historical funding and current exchange filters.

| Strategy/profile | Return | Sharpe | Max DD | Green/red/flat months |
|---|---:|---:|---:|---:|
| Trend Rider v6, current 15%-risk/6x-cap profile | **+784.51%** | 1.49 | -47.05% | 16/21/0 |
| Trend Rider v6, 2%-risk/1x-cap control | **+74.69%** | 1.01 | -16.58% | 22/14/1 |
| Initial 30-minute candidate, 1x | +26.53% | 1.22 | -7.88% | 21/5/11 |
| 30-minute candidate, unsafe 6x sensitivity | +203.60% | 1.14 | -41.79% | 20/6/11 |
| Locked 30m trend + breaker, 1x | +12.10% | 0.28 | -28.15% | 14/22/1 |
| Locked 1h trend + breaker, 1x | +10.34% | 0.26 | -30.86% | 12/24/1 |

The 6x sensitivity is not a deployable result: it lost **10.71%** in the untouched
year, suffered a **-24.93%** worst month, and the bar model does not simulate
liquidation. Increasing leverage does not turn the weak holdout into an edge.

The 15%/6x Trend Rider result is not directly risk-comparable to a 1x strategy. The
1x-cap control is the fairer comparison, and it still beat both intraday alternatives
on historical return and drawdown.

## Research context

The candidate families were based on published approaches, not copied profit claims
from anonymous users:

- Research documents both intraday momentum and reversal in cryptocurrency markets,
  motivating tests of both trend and mean-reversion families:
  [Wen, Bouri, Xu, and Zhao (2022)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253).
- A decade study of Bitcoin trend-following used SMA/EMA/DEMA and walk-forward
  selection, but explicitly assumed negligible costs and reported no robust intraday
  trend-following edge. That is why this run charged costs and kept a holdout:
  [Rozario et al. (2020)](https://arxiv.org/abs/2009.12155).
- Recent work proposes multi-horizon Donchian ensembles and volatility sizing, mainly
  across a broader crypto portfolio rather than one 30-minute BTC market:
  [Zarattini, Pagani, and Barbon](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907).
- Volatility scaling can help crypto momentum but does not systematically improve
  every strategy:
  [Habeli, Barakchian, and Motavasseli (2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5090097).

Published historical profitability is not evidence that another user's strategy will
remain profitable, and it cannot establish month-by-month guarantees.

## Why "every month profitable" is rejected as a release criterion

No locked strategy made every month profitable; the best-looking initial candidate had
21 green, 5 red, and 11 approximately flat months. Trend Rider also has red months.
Selecting a model because it makes all 36 historical months green would use the
evaluation sample as training data and reward overfitting.

An honest release gate should instead require:

- positive results across multiple independent windows;
- both long and short sleeves contributing after costs and funding;
- acceptable drawdown under cost/delay/parameter stress;
- a genuinely untouched holdout;
- forward DEMO evidence before any LIVE consideration.

All candidates fail the later-evaluation gate, so research stops before production
integration. The best strategy supported by this evidence remains Trend Rider v6, not
a new 30-minute or 1-hour replacement.

## Reproduction artifacts

- `results/runs/30m-20260729T053508Z/report.md`
- `results/runs/30m-20260729T053508Z/summary.json`
- `results/runs/30m-20260729T053508Z/monthly.csv`
- `results/runs/30m-20260729T053508Z/manifest.json`
- Six-year 30-minute all-family:
  `results/runs/30m-asymmetric-20260729T055250Z/`
- Six-year 30-minute trend-only with 1x controls:
  `results/runs/30m-asymmetric-trend-20260729T060256Z/`
- Six-year 1-hour all-family:
  `results/runs/1h-asymmetric-all-20260729T055938Z/`
- Six-year 1-hour trend-only with 1x controls:
  `results/runs/1h-asymmetric-trend-20260729T060334Z/`
- Current Trend Rider control:
  `results/runs/20260729T052808Z/`

Raw downloads and timestamped runs are intentionally Git-ignored. The reusable search
implementation lives in `src/trend_rider_lab/search_30m.py` and
`src/trend_rider_lab/asymmetric_30m.py`.
