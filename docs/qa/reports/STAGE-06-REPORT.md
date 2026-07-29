# Stage 6 — Trades / Monthly / Events — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

Complete reconstructable history in the UI. (Events shipped in Stage 2 with its
payload drawer; this stage adds Trades + Monthly.)

- **Trades API** (`api/trades.py`): filterable list (side/environment/strategy/month/
  search), per-trade detail with linked orders, streamed CSV export (exact numeric
  formatting).
- **Monthly API** (`api/monthly.py`): calendar-month ledger (trades, realized P&L, fees,
  net), breaker status, 10%-of-net withdrawal allowance, idempotent manual mark-withdrawn
  (records an owner action; never moves funds).
- **Frontend Trades** (`views/Trades.tsx`): filter toolbar, reconciled table, per-trade
  drawer (round-trip facts + linked orders), authenticated CSV download, out-of-order
  response guard.
- **Frontend Monthly** (`views/Monthly.tsx`): ledger table, withdrawal-rule panel,
  guarded mark-withdrawn modal.

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration, isolated DB) | ✅ 116 passed |
| Playwright `stage-06` | ✅ 6 cases (desktop; the mutation case is desktop-only) |
| **Deterministic regression (all stages)** | ✅ **61 passed, 17 skipped** (live suites) |

QA-6 cases: trades list, side filter, drawer reconstructs linked orders, CSV export
download, monthly aggregation math (realized $150, net $141, withdrawable $14.10),
mark-withdrawn records + removes allowance (idempotent).

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Minor | `__import__("sqlalchemy")` hack in the trade search | Proper `String, cast` import |
| 2 | Minor | Out-of-order trade-filter responses could overwrite the list | Request-sequence guard (as in Events) |
| 3 | Minor | CSV endpoint returns text but `apiRequest` parsed JSON | Dedicated `getTradesCsv` text fetch |
| 4 | Minor | Mark-withdrawn E2E flaky: checked the button before the async ledger loaded; modal/row label collision; parallel mutation across projects | Wait for data load, scope confirm to the dialog, run the mutation case desktop-only + wait for the POST |

No known open bugs.

## Review notes (loose coupling / quality)

- Filter query composition is a single typed helper reused by list + CSV export.
- Money formatted from strings; CSV values are exact DB values; withdrawal is a manual,
  idempotent bookkeeping action that never moves funds (BSD scope boundary).
- Frontend guards against out-of-order responses; drawers/modals are keyboard-closable.

## Sign-off

Stage 6 meets its exit criteria: any trade is reconstructable in a few clicks, exports
match the DB, monthly math is correct. **Stage 7 (Notifier — notify.lk SMS) needs the
owner's notify.lk credentials + sender ID; I will request them before starting Stage 7.**

## 2026-07-29 pagination and performance hardening

- Trade History and Event Ledger now use server-backed pagination with a strict maximum
  of 50 rows, stable timestamp-plus-ID ordering, filtered totals, and shared accessible
  Previous/Next controls.
- Month filtering uses an index-friendly UTC date range. Matching composite indexes were
  applied through Alembic. Trade CSV export streams rows from the database.
- Search requests are debounced; paging Event Ledger no longer reloads market status.
  Route-level code splitting reduced the initial production bundle from 700.82 KB to
  257.38 KB and removed the oversized-chunk warning.
- Decimal display remains string-based, rounds without floating-point coercion, and uses
  standard negative-currency sign placement.
- Live Browser QA verified 50 rows on pages 1 and 2 of a 2,751-event ledger, responsive
  paging at 390 × 844, a responsive 3-row Trade List, and zero console errors. The live
  mobile pass found and fixed long event references clipping the viewport.
- Regression evidence: backend `226 passed, 3 deselected` (exchange-marked tests);
  focused pagination Playwright `4 passed` across Desktop Chrome and Pixel 5; frontend
  lint/type-check, 4 decimal tests, and production build passed.
