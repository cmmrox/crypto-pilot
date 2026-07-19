# Stage 9 — Settings, Security Hardening & Environment Guard — Report

> Historical stage snapshot. Any TOTP reference below describes the superseded
> Stage 1 implementation; current authentication uses owner-configurable SMS OTP
> and is governed by `SMS-2FA-REPORT.md`.

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

Everything configurable that should be; everything locked that must be.

- **Security headers** (`core/middleware.py`): CSP (no inline script; `frame-ancestors
  'none'`), X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy,
  Permissions-Policy, HSTS in production. Request-body size limit (1 MB → 413).
- **Guarded environment switch** (`api/admin_settings.py`): refused while the bot runs
  (409); LIVE requires a typed `LIVE` confirmation (server-enforced); audited.
- **Guarded strategy selection**: switch the active/fallback release only while stopped;
  unknown strategy rejected; audited.
- **Frontend**: Environment card (DEMO/LIVE with guarded modal + typed LIVE confirm),
  strategy library "Select" for the fallback (guarded modal). Security settings
  (session timeout, revoke-others, TOTP) shipped in Stage 1; credentials/SMS/Codex in
  Stages 2/7/8.
- **CI hardening** (from Stage 0, confirmed): non-root containers, gitleaks secrets scan,
  `npm audit --audit-level=high`, import-boundary contracts.

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration) | ✅ 137 passed |
| Playwright `stage-09` | ✅ 5 cases |
| Deterministic regression (all stages) | ✅ 81 passed, 19 skipped (live suites) |

QA-9: security headers present, **14-route authz sweep**, environment switch blocked
while running, LIVE requires typed confirm, strategy switch guarded, body-size limit,
env card render, guarded LIVE modal (cancelled), guarded strategy selection.

## Bugs found & fixed during the stage

None of note — the middleware and guards integrated cleanly.

## Review notes

- Environment/strategy mutations are server-guarded (stopped-bot check + typed LIVE
  confirm), not just UI-guarded — the API enforces the rules independently.
- CSP is strict (no inline/eval, self-only connect); the SPA is same-origin so it fits.

## Sign-off

Stage 9 meets its exit criteria: hardening headers present, authz enforced on every
route, environment/strategy changes guarded and audited. **Stage 10 (reliability
engineering & failure drills) needs no new keys — proceeding.**
