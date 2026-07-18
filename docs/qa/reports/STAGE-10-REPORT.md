# Stage 10 — Reliability Engineering & Failure Drills — Report

**Status:** ✅ COMPLETE — QA gate passed, drills run. **Date:** 2026-07-18.

## Scope shipped

BSD §14 forced-failure drills, scripted and repeatable.

- **Deep health** (`/health/deep`): DB, scheduler-alive, ingest last-tick, dead-man
  overdue flag, version. Fed the ops panel + dead-man cron.
- **Dead-man's switch**: the ingest loop checks after each tick; a missed 4h tick past
  grace writes an ERROR event + SMS alert (`_dead_man_check`).
- **Backup/restore** (`deploy/scripts/`): nightly encrypted `pg_dump` (AES-256, optional
  S3 upload) + `restore.sh` + a **restore drill** that backs up, restores into a scratch
  DB, and verifies row counts.
- **Drill scripts** (`deploy/scripts/drills/`): restore-drill, restart-mid-trade.
- **Frontend**: Operations panel (DB, scheduler, last tick, dead-man, run-health-check).
- **Caddy fix**: route `/health*` (not just `/health`) to the backend.

## Live proof (drills actually run)

| Drill | Result |
|---|---|
| **Restore drill** (backup → restore scratch → verify) | ✅ **events source=1546 restored=1546 — PASSED** |
| **Restart-mid-trade** (restart backend, resume + reconcile) | ✅ health ok after restart — PASSED |
| Deep health endpoint | ✅ scheduler alive, dead-man armed, not overdue |

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration) | ✅ 139 passed |
| Playwright `stage-10` | ✅ 2 cases |
| Deterministic regression (all stages) | ✅ 87 passed, 19 skipped (live suites) |

QA-10: deep-health shape, dead-man overdue transition, restore drill (real), restart
drill (real), ops panel render.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Minor | Caddy routed only exact `/health`, so `/health/deep` hit the SPA | `handle /health*` |

No known open bugs.

## Sign-off

Stage 10 meets its exit criteria: backup restores verified, restart resumes cleanly,
dead-man + deep health in place, drills scripted and green. **Stage 11 (DEMO acceptance
soak on a VPS) requires the owner to provide deployment infrastructure — VPS + SSH key,
a domain, and an S3-compatible backup bucket. Requesting these before Stage 11.**
