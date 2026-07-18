# Stage 1 — Authentication & App Shell — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

Secured owner console: email+password → mandatory TOTP → JWT session, with the
dashboard shell (sidebar, header, environment badge, sign-out) ported from the approved
prototype.

- **Backend security** (`core/security.py`): Argon2id password hashing, HS256 JWT
  (purpose-scoped: access / refresh / totp_pending), pyotp TOTP (±1 step skew).
- **Auth service** (`services/auth.py`): password → TOTP-pending token → TOTP verify →
  access+refresh + server-side `sessions` row. DB-backed rate limiting (5 failures /
  15 min) that **resets on successful login**. Session revocation (logout + revoke-others).
- **Events** (`services/events.py`): audit trail with an autonomous committed-event
  writer so failed-login events survive request rollback (critical for lockout + audit).
- **API** (`api/auth.py`, `api/deps.py`): login, totp, refresh, logout, revoke-others,
  me; `get_current_user` guard verifies token + live session on every request.
- **CLI** (`app/cli.py`): `create-owner` provisions email/password/TOTP, prints enrol URI.
- **Frontend**: typed API client with transparent refresh-and-retry + dead-session
  handler; Login, TOTP, app Shell (react-router), auth store (zustand), route guard,
  session persistence, full dark control-room styling; responsive (desktop + mobile).

## Test run summary

| Gate | Result |
|---|---|
| ruff | ✅ clean |
| mypy --strict | ✅ 27 files |
| import-linter | ✅ 2 contracts kept |
| Migrations up/down/drift | ✅ `sessions` table added, reversible, zero drift |
| pytest (unit + integration) | ✅ 33 passed, 81% coverage |
| frontend lint + build | ✅ clean, 0 vulnerabilities |
| Playwright `stage-01.auth` | ✅ 18 passed (9 cases × desktop + mobile) |
| **Full regression (stage-00 + stage-01)** | ✅ **30 passed** |

QA-1 cases: happy path, wrong password, wrong TOTP, shell-requires-auth, sign-out +
protection, session-persists-reload, sidebar nav, API 401 sweep, rate-limit lockout.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | **Critical** | Failed-login audit events were rolled back with the failed request, so the lockout counter never accumulated and failed logins weren't audited | Added `record_event_committed` (autonomous transaction) for failure/lockout events |
| 2 | Major | Stale `totpToken` in App state → sign-out showed the TOTP screen instead of Login | Clear `totpToken` once authenticated (effect) |
| 3 | Major | Rate-limit counter never reset, so repeated E2E runs locked the owner across runs (14 spurious failures) | Count failures only since the last successful login — standard, more-correct behaviour; added regression test |
| 4 | Minor | Playwright `getByLabel("Password")` matched the show/hide button too | `exact: true` locator |
| 5 | Minor | Mobile nav tests couldn't reach off-canvas sidebar | Open hamburger menu first |
| 6 | Minor | Stage-0 smoke QA-0.03 referenced the removed skeleton health card | Updated to assert the SPA boots to the login screen |

No known open bugs. One transient: a TOTP 30-second-boundary timing edge can rarely flake
a TOTP test (±30s tolerance already applied); passed on re-run. CI uses retries.

## Review notes (loose coupling / quality)

- Thin routers, fat services; guard isolated in `deps.py`; primitives in `core/security.py`.
- 0 naive datetimes; 0 secret fields in API response schemas; TOTP secret AES-GCM at rest.
- Reset-on-success rate limiting is both correct security and removes E2E fragility.

## Docs

No doc changes required; behaviour matches SECURITY_GUIDELINES.md. `sessions` table is a
justified addition (server-side revocation) — noted here and in the migration.

## Sign-off

Stage 1 meets its exit criteria: the dashboard is unreachable without
email + password + TOTP; all auth events are audited; full regression green.
**Stage 2 (Market data & scheduler) needs the Binance DEMO API key + secret — I will
stop and request them before starting Stage 2.**
