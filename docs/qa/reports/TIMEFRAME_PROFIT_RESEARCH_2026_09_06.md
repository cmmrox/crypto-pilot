# Timeframe and profit-focused strategy research — 6 September 2026

## Finding

A **higher-profit historical configuration** was found, but not a proven live upgrade.
The best profit-focused candidate remains **Trend Rider on 4h**, changing only its
long trailing distance from **4 ATR to 4.5 ATR**. All other effective live settings
remain unchanged, including 15% planned long risk, 6x leverage cap, 2.5 ATR initial
stop, 40% first profit-taking at 1R, independent 4% monthly breakers and the original
stop-free short sleeve. This is a parameter candidate, not a new production release.

On a continuous $200 account, September 2023–August 2026, it ended at **$1,643.19**
versus **$1,391.92** for the live configuration: **$251.27 more net profit**, approximately
21.1% more than the baseline net profit. However, the candidate's worst month and
later-year performance were worse. **Do not activate it automatically.**

## Protocol and scope

- Same three-year window for every run: 2023-09-01 00:00 UTC to 2026-09-01 00:00 UTC,
  end exclusive. Initial equity $200; profits remain in the account; no withdrawals.
- First 24 months select parameters. Candidates are locked before evaluating the
  later 12 months. Later-year standalone runs each start flat with $200; continuous
  three-year runs retain equity and positions through the year boundary.
- The historical period was already exposed to earlier research. These are
  **retrospective validation results**, not genuinely untouched out-of-sample evidence.
- Primary search: 57 configurations on 30m, 1h and 4h, plus six training-only neighbors.
  Families: v6 trend/pullback, a new completed-4h entry-confirmation variant, and the
  previously developed long-only breakout hypothesis at comparable aggressive risk.
- Primary ranking prefers profitable training years, >=30 closed trades, drawdown
  <=45%, and worst month >=-15%, then maximizes net profit. The 30m/1h leaders did
  not clear all training requirements; they were still reported rather than hidden.
- Supplementary search: 12 combinations of initial stop and partial-profit fraction
  at the original live risk, then four exit neighbors. Selection maximizes training
  profit with drawdown no worse than the live training baseline. No leverage/risk
  increase, breaker relaxation or validation-result feedback selects its winner.
- Total: **79 training trial runs**, including some repeated configurations between
  the two studies. Additional baseline, validation, stress and repeat runs are not
  counted as new optimization configurations.
- Fee plus execution allowance: 0.06% per side; stress 0.12%. Historical funding is
  included. Fees are assumptions, not a verified current account fee tier.

