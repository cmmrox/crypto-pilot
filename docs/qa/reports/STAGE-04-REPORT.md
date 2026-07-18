# Stage 4 — Risk & Execution Engines — Report

**Status:** ✅ COMPLETE — QA gate passed (live DEMO validated). **Date:** 2026-07-18.
**This is the "connect to Binance DEMO and trade" milestone.**

## Scope shipped

Intents become real (DEMO) orders, safely.

- **Risk engine** (`risk/sizing.py`, `risk/breakers.py`): long sizing (risk % ÷ stop
  distance, leverage-capped at 3×), short sleeve sizing (weight × min(1, volT/realized),
  crash-shrink verified), independent long/short −4% monthly breakers. All Decimal.
- **Exchange filters** (`execution/filters.py`): lot/price rounding + min-notional
  against the real BTCUSDT DEMO filters.
- **Exchange abstraction** (`execution/exchange.py`): `Exchange` protocol + production
  `BinanceExchange` adapter (signed account/order endpoints) + `FakeExchange` (tests).
- **OrderManager** (`execution/orders.py`): MARKET entry + STOP_MARKET + LIMIT TP1 for
  longs; MARKET-only short (no price stop by design); flatten; kill switch. Idempotent
  client order IDs; persists trades + orders + events.
- **Reconciler** (`execution/reconcile.py`): expected-vs-exchange position comparison.
- **Execution service** (`services/execution_service.py`): DB creds → Exchange +
  OrderManager (the seam the Stage 5 bot loop uses).
- **Ops API** (`api/ops.py`): kill switch + DEMO-only self-check round-trip.

## Live DEMO validation (the headline)

Against the **real Binance testnet** (account funded 5000 USDT):

| Check | Result |
|---|---|
| Authenticated account read | ✅ balance/positions/filters |
| Live long round-trip (entry → verify → reconcile → flatten) | ✅ |
| Live short round-trip (sleeve mechanics) | ✅ |
| Self-check round-trip through the full deployed stack (UI creds → API → exchange → DB → ledger) | ✅ reconciled + flattened |
| Kill switch on the live account | ✅ |

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration, isolated DB) | ✅ 102 passed |
| live `@exchange` suite (real DEMO) | ✅ 3 passed |
| Playwright `stage-04` (live) | ✅ 4 passed |
| **Deterministic regression (stage 0–3 + stage-04 skipped)** | ✅ **50 passed** |

QA-4 cases: sizing math, leverage cap, vol-shrink, breakers, lot rounding, idempotent
order IDs, reconcile match/mismatch, flatten, kill, live round-trips, write-only creds.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | **Critical (infra)** | Backend tests shared the compose Postgres (5433/cryptopilot); `drop_all()` was wiping the live stack's owner/candles/events mid-run, causing intermittent login 401s and missing ingest events | Dedicated `cryptopilot_test` DB + a conftest guard that **refuses to run against the app DB**; CI updated |
| 2 | Major | Live/exchange tests running in the parallel pool interfered with deterministic tests (concurrent exchange hits, shared `system` events) | Tagged/serialized the live suite; run it in a separate pass (per QA strategy) |
| 3 | Minor | `db_session` fixture expired objects on commit → async lazy-load error | `expire_on_commit=False` |
| 4 | Minor | QA-2.03 assumed the newest `system` event is an ingest event (broke once self-check events existed) | Search for the ingest event specifically |
| 5 | Minor | QA-1.02 fixed throwaway email locked after repeated runs | Unique email per run |
| 6 | Minor | Leftover `"CRITICAL" if False` ternary; quoted type annotations | Cleaned |

No known open bugs.

## Review notes (loose coupling / quality)

- Dependency inversion at the trading boundary: everything depends on the `Exchange`
  protocol, enabling full test coverage via `FakeExchange` and live validation via
  `BinanceExchange` with no code change.
- All money Decimal end-to-end; quantities round DOWN to lot size; leverage capped;
  short has no price stop by validated design (asserted in tests).
- Idempotent client order IDs make retries safe.

## Sign-off

Stage 4 meets its exit criteria: scripted DEMO round-trips (long + short) reconcile
exactly, chaos cases pass, kill switch works live. **Stage 5 (Bot lifecycle & Overview)
needs no new keys — proceeding.** notify.lk (Stage 7) and Codex (Stage 8) will be
requested when reached.
