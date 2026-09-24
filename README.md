# CryptoPilot

Automated BTCUSDT trading platform executing the validated **Trend Rider v6** long/short
strategy on Binance USDT-M Futures (DEMO testnet first, then LIVE), with a secure web
dashboard, notify.lk SMS alerts, pluggable strategies and an isolated AI news briefing.

**Source of truth:** `docs/BUSINESS_SOLUTION_v2.pdf` (BSD v2.0, 17 Jul 2026). It contains
backtest results, so it is kept private and is not published in this repository.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/` | Python 3.11 · FastAPI · modular-monolith trading core (bot loop, strategy plugins, risk & execution engines, notifier, isolated news agent) |
| `frontend/` | React SPA owner dashboard (ported from the approved prototype) |
| `deploy/` | Docker Compose · Caddy TLS · backup & ops scripts |
| `qa/` | Playwright stage-acceptance suites (one spec per implementation stage) |
| `research/` | Validated strategy research — Pine scripts, backtest engines, market data, results. `research/backtests/final_composite.py` is the **parity reference**: the production strategy module must match it bar-for-bar (BSD §14, Phase 1) |
| `prototype/` | Approved UI/UX reference (`final-cryptopilot`) — run with `npm run dev` |
| `docs/` | All project knowledge — see index below |

## Documentation index (`docs/`)

| Document | What it defines |
|---|---|
| `BUSINESS_SOLUTION_v2.pdf` | **Source of truth** — requirements, scope, rollout (kept private, not in this repo) |
| [`plan/IMPLEMENTATION_PLAN.md`](docs/plan/IMPLEMENTATION_PLAN.md) | Stage-by-stage build plan with QA gates (Stages 0–12) |
| [`plan/CREDENTIALS.md`](docs/plan/CREDENTIALS.md) | Every key/service the owner must provide, per phase |
| [`architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | System architecture, module boundaries, approved BSD deviations |
| [`architecture/DATABASE_ARCHITECTURE.md`](docs/architecture/DATABASE_ARCHITECTURE.md) | PostgreSQL schema, integrity rules, migrations |
| [`architecture/INTEGRATIONS.md`](docs/architecture/INTEGRATIONS.md) | Binance (verified 2026 endpoints), notify.lk, Codex SDK (GPT-5.5 news LLM) |
| [`qa/QA_STRATEGY.md`](docs/qa/QA_STRATEGY.md) | Test pyramid, Playwright conventions, stage gates, acceptance |
| [`guidelines/`](docs/guidelines/) | Development · Backend · Frontend · UI/UX · Clean code · Code review · Testing · Logging · Security · Maintainability |

**AI development:** Claude Code and Codex share the same canonical skill at
`.agents/skills/cryptopilot-dev/SKILL.md`. Claude's `.claude/skills/cryptopilot-dev`
path is a relative symlink to it. Codex reads [`AGENTS.md`](AGENTS.md), while Claude
reads `CLAUDE.md`, which is a relative symlink to that same bootstrap. Product and
engineering truth remains in `docs/`; update it there once for both agents.

## Architecture (BSD §4)

Modular monolith: one deployable FastAPI backend with strictly separated internal
modules (scheduler, strategy plugin, risk & sizing, execution, notifier, news agent)
communicating only through defined interfaces and PostgreSQL 16 — the single source
of truth. The Binance account, not bot memory, is the source of truth for portfolio
state; every start and every 4h close reconciles against the exchange.

Key rules:

- Strategies emit **abstract intents only** — never talk to Binance, never size positions.
- Decisions only on **closed 4h candles**; no intrabar logic.
- The news agent is **read-only context for the human** — no exchange keys, never a trading input.
- No API key ever has withdrawal permission.

## Research scripts

The validated scripts in `research/backtests/` reference the CSVs by bare filename;
symlinks into `research/data/` are provided so they run unchanged:

```sh
cd research/backtests
python final_composite.py
```

## Rollout gates (BSD §14)

1. **Parity tests** — zero bar-for-bar mismatches vs `final_composite.py`
2. **DEMO (testnet)** ≥4 weeks, forced-failure drills, SMS ≤60s
3. **LIVE pilot** at minimum size, owner sign-off
4. **Full operation** with monthly review vs Appendix A expectations

> **Risk notice:** this software trades real money automatically, including stop-free,
> size-managed shorts on futures. Backtested performance does not guarantee future
> results. See BSD §18 for honest limitations.
