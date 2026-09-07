# Experiment Lab

Research-only service for manually requested strategy iterations. This is an
in-progress implementation of `docs/plan/STRATEGY_OPTIMIZATION_PIPELINE_IMPLEMENTATION_PLAN.md`,
not authorization to deploy or activate a candidate.

## Ownership and boundaries

- `domain/`: validated requests, bounded parameter contract, deterministic risk
  eligibility and public failure codes.
- `application/`: one iteration coordinator and declarative candidate export;
  persistence/artifacts supplied through ports.
- `adapters/`: SQLite transactions and leases, immutable artifacts, Binance public
  data ingestion and supervised replay.
- `api.py`: private owner/advisor/runner authorization and HTTP contracts.
- `worker.py`: bounded replay subprocess, heartbeat and cancellation. Only the API
  writes workflow SQLite; workers publish immutable artifacts.
- `backend/app/experiment_lab/`: application-owned advisor process and BFF client.
  The advisor does not initialize the trading app, database, exchange or news agent.
- `packages/strategy_runtime/`: shared strategy math and replay contracts. Production
  wrappers retain immutable v6 defaults; experimental parameters never alter the bot.
- `frontend/src/features/experiment-lab/`: one research screen with study inputs,
  iteration history, effective parameters, monthly outcomes and learned evidence.

The first run measures the exact seed. Each later **Run next iteration** requests
SELECT → REPLAY → REVIEW and stops. Manual/reproduction modes bypass selection,
not review. Failures do not trigger a hidden alternative parameter choice. Retry
review preserves the replay. Cancellation fences late workers. Browser command keys
survive uncertain network errors, preventing duplicate runs after retries.

## Configuration

The opt-in `deploy/docker-compose.experiments.yml` overlay defines Lab API, runner
and advisor. It requires three distinct random credentials, at least 32 characters:
`CP_LAB_SERVICE_TOKEN`, `CP_LAB_RUNNER_TOKEN`, `CP_LAB_ADVISOR_TOKEN`.
Never put production exchange/DB/JWT/master-key credentials in these services.

The main app uses `CP_LAB_URL` and the owner-scoped service token. The advisor is
configured in the application with `CP_LAB_ADVISOR_MODEL` and `CP_CODEX_HOME`.
An authenticated Codex session is an operator prerequisite, not embedded in images.
The feature is unavailable by default when the main app Lab URL/token is unset.

Lab environment settings: `LAB_DATA_DIR`, `LAB_SERVICE_URL`, `LAB_SERVICE_TOKEN`,
optional `LAB_RUNNER_TOKEN`/`LAB_ADVISOR_TOKEN` on the API, and
`LAB_REPLAY_TIMEOUT_SECONDS` (default three hours). Dedicated workers receive only
their own scoped token as `LAB_SERVICE_TOKEN`.

## Actual Binance data

Install with `uv sync --frozen` from this directory. Python is pinned to 3.11 to
match the tested container runtime and numerical dependencies. Prepare a dataset with:

```sh
uv run python -m experiment_lab.cli \
  --start 2023-09-01T00:00:00Z --end 2026-09-01T00:00:00Z --interval 4h
```

Supply Lab environment variables first. Paste the returned content-addressed
dataset ID into **New study**. Dates are UTC, end exclusive, candle-aligned. Each
timeframe needs its own verified dataset. The raw response hashes, funding,
warmup and filter snapshot are retained. Current exchange filters applied to old
data remain a disclosed historical assumption.

