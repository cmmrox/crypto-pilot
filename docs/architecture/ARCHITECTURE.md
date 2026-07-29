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
├── strategies/   Contract v2 + auto-discovered, strategy-owned manifests
│   └── plugins/  trend_rider_v6_4h.py · trend_rider_v52_4h.py (pure, no I/O)
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
    manifest: StrategyManifest  # market, timeframe, risk, education, validation
    params: dict          # validated defaults; read-only in the operator UI
    def on_candle(self, candles: CandleWindow, state: TradeState) -> list[Intent]: ...
    def inspect(self, candles: CandleWindow) -> StrategyWatch | None: ...

# Intents (complete vocabulary — do not extend casually):
EnterLong(stop_distance, tp_levels)      # engine sizes from risk %, places stop+TP
EnterShort(weight, vol_target)           # engine computes vol-scaled notional; NO price stop
ResizeShort(target_notional)             # engine applies >20% drift guard
MoveStop(price)                          # ratchet-only; engine refuses to lower a long stop
TakePartial(level_id)                    # informational; TP orders rest on-exchange
ExitAll(reason)                          # regime death, breaker, manual, kill
Halt(until)                              # monthly breakers stand-aside
```

Registered at launch: `trend_rider_v6_4h` (default), `trend_rider_v52_4h` (long-only
fallback), both pinned to the validated parameter sets. **Parity is law:** the
production `trend_rider_v6_4h` must reproduce `research/backtests/final_composite.py`
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
   briefing. Each strategy plugin owns its optional pure `inspect()` projection, so
   adding a different strategy cannot leave Trend Rider-specific conditions in the
   generic Overview service. Inspection emits no intents and is never used by the
   trading path. Displayed threshold prices are descriptive closed-candle conditions,
   never a promised trigger or execution price. The five-second worker heartbeat is
   distinct from both the bot lifecycle state and the four-hour ingest dead-man signal.
7. **Aggressive risk-defined sizing profile (`risk_pct` 15%, `leverage_cap` 6x).**
   Supersedes the original validated 2%/3x defaults. Each long trade is sized so a
   stop-out loses ~15% of equity (`risk_pct ÷ stop%` ⇒ ~4.7x median leverage, capped
   at 6x). The `LONG_MONTH_CAP` engine constant stays 4%, so a single losing long
   halts longs for the remainder of that month. Backtest (2023-06→2026-07, faithful
   stop/breaker model, funding included): $100 → ~$1,330 with a ~-40% max drawdown and
   no liquidation. This accepts materially higher single-trade and drawdown risk than
   the validated set; it relies on stops filling near their price (gap risk) and on the
   short sleeve remaining at its native vol-targeted sizing. Owner-acknowledged, DEMO
   only. Contract v2 moved these values from mutable application settings into the
   immutable strategy manifest; the chronological production-plugin replay verifies
   the complete configured profile. The earlier settings change was delivered as
   migration `d3e4f5a6b7c8`; migration `f5a6b7c8d9e0` removes those duplicate columns.
8. **Strategy plugin contract v2.** Strategy IDs and filenames include their
   timeframe (for example `trend_rider_v6_4h.py`). An immutable plugin manifest owns
   the market/data window, risk policy, education, and validation evidence. The
   application auto-discovers verified plugins and remains responsible for I/O,
   clocks, reconciliation, exchange filters, sizing mechanics, and orders. Strategy
   selection is read-only apart from choosing the default; it requires stopped and
   flat state. See `docs/strategies/CREATING_A_STRATEGY.md`.
