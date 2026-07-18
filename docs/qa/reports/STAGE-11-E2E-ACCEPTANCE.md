# Stage 11 — Full-Stack End-to-End Acceptance (local production-like) — Report

**Status:** ✅ COMPLETE — full production-like stack verified end-to-end. **Date:** 2026-07-18.
**Only the manual VPS production deploy + the calendar soak remain (owner-performed).**

## What was verified

The complete application was run as a **production-like Docker stack** (postgres +
backend + frontend + caddy, same images/topology as production, reachable via Caddy on
:8090) and exercised end-to-end across every service.

### Clean boot & persistence
- `docker compose down && up --build` → all 4 services **healthy** from images.
- State survived the rebuild via volumes: candles=502, events=1878, briefings=1,
  Codex `auth.json` persisted (`/data/codex`).
- `/health/deep`: db ok, scheduler alive, dead-man armed (not overdue).

### End-to-end user journey (live, through Caddy)
1. **Auth** — email + password + TOTP → access token ✓
2. **Strategy library** — trend_rider_v6 (LONG+SHORT) + v5.2 (LONG), both parity-verified ✓
3. **Market data** — 502 candles, 0 gaps, exchange reachable ✓
4. **Bot lifecycle** — start (reconciled, run 5) → running → safe stop ✓
5. **Overview** — DEMO, account truth (balance $4999.22), 2 independent breakers ✓
6. **AI news** — Codex authenticated (device-code), gpt-5.5 briefing, 7 bullets ✓
7. **SMS** — configured (NotifyDEMO), **real test SMS delivered** ✓
8. **Trades / Monthly** — history + ledger served ✓
9. **Kill switch** — live DEMO flatten + stop ✓
10. **Events** — full audit ledger ✓

## Test acceptance

| Suite | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| Backend pytest (unit + integration + **parity** + **live exchange**) | ✅ **142 passed** |
| Playwright (all stages, deterministic + live DEMO) | ✅ **103 passed**, 3 skipped |
| Playwright live SMS (`@sms`) | ✅ 1 passed (real SMS) |
| Reliability drills (restore, restart) | ✅ passed |

## Coverage summary (Stages 0–11)

Foundations, auth (Argon2/JWT/TOTP), market data, **strategy + parity gate**, risk &
execution (live DEMO), bot lifecycle + Overview, trades/monthly/events, notifier SMS,
AI news (Codex device-code + gpt-5.5), security hardening, reliability drills,
production deploy artifacts. All merged to `main`.

## Remaining (owner-performed, per plan)

- **Stage 11 execution:** deploy to a VPS via `deploy/RUNBOOK.md` (VPS + domain + S3
  bucket) and run the **≥4-week DEMO soak** (BSD G3 gate — calendar time).
- **Stage 12:** LIVE Binance key (trade+read only, withdrawals off, IP-allowlisted),
  switch to LIVE with pilot sizing after the soak.

## Sign-off

The application is **code-complete and production-ready**, verified end-to-end on a
production-like local stack. Everything up to the manual production deployment is done.
