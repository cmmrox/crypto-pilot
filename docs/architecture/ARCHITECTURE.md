# CryptoPilot — System Architecture

Source of truth: `docs/BUSINESS_SOLUTION_v2.pdf` (BSD v2.0). This document makes the
BSD buildable: module boundaries, interfaces, runtime model, and the rules that keep
the system safe. Read together with `DATABASE_ARCHITECTURE.md` and `INTEGRATIONS.md`.

## 1. Style: modular monolith

One deployable backend (FastAPI process) + React SPA + PostgreSQL + Caddy, orchestrated
by Docker Compose. Internal modules are separated by **package boundaries and
interfaces**, never by network calls. Modules communicate through defined Python
interfaces and PostgreSQL — never by reaching into each other's internals.

```
frontend (React SPA)
   │ HTTPS (Caddy TLS) · JWT · WebSocket
   ▼
backend/app
├── api/          FastAPI routers: auth, bot, trades, monthly, events, news, settings, ws
├── core/         config (pydantic-settings) · security (Argon2/JWT/SMS OTP) · AES-GCM crypto
├── db/           SQLAlchemy models · Alembic migrations · session management
├── bot/          BotService: 24/7 loop · lifecycle (start/stop/stop-close/kill/safe-mode)
│                 scheduler (4h ticks UTC, health, reconnect) · persisted state/resume
├── strategies/   Strategy interface + intent types + registry
│                 trend_rider_v6.py · trend_rider_v52.py  (pure functions, no I/O)
├── risk/         RiskEngine: risk-% sizing · sleeve vol targeting · leverage cap
│                 both monthly breakers (independent)
├── execution/    BinanceClient (REST+WS, DEMO/LIVE) · OrderManager (idempotent orders,
│                 lot rounding, retries) · Reconciler (expected vs exchange, safe mode)
├── notifier/     event bus → events table row + notify.lk SMS (fire-and-log, 3 retries)
└── news/         ISOLATED: collector (RSS) · SummaryProvider (Codex SDK · gpt-5.5) · publisher
```

## 2. Hard boundaries (enforced, not aspirational)

| Rule | Enforcement |
|---|---|
| `strategies/` never imports `execution/`, `risk/`, `api/`, or any I/O | import-linter contract in CI |
| `news/` never imports `execution/`, `strategies/`, `risk/`, or reads `api_credentials` | import-linter contract in CI |
| Strategies emit **abstract intents only**; the engine owns sizing & orders | intent dataclasses are the only return type of `on_candle()` |
| Money is `Decimal`/`numeric(20,8)` end-to-end — never float | lint rule + code review checklist |
| All timestamps UTC (`timestamptz`) | DB constraint + review checklist |
| Decisions only on **closed 4h candles** | scheduler passes only closed klines to strategy |

## 3. The strategy plugin contract (BSD §7)

```python
class Strategy(Protocol):
    name: str
    params: dict          # validated defaults; read-only in the operator UI
    def warmup_bars(self) -> int: ...                    # v6: 200
    def on_candle(self, candles: CandleWindow, state: TradeState) -> list[Intent]: ...

# Intents (complete vocabulary — do not extend casually):
EnterLong(stop_distance, tp_levels)      # engine sizes from risk %, places stop+TP
EnterShort(weight, vol_target)           # engine computes vol-scaled notional; NO price stop
ResizeShort(target_notional)             # engine applies >20% drift guard
MoveStop(price)                          # ratchet-only; engine refuses to lower a long stop
TakePartial(level_id)                    # informational; TP orders rest on-exchange
ExitAll(reason)                          # regime death, breaker, manual, kill
Halt(until)                              # monthly breakers stand-aside
```

Registered at launch: `trend_rider_v6` (default), `trend_rider_v52` (long-only
fallback), both pinned to the validated parameter sets. **Parity is law:** the
production `trend_rider_v6` must reproduce `research/backtests/final_composite.py`
decisions bar-for-bar over the full 3-year history (CI-enforced, Stage 3).

## 4. Runtime model

- **One process, three concerns:** FastAPI (uvicorn) serves REST/WS; the bot loop and
  the scheduler run as asyncio tasks in the same process. No Celery/queues — the BSD
  latency budget (act within seconds of a 4h close) doesn't justify them.
