# Database Architecture — PostgreSQL 16

Implements BSD §9. PostgreSQL is the **single source of truth** for configuration,
audit and history; the **Binance account** is the source of truth for live portfolio
state (balance/positions/income) — the DB records it, never invents it.

## Conventions (non-negotiable)

- All timestamps `timestamptz`, always UTC. Column suffix `_at`.
- All prices/quantities/money `numeric(20,8)`. **Never float.** In Python: `Decimal`.
- Every table: `id bigint generated always as identity primary key`, `created_at timestamptz not null default now()`.
- Migrations: Alembic, one revision per change, reversible where possible, never edit an applied migration.
- No ORM lazy-loading in the bot loop — explicit queries only.

## Tables

| Table | Purpose | Key columns / constraints |
|---|---|---|
| `users` | Owner login | `email unique`, `password_hash` (Argon2id), `role` (`owner`), `totp_secret` (encrypted), `totp_enabled` |
| `app_settings` | Singleton config row | `active_environment` (`DEMO`\|`LIVE`), `active_strategy`, `risk_pct`, `sleeve_weight_pct`, `sleeve_vol_target`, `leverage_cap`, `sms_enabled`, `news_sources jsonb`, `news_time`, `news_provider` |
| `api_credentials` | Per-environment exchange + SMS + LLM secrets | `environment`, `service` (`binance`\|`notifylk`\|`codex`), `api_key`, `secret_encrypted` (AES-GCM), unique `(environment, service)` |
| `strategies` | Registered plugins | `name unique`, `class_path`, `params_json jsonb`, `enabled`, `validated_release` |
| `bot_runs` | One row per start→stop | `started_at`, `stopped_at`, `environment`, `strategy`, `stop_reason` (`user`\|`error`\|`kill`\|`breaker`), `started_by` |
| `candles` | Cached klines | `symbol`, `interval`, `open_time` — unique `(symbol, interval, open_time)`; o/h/l/c/v `numeric(20,8)`; `closed boolean` |
| `trades` | One row per round-trip | `opened_at`, `closed_at`, `side` (`LONG`\|`SHORT`), `entry_px`, `exit_px`, `qty`, `fees`, `funding`, `realized_pnl`, `r_multiple`, `exit_reason`, `strategy`, `environment`, `bot_run_id fk` |
| `orders` | Every exchange order | `binance_order_id`, `client_order_id unique` (idempotency!), `trade_id fk`, `type`, `status`, `price`, `stop_price`, `qty`, `reduce_only`, `placed_at`, `filled_at`, `raw_json jsonb` |
| `equity_snapshots` | Every 4h close | `ts`, `environment`, `balance`, `unrealized_pnl`, `month_to_date_pnl`, `sleeve_month_pnl`; unique `(environment, ts)` |
| `events` | Full audit trail | `ts`, `level` (`INFO`\|`WARN`\|`ERROR`), `category` (`trade`\|`bot`\|`breaker`\|`error`\|`sms`\|`news`\|`reconciliation`\|`system`\|`security`), `message`, `payload_json jsonb`, `sms_status`, `ref` |
| `news_items` | Raw collected items | `url unique`, `source`, `title`, `published_at`, `raw_text` |
| `briefings` | Daily AI summaries | `briefing_date unique`, `model`, `bullets jsonb` (with source links), `sentiment`, `generated_at` |
| `withdrawal_marks` | Manual bookkeeping (FR: monthly ledger) | `month unique`, `amount`, `marked_at`, `marked_by` |

## Integrity & audit rules

1. **Events are append-only.** No UPDATE/DELETE beyond `sms_status` transitions. Every
   decision, order, fill, SMS attempt and error gets a row with a reconstructable
   `payload_json` (inputs → decision → action).
2. **`orders.client_order_id` is the idempotency key** — a retried placement with the
   same ID must not create a duplicate row or a duplicate exchange order.
3. **Trades reconcile to Binance income history** — `realized_pnl + fees + funding`
   must match the exchange's income records per round-trip; the reconciler flags drift.
4. **Breaker math derives from `equity_snapshots`** (month-start equity) + live sleeve
   accrual — persisted so restarts cannot forget a tripped breaker.
5. **Secrets:** only `*_encrypted` columns hold secret material (AES-GCM, master key
   from env). Plaintext secrets must never touch the DB, logs, or API responses.

## Indexing (beyond PKs/uniques)

- `trades (environment, opened_at desc)`, `trades (side)`, `trades (strategy)` — history filters.
- `events (ts desc)`, `events (category, ts desc)`, `events (level, ts desc)` — ledger queries.
- `candles (symbol, interval, open_time desc)` — window loads.
- `equity_snapshots (environment, ts desc)` — chart ranges.

## Data lifecycle

- Candles: keep ≥3 years (parity replays need full history). ~6.6k rows/yr at 4h — trivial.
- Events: no automatic pruning in v1 (auditability first); revisit at >5 M rows.
- Backups: nightly encrypted `pg_dump` to object storage; **restore drill is part of
  Stage 10 acceptance** — an untested backup does not count.

## Migration workflow

```
backend$ alembic revision --autogenerate -m "add withdrawal_marks"
backend$ alembic upgrade head        # applied automatically on container start
```
CI runs `alembic upgrade head` against a scratch Postgres and fails on drift between
models and migrations.
