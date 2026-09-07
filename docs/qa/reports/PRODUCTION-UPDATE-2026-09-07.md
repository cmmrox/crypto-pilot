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
