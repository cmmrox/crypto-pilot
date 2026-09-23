# All packaged strategy paths — September 15, 2026 (Sri Lanka)

## Verdict and scope

Do not claim unconditional bot/backtest equivalence. This audit found and reproduced
two defects, corrected them locally, and extended regression coverage. Neither
explains the observed September LIVE long halt. No VPS change, deployment, order,
strategy switch, restart or breaker reset was performed during this audit.

Scope is the three installed production plugins, not arbitrary Lab experiments,
experimental intraday strategies or every frozen research variant. TradingView's
chart model and the manual snapshot companion are not execution parity oracles.
The snapshot companion deliberately cannot generate trades and expires its supplied
account state. Its absence of eligible labels is not proof of a broken bot.

## Defects reproduced and local corrections

1. **Atlas 5.2 prepared-path short leakage.** `on_candle()` filtered short intents,
   but inherited `on_prepared_frame()` did not. A replay invoking the optimized
   entrypoint on that plugin could trade shorts while the actual bot would not.
   `test_public_and_prepared_paths_agree` failed with public `[]` versus prepared
   `EnterShort(weight=0.75, ...)` on a declining market. Moving the filtering
   override to `on_prepared_frame()` makes both entrypoints enforce long-only.
   This is a demonstrated adapter defect, not proof that a particular prior
   published Atlas 5.2 return was calculated through the faulty entrypoint.
2. **Monthly halt crossed account environments.** `_breaker_event_exists()` looked
   up only book/month, so a DEMO event could halt LIVE or vice versa. A real-Postgres
   regression failed with LIVE halted by a DEMO BotRun event. The lookup now joins
   the event's existing `bot_run_id` to its environment. Existing same-environment
   halts remain effective across restarts and strategy selections. Unattributable
   legacy events remain fail-closed. No schema migration or historical event rewrite.

These fixes are in the local workspace only. Production remains at `e0bf690`.
Its active original/refined strategy public decision math is unchanged by the
Atlas 5.2 correction. The September breaker references LIVE run 12, so environment
scoping preserves that halt. Neither correction is a reason to open a trade now.

## Three-year chronological entrypoint comparison

Dataset: the latest 6,770 closed BTCUSDT 4h bars exported from production, including
200 warm-up bars. Replay execution range: 2023-09-15 16:00 through 2026-09-14
12:00 UTC. Each chronological state was passed to both the production public
`on_candle()` and the selected plugin's prepared-frame entrypoint. Both use the
same underlying strategy math; this checks adapter/state consistency, not a second
independent financial model. Separate frozen-reference parity tests also passed.

| Strategy | Release | Decisions checked | Mismatches after fix | Closed modeled trades |
|---|---|---:|---:|---|
| Atlas 5.2 · 4h | 5.2 | 6,570 | 0 | 65 longs, zero shorts |
| Atlas 6 · 4h | 6.0 | 6,570 | 0 | 64 longs, 50 shorts |
| Atlas 6 Trail · 4h | 1.0 | 6,570 | 0 | 60 longs, 50 shorts |

For each strategy the resulting entire trade and equity DataFrames matched exactly
between public-entrypoint and prepared-entrypoint runs. Total: **19,710 decisions**.
Coverage includes entries, regime exits, long stop ratchets and short resizing
intents. Original and refined produced 416 and 413 MoveStop intents respectively;
the long-only plugin produced no short-entry or resize intents after correction.

This controlled adapter comparison uses the same live filter snapshot, 200 USDT
initial equity, default replay costs, and monthly breakers in both paths. Historical
funding is explicitly disabled in both runs because a complete funding dataset was
not downloaded for this audit. Do not use its ending equity as a complete performance
estimate or strategy ranking. It does not replace the funded September comparison
in `LIVE-STRATEGY-AUDIT-2026-09-14.md`.

Reproducible local evidence is under `.artifacts/strategy-audit-2026-09-15/`:
`all_strategies.py`, `all_strategies_results.json`, and allowlisted live/exchange
exports. These are untracked account evidence, not secrets or committed fixtures.

