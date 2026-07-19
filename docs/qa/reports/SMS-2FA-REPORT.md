# SMS 2FA implementation and release-gate report

**Date:** 2026-07-19  
**Branch:** `feature/sms-2fa`  
**Status:** SMS implementation and focused historical QA recorded; current-snapshot
release gates are still open and the change is **not released to LIVE**

## Delivered scope

- Password login now requires a purpose-bound, single-use SMS OTP whenever the
  owner has 2FA enabled.
- OTP generation, keyed hashing, expiry, attempt limits, resend cooldown, hourly
  send cap, concurrent-request serialization, and challenge invalidation are
  enforced in the backend.
- Enable, disable, and phone-change flows require password reauthentication and
  the appropriate current/new-phone OTP. Security changes revoke other sessions
  and pending challenges and emit durable audit events.
- Break-glass recovery remains server-shell-only. Recovery operations revoke
  sessions and pending challenges and are audited.
- The migration preserves a previously enabled 2FA state so upgrade fails
  closed until a phone is enrolled; downgrade refuses while SMS 2FA is enabled.
- Provider failures use fixed public errors. Logs recursively scrub credentials,
  OTPs, secret assignments, and full Sri Lankan phone numbers.
- Production rejects OTP test controls at configuration load. The E2E code
  mailbox is available only in `CP_ENVIRONMENT=test` and now binds code lookup
  to the exact challenge, avoiding concurrent-login cross-talk.
- The frontend includes the SMS OTP login screen and guarded Security settings
  card for enable, disable, and phone change.
- Python production dependencies are installed from a checked-in, hash-locked
  requirements file; CI uses the frozen lock and pinned audit tooling.

## Verification evidence

The table below is historical evidence from the interrupted implementation
snapshot. It is retained for traceability and is not the release result for the
current working tree.

| Gate | Result |
| --- | --- |
| Backend lock check | Passed (`uv lock --check`) |
| Ruff | Passed |
| Mypy strict | Passed, 70 source files |
| Import boundaries | Passed, 2 contracts |
| Backend unit/integration/parity regression | **170 passed, 3 skipped** |
| Backend dependency audit | No known vulnerabilities; local project is not a PyPI package |
| Frontend lint and TypeScript | Passed |
| Frontend production build | Passed |
| Frontend npm audit | 0 vulnerabilities |
| QA dependency audit | 0 vulnerabilities |
| Playwright discovery | 112 tests in 11 files |
| SMS/auth/settings production-like E2E | **43 passed, 1 intentional mobile skip** |
| Full deterministic Playwright regression | **92 passed, 20 expected skips** |
| Hash-locked Docker image build | Passed |
| Isolated-stack health through Caddy | Passed (`database=ok`) |
| Frozen research tree | Unchanged |
| Migration upgrade/downgrade probes | Passed: enabled-state fail-closed upgrade; unsafe downgrade blocked |

## Current working-tree verification

After an independent review of the interrupted branch, the following additional
release blockers were fixed:

- notify.lk `user_id` is encrypted and legacy plaintext credential slots are
  migrated and cleared before the application serves traffic;
- credential-status routing can no longer reinterpret the notify.lk row as a
  Binance credential and break OTP delivery;
- simultaneous 2FA settings confirmations use a consistent owner→challenge lock
  order and observe current owner state;
- manual session revocation is durably audited;
- browser token establishment is atomic when the post-issue identity check fails;
- sensitive password/OTP 401 responses are not transparently retried;
- CI has guarded idempotent fixtures, a failing health timeout, schema-drift
  detection, and Playwright failure artifacts;
- backup/restore tooling targets the external PostgreSQL topology, authenticates
  ciphertext before restore, keeps key material out of process arguments, and
  bounds local temporary files.

Fresh checks on the combined working tree:

| Gate | Current result |
| --- | --- |
| Ruff | Passed |
| Mypy strict | Passed, 71 source files |
| Import boundaries | Passed, 2 contracts |
| Backend unit + parity tests | **90 passed** |
| Frontend lint and TypeScript | Passed |
| Frontend production build | Passed |
| Playwright discovery | **120 tests in 11 files** |
| Shell syntax and Compose rendering | Passed |
| Frozen research tree | Unchanged |
| Integration/full browser/container regression | Blocked in the managed task because Docker socket access is denied; must pass in CI on the committed snapshot |
| Online dependency audits | Blocked in the managed task by restricted DNS; must pass in CI |
| Exact-snapshot security scan | Pending |

The focused E2E run used a fresh isolated PostgreSQL/backend/frontend/Caddy
stack on port 8091 with test-only SMS capture. It covered foundations, password
and SMS login, invalid OTP, logout, session persistence, anonymous authorization,
login limits, security headers, DEMO/LIVE guard UI, 2FA disable guard, and a
new-phone verification round trip that restored the original test number.

## Full E2E regression

The complete 112-test Playwright inventory was executed against the isolated
stack. The first clean-database pass exposed missing historical E2E fixtures:
the Stage 6 July trades/orders/monthly ledger and the Stage 7 notify.lk status
row do not come from migrations, and initial candle backfill had not completed
before the first Stage 2 assertion.

Only documented synthetic Stage 6 rows, a synthetic ingest event, and placeholder
test-mode notify.lk configuration were then loaded into the isolated database;
no production data, credentials, or user stack were touched. The complete suite
was rerun and finished **92 passed, 20 expected skips, 0 failures**.

That manual fixture setup was not reproducible CI evidence. The current branch
now provides the guarded, idempotent `python -m app.e2e_seed` command and invokes
it from CI before Playwright. The reported counts above remain historical until
the updated workflow is run against the exact committed snapshot.

The skips are deliberate: Binance DEMO order/lifecycle cases require externally
supplied DEMO credentials, the real-SMS case requires explicit opt-in and real
notify.lk credentials, and two state-changing cases run only once on desktop.
Their previously recorded live acceptance remains in the stage reports, but no
external credential was copied into this isolated SMS verification stack.

## Security review

A diff security review inspected authentication, OTP, recovery, migration,
logging, notification, scheduler, deployment, dependency, frontend, and QA
surfaces. Twelve plausible candidates were reproduced or source-traced and then
remediated; none survived the post-fix attack-path review. The initial scan
could not be sealed because remediation changed the working-tree snapshot, as
expected. A new final-snapshot workbench was opened and requires the working-tree
selection and **Start scan** action before its canonical report can be sealed.

## Release decision

**No LIVE release was performed.** This is mandatory, not optional:

1. Stage 11 still requires a real VPS deployment, a continuous **at least
   four-week Binance DEMO soak**, and owner sign-off.
2. Stage 12 then requires controlled LIVE credential installation and its pilot
   gates. No LIVE keys may be introduced before that point.
3. This branch has no configured Git remote, so there is no reviewed PR/release
   channel to promote from.
4. The exact-snapshot security scan and the now-automated fixture-backed full E2E
   regression must be green on the reviewed commit before release approval.

The current implementation is suitable for continuing the DEMO acceptance
process only. It must not be represented or deployed as a completed LIVE
release.
