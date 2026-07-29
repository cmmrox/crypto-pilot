# Stage 12 Production Deployment — 2026-07-29

## Decision

**LIVE APPLICATION DEPLOYED; DEPLOYMENT-DAY QA ACCEPTED; FINAL STAGE 12
CALENDAR/INFRASTRUCTURE EXIT REMAINS OPEN.**

The owner authorized production deployment, minimum-size real-money verification,
the immutable `trend_rider_v6_4h` profile, 15% configured long risk, 6x leverage,
and the native volatility-targeted stop-free short sleeve. This report records what
was actually proved on the production VPS. It does not represent elapsed pilot time
or unavailable infrastructure as complete.

## Release identity

- repository: `/home/cmmrox/crypto-pilot`
- branch: `main`
- deployed source and `origin/main`:
  `d1aea00e79c8f50e0c6dee0f61b6e7d6eac4b292`
- backend image:
  `sha256:eb6b1ac6e854c29284f2d903c0a3689ec3560d3809c6bec747b8a933ac27ab32`
- frontend image:
  `sha256:c2cbe0f18a7fcbe6443912528ad5c272768f1bd6127b12a3c38093e52bb92511`
- backend and frontend restart counts after deployment: 0
- database migration: `a6b7c8d9e0f1 (head)`

The shared Odoo PostgreSQL container and unrelated VPS applications were not
recreated or stopped.

## Backup and migration safety

Before deployment the active bot was stopped and confirmed flat. An encrypted,
authenticated backup was created and restored into a fresh scratch database:

- backup size: 72 KiB encrypted plus a 32-byte authentication sidecar
- source events: 137
- restored events: 137
- result: `RESTORE DRILL PASSED`
- scratch database: removed after verification
- protected VPS copy:
  `/home/cmmrox/backups/cryptopilot/cryptopilot-20260729T100626Z.sql.gz.enc`
  with mode 0600

The dedicated `cryptopilot` database role was missing the runbook-required
`CREATEDB` capability. It was granted only that capability so the restore drill can
create and remove its isolated scratch database.

## Secure configuration and credential handling

- `deploy/.env` remains ignored and mode 0600.
- runtime environment is `production`.
- LIVE approval and key-permission gates are enabled.
- OTP test mode and test throttle bypass are disabled.
- LIVE Binance credentials were decrypted only in the existing local backend and
  streamed over authenticated SSH directly into the VPS backend, where they were
  re-encrypted with the VPS master key.
- no plaintext API key or secret was written to disk, command arguments, reports,
  Git, or application logs.
- a dedicated Ed25519 deployment key was installed; its fingerprint is
  `SHA256:uPCFPGziowBykEzqjeBCiZiOrqlxwM6TYgWtnFlA35o`.

## Binance LIVE readiness from the VPS

The production backend independently read Binance immediately before the switch:

- signed account request and clock check passed; observed drift was 118 ms
- API key IP restriction enabled
- reading and USD-M Futures trading enabled
- withdrawals disabled
- spot/margin, transfer, options, portfolio-margin, FIX, and prediction permissions
  disabled
- one-way position mode
- single-asset margin mode
- BTCUSDT isolated margin
- BTCUSDT leverage exactly 6x
- zero non-zero positions
- zero regular or Algo open orders

The guarded application endpoint then recorded `DEMO → LIVE`. The active strategy
remained `trend_rider_v6_4h`, release 6.0, interval 4h.

## Real-money production verification

Two exchange-minimum round trips were placed by the production backend:

1. **LONG 0.001 BTC:** MARKET entry filled and reconciled; the Algo STOP_MARKET and
   reduce-only LIMIT take-profit were visible; individual Algo cancellation,
   cancel-all, reduce-only exit, and final flatten all passed.
2. **SHORT 0.001 BTC:** MARKET entry filled and reconciled; the approved stop-free
   sleeve was covered reduce-only; final flatten and zero-open-order checks passed.

The authenticated production API was then used to start the actual LIVE bot. It
entered `running` with run 3, `trend_rider_v6_4h`, release 6.0, interval 4h. The
LIVE kill endpoint returned success, stopped the run with reason `kill`, and
independently left Binance and the database clean.

Final state:

- active environment: LIVE
- bot: stopped
- Binance positions: 0
- Binance regular/Algo open orders: 0
- database open LIVE trades: 0
- LIVE readiness: pass
- `bot_started` SMS: delivered
- `kill_switch` SMS: delivered
- production ERROR events during this release sequence: 0

The bot was deliberately left stopped. Enabling unattended real-money execution is
an explicit owner operation after reviewing this report and the open infrastructure
items below.

## Service and browser QA

- backend container: running, healthy, no restarts
- frontend container: running, no restarts
- `/health`: HTTP 200 with database `ok`
- root SPA: HTTP 200
- protected unauthenticated API: HTTP 401
- external security headers include CSP, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, and restrictive Permissions-Policy
- headless Chromium loaded the production login surface with the expected title,
  email/password controls, and no console or page errors
- pre-deployment regression remained:
  236 backend tests passed, 53 focused LIVE/lifecycle tests passed, 135 Playwright
  tests passed with 5 documented skips, frontend lint/build/unit tests passed,
  mypy/Ruff/import-linter passed, and backend dependency audit found no known
  vulnerabilities

## Open exit conditions

These items are not software defects in the deployed release, but they prevent a
truthful claim that every Stage 11/12 production exit condition is complete:

1. **TLS/domain:** no production domain or DNS record was supplied. The service is
   reachable only at `http://157.173.96.161:8090`; the production Caddy TLS overlay
   was therefore not activated.
2. **Off-host backups:** no S3-compatible bucket, endpoint, region, or access
   credentials were supplied. The verified encrypted backup is currently local to
   the VPS, not in object storage.
3. **Stage 12 calendar:** the plan requires 4+ elapsed LIVE pilot weeks matching
   DEMO behaviour. Deployment-day QA and the owner's Stage 11 soak waiver authorize
   this pilot but cannot constitute four observed weeks.
4. **Credential hygiene:** the VPS password shared during deployment should be
   rotated now that dedicated SSH key access works.

To close the infrastructure items, the owner must provide a domain whose A/AAAA
record resolves to the VPS and an S3-compatible backup destination. The four-week
pilot can be closed only after the observation period and review evidence exist.
