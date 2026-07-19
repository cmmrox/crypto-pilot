# Security Guidelines

Threat model: internet-exposed dashboard controlling real money on an exchange
account. Assume credential-stuffing, scraped endpoints, and a stolen laptop; design so
the worst case is bounded (no withdrawal permission — ever).

## Identity & access

- Single owner role. Argon2id password hashing (tuned params). The owner may enable
  **SMS OTP 2FA** with an encrypted notify.lk-format phone number. When enabled, no
  access/refresh token is issued until the challenge bound to the password step is
  verified; there is no remembered-device or OTP-bypass path.
- SMS 2FA is weaker than authenticator TOTP (notably SIM-swap risk). Disabling it is
  an owner-approved trade-off that reduces login to password-only. Enable/change/
  disable requires password re-entry and an OTP; change/disable revokes other sessions,
  notifies the previous phone, and writes `security` events.
- OTPs are random six-digit values, HMAC-SHA256 hashed at rest, single-use, valid for
  five minutes, limited to five attempts, resend-throttled, and capped at five sends
  per owner per hour. Raw codes and full phone numbers never enter logs/events.
- Lost-phone recovery is server-side only: `python -m app.cli reset-2fa --email ...`.
  There is no web recovery endpoint. Test code capture/throttle controls are rejected
  by configuration unless `CP_ENVIRONMENT=test`.
- JWT: short-lived access (≤15 min) + rotating refresh; revocation list honored;
  session revoke-others in Settings writes a `security` event.
- Login rate limiting + lockout with event trail; auth failures are `security` events.

## Secrets

- At rest: AES-GCM via `MASTER_KEY` from environment only (including the 2FA phone).
  OTP challenge rows contain only a keyed hash and encrypted target phone. In the UI: write-only
  fields, never echoed (only last-4 hint). In transit: TLS everywhere (Caddy,
  Let's Encrypt), HSTS.
- In code/CI: gitleaks blocking; `.env` gitignored; fixtures use obvious fakes.
- Exchange keys: trade + read only, **withdrawals disabled**, IP-whitelisted to the
  VPS. Stage 12 verifies permissions programmatically and refuses unsafe keys.

## Application hardening

- Security headers: CSP (no inline script; hashes for the built bundle), HSTS,
  X-Content-Type-Options, Referrer-Policy, frame-ancestors 'none'.
- CORS: exact dashboard origin only. Request size limits; JSON-only bodies on API.
- Input validation at the edge (Pydantic strict); output encoding by React defaults —
  no `dangerouslySetInnerHTML`.
- Dependencies: audit in CI (pip-audit / npm audit); base images pinned by digest;
  non-root containers, read-only root FS where possible.
- WebSocket: auth on connect (token), origin-checked, per-connection rate cap.

## Server (VPS)

Firewall: 443 + SSH only; SSH keys only (no passwords), fail2ban, unattended security
upgrades. Postgres not exposed publicly (compose network only). Caddy handles TLS;
cert renewal alerting via dead-man.

## Operational security

- Backups encrypted before leaving the host; restore drill scheduled (untested backup
  = no backup). Backup bucket credentials write-only where provider supports.
- Key rotation runbook (Settings → replace → test → revoke old at provider).
- Incident response: kill switch → rotate exchange keys → revoke sessions → inspect
  `events` (`security` category) → post-mortem in `docs/qa/reports/`.
- Upgrade policy: blue/green; never with an open position unless hotfix-critical.

## Verification (Stage 9 gate)

Automated: header scan, authz sweep (every route × anonymous/expired/revoked), secrets
grep of bundle+logs, dependency audit. Manual: OWASP-ASVS-lite checklist pass recorded
in the stage report.
