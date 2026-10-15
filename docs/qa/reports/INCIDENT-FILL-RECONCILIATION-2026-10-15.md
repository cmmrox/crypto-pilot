# Stop-fill reconciliation race — 2026-10-15

## Finding and scope

A normal protective-stop fill was followed by an intrabar reconciliation mismatch.
The subsequent recovery synchronized the closed trade, but safe mode remained
latched and blocked a later entry signal. This is separate from the previously
fixed Binance timestamp rejection. The exact conflicting quantities were absent
from the historical event, so the REST snapshot race is an inference from the
incident sequence, reproduced deterministically against the original code.

## Correction

For an open tracked trade, synchronize order/fill/position snapshots up to three
times with 0.5-second pauses only after a mismatch. Repeat reads only; perform
existing close/protection/notification actions once after confirmation. The existing
trading mutex prevents concurrent entries while confirmation runs. Persistent
mismatches and verification failures retain the existing safe-mode behavior.
Existing safe mode is never cleared automatically. Untracked exposure still fails
reconciliation immediately. No strategy math, money arithmetic, exchange endpoints,
database schema, dependencies or deployment configuration defaults change.

The configuration bounds attempts to 1–5 and retry pauses to 0.1–2.0 seconds. Total
elapsed time also includes the existing Binance client's bounded request handling.
Audit events record recovered/unresolved status, attempt count, expected/actual
quantities, and allowlisted order statuses/filled quantities. Structured per-attempt
logs remain available if a subsequent verification error rolls back the transaction.

## Reproduction and focused validation

The regression returns a pre-fill STOP_MARKET order response, fills that order on
the fake exchange, and returns the post-fill position to the real worker. Against
the original code both initial cases failed: RUNNING incorrectly became SAFE_MODE,
and a previously safe run did not synchronize the closed trade in that recovery.

After the fix, 37 focused tests passed using disposable PostgreSQL and a deterministic
exchange adapter. Tests cover:

- Long and short stop fills, preserving both RUNNING and pre-existing SAFE_MODE.
- Partial and complete TP fills, correct remaining protection and one-time alerts.
- Duplicate recovery, without duplicate orders or trade-close events.
- Position-read lag recovering on the final permitted attempt.
- Persistent unexplained flat/reduced/reversed positions remaining in safe mode.
- Verification read failure preserving safe mode and existing exchange orders.
- Closed-candle evaluation using the same confirmation path.
- Already-matched snapshots incurring no retry wait or mismatch event.
- Configuration bounds preventing zero attempts, tight loops or excessive retries.
- Pending target/replacement-stop recovery submits once, even when subsequent
  confirmation retries after a fill (restart/ambiguous-submission boundary).

Command (from `backend/`):

```sh
.venv/bin/python -m pytest -q \
  tests/integration/test_reconciliation_race.py \
  tests/integration/test_atlas_protection_worker.py \
  tests/integration/test_trade_sync.py \
  tests/integration/test_atlas_recovery.py tests/unit/test_config.py
```

Ruff lint/format, strict mypy (99 source files), and all four import-boundary
contracts passed. Frontend lint/types, 12 unit tests, and production build passed.

The full local backend run passed 459 tests with three real-DEMO tests skipped
(credentials not configured). Two additional pending-order recovery regressions
then passed within the final 37-test focused run; application code was unchanged.
Combined coverage: execution 91.47%, risk 100%, strategies 95.91%, backend 77%.
The existing research oracle emitted its known pandas timezone-to-period warning.

The isolated production-image build and `restart-mid-trade.sh` health smoke passed.
This was an API/database restart smoke, not a real open-position restart; test mode
intentionally disables background ingest/protection startup. Desktop/mobile browser
regression passed 147 tests with 25 existing conditional skips. Browser tests use
synthetic public market data and make no real exchange orders.

## Release gates and limits

The exact PR head must pass the repository CI: backend full regression and strategy
parity, migrations, dependency/secrets audits, frontend checks, and desktop/mobile
Playwright. The PR checks are the authoritative evidence for those release gates.
The container health/restart smoke uses an isolated test database and the existing
synthetic public-market fixture, never the live account.

The race tests exercise production worker/synchronization code with controlled
exchange ordering; they do not claim reproduction of Binance's historical internal
timing or real-exchange fill certification. No LIVE orders or deployment are part
of this fix. Review approval and owner-authorized cutover remain separate, with a
fresh flat/order-free account check, backup/rollback preparation and post-deploy
health/reconciliation verification under the existing runbook.
