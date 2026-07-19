# Development Guidelines

The workflow rules for building CryptoPilot. Stack-specific rules:
`BACKEND_GUIDELINES.md`, `FRONTEND_GUIDELINES.md`. Quality bars: `CLEAN_CODE.md`,
`CODE_REVIEW.md`, `TESTING_GUIDELINES.md`.

## Workflow

1. **Work happens stage-by-stage** per `docs/plan/IMPLEMENTATION_PLAN.md`. Never start
   stage N+1 with stage N's QA open. Never merge with regression red.
2. **Branching:** trunk-based. `main` is always deployable. Short-lived feature
   branches `stage-XX/<topic>`, merged by PR with review (see `CODE_REVIEW.md`).
3. **Commits:** conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`,
   `chore:`); imperative subject ≤72 chars; body explains *why*. One logical change per
   commit — a reviewer must be able to revert any commit safely.
4. **Definition of Done** for any task: code + tests + docs updated + lints/types clean
   + reviewed. "Works on my machine" is not done; green in CI is done.
5. **AI pair development (Claude Code / Codex):** both agents load the same context —
   Claude via `.claude/skills/cryptopilot-dev/`, Codex via root `AGENTS.md`. Agents
   must read the referenced doc for the area they touch *before* writing code. AI
   output goes through the same review gate as human code — no direct-to-main.

## Non-negotiable engineering rules

- **Money is `Decimal` / `numeric(20,8)`** everywhere. A `float` touching a price,
  quantity, or P&L is a Critical bug.
- **All times UTC** (`timestamptz`, `datetime` aware). Formatting to local time happens
  only at the UI edge.
- **Module boundaries are law** (`ARCHITECTURE.md §2`) — import-linter enforces them;
  don't fight the linter, fix the design.
- **Idempotency:** any operation that talks to the exchange must be safe to retry
  (client order IDs, upserts keyed on natural keys).
- **No secrets in code, logs, fixtures, or screenshots.** gitleaks runs in CI.
- **Config via environment** (pydantic-settings) — no hardcoded URLs, keys, or magic
  numbers; validated defaults live in one place.
- **Never modify `research/`** — it is the frozen validation reference. Parity failures
  mean the *port* is wrong, not the research.

## Dependency policy

- Add a dependency only when it replaces meaningful code; prefer stdlib. Every new dep
  is named in the PR description with a one-line justification.
- Pin everything (uv/pip-tools lock, package-lock). Renovate/audit runs in CI; upgrades
  are their own PRs, never mixed with features.
- After any backend dependency change, regenerate and verify both lock artifacts:

  ```sh
  cd backend
  uv lock
  uv export --frozen --no-dev --no-emit-project \
    --format requirements-txt --output-file requirements.lock
  uv sync --frozen --all-groups
  uv run --frozen pip-audit
  ```

  `uv.lock` pins the complete development/CI graph. The production image installs
  the hash-verified `requirements.lock`; never hand-edit either generated file.

## When blocked or uncertain

Trading code has asymmetric risk: **stop and verify** beats "probably fine". If
exchange behaviour is unclear, write a throwaway probe against DEMO and record the
finding in `docs/architecture/INTEGRATIONS.md`. If the BSD and reality conflict,
document the deviation in `ARCHITECTURE.md §8` and get owner sign-off.
