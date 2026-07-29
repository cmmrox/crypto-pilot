# Trend Rider v6 runtime parity and DEMO verification

**Date:** 2026-07-29 Asia/Colombo
**Scope:** Binance DEMO only
**Branch:** `charithm/fix-trend-rider-runtime-parity`

## Outcome

The application plugin now matches the reference chronological replay under both
the public BTCUSDT and current Binance DEMO filter profiles. The real DEMO adapter
and the bot's database-backed `OrderManager` path were exercised with minimum-size
orders and unconditional cleanup. DEMO bot run `19` was started after every gate
passed.

LIVE trading was neither authorized nor attempted.

## Historical evidence

| Profile | Initial capital | Final equity | Closed trades | Profit | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Public current filter | $100 | $884.37 | 106 | +$784.37 | −47.01% |
| Current DEMO filter | $100 | $986.61 | 105 | +$886.61 | −47.65% |

The tested period is 2023-07-28 16:00 UTC through 2026-07-28 16:00 UTC, 6,577
closed 4h bars. The replay includes explicit fees and public historical funding.

Plugin/reference checks:

- exact side, entry time, exit time, and exit reason for every trade;
- identical long/short breaker trip counts;
- final-equity difference below `5e-13`;
- maximum per-trade numeric difference `1.36e-11`.

## Runtime corrections

- introduced strategy contract v2 with automatic discovery and canonical
  timeframe-qualified identity `trend_rider_v6_4h`;
- moved market/timeframe/history, risk policy, education, capabilities, and
  validation evidence into the immutable strategy-owned manifest;
- moved dashboard watch rules and their safety explanation behind the generic
  strategy inspection contract;
- made the public chronological replay execute the production plugin, retaining
  the reference engine only as a comparison oracle;
- removed the unused strategy registry table and duplicate risk settings;
- made market ingest, scheduler, bot sizing/breakers, overview, settings library,
  sidebar, and trade filters consume the active manifest;
- persisted remaining quantity, highest high, filled quantity, and average fill;
- synchronized regular orders, Algo conditional orders, fills, fees, realized
  PnL, and funding before reconciliation;
- implemented all strategy intents, independent monthly breakers, TP1 state,
  highest-high trailing stops, and short resize guard;
- preserved position management in safe mode while blocking new entries;
- loaded the complete three-year indicator history and sized at the next-open
  mark;
- recovered zero `avgPrice` market responses from order/account-trade truth;
- moved USD-M `STOP_MARKET` orders to Binance's Algo Order API and implemented
  combined open-order query, individual cancellation, cancel-all, and
  replace-before-cancel stop ratchets;
- bounded retries cover Binance's immediate post-placement consistency window.

## Verification

- Ruff format/lint: pass.
- Strict mypy: pass, 78 source files.
- Import contracts: 2 kept, 0 broken.
- Backend: 222 passed, 3 environment-variable live tests skipped.
- Backtesting lab: 7 passed.
- Static live-path audit: pass, no missing intent or state capability.
- Alembic: clean-database upgrade through `f5a6b7c8d9e0 (head)` passed.
- Application health: pass.
- Browser regression: 111 passed, 21 credential/state-gated skips. The full
  desktop/mobile suite passed against a fresh isolated database after exact
  active-state and async-load assertions replaced the ambiguous selector check.
- DEMO long entry/fill query/algo stop/TP/stop replacement/cleanup: pass.
- DEMO short open/increase/reduce/cover/cleanup: pass.
- DEMO `OrderManager` persistence, sync, exact money, close: pass.
- Final exchange state before bot start: flat, zero open orders.

## Remaining release gate

The four-week unattended DEMO soak required by Stage 11 starts with bot run `19`.
Until that completes without unexplained divergence, LIVE remains blocked. A
historical result is not a forecast or guaranteed return.
