# QA Strategy & Test Automation

How CryptoPilot is tested at every stage. Stage-specific test cases live in
`docs/plan/IMPLEMENTATION_PLAN.md` (QA-0 … QA-12); this document defines the process,
the pyramid, the Playwright conventions, and the acceptance protocol.

## 1. The stage gate

A stage closes only when:

1. All stage test cases pass (manual checklist where automation is impossible).
2. The stage's Playwright suite exists in `qa/e2e/` and is green.
3. **Full regression** — every previous stage's suite — is green.
4. Zero known bugs of severity minor or above.
5. Docs touched by the stage are updated in the same PR.

## 2. Test pyramid

| Layer | Tool | Lives in | Scope |
|---|---|---|---|
| Unit | pytest (+hypothesis for math), vitest | `backend/tests/unit`, `frontend/src/**/*.test.*` | Pure logic: strategy rules, sizing math, template rendering, reducers |
| **Parity** ⭐ | pytest harness | `backend/tests/parity` | Bar-for-bar diff vs `research/backtests/final_composite.py` — zero mismatches, mandatory in CI forever |
| Integration | pytest + testcontainers (Postgres), respx/mocked Binance | `backend/tests/integration` | API routes, DB, reconciler, notifier retries, WS |
| E2E / QA automation | **Playwright** | `qa/e2e/` | Real browser against a running stack; stage acceptance |
| Drills | scripted chaos (Stage 10) | `deploy/scripts/drills/` | Restart, network cut, backup restore |

## 3. Playwright conventions (`qa/`)

- One spec file per stage: `stage-XX.<area>.spec.ts`; tests map 1:1 to the QA-XX test
  cases by ID in the test title: `test("QA-4.07 kill switch from running state", …)`.
- Fixtures: authenticated session (login+TOTP via API, storageState reuse); seeded DB
  snapshot per suite; deterministic clock where the UI shows countdowns.
- Backend-only checks use Playwright's request context (API testing) so every stage —
  including pre-UI ones — has an automated suite.
- External services in E2E: Binance DEMO is used **for real** in execution suites;
  notify.lk and the LLM are mocked in E2E (each has one recorded real-call check run
  manually per stage).
- Anti-flake rules: no `waitForTimeout`; await UI state or network responses; retries=1
  in CI, 0 locally — a test that needs retries gets fixed, not retried harder.
- Artifacts on failure: trace + video + screenshot, uploaded by CI.

## 4. Test-case writing

Follow `docs/guidelines/TESTING_GUIDELINES.md`. Template:

```
ID:        QA-<stage>.<nn>
Title:     <behaviour under test>
Pre:       <state/fixtures>
Steps:     <numbered>
Expected:  <observable outcome incl. DB/event side-effects>
Automation: qa/e2e/stage-XX.*.spec.ts::<test title> | pytest path | MANUAL(reason)
```

Rules of thumb: assert side-effects (DB rows, events, exchange state), not just UI
text; every bug found gets a regression test before the fix merges; money assertions
compare `Decimal` strings, never floats.

## 5. Severity & bug workflow

| Sev | Definition | Policy |
|---|---|---|
| Critical | wrong order/size/money, auth bypass, data loss | stop everything, fix now, add regression test + drill |
| Major | feature broken, no workaround | fix before stage close |
| Minor | wrong-but-recoverable UI/UX, cosmetic-with-confusion | fix before stage close |
| Trivial | cosmetic only | backlog allowed, logged |

Every bug: reproduce → write failing test → fix → test green → note in stage report.

## 6. Acceptance protocol (Stages 11–12)

- Weekly: full Playwright regression against the deployed VPS; reconciliation report
  clean; every decision that week explained against strategy rules; SMS latency sample
  ≤60 s; backup restore spot-check monthly.
- Deviation log: anything unexplained → investigate to root cause; unexplained
  deviations reset the 4-week clock (BSD G3).
- Sign-off artifact: stage report with test evidence, stored in `docs/qa/reports/`.

## 7. Stage report template

Each closed stage produces `docs/qa/reports/STAGE-XX-REPORT.md`: scope shipped, test
run summary (counts, link to CI run), bugs found/fixed (with severities), deviations
from plan, docs updated, sign-off line.
