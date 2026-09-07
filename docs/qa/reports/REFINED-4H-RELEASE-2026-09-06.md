# Refined four-hour release — implementation and local QA

Date: 2026-09-06. Branch: `charithm/feature/experiment-lab`.
Scope: local implementation and acceptance, **not a VPS deployment or live activation**.
Existing unrelated Experiment Lab work has been preserved; no commit/merge was made.

## Release and architecture

- ID `trend_rider_refined_v1_4h`, release `1.0`, display `Refined live settings · 4h`.
- Only change from the existing v6 profile: long trailing distance **4 → 4.5 ATR**.
- Initial stop 2.5 ATR, TP1 40% at 1R, long risk 15%, leverage ceiling 6, separate
  4% monthly breakers, all indicator parameters and the stop-free short unchanged.
- Original `trend_rider_v6_4h` remains packaged default; its legacy aliases still
  resolve to the original. No settings migration or automatic selection is included.
- Pure shared `RefinedTrendRider` subclasses the existing shared `TrendRider` decision
  implementation. The backend plugin is only a registry adapter. No strategy-specific
  branch was added to scheduler, risk, execution, database, or API routing.
- Constructors pin parameters; a parameter snapshot regression protects against
  future default drift. Selection requests reject extra/override fields.
- Generic Settings renders immutable parameters, explanations and caveats from each
  manifest. The confirmation explicitly says stopped and flat, next reconciled start,
  no automatic bot start and no environment change. Loading errors are visible with Retry.
- Existing selection audit now includes release, symbol, interval and parameters.
  Decision telemetry already includes release, candle/history hash, state and intents.
- Selecting a release is not starting it. The existing bot-start exchange-readiness,
  reconciliation, environment and credential gates remain authoritative.

## Replay discrepancy found and fixed

The historical OHLC simulator previously retained unrounded long stop/TP prices,
whereas BotService/OrderManager use exchange tick-size half-up rounding. A failing
regression reproduced this (`97.836` simulated stop vs `97.8` valid exchange stop).
Both offline reference and production-plugin replays now use the shared `round_price`
function for initial stop/TP and trailing prices. Live order behavior was **not**
changed to match the less accurate simulator. Frozen `research/` was untouched.

Before the repair, the registered refined plugin reproduced the researched result
exactly through its public closed-candle method: $200 → $1,643.194622229188699309372000.
After the repair: **$200 → $1,643.200415351385582742800000**, still 105 closed trades
and flat at the end. Prior artifacts remain immutable; do not silently relabel their
execution model. The change is about execution precision, not new optimization.

## Historical acceptance

Actual retained Binance BTCUSDT 4h candles/funding, 2023-09-01 00:00 UTC through
2026-09-01 00:00 UTC exclusive, 400 warm-up bars, $200 initial capital, no withdrawals,
per-side fee/slippage allowance 0.0006. The common reconciled dataset is
`b647dc3d1af717e21943b9a9cbbc00dbb76ffbac26a109d89d054d8177b1ec13`.

Every chronological decision is evaluated through the registered plugin's public
`on_candle()` method, with the production history-window limit. It is compared exactly
with the research prepared-frame method under the same rolling account/trade state.
The entire trade, equity and monthly histories then compare exactly as well.

| Evidence | Observed |
|---|---:|
| Closed-candle decisions checked | 6,576 |
| Decision mismatches | 0 |
| EnterLong / EnterShort | 54 / 51 |
| Short resize intents | 2,080 |
| ExitAll / MoveStop intents | 51 / 399 |
| Closed trades | 105 |
| Ending position | Flat |

Evidence under `.lab-data/refined-release/artifacts/`:

- Original unrounded replication: `cdb09ca304a6ecc02eacfbb23a94378b2e5ed3b38ff1c3056dd462573ea0e251`.
- Tick-rounded replication: `ea1963387c8c7127f800ec7e32b00dea03bcc364ce7386bfd502d3a06f6057ba`.
- Repeat including source hashes: `b242160ee8cf8747e5352ff5d24fa990525d59be59e787ac3f113241b49e41c6`.
- Final type-clean harness repeat: `84ac06e960b020116e50b89ed0402d555659b6e38fa399dbdab7549c3d97e068`.

