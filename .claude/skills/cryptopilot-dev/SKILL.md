---
name: cryptopilot-dev
description: Develop the CryptoPilot automated BTCUSDT trading platform (FastAPI + React + PostgreSQL + Binance USDT-M futures). Use this skill for ANY work in this repository — planning, backend, frontend, database, QA/Playwright, deployment, or documentation. It routes to the authoritative docs in docs/ which define the architecture, stage plan, and non-negotiable rules.
---

# CryptoPilot Development Skill

You are building a **production trading system that handles real money**. Correctness
and auditability outrank speed. This skill is a router: the authoritative knowledge
lives in `docs/` — read the referenced file for your task area **before** writing code.

## Ground rules (always apply)

1. **Source of truth:** `docs/BUSINESS_SOLUTION_v2.pdf` (BSD). Approved deviations are
   listed in `docs/architecture/ARCHITECTURE.md §8` — read them; the BSD's Binance
   testnet host and Claude-based news agent are superseded.
2. **Work stage-by-stage** per `docs/plan/IMPLEMENTATION_PLAN.md`. A stage closes only
   through its QA gate (test cases + Playwright suite + full regression green + zero
   known bugs). Never start the next stage early.
3. **Money is Decimal/numeric(20,8), never float. All times UTC. Decisions only on
   closed 4h candles.** Violations are Critical bugs.
4. **Module boundaries are law:** strategies are pure (no I/O); the news module never
   touches credentials/execution; the strategy never sizes or places orders.
5. **Never modify `research/`** — it is the frozen validation reference. The
   production strategy must match `research/backtests/final_composite.py` bar-for-bar
   (parity suite).
6. **The short sleeve has NO price stop by validated design. Do not add one.**
7. **DEMO first:** all work targets Binance demo (`demo-fapi.binance.com`) until the
   Stage 11 gate passes. LIVE keys must not exist in the system before Stage 12.
8. Secrets never appear in code, logs, tests, or responses. Credentials list:
   `docs/plan/CREDENTIALS.md`.

## Route by task

| Working on… | Read first |
|---|---|
| Any planning / "what's next" | `docs/plan/IMPLEMENTATION_PLAN.md` |
| System design, module boundaries, lifecycle | `docs/architecture/ARCHITECTURE.md` |
| Schema, migrations, queries | `docs/architecture/DATABASE_ARCHITECTURE.md` |
| Binance / notify.lk / Codex SDK (news LLM) / RSS code | `docs/architecture/INTEGRATIONS.md` |
| Backend (FastAPI, bot, strategies, risk, execution) | `docs/guidelines/BACKEND_GUIDELINES.md` |
| Frontend (React dashboard port) | `docs/guidelines/FRONTEND_GUIDELINES.md` + `docs/guidelines/UIUX_GUIDELINES.md` |
| Writing/updating tests | `docs/guidelines/TESTING_GUIDELINES.md` |
| QA process, Playwright suites, stage gates | `docs/qa/QA_STRATEGY.md` |
| Logging, events, payloads | `docs/guidelines/LOGGING_GUIDELINES.md` |
| Auth, secrets, headers, hardening | `docs/guidelines/SECURITY_GUIDELINES.md` |
| Reviewing a PR / self-review before commit | `docs/guidelines/CODE_REVIEW.md` |
| Naming, structure, refactoring | `docs/guidelines/CLEAN_CODE.md` |
| Docs, runbooks, upgrades, dependencies | `docs/guidelines/MAINTAINABILITY.md` |
| Workflow, branching, commits, DoD | `docs/guidelines/DEVELOPMENT_GUIDELINES.md` |

## Reference material

- Approved UI/UX: `prototype/final-cryptopilot` (run `npm run dev` there) — port it,
  don't redesign it.
- Validated strategy: `research/strategies/BTC_Trend_Rider_v6.pine` (annotated rules)
  and `research/backtests/final_composite.py` (parity reference).
- Research reports (why the rules are what they are): `docs/reports/`.

## Definition of done (every task)

Code + tests + updated docs + lint/type clean + review checklist
(`docs/guidelines/CODE_REVIEW.md`) passed. For UI work: matches prototype patterns and
a11y basics. For strategy/risk/execution work: parity suite green.
