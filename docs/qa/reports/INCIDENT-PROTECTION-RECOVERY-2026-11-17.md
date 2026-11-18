# Intrabar protection check latched safe mode on one Binance error — 2026-11-17

## Finding and scope

At 16:00:15 UTC on 2026-11-17, fifteen seconds after a 4h close and a funding
settlement, one pass of the 5-second intrabar protection check received an error
response from Binance on LIVE. The worker treated any failure as fatal: it entered
safe mode, sent one error SMS and blocked new entries. Every later pass succeeded,
but safe mode is never cleared automatically, so the bot stayed paused until the
owner restarted it. The same path had paused the bot on 2026-10-09.

There was no real mismatch. A read-only check the next day showed the exchange
position, the database trade and the resting protective stop all in agreement.
Safe mode blocks only new entries, so stop management continued throughout.

Three defects combined:

1. **No tolerance.** One failed pass of a check that repeats every 5 seconds
   latched safe mode, although the event text said "recovery will retry".
2. **No retry of server-side read errors.** The client retried network errors,
   429s and `-1021`, but raised an HTTP 5xx/408 response to a read at once. No
   transport, rate-limit or timestamp warning was logged at 16:00:15, so the
   failure was a single rejected HTTP response.
3. **Missing evidence.** The event and log kept only `error_type: BinanceError`,
   dropping the Binance status, code and endpoint. The exact response can
   therefore not be recovered for this incident.

## Correction

- **Client** (`execution/binance_client.py`): a read that returns HTTP 5xx or 408,
  or `-1001`, `-1006`, `-1007` or `-1008`, is resent freshly signed within the
  existing bounded retry budget with backoff and jitter. Binance's "execution
  status unknown" applies only to writes; writes keep the ambiguous-mutation path
  and are never resent. A read that stays failing after the retries, a network
  failure or a 429 carries `transient=True`; an IP ban (418) and business
  rejections do not. The final error now keeps the rate-limit status.
- **Protection worker** (`bot/protection.py`): a transient failure is tolerated
  for up to two consecutive passes, with a warning log and one `WARN` ledger row
  per streak and no SMS. The third consecutive failure enters safe mode with one
  SMS. A successful pass resets the streak. Safe mode stays immediate for a
  business rejection, an unexpected error, missing credentials, a reconciliation
  mismatch, or any failure after the pass placed or cancelled an order (the
  rollback could otherwise hide an exchange action). Existing safe mode is never
  cleared automatically.
- **Evidence:** the event and log now carry the error type, the exchange's message
  (truncated), Binance status and code, method + path only, whether the failure
  was transient, whether an order action was attempted, and the streak count.

The tolerance is safe because the protective orders rest on the exchange, and every
closed-candle decision reconciles afresh under the trading mutex before it can enter.
No strategy logic, money arithmetic, endpoint, schema, dependency or deployment
default changed. The business document requires safe mode on a reconciliation
mismatch, which is unchanged, so no §8 deviation is needed.

## Validation

Regressions were written first and failed against the original code (12 client
tests, 7 worker tests). They cover:

- Read retries for 503, 502, 408 `-1007`, 503 `-1008` and `-1001`, each resent with
  a fresh timestamp.
- Bounded persistent read failure marked transient with status, code and endpoint.
- Exhausted network failure marked transient; 401 `-2015` and 418 not transient
  and, for the 401, not retried.
- POST and DELETE server errors still raised as ambiguous after one attempt; a
  rate-limited write is not marked transient.
- One transient failure keeps the bot RUNNING with no SMS and one `WARN` row.
- Three consecutive failures enter SAFE_MODE with exactly one SMS.
- A successful pass resets the streak.
- Business rejection and unexpected errors still block entries at once.
- A failure after an order action blocks entries at once.
- The ledger payload is an allowlist with no signature, timestamp query, listen
  key or API-key header.

Commands (from `backend/`):

```sh
.venv/bin/python -m pytest -q tests/unit/test_binance_client.py \
  tests/integration/test_atlas_protection_worker.py   # 36 passed
.venv/bin/python -m pytest -q                         # 479 passed, 3 skipped
.venv/bin/python -m pytest -q tests/parity            # 3 passed
```

The three skips are the real-DEMO tests (credentials not configured). Ruff lint and
format, strict mypy (99 source files) and all four import-boundary contracts passed.
Browser regression does not apply: test mode disables the protection worker and no
API or UI changed.

## Follow-up

A write that returns HTTP 408 or `-1006`/`-1007` with a non-5xx status is still
raised as a plain rejection rather than an ambiguous mutation. It did not occur in
this incident and is left for a separate, order-path change.
