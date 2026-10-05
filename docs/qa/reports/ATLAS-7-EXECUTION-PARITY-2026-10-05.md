# Atlas 7 execution parity — local QA, 5 October 2026

## Verdict and scope

Atlas 7 Dual release 1.2 is implemented locally on
`charithm/fix/atlas7-research-execution`, based on `ad5eb2a`. Local software checks
pass. Production has not been deployed, and this report does not close the real
DEMO exchange acceptance or Stage 12 LIVE certification gates. This publication-safe report records validation and release limits; detailed
research and account artifacts remain local.

The authoritative rule mapping is
[ATLAS_7_EXECUTION_CONTRACT.md](../../strategies/ATLAS_7_EXECUTION_CONTRACT.md).
The approved signals, 4% risk, 3x leverage cap and independent 8% monthly breakers
remain unchanged. Frozen `research/` and the MIR reference engine are untouched.

## Findings corrected

| Finding | Correction | Regression evidence |
|---|---|---|
| Targets based on pre-fill price | Initial stop and TP1 anchored to confirmed market fill, then tick-rounded | `test_atlas_execution_contract.py`, both sides |
| Partial quantity rounded by decimal precision / nearest lot | Floor against actual LOT_SIZE step; display actual fraction | Contract tests; zero-lot recovery test |
| Breakeven delayed until next 4h evaluation | Fill-driven account recovery moves remaining stop to entry after the full planned TP1 fills | Contract and worker tests, both sides; partial-fill test |
| Stop trigger differs from traded-price research | Atlas 1.2 uses CONTRACT_PRICE conditional algo stops | Contract/projection tests; adapter wiring reviewed |
| Accepted replacement can be lost after interruption | Persist PENDING intent before submission; query same client ID on recovery; confirm replacement before retiring predecessor | Crash-after-acceptance and cancel/fill race tests |
| Cancelled protection or crossed replacement | Restore last ratchet without widening; crossed-stop rejection flattens remaining reduce-only | Recovery tests |
| TP placement failure can roll back confirmed protected entry | Commit entry/stop first; persist pending TP; recover ambiguous placement by ID; known rejection remains visible and blocks entries | TP rejection regression |
| Lot-floor TP1 can become zero | Virtual target enables the research trail at a completed candle; no zero-size order or breakeven without a sale | Recovery and ATR-expansion tests |
| Fixed scheduler delay / missing old history | Finalized kline wakeup, +1s REST fallback, bounded retry, all-history gap repair, duplicate cursor and stale-entry guard | Stream/window tests; paginated repair of 1,601 gaps including beyond last 500 bars; incomplete rows rejected |
| Flat intrabar exit loses monthly book attribution | Absolute per-book fill/fee/funding ledgers and explicit month baseline; breaker valuation uses completed candle close | Independent hourly oracle including month rollovers |
| Console omits targets or incorrectly treats every short as stop-free | Exchange-confirmed stop/TP truth on Overview; prices, quantities, fill facts and release on trade details; missing protection warning | Projection integration tests and desktop/mobile browser checks |

Recovery continues in safe mode. Websocket messages only wake REST reconciliation;
duplicates/reordering cannot directly change quantities. Failure blocks entries,
records an event and notifies once on transition. Listen-key lifecycle and API-key
rather than trade-signature authentication are covered. Lifecycle controls and
trading share a mutex through commit/rollback; deployment requires one backend worker.

## Verification results

| Gate | Result |
|---|---|
| Full backend pytest | 422 passed; 3 credential-gated DEMO tests skipped |
| Mandatory frozen research parity (`pytest -m parity`) | 3 passed; zero mismatches |
| Independent production-path hourly oracle | 4,920 hourly equity observations; 1,230 historical 4h bars; all 21 reduction events match reference hour, side, quantity and price; equity tolerance 0.00001 USDT |
| Lab + legacy backtesting regression | 83 passed |
| Backend/shared runtime lint and formatting | Pass |
| Backend strict mypy | 98 files pass |
| Import boundaries | 4 kept; 0 broken |
| Lab lint/format/types | Pass; 32 typed files |
| Scratch PostgreSQL migrations | Upgrade head, schema drift check, downgrade base, upgrade head, drift check all pass |
| Frontend lint/typecheck, Prettier, production build | Pass |
| Frontend unit tests | 12 passed across 3 files |
| Full Playwright desktop + Pixel 5, Lab enabled | 151 passed; 21 intentional skips; zero retries |
| Focused protection UI after final formatting/build | 8 passed |
| Native @Browser | Test-mode OTP login; Atlas 1.2 selection and expanded configuration verified |
| Shared agent setup / diff whitespace | Pass |

