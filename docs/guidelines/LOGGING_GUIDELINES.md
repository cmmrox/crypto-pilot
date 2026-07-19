# Logging & Observability Guidelines

Two distinct planes — don't conflate them:

| Plane | Audience | Medium | Retention |
|---|---|---|---|
| **Events** (`events` table) | The owner; audit & UI | structured rows, `payload_json` | permanent (append-only) |
| **Logs** (stdout JSON) | The operator/developer; debugging | structlog JSON → docker logs | container rotation |

Rule of thumb: *if the owner could care, it's an event; if only a developer debugging
could care, it's a log.* Events additionally log (never the reverse).

## Log format (structlog, JSON to stdout)

Every line: `ts` (UTC ISO), `level`, `logger` (module), `event` (snake_case verb
phrase), plus structured fields — never interpolated prose. Bind context once per
scope: `bot_run_id`, `environment`, `candle_open_time`, `trade_id`, `client_order_id`,
`request_id` (API middleware).

```python
log.info("order_placed", side="SHORT", qty="0.116", px="65711.20",
         client_order_id="CP-TR-2681-01", reduce_only=False)
```

## Levels

- `DEBUG` — dev only (indicator values per bar, WS frames). Off in production.
- `INFO` — normal operations: ticks, decisions, orders, reconciliations, SMS attempts.
- `WARNING` — degraded but coping: retry, reconnect, feed failure, vol-resize skipped.
- `ERROR` — something failed and needs attention: order rejected, SMS exhausted,
  reconcile mismatch. Every `ERROR` log has a paired event row.
- `CRITICAL` — money-safety compromised: safe-mode entry, kill-switch, margin pause.
  Always paired with event + SMS.

## Red lines

- **Never log secrets** — API keys, signatures, OTP codes/hashes, JWTs, phone numbers
  (mask: `+94 77 ••• ••42`). The signing function itself must be excluded from debug
  logging. gitleaks + a log-scrub test (Stage 0) enforce this.
- Never log at `INFO`+ inside per-bar hot loops except the single decision line.
- No print(). No f-string message assembly (fields, not prose).
- Exchange `raw_json` responses go to the `orders.raw_json` column, not to logs.

## Event payload discipline

`payload_json` must make the moment reconstructable: inputs (indicator values, account
state), the decision/action, and identifiers linking to `trades`/`orders`. Write it as
if a future you must explain the trade to the owner from this row alone — because
that is literally the requirement (BSD G5).

## Health & metrics

`/health` returns: DB ok, WS connected + age of last kline, last 4h tick, scheduler
alive, version. The dead-man cron consumes it. Keep it cheap (<50 ms) and
unauthenticated-safe (no sensitive data).
