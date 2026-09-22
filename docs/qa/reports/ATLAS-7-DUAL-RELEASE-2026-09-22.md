# Atlas 7 Dual · 4h — release build and local DEMO QA — 22 September 2026

## Verdict

`atlas_dual_v1_4h` (display name **Atlas 7 Dual · 4h**, release 1.0) is built, tested and
running on a local DEMO stack. Every declared rule was exercised: both books trade, every
position carries a protective stop, stops ratchet one way, reversals flatten before they
flip, and the monthly breakers are set to twice the risk per trade. The owner selected the
**4% risk / 8% monthly breaker** profile on 2026-09-22.

This is release-readiness evidence, not a LIVE promotion. Production still runs
`trend_rider_refined_v1_4h`; nothing on the VPS was touched, no LIVE order was placed, and
no production setting was changed. The backtest expectation remains roughly six profitable
months in ten (`MONTHLY-INCOME-STRATEGY-RESEARCH-2026-09-22.md`), not every month.

## What the release adds to the system

The short book carries a price stop, which the existing intent vocabulary could not express.
Additive changes only; Trend Rider v6/v5.2/Trail behaviour is unchanged and its parity gate
stays green.

| Area | Change |
|---|---|
| `strategy_runtime.contracts` | New `EnterShortStop(stop_distance, tp_levels, reason)` intent. `EnterShort` (stop-free sleeve) untouched. `TradeState` gains `short_position`, `short_entry`, `short_stop`, `lowest_low`, `last_short_closed_at_ms`. |
| `strategy_runtime.atlas_dual` | The pure strategy: regime with a 1 ATR buffer, pullback and squeeze-breakout entries, 2.5 ATR stop both sides, 40% at 2R, 3 ATR trail from the extreme after the partial, regime exit. |
| `strategy_runtime.sizing` | `size_by_risk()` — the existing long formula, direction-free. `size_long()` delegates to it, so its behaviour and callers are unchanged. |
| `execution/orders.py` | `open_short_with_stop()` and `move_short_stop()`; the protected-entry path is shared by both sides, including the emergency flatten when a stop is rejected. `EmergencyExitRecord` carries the side. |
| `bot/service.py` | Dispatches `EnterShortStop`, routes `MoveStop` by side, tracks `lowest_low`, and refreshes the position after a flatten so a reversal can open in the same decision. |
| Database | Migration `c8d9e0f1a2b3`: `trades.lowest_low numeric(20,8) NULL` (mirror of `highest_high`). |
| Overview API/UI | `BreakerSnapshot.cap_pct` exposes the active release's monthly cap; the meter and label use it instead of a hardcoded 4%. |
| Docs | `ARCHITECTURE.md` §3 vocabulary and §8 deviation 3; `docs/strategies/NAMING.md` catalog row. |

## Three defects found and fixed during this build

1. **Reversal was exit-only.** The regime exit was evaluated before the opposite entry, so a
   sharp turn closed the position without opening the other side — the research engine
   reverses in one decision. Fixed by checking the qualifying opposite signal first;
   covered by `test_reversal_exits_then_enters_the_other_side` and by the replay's
   same-decision reversal assertion.
2. **A pullback could be traded repeatedly.** `_resumed()` recomputed from candles only, so
   after a stop-out the same old pullback re-armed on the very next candle (86 entry signals
   in 400 DEMO candles when scanned from a flat state). Fixed the way v6 does it: the
   pullback must have occurred after that book last closed, using
   `last_long_closed_at_ms` / `last_short_closed_at_ms`; covered by
   `test_pullback_is_traded_once_per_book`.
3. **The console hardcoded a 4% breaker.** The Overview meter divided the month-to-date
   drawdown by 0.04 and the label read "halts independently at −4.0% MTD" for every
   release, so an 8%-cap release would have shown a full meter at half its real budget.
   `BreakerSnapshot` now carries `cap_pct` from the active manifest, `_breaker_progress()`
   takes the cap, and the label renders it; regression:
   `test_overview_breaker_meter_uses_this_release_cap`. Verified live: both books report
   an 8.0% cap in the running DEMO console.

## Automated evidence

Backend, from `backend/`:

- `pytest` — **376 passed, 3 skipped** (the 3 skips are the credential-gated DEMO tests below).
  Includes the frozen Trend Rider parity suite, still green.
- New: `tests/unit/test_atlas_dual_strategy.py` (18), `tests/integration/test_atlas_dual_release.py`
  (9), and 3 short-with-stop cases in `tests/integration/test_orders.py`.
- `ruff check` / `ruff format --check` clean; `mypy app` — no issues in 92 files;
  import-linter — **4 contracts kept, 0 broken** (the new strategy stays pure);
  `python -m app.strategies validate` — 4 plugins, default unchanged.
- Frontend: `npm run lint` (eslint + tsc) and `npm run build` pass.