- **Bot lifecycle:** `start` → connect → reconcile → (catch up missed closed candles)
  → loop. `stop` = stop evaluating, leave position. `stop&close` = flatten then stop.
  `kill` = cancel all, flatten all, stop, SMS. State (`bot_runs`, open trade state)
  persists in PostgreSQL; on process restart the bot auto-resumes if it was running.
- **Safe mode:** reconciliation mismatch or margin error → no new entries, management
  and reconciliation continue, SMS sent, banner shown.
- **WebSocket push:** position, P&L, bot state, breaker meters stream to the dashboard;
  REST covers everything else.

## 5. Environment model (DEMO/LIVE)

Single `active_environment` in `app_settings`. Each environment has its own encrypted
key pair and base URLs (see `INTEGRATIONS.md`). Switching requires: bot stopped +
typed confirmation (LIVE) + next start reconciles the new account. Nothing else in the
code path differs — this is what makes 4 weeks of DEMO evidence transferable to LIVE.

## 6. Failure design

| Failure | Behaviour |
|---|---|
| WS drop | auto-reconnect with backoff; REST backfill missed candles; catch-up decisions on closed candles only |
| Process crash / VPS reboot | Docker restarts container; bot resumes from persisted state; reconcile before acting |
| Binance 429/418 | exponential backoff + jitter; never tight-loop; order placement uses idempotent client IDs so retries are safe |
| Margin error −2019 | pause bot + SMS |
| SMS failure | retry ×3 → ERROR event + banner; trading never blocked |
| Missed 4h tick | dead-man's-switch cron alerts owner by SMS |
| Reconciliation mismatch | safe mode + SMS |

## 7. Deployment (BSD §15)

Docker Compose services: `backend` (FastAPI+bot+scheduler), `postgres` (16), `caddy`
(TLS), `frontend` (static build served by Caddy). VPS 1 vCPU/2 GB. Nightly encrypted
`pg_dump` to object storage. Blue/green upgrades; never upgrade with an open position
unless hotfix-critical. Health endpoint + dead-man cron.

## 8. Deviations from the BSD (owner-approved)

1. **News LLM = Codex SDK with GPT-5.5** (BSD said Claude API). No `OPENAI_API_KEY` anywhere; Codex credentials only. Pluggable provider; see `INTEGRATIONS.md §3`.
2. **Binance demo endpoints updated** to `demo-fapi.binance.com` (BSD referenced the retired testnet host).
3. **Strategy parameters are read-only in the operator UI** (prototype-approved override of FR-11's editable parameters); changes ship as versioned releases through parity tests.
4. **Overview live updates use short-interval polling (4s), not WebSocket** (BSD §12 said WebSocket). For a bot that decides once per 4h close, 4s polling delivers a real-time feel with far less complexity and better reconnection robustness. The WebSocket push channel remains a future optimization; the REST `/api/overview` aggregate is the source.
5. **Owner-configurable SMS OTP replaces authenticator TOTP.** When enabled, the
   password step can issue only a five-minute `otp_pending` token bound to one
   single-use challenge. The owner may disable 2FA (password-only login) only through
   password + current-phone OTP confirmation; phone changes prove the new number and
   revoke other sessions. Server-shell `reset-2fa` is the only recovery path. This
   accepts SIM-swap and optional-single-factor risk with the controls documented in
   `SECURITY_GUIDELINES.md` and `docs/plan/SMS_2FA_PLAN.md`.
6. **The Overview command center exposes a read-only explainability projection.**
   `/api/overview` combines the in-process worker heartbeat, public Binance market
   observations, next closed-4h decision time, latest persisted indicator thresholds,
   operational events, account truth, independent breakers, and the isolated news
   briefing. `strategies/watch.py` may reuse pure indicator calculations, but it emits
   no intents and is never imported by the trading path. Displayed threshold prices
   are descriptive closed-candle conditions, never a promised trigger or execution
   price. The five-second worker heartbeat is distinct from both the bot lifecycle
   state and the four-hour ingest dead-man signal.
