# Atlas 7 release dependency follow-up — 5 October 2026

## Scope

Main revision `ba6af3631ff43f46195851ec7e1e8f34385c0869` failed release CI at
dependency audits. This separate dependency PR clears those blockers without
changing the Atlas strategy, risk, execution implementation or frozen research.

Backend pins PyJWT 2.15.0 and regenerates the hash-verified production export.
The complete development lock also upgrades urllib3 to 2.8.0. Frontend pins
Vitest 4.1.11, updates its companion packages and locks brace-expansion 5.0.12.
The generated npm graph includes Vitest's updated test dependencies and optional
WASM dependency nesting needed for clean installation. No new direct dependency
or audit suppression is introduced.

Browser QA exposed two test-harness assumptions. Strategy selection now chooses an
inactive release even when Atlas 7 is already selected, and restores the previous
selection. The session installer waits for the previous page's authentication
bootstrap before replacing tokens, preventing late bootstrap failure from clearing
the newly installed session. Product authentication and strategy code are unchanged.

The first remote follow-up run passed backend, frontend, agent configuration and
secret checks. Its browser job failed six public-market checks because Binance was
unreachable from the GitHub runner. CI now explicitly mounts a public-market fixture
through a separate QA-only Compose overlay, retaining the real decoder, API, candle
storage and manual-backfill paths. Guards require isolated OTP-test E2E settings and
disabled LIVE gates; all signed requests and exchange mutations are refused. The
fixture is absent from production images. A mobile navigation selector was also
made exact to avoid confusing the sidebar link with the Overview's ledger link.
This synthetic CI result cannot substitute for actual Binance acceptance.

The cutover notes now record the owner's production deployment request and DEMO
environment choice. A shared local/production DEMO account is permitted only with
one executing bot and flat/order-free exchange truth at acceptance/cutover.

## Verification

| Check | Result |
|---|---|
| Backend pip-audit, full installed locked graph | No known vulnerabilities |
| uv lock integrity and generated production export comparison | Pass |
| Full backend tests, including frozen parity and execution recovery | 422 passed; 3 exchange tests skipped without credentials |
| Backend lint, formatting, strict mypy and import boundaries | Pass; 98 typed files; 4 contracts kept |
| Lab and legacy backtesting tests | 83 passed |
| npm clean installation and audit | Pass; zero vulnerabilities |
| Frontend lint/types and formatting | Pass |
| Frontend unit tests | 12 passed across 3 files |
| Frontend production build, Lab excluded | Pass |
| Backend and frontend production Docker builds | Pass; backend pip check and Atlas 1.2/PyJWT 2.15.0 imports pass; nginx configuration valid |
| Repeated strategy-switch/session cases, desktop and Pixel 5 | 12 passed |
| Full desktop and Pixel 5 browser regression, Lab excluded | 147 passed; 25 intentional skips; no retries |
| Actual Binance DEMO, both long and short | Confirmed fill anchors, CONTRACT_PRICE reduce-only algo stops, lot-floor LIMIT targets, individual stop cancellation/restoration, fresh client/session recovery, no duplicate orders, tracked reduce-only exit and flat/order-free cleanup |
| Agent bootstrap validation and diff whitespace | Pass |
| CI fixture safety/protocol tests | 10 passed; guarded environment, mutation refusal and real candle decoding/pagination |
| Market browser checks against CI fixture, desktop and Pixel 5 | 16 passed; no retries |

Software suites use disposable local PostgreSQL and synthetic account/provider
fixtures. The separate real DEMO probes use the current Atlas 1.2 OrderManager,
adapter and trade synchronizer with another disposable local database. Credentials
are held only in memory; LIVE entry gates stay disabled. DEMO leverage is set to the
manifest's 3x cap. Probe entries and stop distances are controlled QA fixtures, not
natural strategy signals. Additional controlled DEMO amendments produced subtarget
fills on both sides: the original planned TP quantity remained the completion
criterion, with no premature breakeven. Full-target probes observed actual Binance
fill events after reconnect and exercised breakeven replacement and crossed-level
reduce-only cleanup. These checks do not certify natural signal/target touches,
profitability or an order left in PARTIALLY_FILLED status. Real SMS and sustained
stream/forward monitoring remain external acceptance gates; the broad
software suites' credential-gated skips are still accurately reported above.
Detailed command output remains under ignored `output/atlas7-dependency-*`.
The initial browser pass reported 145 passes, 25 skips and the two harness failures
above. Retain that failure log alongside the corrective verification.

## Release limits

Production services, settings, schema and LIVE orders have not been changed.
Preflight found occupied accounts. With explicit owner authorization, the existing
DEMO position was closed reduce-only and its orders cancelled before the probes.
DEMO cleanup is verified flat/order-free after testing. The existing LIVE trade must finish under its
original Atlas 1.1 policy before upgrading or switching production to DEMO.
Do not flatten, cancel or reprice that LIVE trade as part of this preparation.

Release still requires green reviewed CI, actual flat-DEMO long/short lifecycle
acceptance, stopped/flat account ownership transfer, verified encrypted backup,
the additive migration, runtime health and authenticated post-cutover checks.
Follow [the cutover procedure](../../../deploy/atlas7-release-1.2.md).
