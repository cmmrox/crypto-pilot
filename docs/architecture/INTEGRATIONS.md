# External Integrations Reference

Verified July 2026. When an integration misbehaves, re-verify endpoints against the
linked official docs before changing code.

## 1. Binance USDT-M Futures

> ⚠️ **Correction to BSD §8:** Binance phased out the `testnet.binancefuture.com` web
> testnet (announcement Aug 2025). The demo environment is API-first with new base URLs.

| | DEMO (Phase 1) | LIVE (Phase 2) |
|---|---|---|
| REST | `https://demo-fapi.binance.com` | `https://fapi.binance.com` |
| WebSocket | `wss://demo-fstream.binance.com` | `wss://fstream.binance.com` |

Same code path for both — base URL + key pair come from the active `api_credentials`
row (BSD FR-01). Docs: [developers.binance.com — USDS-M futures](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info).

- **Auth:** HMAC-SHA256 signature over query/body + `timestamp` (ms) + optional `recvWindow` (default 5000 ms). Keys are case-sensitive; restrict to TRADE + USER_DATA (read).
- **Rate limits:** three buckets — `RAW_REQUEST`, `REQUEST_WEIGHT`, `ORDER` (per account). HTTP 429 = back off (exponential + jitter); HTTP 418 = IP ban escalating 2 min → 3 days. Never retry-loop a 429 tightly.
- **Market data:** 4h klines via REST backfill + kline WebSocket stream; act only when the kline `closed` flag is true (BSD FR-03). Cache candles in PostgreSQL.
- **Orders:** long engine — MARKET entry, STOP_MARKET reduce-only protective stop, LIMIT reduce-only TP1; short sleeve — MARKET entry/resize, **no price stop by validated design**. Idempotent `newClientOrderId` on every order (`CP-<trade>-<seq>`), lot-size/min-notional filters respected via `exchangeInfo`.
- **Account:** one-way position mode, isolated margin, explicit leverage (cap 3×). Margin error `-2019` → pause bot + SMS.
- **Reconciliation:** on every start and every 4h close compare expected vs actual position/orders; mismatch → safe mode + SMS (BSD §8).

## 2. notify.lk SMS

Docs: [developer.notify.lk](https://developer.notify.lk/api-endpoints/).

- Endpoint: `https://app.notify.lk/api/v1/send` (GET or POST).
- Params: `user_id`, `api_key`, `sender_id`, `to` (`9471XXXXXXX` format), `message` (≤320 chars).
- Response: JSON `{"status": "success", "data": "Sent"}` — treat anything else as failure.
- **Trading alerts are fire-and-log:** failure never blocks trading. 3 retries with
  backoff, then log `ERROR` event + dashboard banner (BSD §10). Every attempt writes
  an `events` row with delivery status.
- **Authentication OTP is deliberately blocking:** a login/security change never
  succeeds unless its single SMS attempt is accepted by the gateway. Failure is
  audited and surfaced for retry; it never issues tokens or commits the requested
  security change. OTP delivery ignores the alerts on/off toggle.
- Use the approved custom sender ID in production; `NotifyDemo` only for early smoke tests.

## 3. Codex SDK + GPT-5.5 (AI news assistant)

Owner decision (July 2026): the in-app news summariser uses the **Codex SDK** with
model **`gpt-5.5`** instead of the BSD §11 Claude API. **No `OPENAI_API_KEY` is used
anywhere in this application.**

**Auth:** Codex credentials only — `CODEX_API_KEY` env var (or a Codex access token)
for the server; `codex login` (ChatGPT account) on dev machines. See
[developers.openai.com/codex/auth](https://developers.openai.com/codex/auth). Treat
`~/.codex/auth.json` as a secret; never bake it into images — the backend container
receives `CODEX_API_KEY` via `deploy/.env`.

**Integration shape:** the Codex SDK is Node/CLI-based, so the Python news module
calls it through the provider interface (`news/llm.py: SummaryProvider`) with a
`CodexProvider` implementation that invokes headless Codex
(`codex exec` non-interactive mode, model pinned to `gpt-5.5`, workspace-less prompt,
JSON output) as a subprocess with a hard timeout. The provider interface keeps this
swappable (an `AnthropicProvider` can be added later without touching the pipeline).

| Provider | Credential | Model |
|---|---|---|
| Codex SDK (default & only, v1) | `CODEX_API_KEY` / access token | `gpt-5.5` (configurable in Settings) |

Rules:

- Fixed prompt per BSD §11: 5–8 market-relevant bullets, neutral tone, flag anything
  affecting BTC volatility (regulation, ETF flows, Fed). Output stored in `briefings`.
- Summarisation-only: the Codex invocation gets **no filesystem workspace, no tools,
  no network task** — it is a text-in/JSON-out call with a hard timeout and one retry.
- The news module has **no exchange credentials and no strategy imports** — enforced by
  the import-boundary lint (see `docs/guidelines/BACKEND_GUIDELINES.md`). `CODEX_API_KEY`
  is readable only by the news module's settings scope.
- Budget guard: cap output length per briefing; daily schedule + manual refresh only.

### Codex CLI/SDK for development

The same Codex credentials also drive development agents. Codex and Claude Code use
the canonical `.agents/skills/cryptopilot-dev/SKILL.md`; Claude's skill path symlinks
to it. Their root bootstrap is also shared (`CLAUDE.md` → `AGENTS.md`). The shared
skill routes both tools into `docs/`. Use separate credentials for dev machines vs
the deployed server so rotation is independent.

## 4. RSS / calendar sources (news collection)

CoinDesk RSS, Cointelegraph RSS, Bitcoin Magazine, macro headlines, static FOMC/CPI
calendar. URL-unique insert into `news_items`; failures are logged and skipped —
collection must never crash the scheduler.
