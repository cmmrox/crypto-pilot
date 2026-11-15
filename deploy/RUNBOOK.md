# CryptoPilot — Deployment & Operations Runbook

Production deployment, the DEMO acceptance soak (Stage 11), and go-live (Stage 12).

## 1. Provision (owner)

- **VPS**: 1 vCPU / 2 GB RAM (Hetzner/DO/etc.), Ubuntu 22.04+, near Binance endpoints.
  Note its **static public IP** (needed for the LIVE key allowlist later).
- **Domain**: an A record → the VPS IP (e.g. `pilot.yourdomain.com`).
- **Object storage**: an S3-compatible bucket + access keys for encrypted backups.
- **SSH key** access; disable password login.

## 2. Server hardening (once)

```sh
# firewall: only SSH + HTTP/HTTPS
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
apt-get update && apt-get install -y docker.io docker-compose-plugin fail2ban unattended-upgrades
systemctl enable --now docker fail2ban
```

## 3. Configure

```sh
git clone <repo> && cd trading_strategy/deploy
cp .env.example .env
# Fill .env: strong POSTGRES_PASSWORD, MASTER_KEY + CP_JWT_SECRET (openssl rand -base64 32),
# CP_DOMAIN=pilot.yourdomain.com, CP_FRONTEND_ORIGIN=https://pilot.yourdomain.com,
# CP_BACKUP_BUCKET=s3://... and AWS creds in the environment.
# The database role used by the scheduled restore drill also needs CREATEDB on
# the dedicated CryptoPilot database server. Do not grant broader superuser rights.
```

## 4. Launch

```sh
# Dependency lock integrity must pass before an image build.
cd ../backend
uv lock --check
uv export --frozen --no-dev --no-emit-project \
  --no-emit-package cryptopilot-strategy-runtime \
  --format requirements-txt --output-file /tmp/cryptopilot-requirements.check
# uv records the requested output path in its two-line generated header. Compare
# the locked dependency body rather than that non-semantic command comment.
diff -u \
  <(sed '1,2d' requirements.lock) \
  <(sed '1,2d' /tmp/cryptopilot-requirements.check)
cd ../deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# Provision the owner account:
docker compose exec backend python -m app.cli create-owner --email you@example.com --password '...'
```

Caddy obtains a Let's Encrypt cert automatically. Visit `https://pilot.yourdomain.com`.

If a trusted domain is not available, keep HTTP loopback-only and run the
independent monitor plus encrypted local backups:

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml up -d --build
ssh -L 8090:127.0.0.1:8090 user@server
```

Use `http://localhost:8090` through that tunnel. Set `CP_BACKUP_DIR` to an
absolute host directory. `CP_BACKUP_BUCKET` remains the off-host upload switch.

An owner may temporarily expose the non-TLS endpoint by setting
`CP_HTTP_BIND=0.0.0.0`. This sends login credentials, OTPs, and session traffic
without transport encryption and is not an accepted final production posture.

## 5. Configure in the dashboard

- Settings → **DEMO credentials** (Binance testnet key/secret) → Test connection.
- Settings → **SMS** (notify.lk) → Send test SMS.
- Settings → **Two-factor authentication** → enable → enter a fresh login phone in
  `94XXXXXXXXX` form → prove it with the received code. Configure and test notify.lk
  first; the backend refuses to enable SMS 2FA when delivery is unavailable.
- Settings → **Codex** → Connect (device-code) for daily briefings.
- Confirm environment = **DEMO**. Start the bot.

## 6. DEMO acceptance soak (Stage 11 — G3 gate)

Run **≥4 weeks on DEMO** with real 4h decisions. Weekly:
- `deploy/scripts/drills/restore-drill.sh` — verify backups restore.
- Review every decision vs the strategy rules; every event explained.
- Confirm SMS latency ≤60s; reconciliation clean.
- Run the full Playwright regression against an **isolated test-mode clone** of the
  deployed release, never the active trading database. Set `CP_ENVIRONMENT=test`,
  `CP_OTP_TEST_MODE=true`, and `CP_OTP_TEST_DISABLE_THROTTLE=true` only on that clone;
  production configuration rejects these controls. Also perform one manual real-SMS
  login against the deployed host.
- Log any deviation. **Any unexplained deviation resets the 4-week clock.**

Exit: 4 clean weeks + owner sign-off recorded in `docs/qa/reports/`.

