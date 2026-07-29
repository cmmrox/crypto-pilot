# Trend Rider v6 — latest three-year evidence

**Run date:** 2026-07-29 Asia/Colombo
**Latest closed candle:** 2026-07-28 16:00 UTC
**Production source revision:** `62ec282ab7a730eb5c8f346b7e20628e48c85439`

## Answer

Trend Rider v6 was historically profitable in the tested three-year window. The
application's actual `trend_rider_v6_4h` plugin now reproduces the chronological
reference replay trade-for-trade under both the public-market and current Binance
DEMO filter profiles.

### Current application profile replay

The primary replay uses the current owner-approved settings: $100 initial capital,
15% long risk per trade, 6x leverage cap, 75% vol-scaled short sleeve, current
BTCUSDT exchange filters, explicit fees, and actual public funding history.

| Metric | Result |
|---|---:|
| Period | 2023-07-28 16:00 UTC → 2026-07-28 16:00 UTC |
| Closed 4h bars | 6,577 |
| Initial capital | $100.00 |
| Final marked equity | **$884.37** |
| Historical profit | **+$784.37** |
| Total return | **+784.37%** |
| CAGR | +106.76% |
| Maximum drawdown | **−47.01%** |
| Worst / best month | −10.96% / +105.70% |
| Closed trades | 106 |
| Win rate | 35.85% |
| Profit factor | 1.48 |
| Fees | $132.91 |
| Net funding | **−$81.18** |
| Green / red / flat months | 16 / 21 / 0 |
| Long / short breaker trips | 18 / 4 |
| Ending open position | none |

The account never reached zero in this OHLC replay, but this is not a Binance
liquidation-engine simulation. The equity curve peaked around $1,353.72 and later
drew down to the final $884.37; the result therefore includes a large giveback.

Primary artifacts:

- `results/runs/20260728T213731Z/report.md`
- `results/runs/20260728T213731Z/summary.json`
- `results/runs/20260728T213731Z/manifest.json`
- `results/runs/20260728T213731Z/equity.csv`
- `results/runs/20260728T213731Z/trades.csv`
- `results/runs/20260728T213731Z/monthly.csv`

### Controls and benchmarks

| Evidence layer | $100 historical ending value | Meaning |
|---|---:|---|
| Current 15%/6x replay, actual funding | **$884.37** | Primary configured-profile result |
| Same replay, current DEMO quantity filter | $986.61 | Filter-control result; still LIVE historical market data |
| Same replay, funding disabled | $1,415.82 | Control that explains the older ~$1,330 claim |
| Production parity engine, frozen validated data | $304.45 | Reproduces the documented +204.5% strategy |
| Production parity engine, latest exact 3 years | $229.57 | Current-window normalized strategy result |
| Buy and hold, latest exact 3 years | $217.44 | Market benchmark |

The no-funding control is close to the later architecture note claiming approximately
$1,330. The authoritative business document explicitly says funding was not modeled,
so that note's phrase “funding included” is inconsistent with the evidence. Including
actual public funding reduced the current-profile ending equity by about $531.46 in
this path-dependent replay; it is not valid to subtract funding linearly from the
control because funding changes equity, later position sizes, breaker timing, and
minimum-notional eligibility.

## Application-plugin equivalence

The application plugin and reference engine were run over every one of the 6,577
period bars using the same account/fill model:

| Gate | Public filter profile | Current DEMO filter profile |
|---|---:|---:|
| Closed trades | 106 / 106 | 105 / 105 |
| Entry/exit structure | Exact | Exact |
| Long/short breaker trips | 18 / 4 | 18 / 6 |
| Final equity absolute difference | $0.000000000000389 | $0.000000000000419 |
| Maximum per-trade numeric difference | $0.0000000000136 | $0.0000000000136 |

The live-path audit now passes all required capabilities: all seven intent types,
persisted independent breakers, long entry/stop/TP/highest-high state, fill
synchronization, individual stop replacement, safe-mode position management,
closed-trade persistence, and close-to-next-open execution.

Therefore:

1. **The intended Trend Rider v6 strategy was profitable historically.**
2. **The current 15%/6x profile is extremely aggressive**; a roughly 47% historical
   drawdown means $100 could fall to about $53 from a prior peak, and future losses
   can be worse.
3. **$784.37 is historical simulated profit, not profit expected “today” or a
   guarantee.**
4. **Do not use this result to authorize LIVE trading.** Deterministic equivalence
   and controlled DEMO execution now pass, but the required four-week DEMO soak has
   only begun.
