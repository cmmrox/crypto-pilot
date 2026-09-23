# Production update without Experiment Lab — 2026-09-07

Owner explicitly authorized deploying the application to the existing VPS and
excluding Experiment Lab. Release source: `117e6675f25079fff9c287a0a117710a6f227550`,
built on the VPS from a Git bundle of the locally tested branch. This is a direct
owner-authorized deployment; no main-branch merge or remote CI pass is implied.

## Scope and preflight

Target: `/home/cmmrox/crypto-pilot`, existing Compose project `cryptopilot` using
`docker-compose.yml` and `docker-compose.ops.yml`. Five services: backend, frontend,
Caddy, deadman and backup. Existing shared PostgreSQL, network, proxy, credentials,
Codex volume and backup location are preserved. No Lab overlay or Lab containers.

Initial source `a28b567` was clean. All five containers were running and backend deep
health was OK. The account was LIVE on `trend_rider_v6_4h`, run 12. Signed Binance
read-only requests confirmed zero nonzero positions, regular orders and conditional
Algo orders; the database reported zero open trades. Alembic was already at
`b7c8d9e0f1a2`, the same head as the release; no migration change is required.

## Release preparation

An encrypted database snapshot was created using the existing backup container at
`/home/cmmrox/backups/cryptopilot-continuous/cryptopilot-pre-117e667.sql.gz.enc`, with
an adjacent HMAC. Authentication and decrypted gzip integrity checks passed. This
is not a fresh restore-to-database drill; the full local migration/restore evidence
is in the release regression report.

Prior backend/frontend/deadman images have retained `rollback-117e667` tags.
Protected previous environment, previous commit/image identities, build logs and
rollback script reside under `/home/cmmrox/crypto-pilot-releases/117e667/`. No secret
values are recorded in this report or Git. New images were built in a detached
release worktree while the previous containers kept serving traffic.

The default frontend build now excludes the Lab lazy-loaded page and hides its
navigation/route. The experimental Compose overlay explicitly enables the build
flag. Both build variants, frontend lint/types and seven frontend tests passed.
The production backend Lab URL and token are cleared; existing trading configuration
is retained. The full prior regression is documented in
[the September 7 report](RELEASE-REGRESSION-2026-09-07.md).

## Completed deployment and verification

Cutover completed around 01:42 UTC. Backend, frontend and deadman were recreated;
Caddy and backup remained running. Startup fetched 6,770 closed candles with zero
gaps, then completed successfully. The public API briefly returned 502 during
startup and recovered to 200. The schema stayed at `b7c8d9e0f1a2`.

Verified running image identities:

- Backend and deadman:
  `sha256:c8c66f70ec822458e2861c64d98baf4c26ccad64f847111ba8bb91cbb872fbe2`
- Frontend:
  `sha256:063ea1041d9d5b36d279c72ddac86be16b2ba0717bcf107ea639599875a06b90`

All five services are running; backend is healthy and all three replacement
containers have zero restarts. Deep health reports database OK, healthy worker,
alive scheduler and no overdue ingest. Production environment and disabled Lab
configuration were read back from the running backend. No experimental service was
created. The production frontend image contains no ExperimentLab page bundle.

Existing v6 parameter values, risk policy, market contract and release were compared
between the old running container and new image. They match numerically. The new
runtime exposes additional parameter metadata; values such as Decimal `15` versus
`15.0` are numerically equal. No active strategy change occurred.

Post-cutover database state remains LIVE / trend_rider_v6_4h, run 12, release 6.0,
interval 4h, with no stop timestamp or stop reason. Fresh signed Binance reads
confirm zero positions, regular orders and conditional orders, matching zero open
database trades. No order was submitted as a deployment test.

Browser smoke loaded the public login page after cutover. Authenticated real-SMS
login and a future scheduled candle are not certified by this brief smoke check.
The existing public HTTP configuration was preserved under the earlier accepted
exception; this deployment does not close the outstanding domain/TLS, off-host
backup and long-running trading acceptance gates.

Final smoke checks: public root HTTP 200, unauthenticated strategy API HTTP 401,
browser console zero errors/warnings, deadman healthy with zero consecutive
failures, and no WARNING/ERROR application events in the cutover window.

## Follow-up production deployment: merged main, 08:08 UTC

The owner again requested production deployment without Lab. Deployed merged main
`e0bf69090dd9d1e1943e5e5952fddabdd39b3958` from the clean VPS checkout at `117e667`.
This adds the confirmed trading-environment display and Atlas strategy labels.
The VPS checkout now matches freshly fetched `origin/main`.

Fresh preflight and post-cutover signed Binance reads both showed zero positions,
regular orders and Algo orders, matching zero open database trades. The existing
LIVE run 13 and active `trend_rider_refined_v1_4h` strategy were preserved. Its full
manifest compared equal between old and new images after excluding display name.
No strategy selection, environment switch or test order was performed.

Only backend, frontend and deadman containers were replaced. Caddy, backup and
every unrelated running container retained their IDs. Compose still has exactly
five production services, without the experiments overlay. Backend Lab URL/token
remain empty; the frontend was built with `VITE_EXPERIMENT_LAB_ENABLED=false` and
the image contains no ExperimentLab page bundle.

Rollback images carry `rollback-e0bf690` tags. Previous configuration, image IDs,
source identity, build logs and executable rollback script are protected under
`/home/cmmrox/crypto-pilot-releases/e0bf690/`. The encrypted database snapshot is
`/home/cmmrox/backups/cryptopilot-continuous/cryptopilot-pre-e0bf690.sql.gz.enc` with
its HMAC sidecar. Authentication and decrypted gzip integrity passed; no fresh
database restore drill was performed. Alembic remained `b7c8d9e0f1a2`; there were no
new migrations.

Running image identities:

- Backend/deadman: `sha256:bbd4c250de94c9165a2bb676b089d45de57780acfebb58627482f49e4444592b`
- Frontend: `sha256:78d3f2e4fef03299ec3934b8268924b2ff697e36b40af2a249ac7c5dff2bc7d3`

All replacement containers had zero restarts. Deep health confirmed database OK,
healthy worker, live scheduler and current ingestion. Public root and health
returned HTTP 200; unauthenticated strategies returned HTTP 401. Browser smoke
rendered the production login form with no warning/error console entries.

Fresh local verification: dependency lock/export integrity passed; parity plus
overview/catalog API tests passed (8 tests); frontend lint/types, seven unit tests
and the Lab-disabled production build passed. The existing pytest executable had
a stale interpreter path from the previous repository name; running the same
suite through `.venv/bin/python -m pytest` passed. Prior broader regression is
documented in `ENVIRONMENT-NAMES-AGENTS-2026-09-07.md`; it was not rerun here.
Real-SMS authenticated browser acceptance and future trading outcomes were not
tested during this deployment. Existing infrastructure gates remain unchanged.
