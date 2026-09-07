# CryptoPilot release regression — 2026-09-07

## Release decision

Local software regression and author code review passed for the Experiment Lab,
shared strategy runtime and refined 4h release working tree. This is a reviewable
release candidate, **not production approval or deployment**. No LIVE orders,
production database writes, real SMS messages, push or deployment were performed.
The open research and operational gates below prevent unconditional production
sign-off. This report supersedes the older implementation report only for the
checks explicitly completed here.

## Failure diagnosis and corrections

The browser and main API were running while the Lab API, replay runner and advisor
were stopped. The Lab requires all three services. A complete local foreground
supervisor now starts the five QA processes together, refuses occupied ports and
stops its own children on failure. Fixture advisor startup tolerates API startup
ordering. Existing real research stores were preserved.

Additional reproduced defects fixed during regression:

- The authenticated gateway dropped upstream 201/202 statuses. It now preserves
  success status, forwards pagination, handles malformed upstream responses and
  retains bounded public errors. Invalid JSON and oversized requests are tested.
- Study/history queries decoded every result and advisor context fetched the entire
  history. Keyset pages, indexes and bounded context now limit large object decoding;
  global totals/best result remain correct when navigating older pages.
- New-study inputs shared state with existing manual iteration controls. A dedicated
  `NewStudyForm` owns its draft. Monetary displays use decimal string formatting.
- Invalid capital could produce HTTP 500; it now produces validation failure.
  Chunked oversized bodies are rejected before Lab JSON parsing.
- Cancellation/lease exhaustion could leave pending jobs without complete audit
  closure. Jobs are closed atomically and terminal audit events are idempotent.
- Artifact fsync failures left temporary files. Failed publication now cleans up.
- Backup/recovery was absent. Online SQLite snapshots now include committed WAL,
  immutable artifacts and trade archives, verify hashes/database/reference integrity,
  and publish atomically to a new path. Corruption, missing files, missing referenced
  datasets, unlisted files and disk-full failures are covered.
- LIVE readiness counted regular orders but missed conditional Algo orders. It now
  checks both across symbols. A pending conditional order blocks first start.
- Eight ORM defaults differed from already-applied migrations. Model declarations
  now match the database; no new PostgreSQL migration was needed.
- Dependency audits found vulnerable transitive packages. Cryptography, pip image
  bootstrap and frontend lock entries were updated; audits now report no known
  vulnerabilities for audited packages. Local application packages have no PyPI
  advisory entry and were reviewed as source.
- CI secret generation could assign the same value to master/JWT keys. It now
  generates each named secret independently without printing them.

## Regression evidence

All commands ran locally against disposable/test data unless explicitly described
as the real provider acceptance. No fixture pass is presented as exchange evidence.

| Check | Result |
|---|---|
| Full backend unit/integration/parity suite | 325 passed, 3 credential-gated exchange tests skipped |
| Lab plus legacy backtesting suite | 83 passed |
| Standalone Lab environment | 65 passed |
| Frontend unit tests | 7 passed |
| Desktop/mobile Playwright | 125 passed, 21 skipped, no retries |
| Backend Ruff, formatting, strict mypy | Passed; 91 source files type checked |
| Lab/shared runtime Ruff, formatting, Lab mypy | Passed; 32 Lab source files type checked |
| Import boundaries | All four contracts passed |
| Frontend lint, TypeScript, production build | Passed |
| Python / frontend / QA dependency audit | No known vulnerabilities in audited packages |
| Redacted gitleaks source snapshot | No leaks found |
| Fresh PostgreSQL migration drill | Upgrade, drift check, full downgrade, re-upgrade and drift check passed |
| Lab SQLite migration | Version 1 to 3, retained data and future-version rejection covered |
| Current backend and Lab Docker images | Built successfully |
| Disposable container acceptance | Scoped auth, actual-public-data replay, idempotency, restart durability, exact reproduction and non-root isolation passed |
| Hardened container runtime | Read-only roots, temporary filesystem, PID/CPU/memory limits exercised for API and runner |
| Compose configuration | Internal API-only network, no published Lab ports, separate worker/advisor egress and no direct database network verified from resolved configuration |
| Backup/restore drills | Two isolated snapshots/restores, including a live WAL store; final drill validates referenced artifacts |
| 10,000-iteration history benchmark | See below |
| Real Codex advisor acceptance | Two explicitly requested cycles completed; SELECT/REPLAY/REVIEW, lessons retained; no automatic next iteration |
| Local supervisor occupied-port guard | Refused startup and preserved existing services |

