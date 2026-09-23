# Production strategy fixes — September 15, 2026

Owner explicitly authorized deploying the reviewed fixes. Release `83ddaf8` on
`charithm/fix/strategy-paths-20260915` contains the Atlas 5.2 public/prepared path
correction and environment-scoped monthly halt lookup, associated regressions,
and audit documentation. This is an owner-authorized branch deployment; it is not
a main-branch merge or remote CI claim. Prior release was `e0bf690`.

## Release gates and preflight

The preceding full local regression passed 341 tests; three credential-gated live
exchange tests were skipped. Backtesting tests: 18 passed. Ruff lint/format, mypy
and four import-boundary contracts passed. A 19,710-decision three-plugin comparison
matched public and prepared entrypoints. See `ALL-STRATEGY-PATH-AUDIT-2026-09-15.md`
for limitations. This deployment separately verified dependency lock/export parity.

Fresh VPS inventory found the owning checkout clean, healthy database/worker/
scheduler, and 91 GB free disk. Signed Binance requests confirmed flat LIVE state,
zero regular and conditional open orders, matching zero open database trades.
Balance: 190.18202024 USDT. Active run 14 uses Atlas 6 Trail release 1.0 and had no
stop timestamp/reason. September long halt true, short halt false. This check was
repeated immediately before cutover. No test order or account mutation was used.

## Backup, image and rollback

The protected release directory is `/home/cmmrox/crypto-pilot-releases/83ddaf8/`.
It contains the source bundle, detached build worktree, previous environment,
container/image/mount metadata, build log, cutover timestamp and executable rollback
script. Previous images are retained as `cryptopilot-backend:rollback-83ddaf8` and
`cryptopilot-deadman:rollback-83ddaf8`. Rollback recreates only those two services
through an explicit image override; it does not restore the database or alter risk.

The existing backup container produced `cryptopilot-pre-83ddaf8.sql.gz.enc` and its
HMAC in the existing continuous backup directory. HMAC verification and decrypted
gzip integrity passed. This is not a new restore-to-database drill.

The release image was built from the isolated committed source using the existing
Dockerfile and locked dependencies:

`sha256:db1bd3e2592489f2adb6b3d48ccec089b70327934dc98b262c8c2ff459e74c12`

A network-disabled, non-serving candidate container passed the long-only regression
and public/prepared check. All three manifests matched the preceding live image
exactly; source hashes matched the tested local files.

## Cutover

Only backend and deadman are targeted with the existing production Compose files.
Frontend, proxy, backup, shared database, networks, credentials and unrelated
applications are outside the cutover. No Lab service or frontend change is included.
No migration changes are present; startup's normal Alembic invocation is expected
to remain at `b7c8d9e0f1a2`.

Final live verification is recorded below.

## Completed verification

Cutover began 03:37:41 UTC (09:07:41 Sri Lanka). Startup ingestion completed with
zero gaps; the API returned HTTP 200 and backend health became healthy. Backend
and deadman both run the release image above with zero restarts. Deep health at
03:39:37 UTC reports healthy database, worker and scheduler, no overdue ingestion.
No WARN/ERROR events were recorded in the cutover window.

Fresh signed account verification at 03:39:33 UTC matched the pre-cutover snapshot:
LIVE run 14, Atlas 6 Trail 1.0, no stop reason, flat account and database, zero
regular/conditional open orders, unchanged 190.18202024 USDT balance. Long monthly
halt remains true, short halt false. All manifest fields and schema version
`b7c8d9e0f1a2` match exactly. Deployed source hashes match the tested release image.
The persisted decision cursor remains September 14 20:00 UTC, the latest candle
closed before cutover; no new closed-candle trade was forced as a deployment test.

Container-ID comparison confirms exactly backend and deadman changed. Frontend,
Caddy, backup and every unrelated running container retained their IDs. No Lab
service was introduced. VPS checkout is on the authorized release branch at
`83ddaf8`; main was not merged or rewritten.

Future scheduled candle execution and a future real entry/exit are not certified
by this immediate post-deployment check. The completed local regression and live
pre/post account evidence are separate evidence layers. Backup authentication and
integrity were checked; no fresh restore drill or real-SMS/browser login was run.

## Subsequent merge to main

Release `83ddaf8` reached `main` on September 22, 2026 through PR #2 (merge commit
`2cb7f98`), as the parent of the Atlas 7 Dual release. The merge is a repository event
only: it did not deploy anything, and production continues to run the `83ddaf8` image
recorded above. Because `83ddaf8` is now an ancestor of `main`, a future deployment
of `main` from the VPS checkout can fast-forward instead of switching branches.
