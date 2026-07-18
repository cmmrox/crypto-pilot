# Stage 5 — Bot Lifecycle & Overview — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

The 24/7 loop with full owner control and the real-time Overview.

- **BotService** (`bot/service.py`): start (connect → reconcile → run), safe stop
  (leaves position), stop & close (flatten then stop), kill, safe mode. Reconcile
  before acting; reconcile mismatch → auto safe mode. State survives restarts (an open
  `bot_run` = running). `evaluate_once` ties **strategy → risk → execution** on a
  closed candle and writes an equity snapshot (FR-12).
- **4h-close loop**: the ingest service drives the bot on each real candle close
  (`_drive_bot`) when running and credentials exist — the live 24/7 loop.
- **Bot API** (`api/bot.py`): start / stop / stop-close / safe-mode / status.
- **Overview API** (`api/overview.py`): account truth (balance/equity/uPnL), live
  position (with `has_price_stop=false` for shorts), independent breakers from
  month-to-date realized P&L, equity curve from snapshots.
- **Frontend Overview** (`views/Overview.tsx`): stat cards, live position card with the
  no-price-stop short callout, breaker meters, guarded control modals (reconcile-and-
  start, safe stop, stop & close, typed-FLATTEN kill switch), safe-mode + unreachable
  banners, 4s polling, toasts. Reusable `ConfirmModal` (Escape-close, typed confirm).

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration, isolated DB) | ✅ 110 passed |
| Playwright `stage-05` (live, own pass) | ✅ 4 passed |
| Playwright `stage-04` (live, own pass) | ✅ 4 passed |
| **Deterministic regression (stage 0–3 + 4/5 skipped without keys)** | ✅ **50 passed, 16 skipped** |

QA-5 cases: start creates run + RUNNING, start-twice conflict, reconcile-mismatch →
safe mode, stop leaves position, stop & close flattens, safe mode blocks evaluate,
**evaluate opens a long on fresh regime (strategy→risk→execution)**, restart-resume,
Overview live render, guarded start/stop, typed-FLATTEN kill, cancel is safe.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | **Major** | `evaluate_once` passed a datetime where the strategy expects `open_time_ms` (int) | Convert candle open_time → ms int |
| 2 | Minor | `_drive_bot` referenced undefined `reason` in its except; stray type-ignores | Own error context; cleaned annotations |
| 3 | Minor | Unused `safeModeBot` import in the frontend | Removed |

No known open bugs.

## Design decision

Overview live updates use **4s polling**, not WebSocket (recorded in
`ARCHITECTURE.md §8`). For a 4h-decision bot this is real-time enough and far more
robust; WebSocket push is a future optimization.

## Review notes (loose coupling / quality)

- BotService depends on the `Exchange` protocol + OrderManager (testable with fakes,
  live-validated with Binance). Thin API routers.
- Reconcile-before-act and restart-resume are enforced in `start`/`status`.
- All money Decimal; every transition writes an audit event.

## Sign-off

Stage 5 meets its exit criteria: the bot runs unattended, all controls are guarded and
work against the live DEMO account, decisions tie strategy→risk→execution, and the
Overview reflects account truth. **Stage 6 (Trades / Monthly / Events surfaces) needs
no new keys — proceeding.**