Playwright covers authentication/session flows, dashboard, settings, strategy
selection, monthly/portfolio/trade/event views, reliability health and Lab creation,
baseline, advised run, reproduction, evidence, responsive layout and history paging.
The 21 skips comprise 16 real DEMO/lifecycle cases, two real SMS cases and three
mobile cases intentionally covered only in the desktop project. These remain skips.
Backend has three real exchange tests skipped because credentials are absent.
The test suites do not exhaust every possible execution path.

Combined backend and browser line coverage: overall **75.07%**, execution **90.70%**,
strategies **95.78%**, risk **100%**. This meets the repository's minimums. The combined
measurement uses the same source revision; it is not unit-only coverage. Remaining
uncovered branches still require review and are not proof of runtime correctness.

The actual Codex check used preserved public Binance data in a new isolated store:
`.lab-data/real-advisor/f302468484d243c1ac458a48028fb87d`. Both results explicitly
reported `suitable_for_live=false`. Model results and local auth files are ignored
and excluded from the commit.

## Performance and architecture review

Synthetic benchmark: 10,000 iterations, each with 36 monthly records, measured with
`qa/fixtures/lab_history_benchmark.py` on this workstation. One sampled run:

| Operation | Time | Peak traced Python allocation | Decoded records |
|---|---:|---:|---:|
| Previous full history access | 2810.83 ms | 148,666,453 bytes | 10,000 |
| History page | 4.59 ms | 342,667 bytes | 20 |
| Advisor history context | 120.15 ms | 339,795 bytes | 21 |

These are synthetic measurements, not production latency guarantees. The exact
Decimal best-profit selection streams scalar metadata and remains O(N); payload
memory is bounded. CPU and disk costs still grow with replay data and archive size.

Reviewed boundaries: pure shared runtime; immutable production strategy wrappers;
Lab domain/application/adapter layers through ports; owner-only allowlisted gateway;
separate advisor process; feature-owned UI state; committed-observation export.
Import-linter enforces strategy purity and news/advisor isolation. Folder ownership
and API/backup contracts are documented in the Lab README and architecture guide.
Frozen `research/` was not modified. Legacy v6 parity and the stop-free short sleeve
are retained. Refined strategy selection remains explicit and blocked while running
or holding an open position. No experiment mutates active strategy parameters.

## Outstanding production gates and limits

1. Remote CI and human PR review have not run for this commit. Production rollout,
   target-host health, immutable-image identity, rollback and soak verification are
   still required. No remote deployment state was inferred from local tests.
2. Credential-backed DEMO order/lifecycle and real SMS acceptance remain unverified
   in this regression. The local fixture uses fake SMS and a clearly labeled advisor.
3. The final Compose network configuration was checked structurally. A complete
   target-host stack drill, advisor authentication under its restricted container,
   sustained resource pressure/OOM recovery and off-host encrypted backup scheduling
   still require deployment-environment evidence. Container smoke used an isolated
   loopback-published bridge because Docker Desktop cannot publish the internal API.
4. Formal untouched holdout/walk-forward evaluation, trial exposure policy,
   liquidation/liquidity survival modeling and complete raw-trade/funding coverage
   remain research gates. Missing or inconsistent public data is rejected. No
   candidate is certified for live activation.
5. Generic multi-strategy Lab registration, richer evidence conflict resolution/
   rollback, dataset-preparation UI, production observation import and the reviewed
   candidate compatibility pipeline remain planned functionality. The current Lab
   is a manually requested research workflow with supplied dataset IDs.
6. SQLite workflow/index migrations are covered; a future stricter relational schema
   and a scale benchmark beyond the measured 10,000 histories are not claimed here.

The author review used `docs/guidelines/CODE_REVIEW.md`: money precision, UTC,
idempotency, error handling, module isolation, parity, secrets, behavior tests,
readability and documentation were checked. This does not replace the required
independent human review before merging to main.
