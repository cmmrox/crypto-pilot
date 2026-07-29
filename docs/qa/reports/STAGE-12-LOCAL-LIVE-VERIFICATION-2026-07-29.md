# Stage 12 Local LIVE Verification — 2026-07-29

## Decision

**LOCAL LIVE ACCEPTED; VPS DEPLOYMENT NOT STARTED.**

The local production-mode stack is configured for Binance LIVE and the active DEMO
strategy profile is applied without dilution:

- strategy: `trend_rider_v6_4h`, release 6.0
- market: BTCUSDT, closed 4-hour candles
- direction: native LONG + SHORT
- long risk setting: 15%
- leverage cap and Binance BTCUSDT leverage: 6x
- margin/account mode: isolated, one-way, single-asset
- long and short monthly loss breakers: 4% independently
- short sleeve: volatility-targeted, no price stop by approved design

The owner explicitly approved this aggressive profile for LIVE on 2026-07-29 and
waived the remaining Stage 11 calendar-soak duration. That waiver is authorization,
not evidence that four elapsed weeks were observed.

## Binance LIVE controls

The readiness gate re-read Binance immediately before the environment switch and
again after the verification trades. It confirmed:

- API key IP restriction enabled
- reading and Futures permissions enabled
- withdrawals and unrelated trading/transfer permissions disabled
- one-way and single-asset account modes
- BTCUSDT isolated margin and exactly 6x leverage
- flat BTCUSDT position and zero open regular/Algo orders

The implementation follows Binance's current USD-M Futures endpoints for
[position mode](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode),
[margin type](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type),
[leverage](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage),
[regular orders](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order), and
[Algo conditional orders](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order).

## Real-money verification

Four deliberately short-lived LIVE round trips were executed. Every operation used
the application exchange adapter and ended with an independent Binance read-back.

1. Minimum-size LONG, 0.001 BTC:
   MARKET entry filled; position reconciled; Algo STOP_MARKET and reduce-only LIMIT
   take-profit were visible; individual Algo cancellation worked; cancel-all and
   reduce-only exit worked.
2. Minimum-size SHORT, 0.001 BTC:
   MARKET entry filled; negative position reconciled; the approved stop-free short
   sleeve was covered reduce-only.
3. Managed LONG, 0.003 BTC:
   bot start reconciled; trade/order/fill state was persisted; full protective stop
   and partial reduce-only TP were visible at Binance; managed flatten closed the
   database trade and refreshed fees/PnL.
4. Managed SHORT, 0.001 BTC:
   trade/order/fill state was persisted; the application kill switch covered the
   position, closed the trade, and stopped the active LIVE bot run.

The two persisted checks recorded total execution fees of 0.25770520 USDT and
combined realized price PnL of -0.00039999 USDT. These are actual verification costs,
not simulated results.

Six expected operational SMS messages were delivered: bot start, long open, long
close, short open, short close, and kill switch.

## Final state

- local active environment: LIVE
- active strategy: `trend_rider_v6_4h`
- LIVE readiness: pass
- bot: stopped
- BTCUSDT position: flat
- Binance open regular/Algo orders: 0
- database open LIVE trades: 0
- local `/health`: HTTP 200, database `ok`
- `deploy/.env`: LIVE approval/key-verification flags enabled; mode 0600
- VPS: unchanged; deployment intentionally deferred until local handoff

## Defects corrected

- LIVE switching and bot start now re-read Binance account controls rather than
  trusting only static release flags.
- Readiness now requires the active strategy's exact leverage instead of a stale
  hard-coded 3x ceiling.
- LIVE self-check requires an explicit `LIVE-DUST` confirmation and guarantees
  cancellation/flatten cleanup on intermediate failure.
- The operations kill endpoint now closes the active bot run as well as exchange
  orders/positions.
- Trade-close and kill-switch SMS events are emitted.

## Regression evidence

- focused LIVE/order/lifecycle tests: 53 passed
- full backend non-exchange suite: 236 passed, 3 exchange-marked tests deselected
- strategy parity tests: included and passed
- mypy strict: 80 source files passed
- Ruff lint: passed
- Ruff format check: 129 files passed
- import-linter: 2 architecture contracts kept
- frontend ESLint + TypeScript: passed
- frontend production build: passed
- frontend unit tests: 4 passed
- isolated desktop/mobile Playwright regression: 135 passed, 5 deliberate
  single-project/real-SMS skips; the real LIVE SMS lifecycle was separately proven
  by the six delivered notifications above
- experiment lab: 15 tests passed; live-path audit passed every intent, breaker,
  reconciliation, fill-sync, persistence, and next-open check
- backend dependency audit: no known vulnerabilities
- rebuilt local production containers: backend healthy; frontend and Caddy running

The three exchange-marked automated tests were not rerun because the stronger
guarded LIVE verification above exercised the current production adapter against the
actual account. No unattended strategy execution was left running.

## Dependency-audit disposition

Frontend runtime dependencies are pinned to the latest available
`react-router-dom` 7.18.2. `npm audit --omit=dev` still reports
`GHSA-qwww-vcr4-c8h2`; the advisory itself states that it affects only unstable React
Server Components APIs. CryptoPilot is a static Vite SPA using browser routing and
does not import or expose React Server Components, server actions, or the affected
RSC request handler. The finding is therefore accepted as non-applicable until a
patched `react-router-dom` release exists. ESLint, TypeScript-ESLint, React Hooks
linting, and their transitive build-time dependencies were upgraded independently.
