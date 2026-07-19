---
name: cryptopilot-dev
description: Develop and operate the CryptoPilot automated BTCUSDT trading platform safely. Use for any work in this repository, including planning, backend, frontend, database, Binance or notify.lk integrations, Codex news, strategy parity, risk, execution, QA/Playwright, deployment, security, documentation, review, or deciding the next stage.
---

# CryptoPilot development

Build a production trading system that handles real money. Prioritize correctness,
auditability, and evidence over speed. Treat this skill as the workflow router and
the repository's `docs/` directory as the authoritative knowledge base.

## Start every task

1. Confirm the repository root with `git rev-parse --show-toplevel`.
2. Read `docs/plan/IMPLEMENTATION_PLAN.md` for planning, current-stage, or next-work
   questions. Do not infer stage completion from code alone; inspect the matching
   report under `docs/qa/reports/` and current test evidence.
3. Read every task-specific document in the routing table before changing code.
4. Inspect the implementation, tests, migrations, and recent history relevant to the
   request. Do not rely on a report as proof that the current tree is still green.
5. Keep the change within the current stage and module boundary. Add or update tests
   and docs in the same change.
6. Run the narrow checks first, then all required regression gates for the affected
   risk area.
7. Self-review against `docs/guidelines/CODE_REVIEW.md` before declaring completion.
8. For ordinary code-review requests, use this repository's review checklist and
   validation gates. Do not start the Codex Security plugin/workbench workflow unless
   the owner explicitly requests a Codex Security scan or security-specific review.

## Non-negotiable rules

- Use `docs/BUSINESS_SOLUTION_v2.pdf` as the business source of truth. Apply only the
  owner-approved deviations recorded in `docs/architecture/ARCHITECTURE.md §8`.
- Use `Decimal` and PostgreSQL `numeric(20,8)` for money; never use float. Use UTC-aware
  time everywhere. Make trading decisions only from closed 4h candles.
- Keep strategies pure: no I/O, sizing, orders, clocks, or randomness. Emit only the
  intent vocabulary defined by the architecture.
- Never modify `research/`. Production Trend Rider v6 must match
  `research/backtests/final_composite.py` bar-for-bar.
- Preserve the stop-free, size-managed short sleeve. Never add a price stop.
- Keep the news module informational and isolated from credentials, strategy, risk,
  bot, and execution.
- Treat Binance as the source of truth for live account state. Reconcile before acting;
  use idempotent client order IDs and safe mode on unexplained mismatch.
- Use Binance DEMO only until Stage 11 passes and the Stage 12 LIVE gate is explicitly
  opened. Never introduce LIVE credentials early.
- Never expose secrets in code, logs, tests, fixtures, screenshots, commands, or
  responses. Never grant withdrawal permission.
- Do not close a stage with a known bug or red regression.

## Route by task

| Task | Read before changing code |
|---|---|
| Planning, status, next stage | `docs/plan/IMPLEMENTATION_PLAN.md` and matching `docs/qa/reports/` |
| Architecture, lifecycle, boundaries | `docs/architecture/ARCHITECTURE.md` |
| Database, SQLAlchemy, Alembic | `docs/architecture/DATABASE_ARCHITECTURE.md` |
| Binance, notify.lk, Codex news, RSS | `docs/architecture/INTEGRATIONS.md` |
| Backend | `docs/guidelines/BACKEND_GUIDELINES.md` |
| Frontend | `docs/guidelines/FRONTEND_GUIDELINES.md` and `docs/guidelines/UIUX_GUIDELINES.md` |
| Tests | `docs/guidelines/TESTING_GUIDELINES.md` |
| QA, Playwright, stage gates | `docs/qa/QA_STRATEGY.md` |
| Logging and audit events | `docs/guidelines/LOGGING_GUIDELINES.md` |
| Auth, secrets, hardening | `docs/guidelines/SECURITY_GUIDELINES.md` |
| Review and pre-commit check | `docs/guidelines/CODE_REVIEW.md` |
| Naming, structure, refactoring | `docs/guidelines/CLEAN_CODE.md` |
| Workflow, branches, commits | `docs/guidelines/DEVELOPMENT_GUIDELINES.md` |
| Docs, runbooks, dependencies | `docs/guidelines/MAINTAINABILITY.md` |
| Credentials and phase timing | `docs/plan/CREDENTIALS.md` |
| SMS 2FA | `docs/plan/SMS_2FA_PLAN.md` and `docs/guidelines/SECURITY_GUIDELINES.md` |

Read all listed documents when a task crosses concerns. Re-verify external integration
behavior against official provider documentation before changing an endpoint or auth
flow.

## Repository map

- `backend/`: FastAPI modular monolith, PostgreSQL persistence, trading loop, strategy,
  risk, execution, notifier, and isolated news provider.
- `frontend/`: React 19 and Vite owner console backed by real APIs.
- `qa/e2e/`: Playwright acceptance suite, one spec per implementation stage.
- `deploy/`: Compose, Caddy, backups, restore tooling, drills, and runbooks.
- `prototype/final-cryptopilot/`: approved UI/UX reference to port, not redesign.
- `research/`: frozen strategy validation reference; read-only.
- `docs/`: business, architecture, plans, QA evidence, engineering rules, and reports.

## Validation

Choose checks proportionate to the change, but never skip a mandatory money-path gate.

```sh
cd backend
pytest
pytest tests/parity
ruff check app tests
ruff format --check app tests
mypy app
lint-imports
```

```sh
cd frontend
npm run lint
npm run build
```

```sh
cd qa
npx playwright test
```

For deploy or lifecycle changes, run the applicable Compose health checks and drill
scripts from `deploy/`. Never claim remote Stage 11 soak or Stage 12 evidence from
local tests.

## Definition of done

Complete code, tests, affected docs, lint, types, applicable Playwright regression,
and the code-review checklist. Require a green parity suite for any strategy, risk, or
execution change. Report commands and observed results; distinguish skipped or blocked
checks from passes.

## Maintain the shared agent setup

This file is the single skill source for both tools:

- Codex discovers `.agents/skills/cryptopilot-dev/`.
- Claude Code discovers `.claude/skills/cryptopilot-dev`, a relative symlink to this
  directory.
- Codex loads `AGENTS.md`; Claude Code loads `CLAUDE.md`, a relative symlink to the
  same bootstrap file.

Edit this file only once when changing the workflow. Put durable product or engineering
truth in the appropriate `docs/` file and keep this skill as a concise router. Do not
replace either symlink with a copied file. After changing the agent setup, run:

```sh
bash .agents/skills/cryptopilot-dev/scripts/validate-agent-setup.sh
```
