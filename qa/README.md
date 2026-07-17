# QA Automation (Playwright)

Stage acceptance suites live here — one spec per stage, mapping 1:1 to the QA test
cases in `docs/plan/IMPLEMENTATION_PLAN.md`. Process and conventions:
`docs/qa/QA_STRATEGY.md`.

## Layout (populated from Stage 0 onward)

```
qa/
├── package.json            # playwright + tooling (created in Stage 0)
├── playwright.config.ts    # projects: chromium desktop + mobile-390; retries=1 CI
├── fixtures/               # auth storageState, seeded-DB helpers, mock servers (SMS/LLM)
└── e2e/
    ├── stage-00.smoke.spec.ts
    ├── stage-01.auth.spec.ts
    ├── stage-02.marketdata.spec.ts
    ├── stage-03.strategy.spec.ts
    ├── stage-04.execution.spec.ts      # @exchange — hits Binance DEMO
    ├── stage-05.lifecycle.spec.ts      # @exchange
    ├── stage-06.history.spec.ts
    ├── stage-07.sms.spec.ts
    ├── stage-08.news.spec.ts
    ├── stage-09.settings.spec.ts
    ├── stage-10.reliability.spec.ts
    └── stage-12.live-pilot.spec.ts     # runs only with explicit LIVE_PILOT=1
```

## Rules

- Test titles carry QA IDs: `test("QA-4.07 kill switch from running state", …)`.
- Full regression (`npx playwright test`) must be green to close any stage.
- `@exchange` suites use real Binance DEMO; SMS/LLM are mocked (one recorded real call
  per stage, run manually).
- No `waitForTimeout`; no retry-masking of flakes; artifacts (trace/video) on failure.
