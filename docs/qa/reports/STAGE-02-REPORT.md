# Stage 2 — Market Data & Scheduler — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

The bot's heartbeat: real Binance DEMO candle ingest, 4h scheduling, connection
health, the event ledger, and encrypted API-credential entry.

**Note on credentials:** Binance **market data is public**, so Stage 2 was built and
tested end-to-end against the real DEMO endpoint (`demo-fapi.binance.com`) **without**
an API key. The key/secret is only needed for account/trading endpoints (Stages 4–5).
The credential-entry UI + encrypted storage + public connection test are complete now;
the authenticated account test path is wired and will be validated when keys arrive.

- **BinanceClient** (`execution/binance_client.py`): public REST (klines, exchangeInfo,
  time), HMAC-SHA256 signing (verified against Binance's canonical vector via openssl),
  DEMO/LIVE base-URL switching, exponential backoff + jitter, 429/418 handling, clock-drift.
- **Candle service** (`execution/candles.py`): REST backfill, closed-only idempotent
  upsert (on-conflict), gap detection, latest-open-time.
- **Scheduler** (`bot/scheduler.py`): pure UTC 4h close/next-close math + dead-man tracker.
- **Ingest service** (`bot/ingest.py`): backfills on startup, wakes after each 4h close,
  records heartbeat + system event; survives transient errors.
- **Credentials** (`services/credentials.py`): AES-GCM write-only storage, masked hint.
- **APIs**: `/api/market/{status,candles,backfill}`, `/api/events` (level/category/search),
  `/api/settings/credentials` (PUT write-only, status, connection test).
- **Frontend**: Event ledger (connection status cards, filters, payload drawer) and
  Settings (credential entry + connection test), wired into the shell.

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean (2 contracts kept) |
| Schema drift | ✅ none (no model changes) |
| pytest | ✅ 58 passed, 74% coverage |
| frontend lint + build | ✅ clean |
| Playwright `stage-02` | ✅ 14 passed (7 cases × desktop + mobile) |
| **Full regression (stage 0+1+2)** | ✅ **44 passed** |
| **Live proof** | ✅ startup ingest pulled **500 real BTCUSDT 4h candles, 0 gaps** through the full Docker stack |

QA-2 cases: connection reachable, real candles with zero gaps, event ledger + payload
drawer, filters, manual ingest, write-only credentials (masked hint, secret never in
DOM), connection test.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Minor | Messy `retry_after` handling in the retry loop (`"x" in dir()`) | Clean exponential backoff with jitter |
| 2 | Minor | Signing unit test used a misremembered expected hash | Corrected to the openssl-verified canonical value; implementation was already correct |
| 3 | **Major** | Out-of-order filter responses could overwrite the events list (raced on slower mobile) | Request-sequence guard in the Events loader — only the latest result applies |
| 4 | Minor | Filter-reload race in E2E (clicked before list settled) | Wait for the filtered result before interacting |
| 5 | Minor | Stage-0 QA-0.05 flagged the legitimate `api_secret` write-only field name in the JS bundle | Narrowed to genuine server secrets; secret-value exposure covered by QA-2.06 |

No known open bugs.

## Review notes (loose coupling / quality)

- `BinanceClient` is injectable (client param) → services and tests mock at the boundary.
- Scheduler is pure functions (deterministic, fully unit-tested); ingest owns its task.
- Money is `Decimal`/`numeric(20,8)` from kline parse → DB; all datetimes UTC.
- Candle upsert is idempotent (safe re-backfill); ingest loop survives transient errors.
- Credentials strictly write-only (encrypted at rest, masked hint, never returned).

## Sign-off

Stage 2 meets its exit criteria: gap-free closed-candle ingest running unattended against
real DEMO data, connection health visible, full audit ledger, encrypted credential entry.
**Stage 3 (Strategy engine & parity) needs no external keys — proceeding.** The Binance
DEMO key/secret becomes required at Stage 4 (placing DEMO orders); I will request it then.