Full browser skips: 16 credential-gated DEMO account/execution checks, 2 real-SMS
checks, and 3 mobile duplicates of once-only security/withdrawal mutations. These
are open external checks, not passing exchange/SMS results. Backend's three skipped
tests likewise require dedicated DEMO credentials. The backend parity suite emits
its existing pandas timezone-period warning; the Lab suite emits an existing
Starlette/httpx deprecation warning.

The independent oracle uses unchanged `mir.strategies:dual` and `mir.engine:run`,
not the production strategy to manufacture expected values. Input/metadata builder:
`qa/replay/build_atlas_oracle.py`; runtime reference:
`qa/replay/run_atlas_oracle.py`. The isolated reference process disables only numba
compilation, executing original engine/strategy expressions unchanged as plain Python.
Its equity/trade arrays were checked against the prior JIT reference within 1e-8.
Expected results are calculated during testing rather than published as fixtures.
Source/input hashes are pinned and checked in
`backend/tests/fixtures/atlas7_execution_oracle.json`. Period: 1 March through
21 September 2026. It includes actual funding observations, configured maker/taker
fees, a 400-bar warmup, month changes, TP1 and trailing exits. Its 0.0001 quantity
step and 1e-8 price ticks isolate continuous research rules; exchange lot/tick
rounding and zero-lot handling are separately tested. This is a historical OHLC
simulation with stop-first ordering when both levels touch in one hour, not a tick,
order-book, latency, liquidity, liquidation or profitability certification.

## Browser artifacts and local environment

The production Vite bundle runs at `http://localhost:5173`, proxied to the isolated
QA backend on `127.0.0.1:8000`. PostgreSQL is our separate QA container on loopback
port 55432; migrations use a second scratch database. LIVE gates are false. The
QA fixture has synthetic account/provider data and test-mode OTP. Background
scheduler/news/protection services are disabled by the existing test-mode lifespan;
worker behaviour is exercised through real worker transactions with FakeExchange
and PostgreSQL. The console can therefore show scheduler degraded in this fixture.
Atlas 1.2 is selected; the bot is stopped. This is a UI/test environment, not a
configured exchange trading environment. Lab API/runner/fixture advisor run locally;
its synthetic advisor is not model-capability evidence.

Long desktop and short mobile screenshots are retained under ignored
`output/atlas7-qa/screenshots/`. These panels use deterministic Playwright response
fixtures through the real owner
console and authentication; backend projection tests independently verify exchange
order mapping. They are not screenshots of a natural Binance trade.

Command output is retained locally in `output/atlas7-backend-qa.log`,
`atlas7-parity-qa.log`, `atlas7-browser-qa.log`, `atlas7-target-browser-qa.log`,
`atlas7-lab-qa.log`, `atlas7-migration-qa.log` and `atlas7-frontend-qa.log`.
No credentials are included in committed fixtures or this report.

## Remaining release gates

Dedicated flat-DEMO exchange acceptance remains pending. No exchange
position/order was changed in this task. A dedicated flat account is required for
natural long/short entry, algo-stop acceptance, TP partial/full fills,
breakeven, reconnect/restart and final flat/order-free verification. Real SMS,
container image/remote CI certification, operational restore/soak and LIVE forward
monitoring are not claimed by this local report.

A real exchange cannot guarantee the research's exact next-open fill or zero-latency
stop movement. User-stream events plus five-second REST recovery reduce the software
wait; outages and exchange latency still require acceptance/monitoring.

Existing Atlas 1.1 positions keep their original policy; deployment waits until the
account is flat/order-free. Owner production approval is still required. The concrete
cutover and rollback procedure is
[atlas7-release-1.2.md](../../../deploy/atlas7-release-1.2.md).
Self-review covered Decimal/UTC, idempotency, stop ratchets, safe-mode boundaries,
legacy short behaviour, isolation, migration reversibility and honest UI states.