Chronological bot replay (`test_atlas_dual_release.py`): the real `BotService.evaluate_once`,
production `OrderManager` and production risk engine are driven over **1,233 committed
BTCUSDT 4h candles (2026-03-01 → 2026-09-22)**, decisions at each close, fills at the next
open, resting stop/TP resolved against the following candle (stop first on a tie). Asserted:

- both books traded; every trade has a protective stop **and** a take-profit order;
- no bar where an open position lacked an active stop;
- every bot entry occurred on a candle where the pure strategy asked for one;
- stop prices only rise for longs and only fall for shorts;
- one decision observation recorded per closed candle;
- at least one same-decision reversal flattened before opening the opposite side;
- the release never emits the stop-free sleeve intents (`EnterShort` / `ResizeShort`).

## Real Binance DEMO evidence

`tests/integration/test_live_demo.py` with the local DEMO keys: **3 passed** — account
readable, long round trip, short round trip against `demo-fapi.binance.com`.

Local stack (isolated Compose project `cryptopilot-qa`: its own Postgres, its own volumes,
Caddy on `127.0.0.1:8099`, fresh master key and JWT secret; the owner's `deploy/.env`
stack and database were not used):

- Backfilled **6,970 closed 4h candles** from DEMO, 0 gaps; worker heartbeat healthy,
  scheduler alive, next close reported correctly.
- Bot started on DEMO with `atlas_dual_v1_4h`; restart mid-run auto-resumed and re-evaluated
  the latest closed candle with entries blocked (startup recovery never chases a passed
  execution point).
- Decision telemetry records the new state fields and `NO_SIGNAL` outcomes.
- Owner console watch panel, live: Regime **Bull** (close 7.04% above the bull line at
  80,759), Pullback entry *Monitoring* (EMA20 83,394), Squeeze breakout *Not armed*.

**Signal drill (DEMO funds).** The 2026-09-18 00:00 candle produced `EnterLong ("fresh
regime")`. Driving that decision through the production path placed, on the real DEMO
exchange:

| Order | Detail |
|---|---|
| MARKET BUY | 0.1085 BTC filled @ 86,497.10 |
| STOP_MARKET SELL (reduce-only) | 0.1085 @ 84,718.80 — 2.5 ATR below the decision mark |
| LIMIT SELL (reduce-only) | 0.0434 (40%) @ 90,123.90 — exactly 2R |

Risk check: 192.95 USDT at risk = **3.95% of 4,888 USDT equity** (profile: 4%), notional
9,385 USDT = **1.92x** (cap 3x). The drill then flattened and cancelled everything: position
0, 0 open orders, DEMO balance 4,880.22 (about 8 USDT of fake funds spent on fees/spread).

UI acceptance (`qa/e2e/atlas-dual-strategy.spec.ts`, new, desktop + mobile) plus existing
strategy specs against the local stack: **34 passed** — library card with pinned parameters
and honest caveats, read-only parameters, API manifest, audited selection while stopped,
HTTP 409 refusal while running, and the watch panel's three rules with its disclaimer.
`stage-03` and `refined-strategy` pass unchanged, so the older releases still behave.

## Limits

- DEMO klines differ slightly from mainnet: a signal chosen from mainnet research did not
  reproduce on the DEMO series, so the drill used a DEMO-derived signal. Research numbers
  come from mainnet data.
- The plugin gates re-entry on "this book's last close", while the research engine consumed
  an armed pullback. Both stop immediate re-entry after a stop-out; they are not identical,
  so live trade counts may differ slightly from the backtest.
- Replay fills are simulated (next-open entries, stop-before-TP on ambiguous bars, no
  funding, no latency, no liquidity or liquidation model).
- One DEMO round trip is not a soak. No LIVE key was used and no LIVE gate was opened.
- The full Playwright regression needs the dedicated `CP_ENVIRONMENT=test` stack (which
  disables ingest by design); this run used a `development` stack so the real ingest loop
  and DEMO bot could run. Suites depending on OTP test mode were not part of this run.

## Recommended next steps

1. Run Atlas 7 Dual on DEMO unattended for a few weeks and compare its decisions with the
   research expectation before considering any LIVE change.
2. Keep production on `trend_rider_refined_v1_4h` until that DEMO evidence exists.
3. If LIVE is later chosen, pin risk 4% / breaker 8% explicitly and re-verify the account's
   minimum-lot sizing at the real balance (0.001 BTC steps dominate a ~190 USDT account).

## Reproduce

```sh
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m app.strategies validate
.venv/bin/python -m ruff check app tests && .venv/bin/python -m mypy app
# real DEMO adapter checks (needs DEMO keys in the environment)
set -a && . ../deploy/.env && set +a && .venv/bin/python -m pytest -q tests/integration/test_live_demo.py
# UI acceptance against a running stack
cd ../qa && CP_BASE_URL=http://localhost:8099 npx playwright test atlas-dual-strategy.spec.ts
```