Separating parameter selection from later evaluation and limiting repeated tuning
is consistent with [QuantConnect's walk-forward optimization guidance](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization).
This experiment does not claim that a repeatedly observed historical test set has
become untouched simply because the code uses a chronological split.

## Does changing only the timeframe help?

The same numerical live parameters were used on each interval. A 200-bar lookback
therefore covers different elapsed time; these are native-bar variants, not an
elapsed-time-normalized strategy. The separate 4h-confirmation family tests a slower
regime while using the lower-timeframe entry/management rules.

| Native timeframe, unchanged parameters | Ending equity | Net P/L | Drawdown | Closed trades | Profitable months |
|---|---:|---:|---:|---:|---:|
| 30m | $53.24 | -$146.76 | 80.29% | 417 | 4/36 |
| 1h | $48.59 | -$151.41 | 85.25% | 204 | 4/36 |
| 4h | $1,391.92 | +$1,191.92 | 46.54% | 110 | 14/36 |

Faster trading did not improve the tested live rules. It increased turnover and
changed the signal horizon; neither more trades nor a faster candle creates an edge.

## Selected optimized candidates

| Candidate | Ending equity | Net P/L | Drawdown | Worst month | Profitable months |
|---|---:|---:|---:|---:|---:|
| 30m, completed-4h confirmation | $135.76 | -$64.24 | 50.39% | -10.11% | 8/36 |
| 1h, completed-4h confirmation | $267.18 | +$67.18 | 68.09% | -9.72% | 11/36 |
| 4h, lower-risk training leader | $937.53 | +$737.53 | 26.65% | -11.80% | 18/36 |
| 4h, original live configuration | $1,391.92 | +$1,191.92 | 46.54% | -11.77% | 14/36 |
| **4h, profit-focused 4.5 ATR trail** | **$1,643.19** | **+$1,443.19** | **43.59%** | **-13.11%** | **15/36** |

The lower-risk 4h leader uses 8% risk, 4x cap and 30% first profit-taking, retaining
the original 2.5 ATR initial stop and 4 ATR trail. The selected 1h variant uses 15%
risk, 6x cap, 2 ATR initial stop, first target 1.5R and 5 ATR trail. The selected 30m
variant uses 8% risk, 4x cap, 3 ATR initial stop and 4 ATR trail. Full effective
parameters are stored in each replay artifact.

All configurations in these full-period comparison tables ended flat. Drawdown is
measured at candle closes and does not certify intrabar or liquidation survivability.

## Best historical-profit candidate versus live

| Metric | Live | 4.5 ATR trail |
|---|---:|---:|
| Net return over three years | +595.96% | +721.60% |
| Net profit factor | 1.37 | 1.45 |
| Daily-return Sharpe | 1.30 | 1.39 |
| Closed trades | 110 | 105 |
| Winning / losing trades | 38 / 72 | 36 / 69 |
| Fee/slippage allowance paid | $363.30 | $375.03 |
| Funding P/L | -$155.52 | -$165.36 |
| Ending equity with doubled execution costs | $975.83 | $1,317.23 |
| Drawdown with doubled execution costs | 52.38% | 44.62% |

The wider trail allows a winning long more room before the remaining position is
closed. It improved the large historical trend year, but also allowed worse losses
in some later conditions. It is not universally superior.

### Continuous-account yearly P/L

| Twelve-month block | Live | 4.5 ATR trail |
|---|---:|---:|
| Sep 2023–Aug 2024 | +$110.89 | +$123.39 |
| Sep 2024–Aug 2025 | +$1,526.46 | +$1,853.70 |
| Sep 2025–Aug 2026 | **-$445.42** | **-$533.90** |

The candidate also underperformed in a fresh-$200 later-year test: ending **$135.04**
versus live **$147.00**, with 41.35% versus 36.61% drawdown. Both had only 3/12
profitable months. Thus the full-period improvement did **not** translate into better
recent validation. The candidate's full-period profitable-month rate is only 41.7%,
still well below the owner's >60% objective.

The 1h confirmation candidate earned $28.48 in its fresh-$200 later-year test, but
lost $9.06 under doubled costs. Its full-period doubled-cost result also lost money.
That cost sensitivity and 68% full-period drawdown rule out treating it as a robust
alternative merely because one later-year result was positive.

## Data quality findings and limits

Fresh public Binance 30m and 1h datasets contain 53,008 and 26,704 candles respectively,
including 400 warmup bars, and 3,288 funding records each. The existing 4h dataset
was retained as the historical reference. Native candles disagreed in two windows:
2023-11-10 12:00–16:00 UTC and 2024-10-28 20:00–24:00 UTC.

Actual Binance 1-minute responses for those complete windows were fetched and
archived. Aggregating them reconciled four 30m bars, three 1h bars and two 4h bars.
Original datasets were not overwritten. Each derived dataset records original and
replacement values and its minute-source hashes. After reconciliation, all evaluation
30m bars aggregate exactly to the 1h and 4h OHLC values. This treats the minute data
as the common source for these conflicting windows; it is **not raw-trade proof**.

The reconciled live baseline is $1,391.92 rather than the earlier $1,392.10, a $0.18
difference caused by this explicit data reconciliation. All comparisons here use the
same reconciled market, not a mixture of repaired candidate data and old baseline data.
One invalid intermediate resampling attempt failed the aggregation gate before any
strategy testing; its hash is marked invalid in the reconciliation receipt.

These are actual Binance candles and funding with **simulated fills**, not account
trade history or tick/order-book replay. Historical funding mark prices were missing
for 78 applied events in the live full-period run and 81 in the wider-trail run; the
existing candle-price approximation was counted explicitly. Later-year runs had zero
such fallbacks. Current exchange filters are applied historically. Stops and monthly
breakers are not guaranteed loss ceilings. Slippage is an allowance, not a liquidity
model. No liquidation engine is present, so no survivability certification is made.

## Implementation and QA

- Research stays under `experiment_lab/research/`; new strategy logic is pure and
  reuses the existing abstract intents. No live registration, settings, orders, VPS
  deployment, credentials, LLM provider changes or automatic activation occurred.
- `timeframe_strategy.py`: causal completed-4h entry confirmation, preserving v6
  exits and the price-stop-free short sleeve. Its manifest is unverified/research-only.
- `timeframe_replay.py`: common Decimal engine, costs and funding, timeframe-correct
  interval Sharpe and common daily-return Sharpe for comparisons.
- `timeframe_study.py` and `profit_refinement.py`: bounded selection, saved protocols,
  individual results, hypotheses and locked later-year evaluation.
- `reconcile_candles.py`: complete-minute aggregation with original-source lineage.
- Fixed the existing offline replay's Binance `30m`/pandas month-end alias bug using
  an explicit minute duration for funding buckets. Regression was demonstrated failing
  first for 30m, while 1h/4h passed, then all three passed after the repair.
- **69 Lab/backtesting tests passed**, including 14 new timeframe/data/selection tests.
- **4 production parity tests passed**; the production v6/reference files are unchanged.
- Strict mypy passed for five added research modules; Ruff lint and formatting passed.
- Winning full replay repeated exactly, including a repeat after the final type-only
  reconciliation guard change. Closed plus open P/L reconciled within 1e-8 throughout.
- No UI changes: Browser/live-order QA was not claimed for this offline research.

## Evidence

Artifacts live under `.lab-data/timeframe-research/2026-09-06/artifacts/`:

- Reconciliation receipt: `02be3855086cea6ca4f4e4c3ce8f875d66084d06e9faf3183282742610e09c28`
- Timeframe report: `9af1a805a42e9987b6f6d307630c54bdaa525c0056dcae08a6566e8ec5a24d4c`
- Profit-refinement report: `c59c26355f53d8afa265f2dd2a90f458271b936ec3d47a041a32938d1f720bab`
- Final repeat, baseline stress and yearly verification: `229758e971f09b9cb762e0c8710975c97fb6400525d8f84cb5e0150cebe4a185`

These link effective parameters, training selection, monthly P/L, closed trades,
final-candidate equity curves, costs, funding, and run-specific code/data hashes.

## Conclusion

For this experiment, **4h remains the strongest timeframe**. The 4.5 ATR trail is the
strongest profit-focused *historical research candidate* found, not proof of higher
future profitability. Its worse later-year and worst-month results block a confident
LIVE recommendation. Further work should prioritize genuinely forward evaluation,
execution fidelity and performance across regimes, not endlessly optimize this same
three-year sample until the chart looks favorable. There is no passive-income or
profitable-month guarantee.
