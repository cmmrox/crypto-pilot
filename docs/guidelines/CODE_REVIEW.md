# Code Review Guidelines

Every change reaches `main` by PR, and every PR is reviewed — including AI-generated
code (Claude/Codex output gets the *same* scrutiny; the agent is the author, the human
is accountable).

## PR hygiene

- Small, focused PRs (< ~400 changed lines preferred); one concern per PR. Stage work
  is split into reviewable slices, not one mega-PR per stage.
- Description states: what, why, how tested (with evidence — test names, screenshots
  for UI), affected docs updated, new deps justified.
- CI must be green before review starts (lint, types, unit, parity, migrations,
  gitleaks). Reviewers review code, not linting.

## Reviewer checklist

**Correctness & safety (blocking):**
- [ ] Money: `Decimal`/string end-to-end; rounding only at exchange filters, `ROUND_DOWN` qty
- [ ] Time: UTC-aware datetimes; 4h boundaries and month rollovers handled
- [ ] Exchange calls idempotent (client order IDs) and retry-safe; no tight retry loops
- [ ] Errors surface as events; no swallowed exceptions; safe-mode paths intact
- [ ] Module boundaries respected (strategy purity, news isolation)
- [ ] **Strategy/risk/execution changes: parity suite ran and is green** — any change
      to validated math is a red flag; demand the research justification
- [ ] Secrets: none in code/logs/tests/fixtures; new config via env + settings model

**Quality:**
- [ ] Tests accompany behaviour (see `TESTING_GUIDELINES.md`); bug fixes include the
      regression test that fails without the fix
- [ ] Names use domain vocabulary; no dead code; no needless dependency
- [ ] Docs updated when architecture/DB/integration behaviour changed
- [ ] UI: matches prototype patterns, honest states, a11y basics (labels, focus, Escape)

## Review conduct

- Review the code, not the author. Blocking comments state the risk and, where
  possible, the fix. Nitpicks are prefixed `nit:` and never block.
- Author responds to every comment (fix or reasoned pushback). Two unresolved
  rounds → synchronous discussion, decision recorded in the PR.
- Reviewer runs the change locally for anything touching bot lifecycle, execution, or
  auth — "read-only review" is insufficient for money paths.

## Merge rules

Squash-merge with a conventional-commit title. The PR author merges after approval.
Anything reverted gets a post-mortem note in the stage report.
