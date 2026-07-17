# Test Case Writing & Testing Guidelines

Process and stage gates: `docs/qa/QA_STRATEGY.md`. This document is about writing
*good* tests.

## What to test, at which layer

- **Unit** — every strategy rule, sizing formula, breaker condition, template render,
  reducer. Pure logic gets exhaustive unit coverage including boundaries (equal
  closes, zero ATR, month rollover at 00:00 UTC on the 1st, warmup edge).
- **Parity** — the whole strategy, against history. Not a sample: all bars, all
  decisions, zero tolerance.
- **Integration** — anything crossing a boundary: API+DB, reconciler+mocked exchange,
  notifier retries, WS push. Real Postgres (testcontainers), mocked externals.
- **E2E (Playwright)** — user-visible behaviour per QA test case ID. Real stack; real
  Binance DEMO for execution suites; mocked SMS/LLM.

## Writing rules

1. **Test names state behaviour**: `test_sleeve_resize_skipped_below_20pct_drift`,
   `test("QA-5.03 stop&close flattens then stops")`. A failing name should tell you
   what broke without opening the file.
2. **Arrange–Act–Assert**, one behaviour per test. Multiple asserts are fine when they
   describe one outcome (order row + event row + SMS attempt).
3. **Assert side-effects, not implementation.** Check the DB row, the event payload,
   the exchange call — not internal method calls. Mock at module boundaries only
   (`BinanceClient`, `SummaryProvider`, `SmsGateway`, `TimeProvider`).
4. **Determinism is sacred.** Injected clock, seeded data, no sleeps, no ordering
   assumptions. Flaky = broken: fix or delete, never retry-mask.
5. **Money asserts compare Decimal strings** (`assert pnl == Decimal("126.48")`);
   float comparison of money is a review-blocking bug even in tests.
6. **Fixtures are minimal and named for their scenario** (`open_short_state`,
   `month_with_tripped_long_breaker`) — no thousand-line fixture dumps.
7. **Negative paths are first-class:** every guard (auth, environment switch, breaker,
   reconcile mismatch, kill switch) has tests proving it *blocks*.
8. **Every bug → regression test first**, failing before the fix, referenced in the
   fix commit.

## Coverage policy

Coverage is a smoke detector, not a target: ≥90% on `strategies/`, `risk/`,
`execution/` (the money paths), ≥75% overall backend. Uncovered money-path lines fail
CI. Frontend: logic (stores, formatters, api client) unit-tested; components covered
via Playwright rather than shallow snapshot tests. No test theater — a test without a
meaningful assertion is deleted.

## Playwright specifics

See `QA_STRATEGY.md §3` for conventions. Additionally: prefer role/label locators over
CSS; keep specs independent (each seeds its own state); tag slow DEMO-hitting suites
`@exchange` so CI can schedule them; screenshot assertions only for layout-critical
panels (position card, breaker meters) with generous thresholds.