Candle replay is screening, not actual-fill verification. Trade replay streams
checksum-pinned Binance raw trades (daily partitions for short windows, monthly
otherwise). Aggregate trades can be inspected separately; no ticks are invented.
Trade IDs, chronology and each candle's OHLC must reconcile. Missing funding marks,
archive gaps, checksum failures and OHLC mismatches reject verification. A public
archive is not automatically complete merely because its checksum is valid.
See [Binance's archive contract](https://github.com/binance/binance-public-data).

In a September 2026 QA probe, the 2026-08-01 aggregate archive differed from the
candle open by one tick; the raw archive contained a nonconsecutive trade ID. Those
inputs were rejected, not silently repaired. Candle runs explicitly count missing
funding marks approximated with candle-open prices. Neither mode models order-book
queue position or liquidation. No candidate is currently certified for live use.

## Evidence and operations

`lab.sqlite3` uses WAL, foreign keys, FULL synchronous writes, one active iteration
per study, idempotency keys, expiring leases and fencing tokens. Current schema is
version 3 (transactional index migrations from versions 1 and 2); a newer version is rejected before schema modification. Run histories,
reviews and lesson revisions remain durable. Runtime/evaluator hashes reject
cross-version comparisons. Context/output artifacts are linked from saved results.

Artifacts are canonical JSON named by SHA-256, fsynced and atomically published
before metadata references them. Never edit an artifact in place. Preserve the
SQLite database **and** artifacts/trade-archives directories together. Use the online
backup command, which captures committed WAL pages, verifies hashes, referenced
objects and SQLite integrity, and atomically publishes to a new destination:

```sh
uv run python -m experiment_lab.backup backup /data /backups/lab-snapshot
uv run python -m experiment_lab.backup verify /backups/lab-snapshot
uv run python -m experiment_lab.backup restore /backups/lab-snapshot /restored-data
```

Never restore over a running store. Off-host encrypted backup scheduling and the
production-volume restore drill remain operator release gates.

History uses keyset pagination: `/studies?limit=50&before_id=...` and
`/studies/{id}?limit=20&before=...`. The study response contains a global `summary`,
a bounded `iterations` page and `next_cursor`; lessons are served by `/skill`.
Advisor context contains the latest 20 iterations plus baseline/best and latest
20 lessons. Exact Decimal best-profit selection streams scalar metadata; it remains
linear in history size, while large result bodies stay bounded in memory.

Lessons carry original study/data/timeframe scope. Recent history, baseline and
best observed ancestor remain in bounded advisor context, along with cross-study
strategy lessons. Reproduction is not independent replication. All exposed history
is development data, not an untouched holdout. Global skill conflict adjudication,
rollback and formal walk-forward validation remain planned.

## Local QA only

`qa/fixtures/lab_stack.py` provisions `qa-owner@example.com` in the explicitly named
`cryptopilot_lab_e2e` database on loopback port 55432. It uses disposable test-only
credentials, fake SMS and a labeled fixture advisor; it never configures exchange
credentials. The real Codex provider capability is checked separately.

From the repository root, after starting a disposable PostgreSQL instance:

```sh
backend/.venv/bin/python qa/fixtures/lab_stack.py seed
backend/.venv/bin/python qa/fixtures/lab_stack.py lab
backend/.venv/bin/python qa/fixtures/lab_stack.py runner
backend/.venv/bin/python qa/fixtures/lab_stack.py advisor
backend/.venv/bin/python qa/fixtures/lab_stack.py backend
```

Alternatively, after seeding, use one foreground supervisor:
`backend/.venv/bin/python qa/fixtures/lab_serve.py`. It starts all five services,
refuses occupied ports and stops its children together. Optional
`CP_QA_DATABASE_NAME=cryptopilot_release_regression_e2e` and
`CP_QA_LAB_DATA_DIR=.lab-data/qa/release-regression` isolate regression evidence.

For separate processes, run each in its own terminal. Start the frontend with
`VITE_DEV_API_PROXY=http://127.0.0.1:8000 npm run dev` from `frontend/`.
In `qa/`, set `CP_QA_OWNER_EMAIL=qa-owner@example.com`,
`CP_BASE_URL=http://localhost:5173`, and `CP_LAB_DATASET_ID` to the real Binance
dataset ID before `npx playwright test`. Do not run these provisioning commands
against the VPS or a production database.

See `docs/qa/reports/EXPERIMENT_LAB_IMPLEMENTATION_QA.md` for observed results and
explicitly outstanding gates.

Latest cross-application regression and release limitations:
[2026-09-07 report](../../docs/qa/reports/RELEASE-REGRESSION-2026-09-07.md).
