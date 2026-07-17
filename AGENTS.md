# AGENTS.md — CryptoPilot (for Codex and all AI coding agents)

You are building a **production trading system that handles real money** (automated
BTCUSDT futures trading on Binance). Correctness and auditability outrank speed.

This file is a router. The authoritative knowledge lives in `docs/` — **read the
referenced doc for your task area before writing code.** The same rules are exposed to
Claude Code via `.claude/skills/cryptopilot-dev/SKILL.md`; both agents must behave
identically because they share these docs.

## Ground rules (always apply)

1. Source of truth: `docs/BUSINESS_SOLUTION_v2.pdf`. Approved deviations:
   `docs/architecture/ARCHITECTURE.md §8` (Binance demo endpoints, Codex SDK +
   GPT-5.5 news provider — no OPENAI_API_KEY anywhere, read-only strategy params).
2. Work stage-by-stage per `docs/plan/IMPLEMENTATION_PLAN.md`; a stage closes only via
   its QA gate (test cases + Playwright suite in `qa/e2e/` + full regression green).
3. **Money is Decimal/numeric(20,8), never float. All times UTC. Trading decisions
   only on closed 4h candles.**
4. Module boundaries are law: strategies pure (no I/O, no sizing, no orders); news
   module never touches credentials/execution.
5. **Never modify `research/`** — frozen validation reference. Production strategy
   must match `research/backtests/final_composite.py` bar-for-bar.
6. **The short sleeve has NO price stop by validated design. Do not add one.**
7. DEMO only (`demo-fapi.binance.com`) until Stage 11 passes; no LIVE keys before
   Stage 12.
8. No secrets in code, logs, tests, or responses. Credentials: `docs/plan/CREDENTIALS.md`.

## Route by task

- Planning / next work item → `docs/plan/IMPLEMENTATION_PLAN.md`
- Architecture & lifecycle → `docs/architecture/ARCHITECTURE.md`
- Database & migrations → `docs/architecture/DATABASE_ARCHITECTURE.md`
- Binance / notify.lk / Codex SDK (news LLM) integrations → `docs/architecture/INTEGRATIONS.md`
- Backend code → `docs/guidelines/BACKEND_GUIDELINES.md`
- Frontend code → `docs/guidelines/FRONTEND_GUIDELINES.md` + `docs/guidelines/UIUX_GUIDELINES.md`
- Tests → `docs/guidelines/TESTING_GUIDELINES.md`; QA process → `docs/qa/QA_STRATEGY.md`
- Logging/events → `docs/guidelines/LOGGING_GUIDELINES.md`
- Security → `docs/guidelines/SECURITY_GUIDELINES.md`
- Review / pre-commit self-check → `docs/guidelines/CODE_REVIEW.md`
- Code style & refactoring → `docs/guidelines/CLEAN_CODE.md`
- Workflow, branching, commits → `docs/guidelines/DEVELOPMENT_GUIDELINES.md`
- Long-term upkeep → `docs/guidelines/MAINTAINABILITY.md`

## Reference material

- Approved UI/UX to port (don't redesign): `prototype/final-cryptopilot`
- Validated strategy rules: `research/strategies/BTC_Trend_Rider_v6.pine`
- Why the rules are what they are: `docs/reports/`

## Commands (once stages build them)

- Backend: `cd backend && pytest` (unit+integration), `pytest tests/parity` (parity gate),
  `ruff check . && mypy .`
- Frontend: `cd frontend && npm run lint && npm run build`
- E2E: `cd qa && npx playwright test`
- Stack: `docker compose -f deploy/docker-compose.yml up`

## Definition of done

Code + tests + updated docs + lint/type clean + `docs/guidelines/CODE_REVIEW.md`
checklist passed. Strategy/risk/execution changes additionally require a green parity
suite. Never merge with regression red; never close a stage with known bugs.
