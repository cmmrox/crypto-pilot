# Incident — LIVE long entries never opened (2026-07-30, 2026-08-07)

## Summary

Every long entry attempted in LIVE failed. Two signals fired, both were lost, each to
a different defect in the long entry path. All four short-sleeve trades in the same
period executed and closed normally, which is why the failure stayed hidden: the
sleeve sizes by weight and never approaches the constraints that break the long.

The owner was paged only by a **downstream** alert four hours after each failure
("missed closed-candle decision"), never by the failure itself.

## Evidence

Read from the production `events`, `bot_runs`, `orders`, `trades`, and
`equity_snapshots` tables on the VPS, plus `docker inspect` and a strategy replay
against the stored candles.

| When (UTC) | What | SMS |
|---|---|---|
| 2026-07-30 12:00:22 | `EnterLong` filled 0.006 BTC @ 64796.30; protective stop rejected — `Precision is over the maximum defined for this asset` (stop `63061.4923581023983`, tick 0.10); emergency-flattened | none |
| 2026-07-30 16:00:11 | `Missed closed-candle decision` (previous 04:00, current 12:00) → safe mode | delivered |
| 2026-08-07 20:00:13 | `EnterLong` entry rejected — `Margin is insufficient.` (Binance -2019) | none |
| 2026-08-08 00:00:11 | `Missed closed-candle decision` (previous 12:00, current 20:00) → safe mode | delivered |

Replaying `trend_rider_v6_4h` release 6.0 against the stored candles at the
2026-08-07 16:00 decision bar reproduces the intent exactly:

```
EnterLong(stop_distance=1385.9964927046346, tp_levels=((1.0, 0.4),), reason='fresh regime')
```

Account state at that decision: `totalWalletBalance` 218.75276290,
`availableBalance` 218.75276290, flat, zero open orders, BTCUSDT leverage 6x,
isolated margin, `stepSize` 0.001, `tickSize` 0.10.

The 20:00 transaction rolled back whole: no `orders` row and no 20:00
`equity_snapshots` row exist. The 2026-08-07 06:18–06:26 backend restart
(`ExitCode=0`, `RestartCount=0`, not OOM) did not span a 4h close and is unrelated.

## Root causes

### 1. Sizing at the leverage cap is unplaceable (`-2019`)

`leverage_cap` is 6 and the account's configured leverage is also 6x, so a notional
capped at `equity × 6` needs `notional / 6` = **the entire wallet** as initial margin,
leaving nothing for the taker fee.

Observed: qty 0.020 → notional 1298.66 → margin 216.44 + fee 0.52 = **216.96, or
99.2% of the 218.75 wallet**. Binance rejected on the 0.8% remainder.

This is deterministic, not marginal. The cap binds whenever
`stop_distance < risk_pct / leverage_cap = 0.15 / 6 = 2.5%` of price. The failing
signal's stop was 2.13% of price. Most long signals are tighter than 2.5%, so most
long entries were unplaceable.

### 2. Protective stop and TP1 prices were never rounded to tick (`-1111`)

`stop_distance` is a float, so `execution_price - stop_distance` lands on sub-tick
precision and reached the exchange unrounded. `round_price` was applied in
`move_long_stop` and in `run_execution_self_check` — but not on the entry path. The
deployment-day self-check therefore passed with rounded prices while production sent
unrounded ones, giving false confidence.

### 3. The real failure was silent

`_drive_bot` recorded a `bot_drive_failed` event but never called `notify_event`. The
handler's `session.rollback()` also discards `run.last_evaluated_candle_at`, so the
decision cursor legitimately does not advance; the missed-decision guard then fires
correctly at the *next* close. The guard was a true positive both times — it was
reporting a real missed decision caused by defects 1 and 2, one candle late, with a
message naming neither.

## Fixes

- `app/risk/sizing.py` — new `margin_capped_qty`, applied in `size_long` and
  `size_short`. Reduces quantity so `initial margin + taker fee` fits inside
  `availableBalance` less a 2% buffer (`MARGIN_SAFETY_BUFFER`,
  `TAKER_FEE_RATE` 0.0005 taken conservatively). It only ever lowers quantity.
- `app/bot/service.py` — threads `available_margin=acct.available` into both entry
  paths, applies the clamp to the inline short sizing, and rounds `stop_price` and
  `tp1_price` with `round_price(..., filters.tick_size)`.
- `app/bot/ingest.py` — `_notify_drive_failure` pages the owner from both the generic
  and `ProtectiveStopFailed` handlers, carrying the real exchange reason.
- `app/bot/deadman_monitor.py` — repaired a pre-existing `mypy` `no-any-return`
  failure that was already red on `1ba2514`, unrelated to this incident.

`leverage_cap` and `long_risk_pct` are unchanged: the approved profile in
`ARCHITECTURE.md §8.7` is untouched. The clamp is an execution-placeability
constraint, not a risk-policy change. `research/backtests/final_composite.py` models
no leverage or margin, and the parity suite asserts the equity curve and signals
rather than sized quantity, so parity is unaffected.

## Verification

Replaying the failed 2026-08-07 decision through the fixed sizing:

| | before | after |
|---|---|---|
| qty | 0.020 (rejected) | 0.019 |
| notional | 1298.66 | 1233.73 |
| initial margin + fee | 216.96 | 206.11 |
| headroom vs 218.75 available | 1.79 (0.8%) | **12.64 (5.8%)** |
| stop / TP1 submitted | `63546.9035072953654` (-1111) | `63546.90` / `66318.90` |

Effective per-trade risk on that signal moves from 12.67% to 12.04% of equity — a 5%
size reduction. The 15% target was already unreachable whenever the leverage cap
binds; that is inherent to the approved profile and not changed here.

Gates run on `backend/`:

- `pytest` — 245 passed, 3 skipped
- `pytest tests/parity` — 4 passed
- `ruff check app tests`, `ruff format --check app tests` — clean
- `mypy app` — 81 files, no issues
- `lint-imports` — 2 contracts kept

New regression tests fail without their fix (verified by reverting each):

- `test_size_long_reserves_margin_for_fees_at_the_leverage_cap`
- `test_size_long_margin_clamp_is_inert_when_margin_is_ample`
- `test_size_long_without_available_margin_cannot_size`
- `test_long_entry_submits_tick_aligned_stop_and_take_profit`
- `test_closed_candle_failure_notifies_owner_with_the_real_error`

## Not addressed

- **`set_leverage` is never called.** Sizing assumes the account's leverage equals
  `leverage_cap`. It is 6x today and the deployment report verified it, but nothing in
  the application asserts or sets it; a manual change on Binance would silently
  re-break sizing.
- **A failed evaluation still costs the next candle.** Safe mode plus a non-advancing
  cursor means one transient rejection blocks entries until the owner restarts. That
  is the intended conservative design; it is now at least paged immediately and with
  the real reason.
- The two lost signals cannot be recovered. The 2026-08-07 long lapsed — replaying the
  20:00 bar returns no intent.
