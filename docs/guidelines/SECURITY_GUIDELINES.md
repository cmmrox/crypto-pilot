# Security Guidelines

Threat model: internet-exposed dashboard controlling real money on an exchange
account. Assume credential-stuffing, scraped endpoints, and a stolen laptop; design so
the worst case is bounded (no withdrawal permission — ever).

## Identity & access

- Single owner role. Argon2id password hashing (tuned params), **mandatory TOTP** —
  no bypass path, no "remember this device" for TOTP.
- JWT: short-lived access (≤15 min) + rotating refresh; revocation list honored;
  session revoke-others in Settings writes a `security` event.
- Login rate limiting + lockout with event trail; auth failures are `security` events.

## Secrets

- At rest: AES-GCM via `MASTER_KEY` from environment only. In the UI: write-only
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
