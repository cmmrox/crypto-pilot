# Maintainability Guidelines

This system must be operable and evolvable by one person with AI assistance, years
from now. Optimize for the reader and the operator, not the writer.

## Documentation contract

- `docs/` is the brain: architecture, DB, integrations, guidelines, plan, QA. **Code
  changes that alter behaviour described in docs update those docs in the same PR** —
  reviewers block on stale docs (`CODE_REVIEW.md`).
- Each module gets a short `README.md` (what it owns, its interface, what it must
  never do) once it's built — the `ARCHITECTURE.md` table stays the index.
- Decisions with alternatives get a dated note in `ARCHITECTURE.md §8` (deviations) —
  tiny ADRs, not ceremony.

## Keeping the system understandable

- Boundaries enforced by tools (import-linter), not memory.
- The BSD's domain vocabulary everywhere — code, DB, UI, docs, tests speak one language.
- Runbooks live in `deploy/` and stay executable (scripts > prose): start/stop,
  upgrade blue/green, restore, key rotation, incident.
- The parity suite is the permanent regression anchor for the strategy — it never gets
  deleted, weakened, or "temporarily skipped".

## Dependency & upgrade hygiene

- Lockfiles committed; upgrades in dedicated PRs on a monthly cadence; read release
  notes for FastAPI/SQLAlchemy/React majors before bumping.
- Pin Postgres major (16) until a planned migration; test restores across versions.
- Vendor-risk notes: Binance API changes are the top external risk — `INTEGRATIONS.md`
  records verified endpoints/dates; re-verify on any unexplained 4xx.

## Operational maintainability

- Everything reproducible from the repo + `.env` + a DB backup: `docker compose up`
  is the whole deployment story.
- Logs/events make yesterday reconstructable (see `LOGGING_GUIDELINES.md`); the
  monthly review (Appendix A comparison) is a scheduled calendar ritual, not vibes.
- Chaos drills re-run quarterly after release (restart, WS cut, restore) — Stage 10
  scripts stay green forever.

## Code-level rules that age well

- Prefer boring technology and stdlib; every clever abstraction must pay rent today,
  not hypothetically.
- Feature flags are temporary; remove within one stage of shipping.
- TODOs carry an owner and a ticket/stage reference or they're deleted.
- When touching old code, first add the missing test, then change it.
