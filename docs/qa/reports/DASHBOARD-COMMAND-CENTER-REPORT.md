# Dashboard Command Center — QA Report

**Date:** 2026-07-19
**Feature branch:** `charithm/dashboard-command-center`
**Scope:** Stage 5 owner command-center enhancement

## Scope Shipped

- Five-second in-process worker heartbeat, age, freshness, scheduler, database,
  market-feed, gap, and dead-man visibility.
- BTCUSDT / 4h market panel with Binance mark price, 24-hour change, observation
  freshness, closed-candle chart, and next UTC decision countdown.
- Read-only Trend Rider v6 watch projection for long regime, pullback resume, and
  deep-bear short conditions, including threshold and mark distance.
- Current isolated news briefing and operational activity timeline.
- Live account metrics, open-position truth, and independent long/short monthly
  circuit breakers.
- Honest loading, stale, unavailable, and refresh-failure states.
- Single-flight four-second polling and database-connection release before exchange
  network waits.
- Responsive desktop and mobile layouts based on the owner-selected screen.

## Automated Evidence

### Backend

- `uv run pytest`
  - **206 passed, 3 skipped, 1 upstream research warning**
- `uv run pytest tests/parity -q`
  - **4 passed, 1 upstream research warning**
- `uv run ruff check app tests`
  - **passed**
- `uv run ruff format --check app tests`
  - **115 files already formatted**
- `uv run mypy app`
  - **passed, 73 source files**
- `uv run lint-imports`
  - **2 contracts kept, 0 broken**

The three skipped backend cases are explicitly marked real-DEMO tests that require
their dedicated external run. The equivalent browser DEMO credential, self-check,
reconciliation, and flatten flows passed below.

### Frontend

- `npm run lint`
  - **passed**
- `npm run build`
  - **passed**
  - Vite reports the existing non-blocking bundle-size advisory.

### Browser Acceptance

- `npx playwright test e2e/stage-05.lifecycle.spec.ts`
  - **18 passed** across desktop and mobile.
- `npx playwright test`
  - **127 passed, 5 intentionally skipped** across desktop and mobile.

The full suite's skips are deliberate duplicate/mobile or externally gated cases:
real notify.lk SMS delivery remains manual/external, while the mutation-heavy cases
run once in the safe project order. Real Binance DEMO credential verification,
self-check round trips, reconciliation, kill/flatten, and lifecycle controls passed.
No LIVE environment or funds were touched.

## Manual and Visual Evidence

- Source: `docs/design/dashboard-command-center-reference.png`
- Desktop: `docs/design/dashboard-command-center-implementation.png`
- Mobile: `docs/design/dashboard-command-center-mobile.png`
- Combined comparison: `docs/design/dashboard-command-center-comparison.png`
- Detailed review: `design-qa.md`
- Final design result: **passed**

The in-app browser verified the authenticated dashboard at 1672 × 941 and 390 × 844,
mobile navigation, safe-stop cancellation, current heartbeat, market freshness,
strategy-watch conditions, news isolation, and the absence of console errors.

## Bugs Found and Fixed

- **Minor:** initial account metrics stacked vertically. Added the missing responsive
  metrics grid.
- **Minor:** page-heading density pushed key owner state below the selected viewport.
  Preserved the semantic heading while matching the selected screen's visual density.
- **Minor:** concurrent interval polls could overlap during slow Binance responses.
  Added a single-flight guard and released database connections before external waits.
- **Minor:** zero-valued Decimal strings could render as `$0E-8.00`. Normalized all
  owner-facing monetary values to fixed decimal strings.
- **Minor:** loading state initially implied “Bot stopped.” It now says “Checking
  status,” disables lifecycle mutations, and waits for authoritative state.
- **Minor:** a guarded lifecycle test acted while the confirmation request was still
  open. The UI closes promptly after a completed mutation, and acceptance waits for
  authoritative Overview state.

## Deviations

- The selected screen shows strategy conditions as three rows. The implementation
  uses three compact cards at desktop width and stacked cards on mobile. The data,
  hierarchy, status, thresholds, distances, and closed-candle warning are unchanged;
  the design QA accepted this density-preserving implementation.
- The public chart uses persisted closed 4h candles while the headline price uses
  Binance mark price. Neither value enters the trading decision path.

## Sign-off

All implementation, documentation, parity, static-analysis, design, Stage 5, and full
browser regression gates required for this enhancement are green. The feature is
ready to commit, merge to `main`, and verify from the merged tree.
