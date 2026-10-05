# Atlas 7 Dual release 1.2 execution contract

The approved Atlas 7 parameters and entry signals remain unchanged. The independent
reference is `experiments/monthly_income_research/src/mir/strategies.py:dual`, with
`final_eval.py:PARAMS`, and `src/mir/engine.py` for execution. `research/` is untouched.
Source and input SHA-256 values are pinned in
`backend/tests/fixtures/atlas7_execution_oracle.json` and checked by the regression.

| Rule | Release 1.2 |
|---|---|
| Market / decisions | BTCUSDT; completed 4h UTC candles only; 400-bar warmup |
| Regime | SMA200 plus/minus 1 ATR; EMA50 on the corresponding side of EMA200 |
| Entry | Fresh regime or EMA20 pullback resumption, or prior tight 24-bar range breakout; 360-bar 35% width threshold |
| Initial risk | 2.5 ATR distance from confirmed entry fill; 4% equity risk budget; 3x leverage cap; quantity rounded down |
| Stop trigger | `CONTRACT_PRICE` via USD-M conditional algo orders; reduce-only |
| TP1 | Confirmed entry +/- 2 times initial stop distance; floor(entry quantity * 0.4 / lot step) * lot step; reduce-only GTC limit |
| Partial fills | Breakeven waits for the entire planned positive TP1 quantity to fill |
| After TP1 | Stop ratchets to actual entry fill immediately on account recovery; remaining quantity protected; never widens |
| Trail | After TP1, highest high minus 3 ATR for long; lowest low plus 3 ATR for short; updated only at completed 4h candles |
| Zero-lot TP1 | No exchange TP order or partial sale. Persist a virtual target; its touch enables the next completed candle's trail, matching MIR. No immediate breakeven without a sale |
| Other exits | Buffered regime exit, reversal, independent 8% monthly long/short breaker |
| Breaker accounting | Closed-candle traded-price valuation; absolute per-book net realized P&L, fees, funding and unrealized value retain attribution after an intrabar close; explicit month-start equity baseline |

Real market orders execute at the first available exchange price after the completed
candle. They cannot guarantee the backtest's exact next-open price, zero latency,
liquidity or historical profitability. Tick rounding is an exchange constraint.
The one-hour historical oracle uses stop-first ordering if both levels occur in the
same bar. Live recovery uses actual exchange fills and event ordering, not that
historical assumption.

## Timing, recovery and concurrency

Finalized Binance kline events wake ingest immediately. REST starts at close +1s,
retries if the final candle is absent, and repairs missing candles even beyond the
last 500 bars. Finalized symbol, interval, duration and UTC alignment are validated.
Incomplete/future candles are discarded. The durable candle cursor prevents duplicate
decisions. Startup/reconnect manage existing positions without chasing old entries;
entries more than 60 seconds after the close are blocked. A missed decision enters
safe mode; history repair does not pretend missed live fills happened.

User-stream ORDER_TRADE_UPDATE, ACCOUNT_UPDATE and ALGO_UPDATE events wake account
recovery. Websocket messages never determine quantities by themselves. REST order,
fill and position truth determines the result, with recovery every five seconds if
events are absent, duplicated, delayed or reordered. Listen keys are renewed every
25 minutes and recreated on expiry/reconnect. Credentials and stream URLs are never
logged. A stopped bot does not resume position management automatically.

One backend worker is required, as in the existing deployment. Lifecycle controls,
credential/environment/strategy changes, account recovery and candle execution share
a mutex held through database commit/rollback. Slow read-only credential tests do not
hold the trading mutex.

Replacement stops are recorded as durable PENDING intents before submission, then
confirmed before retiring old protection. Recovery queries the same client ID before
any retry. An accepted replacement is recovered after a crash; cancel/fill races use
exchange truth. A crossed ratchet (-2021) closes the remaining quantity reduce-only.
Cancelled protection is restored from the last known ratchet, without widening it.
Entry and initial stop records survive a later TP rejection; the bot enters safe mode
and preserves exchange protection. Pending TP placement is recovered by client ID.

## Console truth

Overview shows confirmed current stop, quantity, trigger source and status; original
stop; TP1 target, planned and filled quantity, percentage and status; and exit stage.
Archived TP statuses are labelled recorded. Missing/unconfirmed required protection
produces a warning, including for Atlas shorts. Trades show linked order prices,
quantities, average fills and timestamps. Older size-managed short strategies retain
their stop-free policy and callout.

## Compatibility and release boundary

ExecutionSpec defaults preserve older releases. New Atlas entries are tagged 1.2.
Existing Atlas 1.1 positions retain their mark-price stops and original management
policy; this patch does not silently reprice or adopt a live carried trade. The
production cutover must wait for a flat, order-free account and owner release approval.
Local software verification does not replace a dedicated flat-DEMO exchange lifecycle
check or production monitoring. See `deploy/atlas7-release-1.2.md`.