## 7. Go-live (Stage 12)

- Create a **LIVE** Binance key: trade + read only, **withdrawals disabled**,
  **IP-allowlisted to the VPS**.
- Settings → LIVE credentials → the app verifies permissions and refuses unsafe keys.
- Settings → Environment → switch to **LIVE** (typed confirmation), pilot sizing
  from the selected immutable strategy manifest. The currently approved Trend Rider
  v6 release uses 15% long risk and a 6× leverage cap; see the risk acceptance in
  `ARCHITECTURE.md §8`. Start and monitor the first closes.
- After 4+ LIVE weeks matching DEMO behaviour → raise to validated defaults.

## 8. Routine ops

- **Upgrade (blue/green)**: never with an open position unless hotfix-critical.
  `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- **Backup/restore**: scripts run a short-lived PostgreSQL client container on
  `CP_DB_NETWORK` and connect to `CP_DB_HOST`; they do not assume the Compose
  stack owns a `postgres` service. Use `scripts/restore.sh <backup.enc> <db>`.
- **Kill switch**: dashboard → Kill switch (type FLATTEN) — cancels + flattens + stops.
- **Key rotation**: Settings → replace key → test → revoke old at the provider.
- **Incident**: kill switch → rotate keys → revoke sessions → inspect Events
  (`security`/`error`) → post-mortem in `docs/qa/reports/`.

## 9. SMS 2FA deployment and recovery

The SMS migration removes the prior authenticator secret but preserves its enabled
state. An owner previously enrolled in TOTP therefore fails closed (2FA remains on,
with login blocked until a phone is enrolled) rather than falling back to a password.
Use a blue/green rollout: migrate the inactive stack, confirm notify.lk remains
configured, then run the server-side phone enrolment before switching traffic:

```sh
docker compose exec backend python -m app.cli set-phone \
  --email you@example.com --phone 94711234567
```

`set-phone` refuses to enable 2FA when notify.lk is not configured and revokes all
existing sessions. Confirm a real SMS login before promoting the stack.

Lost phone or notify.lk outage (server-shell break glass only):

```sh
docker compose exec backend python -m app.cli reset-2fa --email you@example.com
```

This disables 2FA, clears the enrolled number, revokes active sessions, and writes a
`security` event. Sign in with the password, restore/test notify.lk, and re-enable 2FA
immediately. There is intentionally no web recovery endpoint.

## 10. Resource limits

The memory and CPU policy lives in `docker-compose.yml` (backend, frontend, caddy) and
`docker-compose.ops.yml` (deadman, backup), so every deploy, rollback and drill command
applies it without an extra `-f` file.

| Service | Memory limit | Memory + swap | Reservation | CPU shares | OOM score adj |
|---|---|---|---|---|---|
| `backend` | 1g | 2g | 512m | 2048 | -500 |
| `deadman` | 256m | 512m | 64m | 2048 | -500 |
| `caddy` | 192m | 384m | 32m | default | default |
| `backup` | 256m | 512m | none | default | default |
| `frontend` | 96m | 192m | none | default | default |

- The limits are leak guards at about twice the peak seen over 28 days of production
  (backend 468 MiB, deadman 100 MiB, caddy 52 MiB, backup 49 MiB, frontend 13 MiB). A
  container that reaches its limit is killed and restarted by its restart policy, so
  re-measure before lowering one.
- There is no CPU ceiling. `cpu_shares` gives the backend and the monitor priority only
  when the host is contended; the backend averaged 9% of one core, and its peak during
  heavy trading has not been measured.
- A limit is a ceiling for that container, not a reservation. On a shared host, cap the
  other applications as well, and protect the shared Postgres the same way as the
  backend: trading stops when the database is starved.
- `docker-compose.prod.yml` lowers the backend limit to 768m for the small VPS in §1.
- Rootless Docker cannot set a negative `oom_score_adj`; run the stack with a rootful
  daemon or override that key locally.
- Changing any value recreates the container on the next `up -d`. Follow the upgrade
  rule in §8: not with an open position unless hotfix-critical.

Read the live values back with:

```sh
docker inspect -f '{{.Name}} mem={{.HostConfig.Memory}} res={{.HostConfig.MemoryReservation}} shares={{.HostConfig.CpuShares}} oom={{.HostConfig.OomScoreAdj}}' \
  $(docker compose -f docker-compose.yml -f docker-compose.ops.yml ps -q)
```