Reproduce from repository root:

```sh
PYTHONPATH=backend:experiments/experiment_lab/src backend/.venv/bin/python \
  qa/fixtures/refined_release_replay.py \
  .lab-data/timeframe-research/2026-09-06/artifacts/b647dc3d1af717e21943b9a9cbbc00dbb76ffbac26a109d89d054d8177b1ec13.json \
  --output .lab-data/refined-release/artifacts
```

## Verification

- Backend full suite including original frozen-reference parity: **281 passed,
  3 skipped**. Existing timezone warning in frozen research remains.
- Lab and older backtesting regressions after tick repair: **69 passed**, one
  existing Starlette/httpx deprecation warning.
- Frontend unit: **7 passed**; frontend lint/typecheck/build passed.
- Backend Ruff, formatting and strict mypy: passed. Import boundaries: **2 kept,
  0 broken**. Catalog validates **3 plugins**, original v6 default retained.
- New shared release and acceptance harness strict mypy: passed with source paths.
- New integration cases verify audit/persistence, no start or environment mutation,
  blocked running/open-position selection, rejected parameter overrides, refined
  bot-run/trade identity, duplicate-candle protection, TP1 fill synchronization and
  exact tick-rounded 4.5 ATR stop management while in safe mode.
- Full desktop/mobile browser regression: **121 passed, 23 skipped** (3.2 minutes).
  The skips include 16 credential-gated exchange/lifecycle checks, two real SMS
  checks, two opt-in Lab iteration checks, and three desktop-only mutations on mobile.
  The two new refined tests passed selection/cancel/reload, risk/parameter display,
  retained DEMO/stopped state, audit events, restoration and no horizontal overflow.
  The full run preceded the final extra-field rejection/audit metadata backend reload;
  focused strategy/settings regression was rerun on the final backend separately.
  That rerun passed **24 tests, 2 desktop-only mobile skips**. The final in-app
  Browser walkthrough also verified the expanded refined release explanation,
  immutable 4.5 ATR parameter and caveats visually.

Initial new test runs exposed two fixture assumptions (an absent `Trade.stop_px`
attribute and wrong expected rounding direction), then two E2E schema assumptions
(`STOPPED` vs `stopped`, `payload` vs `payload_json`). Those tests were corrected to
the actual contracts. The unrounded replay defect was separately reproduced red
before its production-filter-based fix; it is not merely a changed expected value.

## What this does not certify

This is software decision-path parity plus mocked-exchange integration. It is not
three-year tick/order-book replay, proof of identical live fills, liquidation
survivability, or forward profitability. Candle replay retains the documented
funding mark proxies, current filters applied historically, OHLC intrabar ordering,
and idealized next-open fills. Actual execution depends on mark prices, fills,
latency, liquidity, exchange state and operational availability.

The candidate's later-year loss and worst-month weakness remain; no claim of
consistent passive income or >60% profitable months is made. Monthly breakers are
stand-aside rules, not hard loss ceilings. "Parity verified" means software parity,
not a profitability endorsement. All warnings are available in Settings.

## Deployment and operator handoff

No VPS access, release deployment, credentials change, live strategy selection or
live order action was performed. QA uses the existing isolated local PostgreSQL
`cryptopilot_lab_e2e`, test owner and fake OTP/SMS; only dummy DEMO keys from fixtures
are present. The test lifespan intentionally does not start the trading scheduler.

Before VPS availability: review and package the intended release without accidentally
deploying unfinished unrelated Lab work; perform a fresh read-only VPS/account
inventory, backup and controlled deployment in a stopped/flat maintenance window.
Then verify the deployed catalog/version and complete credential-gated Binance DEMO
order/lifecycle acceptance. Those checks are not replaced by local FakeExchange tests.

After deployment, the owner can open Settings → Strategy library → Refined live
settings · 4h → Select, review the warnings, and separately start the bot after
reconciliation. Do not automatically stop/close an existing position to enable this.
