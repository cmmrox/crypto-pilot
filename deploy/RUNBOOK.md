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
```

## 4. Launch

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# Provision the owner account:
docker compose exec backend python -m app.cli create-owner --email you@example.com --password '...'
# Scan the printed otpauth URI in your authenticator.
```

Caddy obtains a Let's Encrypt cert automatically. Visit `https://pilot.yourdomain.com`.

## 5. Configure in the dashboard

- Settings → **DEMO credentials** (Binance testnet key/secret) → Test connection.
- Settings → **SMS** (notify.lk) → Send test SMS.
- Settings → **Codex** → Connect (device-code) for daily briefings.
- Confirm environment = **DEMO**. Start the bot.

## 6. DEMO acceptance soak (Stage 11 — G3 gate)

Run **≥4 weeks on DEMO** with real 4h decisions. Weekly:
- `deploy/scripts/drills/restore-drill.sh` — verify backups restore.
- Review every decision vs the strategy rules; every event explained.
- Confirm SMS latency ≤60s; reconciliation clean.
- Run the full Playwright regression against the deployed host:
  `CP_BASE_URL=https://pilot.yourdomain.com npx playwright test`
- Log any deviation. **Any unexplained deviation resets the 4-week clock.**

Exit: 4 clean weeks + owner sign-off recorded in `docs/qa/reports/`.

## 7. Go-live (Stage 12)

- Create a **LIVE** Binance key: trade + read only, **withdrawals disabled**,
  **IP-allowlisted to the VPS**.
- Settings → LIVE credentials → the app verifies permissions and refuses unsafe keys.
- Settings → Environment → switch to **LIVE** (typed confirmation), pilot sizing
  (risk 1–2%, sleeve 50%). Start. Monitor first closes.
- After 4+ LIVE weeks matching DEMO behaviour → raise to validated defaults.

## 8. Routine ops

- **Upgrade (blue/green)**: never with an open position unless hotfix-critical.
  `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- **Restore**: `scripts/restore.sh <backup.enc> <db>`.
- **Kill switch**: dashboard → Kill switch (type FLATTEN) — cancels + flattens + stops.
- **Key rotation**: Settings → replace key → test → revoke old at the provider.
- **Incident**: kill switch → rotate keys → revoke sessions → inspect Events
  (`security`/`error`) → post-mortem in `docs/qa/reports/`.
