# Dashboard Command Center Implementation Plan

**Status:** Complete — implementation and full QA passed 2026-07-19
**Owner-selected visual:** `docs/design/dashboard-command-center-reference.png`
**Feature branch:** `charithm/dashboard-command-center`
**Affected stages:** Stage 2 market data, Stage 5 lifecycle/Overview, Stage 8 news,
Stage 10 reliability
**Source of truth:** `docs/BUSINESS_SOLUTION_v2.pdf`, with
`docs/architecture/ARCHITECTURE.md §8` deviations

## 1. Outcome

Replace the sparse Overview with the selected owner command center so the owner can
answer, without navigating elsewhere:

1. Is the background worker actually alive now?
2. Which symbol and timeframe are active?
3. What is the current Binance mark price and how fresh is it?
4. When will the strategy evaluate again?
5. Which long and short conditions are currently being watched?
6. What happened recently?
7. What is today's informational market briefing?
8. What are the account, position, and independent breaker states?

The dashboard explains possible rule outcomes; it never predicts a trade. Strategy
decisions remain restricted to closed 4h candles.

## 2. Non-negotiable product rules

- Binance remains the source of truth for account and mark-price state.
- Money and price values cross the API as decimal strings.
- A five-second worker pulse proves the ingest task and event loop are alive between
  four-hour closes; the existing dead-man tick remains a separate 4h safety signal.
- "Live" is shown only while the response and worker pulse are fresh. Failed refreshes
  retain the last response but visibly mark it stale.
- Strategy-watch data is a read-only projection of the validated indicator engine. It
  must never feed intents, risk, sizing, or execution.
- The short sleeve remains stop-free, volatility-sized, and protected by its
  independent monthly breaker plus closed-candle cover logic.
- News remains read-only human context, isolated from trading.
- Start, stop, stop-and-close, and typed `FLATTEN` controls keep their current guarded
  server-confirmed behavior.
- No files under `research/` are modified.

## 3. Deliverables and file locations

### Backend

- `backend/app/bot/ingest.py`
  - Maintain an in-memory five-second worker heartbeat from the actual ingest task.
  - Expose heartbeat timestamp/age without creating high-frequency database events.
- `backend/app/execution/binance_client.py`
  - Add the public, symbol-scoped USD-M mark-price request
    (`GET /fapi/v1/premiumIndex`, request weight 1).
- `backend/app/services/overview_service.py`
  - Build the command-center projection from account truth, mark price, candles,
    scheduler state, recent events, breakers, and the latest briefing.
  - Calculate thresholds from the existing validated indicator functions.
- `backend/app/api/overview.py`
  - Keep the router thin and return the expanded typed response.

### Frontend

- `frontend/src/api/client.ts`
  - Add the typed command-center contract.
- `frontend/src/views/Overview.tsx`
  - Implement the selected layout and all loading, empty, degraded, stale, running,
    stopped, safe-mode, flat, long, and short states.
- `frontend/src/styles/index.css`
  - Add responsive command-center grids and match the approved dark control-room
    reference at desktop, tablet, and 390px mobile widths.

### Documentation and QA

- `docs/plan/IMPLEMENTATION_PLAN.md`
  - Record the approved Stage 5 command-center enhancement and QA IDs.
- `docs/architecture/ARCHITECTURE.md`
  - Record the read-only strategy-watch projection and worker-pulse distinction.
- `docs/architecture/INTEGRATIONS.md`
  - Record the verified mark-price endpoint and request weight.
- `qa/e2e/stage-05.lifecycle.spec.ts`
  - Extend owner-visible command-center acceptance coverage.
- `backend/tests/unit/`
  - Cover mark-price parsing, worker-heartbeat freshness, and watch-state boundaries.
- `backend/tests/integration/`
  - Cover the authenticated aggregate contract and degraded behavior.
- `design-qa.md`
  - Compare the selected reference to a browser capture at the same 1672×941 viewport.

## 4. API contract

`GET /api/overview` remains the four-second polling source and adds:

- `checked_at`, `fresh_for_seconds`
- `engine`: worker running/healthy, heartbeat timestamp/age, scheduler status,
  ingest tick, dead-man state, database state, candle-gap count
- `market`: symbol, interval, mark price, 24h change percent, mark timestamp,
  recent closed-candle sparkline, next-close timestamp/countdown
- `watch`: last closed candle, indicator values, three owner-facing rule rows,
  threshold distances, and the "closed candle, not prediction" disclaimer
- `activity`: recent permanent events plus ephemeral response/market heartbeat entries
- `briefing`: latest sentiment, up to three bullets, generated timestamp, and the
  mandatory isolation notice
- existing account, position, breaker, and monthly P&L fields

If public market data fails, account and persisted sections still render while market
and strategy-watch surfaces explicitly degrade. If authenticated account access fails,
public mark/health/news/watch data still renders and the account surface is marked
unavailable.

## 5. Strategy-watch definitions

Using the last 200 or more persisted closed candles:

- **Long regime:** last close above SMA200 and EMA50 above EMA200.
- **Pullback resume:** a close below EMA20 occurred in the active bull-regime run and
  the latest closed candle reclaimed EMA20.
- **Deep-bear short:** close below SMA200, EMA50 below EMA200, and close below
  `SMA200 - 0.5 × ATR14`.

Threshold distance is `mark - threshold`, returned as signed decimal value and signed
percent of the threshold. It describes current distance only; it is not an execution
price or forecast.

## 6. UI structure

1. Existing header and guarded lifecycle controls.
2. Full-width live-engine status rail.
3. BTCUSDT market card with mark, 24h change, freshness, and sparkline.
4. Next-decision countdown card.
5. Today's briefing card.
6. Strategy-watch panel with three status rows and disclaimer.
7. Recent-activity timeline.
8. Four account-stat cards.
9. Position card and independent breaker panel.

The desktop target follows the approved 1672×941 reference. At narrower widths the
market, briefing, strategy, activity, stats, position, and breaker regions collapse in
reading order without hiding controls or introducing horizontal overflow.

## 7. QA cases

- **QA-5.05 — Worker pulse proves background liveness**
  - With the ingest service running, Overview shows a fresh heartbeat and healthy
    background worker.
  - With a stale/missing pulse, it shows degraded—not live.
- **QA-5.06 — Market and next decision are truthful**
  - Shows BTCUSDT, 4h, Binance mark price, source timestamp, 24h change, next UTC close,
    and a decreasing countdown.
- **QA-5.07 — Strategy watch explains conditions**
  - Shows long regime, pullback resume, and deep-bear short rows from seeded closed
    candles, with thresholds and the non-prediction disclaimer.
- **QA-5.08 — News and activity are present but isolated**
  - Shows up to three briefing bullets and the read-only isolation notice.
  - Recent owner events remain navigable to the Event ledger.
- **QA-5.09 — Degraded and stale states are honest**
  - A failed poll or market call never leaves a frozen value styled as live.
- **QA-5.10 — Responsive and accessible command center**
  - Desktop matches the reference hierarchy.
  - Mobile has zero horizontal overflow and all controls remain keyboard/touch
    reachable with text-plus-color state cues.
- **QA-5.11 — Existing guarded controls regress green**
  - Start/stop/stop-close/kill confirmations and safe-mode behavior remain unchanged.

## 8. Validation gates

Run narrow checks first, then:

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

Also rebuild the Compose stack, verify `/health/deep`, capture desktop and mobile
screenshots, check browser console errors, run design QA until
`design-qa.md` says `final result: passed`, then self-review with
`docs/guidelines/CODE_REVIEW.md`.

## 9. Merge gate

Merge to `main` only when:

- all implementation and documentation deliverables exist;
- all QA-5.05 through QA-5.11 evidence is green;
- full backend, parity, lint, type, import-boundary, frontend build, and Playwright
  regression gates pass;
- design QA passes with no P0/P1/P2 findings;
- the feature branch is committed with a conventional commit;
- the merged `main` tree is rebuilt/rechecked and contains no uncommitted changes.
