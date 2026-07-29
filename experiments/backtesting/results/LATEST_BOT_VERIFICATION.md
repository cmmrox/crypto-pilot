# Trend Rider v6 — application execution verification

**Verification date:** 2026-07-29 Asia/Colombo
**Application revision:** `62ec282ab7a730eb5c8f346b7e20628e48c85439`
**Scope:** Binance DEMO only; no LIVE order was authorized or attempted.

## Verdict

The bot is correctly configured for Binance DEMO and the configured strategy
profile matches the replay. Deterministic plugin/reference equivalence, runtime
capability audit, real DEMO order mechanics, database persistence, and cleanup all
pass. DEMO bot run `19` is running to begin the required soak.

This does not authorize LIVE trading or guarantee that future DEMO/live results
will equal the historical simulation.

## Configuration and account checks

| Check | Result |
|---|---|
| Application health | PASS |
| Active environment | PASS — `DEMO` |
| Active strategy | PASS — `trend_rider_v6` (pre-contract-v2 persisted ID) |
| Long risk per trade | PASS — `15%` |
| Short sleeve / vol target | PASS — `75%` / `40%` |
| Leverage cap | PASS — `6x` |
| Stored Binance DEMO credentials | PASS — encrypted records present |
| Bot state before probe | PASS — stopped |
| Position/orders before probe | PASS — flat / zero |
| Closed local 4h candles | 6,770 including warmup/history backfill |
| Database migration | PASS — `e4f5a6b7c8d9` |
| Current bot run | PASS — `19`, running, DEMO |

The current DEMO BTCUSDT market quantity step is `0.0001`, tick size is `0.10`,
and minimum notional is `50`. The primary historical replay downloaded the LIVE
public BTCUSDT filter snapshot (`0.001` quantity step), so its filter assumptions
do not exactly match the current DEMO venue.

A replay using the current DEMO quantity filter ended at `$986.61`
(`+$886.61`, `+886.61%`) instead of `$884.37`. This demonstrates that venue
rounding changes the path and reinforces that final-profit equality alone is not
an equivalence test. This replay still uses LIVE public historical
candles and funding because it is not a reconstruction of a three-year DEMO
order book.

## Controlled DEMO execution probe

The probe refused non-DEMO execution and required a flat account with zero open
orders. It then placed minimum-size long and short market round trips and ran
unconditional cancel/flatten cleanup.

| Direction/path | Requested quantity | Result | Flat afterward |
|---|---:|---:|---:|
| Long market fill/query | `0.0009 BTC` | PASS | PASS |
| Protective algo stop + replacement | `0.0009 BTC` | PASS | PASS |
| Short open/increase/reduce | `0.0009 BTC` steps | PASS | PASS |
| Actual `OrderManager` + database sync | `0.0009 BTC` | PASS | PASS |

Final cleanup: position flat, zero open orders.

Binance DEMO returned a filled market order with `avgPrice=0`; the adapter now
queries order truth and account trades and persists a non-zero weighted fill
price. Binance also rejected futures `STOP_MARKET` on the standard endpoint; the
adapter now uses the documented Algo Order API and combines regular and algo
orders for query, cancel, cancel-all, and reconciliation.

## Backtest-to-bot equivalence gate

| Required behavior | Verified bot |
|---|---|
| All intent types | PASS |
| TP1 fill state and remaining quantity | PASS |
| Highest-high runner stop ratchet | PASS |
| Short sleeve resize with >20% guard | PASS |
| Independent persisted monthly breakers | PASS |
| Exact order/fill/fee/PnL/funding sync | PASS |
| Stop replace/cancel via Binance Algo API | PASS |
| Safe-mode management of open positions | PASS |
| Full-history signal calculation and next-open mark sizing | PASS |
| Public-filter plugin/reference replay | PASS — 106/106 trades |
| DEMO-filter plugin/reference replay | PASS — 105/105 trades |

Automated verification: formatting and lint pass, strict mypy passes, both import
contracts pass, backend `219 passed / 3 credential-env tests skipped`, lab `7
passed`, and the live-path audit passes.

## Profit interpretation

The separate historical replay produced `$884.37` final marked equity from `$100`
(`+$784.37`) over the tested three-year window, with a `-47.01%` maximum drawdown.
For the filter profile the current DEMO venue reports, the historical replay
produced `$986.61` final marked equity from `$100` (`+$886.61`) with a `−47.65%`
maximum drawdown. The bot is decision-equivalent under the replay model, but the
actual DEMO account has a different starting balance and starts now, not three
years ago. Absolute future profit will therefore not equal that historical dollar
number. A four-week DEMO soak is still mandatory.