## Actual bot path versus simulation

The integration tests exercise actual BotService, SQLAlchemy persistence and
OrderManager against a fake exchange with a disposable PostgreSQL database.
For all three plugins they verify selected release identity, long entry and
protective-order persistence, duplicate-candle rejection, filled 40% TP1 leaving
60%, and the exact tick-rounded stop ratchet while in safe mode. They also verify
short execution for v6/refined and no short position for long-only v5.2.

Existing lifecycle/execution regression covers reconciliation, missing candle
protection, independent monthly halts, exchange fill synchronization, emergency
handling, stop replacement, and short sizing/management. A passing mock-exchange
suite does not certify a future Binance order will fill or a network will respond.

Material distinctions retained:

- Bot acts after a closed candle using the available exchange mark and actual
  fills; OHLC replay models next-open execution. Entry/exit prices can differ.
- Stops/TP are resting exchange orders. OHLC replay resolves an ambiguous
  stop/TP dual-touch bar conservatively; it cannot reconstruct intrabar order.
- Live risk uses persisted account equity/sleeve state and latched monthly events;
  a new flat backtest starts its own account history. Same parameters alone do
  not imply the same position, loss history or next intent.
- Funding, fees, exchange filters, liquidity, minimum notional, margin, manual
  account changes and reconciliation can affect outcomes. There is no exact
  live-versus-OHLC PnL guarantee.
- Public/prepared agreement is not a full historical replay through BotService,
  database, OrderManager and recorded exchange fills for every bar. That broader
  end-to-end historical certification is not established by these results.

## Refreshed live evidence

VPS clock: September 14 approximately 18:36 UTC, already September 15 in Sri Lanka.
Health reports healthy database/worker/scheduler and no overdue ingest. Run 14 is
LIVE Atlas 6 Trail release 1.0, running without safe-mode/stop reason. Latest evaluated
candle opened September 14 12:00 UTC, closed 16:00 UTC; the next candle was not closed.
There are still 46 retained decision observations, all entries-allowed with the
long halt active and short halt inactive, matching the preceding exact-state audit.

Signed exchange reads: 190.18202024 USDT, flat, zero regular/conditional open orders,
and the same two September fills. The September 1 event belongs to LIVE run 12;
there is no evidence this month's long halt was caused by DEMO leakage. It follows
the configured four-percent monthly policy. No new missed BUY is established.

## Validation

- Before fixes: the long-only entrypoint test and cross-environment database test
  each failed on the relevant defect; both pass after correction.
- Full backend suite: see final result below. Three credential-gated live exchange
  tests are skipped; they must not be described as passed live acceptance.
- Final focused integration: **15 passed** (all-plugin execution plus account scoping
  and fail-closed legacy behavior).
- Backtesting suite: **18 passed**.
- Ruff lint and formatting: pass. Mypy: **91 source files**, no issues.
- Import boundaries: recorded below.
- No frontend changed; browser and Pine compilation were not run for this audit.
- Frozen research was not modified. Existing dirty production report, Pine files
  and account evidence were preserved. No commit or deployment is implied.

Final regression result: **341 passed, 3 skipped** in 45.91 seconds, including the
frozen-reference parity suite; one existing pandas timezone-to-period warning.
Import-linter: **4 contracts kept, 0 broken**. Final Ruff lint/format and
`git diff --check` passed. The stale virtualenv launcher paths were bypassed by
invoking mypy/import-linter through the current Python interpreter; no runtime
package or dependency changes were made.

## Subsequent deployment

Following explicit owner authorization, release `83ddaf8` was deployed September 15
at 03:37 UTC. The earlier local-only status above records the audit-time state;
deployment is now complete. Fresh post-cutover verification preserved LIVE run 14,
its active refined strategy and September long halt. See
`PRODUCTION-STRATEGY-FIX-2026-09-15.md` for image identity, backup, rollback and
verification evidence.
