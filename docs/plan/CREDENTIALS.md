# Credentials & Services Required

Everything the owner must provide, in the order the build needs it. Values go into
`deploy/.env` (never committed — see `.gitignore`) or the encrypted `api_credentials`
table once the app is running.

## Phase A — needed from Stage 0 (development start)

| # | Credential | Used by | How to obtain | Notes |
|---|---|---|---|---|
| 1 | **Binance DEMO API key + secret** | Execution engine, market data (Stages 2–10) | Binance Futures **Demo Trading** page → API key setup. The old `testnet.binancefuture.com` web UI is being phased out; demo is API-first now | REST `https://demo-fapi.binance.com`, WS `wss://demo-fstream.binance.com`. HMAC-SHA256 pair. Demo funds only — zero financial risk |
| 2 | **Codex credentials** (`CODEX_API_KEY` or ChatGPT sign-in / access token) | ① AI news assistant (Stage 8) — summarisation via the **Codex SDK**, model **`gpt-5.5`** · ② Development tooling (Codex CLI/SDK agents working from `AGENTS.md`) | `codex login` (ChatGPT account) or API-key mode | Owner decision: news summarisation uses the **Codex SDK + GPT-5.5** (deviation from BSD §11, which named the Claude API). **No `OPENAI_API_KEY` is used anywhere in this application.** For the server deployment use a non-interactive credential (`CODEX_API_KEY` / access token), not your personal `~/.codex/auth.json` |
| 3 | **notify.lk `user_id` + `api_key` + approved `sender_id`** | Notifier (Stage 7) | notify.lk dashboard → settings. Order a real sender ID early — approval takes time and the shared `NotifyDemo` sender must not be used for production alerts | Endpoint `https://app.notify.lk/api/v1/send`; 320-char limit per message; recipient format `9471XXXXXXX` |
| 4 | **Owner phone number** | SMS recipient | — | `947XXXXXXXX` format |
| 5 | **`MASTER_KEY`** (32-byte random, base64) | AES-GCM encryption of secrets at rest | Generate: `openssl rand -base64 32` | Provided only via environment variable; losing it means re-entering all stored credentials |

## Phase B — needed before Stage 11/12 (deployment & LIVE)

| # | Credential | Used by | Notes |
|---|---|---|---|
| 6 | **VPS** (1 vCPU / 2 GB, e.g. Hetzner/DO) + SSH key | Deployment (§15) | Region near Binance endpoints; its static IP is needed for key allowlisting |
| 7 | **Domain name** | Caddy TLS (Let's Encrypt auto-cert) | e.g. `pilot.yourdomain.com` |
| 8 | **Object storage bucket + access keys** (S3-compatible) | Nightly encrypted `pg_dump` backups | Any S3-compatible provider |
| 9 | **Binance LIVE API key + secret** | LIVE trading — only after the 4-week DEMO acceptance gate passes | Create with **trade + read only, withdrawals disabled, IP-whitelisted to the VPS**. REST `https://fapi.binance.com`, WS `wss://fstream.binance.com` |

## Explicitly NOT required

- No Binance withdrawal permission — ever (BSD security rule).
- No credentials for the news agent to reach trading — it is firewalled by design.

## Handling rules

1. All secrets enter the system through `deploy/.env` (local/dev) or the Settings UI (write-only fields, AES-GCM encrypted into `api_credentials`).
2. Secrets never appear in logs, error messages, API responses, or the frontend bundle (see `docs/guidelines/LOGGING_GUIDELINES.md`, `docs/guidelines/SECURITY_GUIDELINES.md`).
3. Rotation runbook: replace key in UI → test read-only connection → revoke old key at provider.
