# CryptoPilot — Implementation Plan (Production, not MVP)

Source of truth: `docs/BUSINESS_SOLUTION_v2.pdf`. Architecture:
`docs/architecture/ARCHITECTURE.md`. QA process: `docs/qa/QA_STRATEGY.md`.

**Operating rule:** each stage is a complete, QA-able deliverable. A stage is DONE only
when: (1) all its features work end-to-end, (2) its QA test cases pass, (3) its
Playwright automation suite (`qa/e2e/stage-XX.*.spec.ts`) is written and green, (4) all
bugs found are fixed, (5) the full regression suite (all previous stages' specs) is
green. Only then does the next stage begin. No stage-skipping, no "we'll test later."

**Environment policy:** Stages 0–11 run exclusively against **Binance DEMO**
(`demo-fapi.binance.com`). LIVE credentials do not exist in the system until Stage 12.

Credentials needed per stage: `docs/plan/CREDENTIALS.md`.

---

## Stage 0 — Foundations & walking skeleton

**Goal:** a running Docker Compose stack with an empty-but-real app: DB, migrations,
config, logging, CI. The skeleton that every later stage plugs into.

**Deliverables**
- Git repo initialized; CI pipeline (lint → typecheck → unit tests → migration check → build).
- `deploy/docker-compose.yml`: backend, postgres, caddy, frontend (placeholder page).
- `backend/`: FastAPI app factory, `/health` endpoint (DB + version), pydantic-settings
  config, structlog JSON logging, AES-GCM crypto utils, Alembic wired, initial migration
  (all tables in `DATABASE_ARCHITECTURE.md`).
- `frontend/`: Vite + React scaffold that builds and is served by Caddy.
- `qa/`: Playwright project scaffold (config, fixtures, CI wiring).
- Tooling: ruff + mypy (strict) + pytest (backend); eslint + prettier (frontend);
  import-linter contracts for the module boundaries.

**QA test cases (QA-0):** compose up → all 4 services healthy; `/health` returns DB ok;
migration up/down clean on scratch DB; crypto round-trip test; CI red on lint/type/test
failure; secrets absent from logs and images.
**Playwright:** `stage-00.smoke.spec.ts` — stack boots, placeholder page served over
HTTP(S), `/health` 200 via request context.

**Exit:** compose stack + CI green; skeleton deployed locally.

---

## Stage 1 — Authentication & app shell

**Goal:** the secured owner console shell, matching the approved prototype design.

**Deliverables**
- Backend: owner user provisioning (CLI command), Argon2id password verify, JWT
  (short-lived access + refresh), owner-configurable **SMS OTP 2FA** (encrypted phone,
  single-use challenge; password-only only while explicitly disabled),
  session revocation, login rate-limiting, auth audit events (`security` category).
- Frontend: Login → SMS OTP when enabled → app shell (sidebar nav, header, environment badge, sign-out),
  ported from `prototype/final-cryptopilot` design; route guards; session expiry handling.

**QA test cases (QA-1):** valid login+SMS OTP succeeds; wrong password / wrong, expired,
locked, or reused OTP rejected; OTP is bound to its challenge; rate limit locks after N failures (event logged); JWT expiry forces
re-auth; revoked session dies; no auth bypass on any API route (401 sweep); XSS-safe
rendering of inputs.
**Playwright:** `stage-01.auth.spec.ts` — full happy path, all failure paths, session
expiry, route-guard redirects, API 401 sweep via request context.

**Exit:** while 2FA is enabled, dashboard unreachable without email+password+fresh SMS
OTP; while disabled, the approved password-only policy applies; all auth events audited.

---

## Stage 2 — Market data & scheduler (first Binance DEMO connection)

**Goal:** the bot's heartbeat: candles flow in, 4h closes tick, health is visible.

**Deliverables**
- `execution/BinanceClient`: signed REST (HMAC), WS kline stream, testnet/live base-URL
  switching, backoff+jitter retry, 429/418 handling, clock-drift check (`recvWindow`).
- Candle service: REST backfill ≥200 warmup bars → live WS; only `closed` klines
  persisted as closed; gap detection + catch-up after disconnect.
- Scheduler: UTC 4h tick aligned to candle close; health checks; dead-man timestamp.
- Settings → API credentials (write-only fields, encrypted storage, "test connection").
- Dashboard: connection status (WS latency, DB, next candle countdown), Events view
  (backend-fed, with payload drawer).

**QA test cases (QA-2):** backfill inserts exactly the expected candles (fixture vs
DEMO); WS close event persists a closed candle within seconds; kill the WS → reconnect
+ gap backfill proven; forced 429 → backoff not tight-loop; bad API key → clear error
event, no crash; countdown matches real UTC 4h grid; credentials never echoed back.
**Playwright:** `stage-02.marketdata.spec.ts` — credentials entry + test-connection UI,
health panel shows connected state, events list shows ingest events with payloads.

**Exit:** 48 h unattended DEMO candle ingest with zero gaps (soak check scripted).

---

## Stage 3 — Strategy engine & parity gate ⭐

**Goal:** Trend Rider v6 + v5.2 as plugins, proven **bar-for-bar identical** to the
validated research engine. This is the G1 success criterion and the highest-risk stage.

**Deliverables**
- Intent types + `Strategy` protocol + registry (BSD §7 vocabulary, exactly).
- `trend_rider_v6_4h.py` / `trend_rider_v52_4h.py`: pure, deterministic ports
  of the validated logic (regime, pullback state, TP1/breakeven/trail state machine,
  deep-bear sleeve, vol targeting math, both breakers' decisions).
- **Parity harness** (`backend/tests/parity/`): replays `research/data/btc_4h.csv`
  through the plugin and diffs every decision (entries, exits, stops, sizes, breaker
  trips) against `research/backtests/final_composite.py` output. Zero mismatches, in CI.
- Decision events: every `on_candle` writes a `payload_json` with indicator values +
  intents (the audit record the prototype's event drawer shows).

**QA test cases (QA-3):** parity = 0 mismatches over full 3-year history; warmup
respected (no decision before 200 bars); determinism (same input twice → identical
output); Decimal edge cases (tiny ATR, equal closes); unit tests per rule (each entry/
exit condition, TP1 state, trail ratchet, breaker month rollover).
**Playwright:** `stage-03.strategy.spec.ts` — strategy library UI shows both releases
with parity status; decision events visible with full indicator payloads.

**Exit:** CI parity job green and mandatory; strategy state survives process restart.

---

## Stage 4 — Risk & execution engines (DEMO orders)

**Goal:** intents become real (DEMO) orders, safely.

**Deliverables**
- `risk/`: long sizing (risk % of equity / stop distance), leverage cap 3×, sleeve
  sizing (weight × min(1, vol-target/realized-vol)), >20% drift resize guard, **both
  independent monthly breakers** (persisted, restart-proof).
- `execution/OrderManager`: MARKET entries, STOP_MARKET reduce-only stops, LIMIT
  reduce-only TP1, stop modification (trail), covers; lot-size/min-notional rounding
  from `exchangeInfo`; idempotent client order IDs; fill tracking → `orders`/`trades`.
- `execution/Reconciler`: start + every-close comparison; mismatch → safe mode + event.
- Kill-switch backend: cancel all → flatten all → stop → events (+SMS placeholder).

**QA test cases (QA-4):** each intent produces exactly the right DEMO order
(side/qty/type/reduce-only/rounding — asserted against the exchange response); double
placement with same client ID creates one order; stop trail only ratchets; long stop
never lowered; sleeve resize only beyond 20% drift; breaker trip flattens/covers and
halts until the 1st (simulated month roll); reconciler catches an out-of-band manual
DEMO order → safe mode; kill switch from every state; −2019 margin error pauses bot.
**Playwright:** `stage-04.execution.spec.ts` — API-driven scenario runs against DEMO
verifying order/trade rows and safe-mode banner; kill-switch UI with typed FLATTEN.

**Exit:** scripted end-to-end DEMO round-trips (long with TP1+trail, short open/resize/
cover) reconcile exactly; chaos cases pass.

---

## Stage 5 — Bot lifecycle & Overview dashboard (live loop)

**Goal:** the 24/7 loop with full owner control and the real-time Overview screen.

**Deliverables**
- `bot/BotService`: start (connect→reconcile→catch-up→loop), safe stop, stop&close,
  restart auto-resume, safe mode; `bot_runs` records; all transitions evented.
- WebSocket push channel: position, mark, P&L, equity, bot state, breaker meters.
- Overview (full prototype port): strategy hero, stat cards, live position card
  (streaming mark, no-price-stop callout for shorts), equity curve vs buy-and-hold
  (from `equity_snapshots`), breaker meters, health panel, guarded control modals
  (reconcile-and-start, safe stop, stop&close, typed-FLATTEN kill switch).
- Equity snapshot writer every 4h close (FR-12).

**QA test cases (QA-5):** start reconciles before first decision; stop leaves position
+ resting stops on exchange; stop&close flattens then stops; container restart mid-run
→ auto-resume + reconcile (drill); WS pushes reach UI <1 s; equity snapshot written
each close; all modals guard correctly (typed confirmations, cancel paths).
**Playwright:** `stage-05.lifecycle.spec.ts` — full control-flow UI matrix; live update
assertions via mocked mark events; restart-resume drill scripted.

**Exit:** bot runs unattended on DEMO through ≥2 real 4h closes with correct decisions,
snapshots, and live UI.

### Approved command-center enhancement — 2026-07-19

The owner selected `docs/design/dashboard-command-center-reference.png` as the
production Overview direction. The full implementation and merge gate are defined in
`docs/plan/DASHBOARD_COMMAND_CENTER_IMPLEMENTATION_PLAN.md`.

Additional acceptance cases:

- **QA-5.05:** a fresh five-second worker pulse proves background liveness; stale or
  missing pulses degrade honestly.
- **QA-5.06:** BTCUSDT mark price, source time, 24h change, next UTC close, and
  countdown come from live/persisted truth.
- **QA-5.07:** the read-only strategy-watch projection explains long regime, pullback
  resume, and deep-bear short conditions without predicting a trade.
- **QA-5.08:** today's briefing and recent owner activity appear on Overview while
  news remains isolated from trading.
- **QA-5.09:** failed refreshes and unavailable market/account sources never leave
  frozen values styled as live.
- **QA-5.10:** the command center matches the selected desktop hierarchy and has no
  horizontal overflow at 390px.
- **QA-5.11:** existing guarded lifecycle controls remain server-confirmed and green.

---

## Stage 6 — Trades, Monthly & Events (audit surfaces)

**Goal:** complete reconstructable history in the UI.

**Deliverables**
- Trades view: filters (search/side/environment/strategy/month), CSV export (streamed,
  exact `numeric` formatting), per-trade drawer (orders, fills, decision timeline,
  reconciliation status).
- Monthly view: calendar-month ledger (trades, realized P&L, fees+funding, net, both
  breaker states), withdrawal allowance (10% rule), manual mark-withdrawn (audited).
- Events view completed: level/category/search filters, payload drawer, JSON export.

**QA test cases (QA-6):** filters compose correctly (property-based where cheap); CSV
matches DB to the satoshi; trade drawer reconstructs a full round-trip from `orders`;
month aggregates equal sum of trades ± fees/funding vs Binance income history on DEMO;
mark-withdrawn writes audit event and is idempotent-guarded.
**Playwright:** `stage-06.history.spec.ts` — filter matrix, export download+content
check, drawer reconstruction, monthly ledger math against seeded fixtures.

**Exit:** any trade fully reconstructable in ≤3 clicks; exports byte-exact.

---

## Stage 7 — Notifier (notify.lk SMS)

**Goal:** every significant event reaches the owner's phone ≤60 s (G4).

**Deliverables**
- Notifier consuming the event bus: templates per event type (BSD §10 set), per-event
  toggles, fire-and-log with 3 backoff retries, delivery status on the event row,
  failure banner; test-SMS button; settings UI (write-only creds, sender ID, phone).

**QA test cases (QA-7):** each event type renders its template with correct values
(unit-tested rendering); provider timeout → retries then ERROR event + banner — trading
loop provably unblocked during outage (simulated); toggles suppress only their type;
delivery latency measured ≤60 s on real notify.lk; test SMS audited.
**Playwright:** `stage-07.sms.spec.ts` — settings flows, toggle matrix, template editor,
delivery-status rendering (provider mocked in E2E; one manual real-SMS check).

**Exit:** real SMS received for start/stop/trade/breaker/error on DEMO run.

---

## Stage 8 — AI news assistant (Codex SDK · GPT-5.5)

**Goal:** the isolated daily briefing (FR-10) — informational only, never a trading input.

**Deliverables**
- Collector (RSS set + FOMC/CPI static calendar) → URL-unique `news_items`; robust to
  feed failures. `SummaryProvider` interface with `CodexProvider` (headless
  `codex exec`, model `gpt-5.5`, no workspace/tools, JSON-out, hard timeout + one
  retry — see `INTEGRATIONS.md §3`); fixed BSD prompt; output budget.
- Daily schedule at configured local time + on-demand refresh; briefing storage.
- News UI (prototype port): briefing with source links, sentiment, archive, macro
  calendar, isolation notice; Overview mini-briefing; News settings (sources, time,
  provider/model, enable).

**QA test cases (QA-8):** dedupe proven; feed outage → partial briefing + WARN, no
crash; provider outage → yesterday's briefing stays, error evented; **isolation
verified: import-linter + runtime test that news module cannot reach credentials or
execution**; briefing arrives by configured time; refresh audited.
**Playwright:** `stage-08.news.spec.ts` — briefing render with links, archive
navigation, refresh flow, settings; LLM mocked in E2E, one recorded real-provider run.

**Exit:** scheduled briefing lands correctly; isolation contract green in CI.

---

## Stage 9 — Settings, security hardening & environment guard

**Goal:** everything configurable that should be; everything locked that must be.

**Deliverables**
- Settings complete: environment switch (bot-stopped guard + typed LIVE confirmation —
  UI complete but LIVE row absent until Stage 12), strategy library (guarded fallback
  selection while stopped), credentials, security (session timeout, revoke-others,
  SMS 2FA enable/disable/phone-change + server-only recovery), operations page
  (service health, rollout gate, drill evidence).
- Hardening: security headers/CSP, strict CORS, request-size limits, dependency audit
  in CI, non-root containers, firewall doc, fail2ban, secrets-scan CI job (gitleaks).

**QA test cases (QA-9):** environment switch blocked while running; typed confirmation
enforced; strategy switch guarded + audited; header/CSP scan passes; authz sweep (every
route × unauthenticated/expired/revoked); secrets absent from bundle, logs, responses
(automated grep + manual pass); dependency audit clean or waived with rationale.
**Playwright:** `stage-09.settings.spec.ts` — full settings matrix incl. guard modals
and security flows.

**Exit:** external checklist (OWASP-ASVS-lite, documented in SECURITY_GUIDELINES) passes.

---

## Stage 10 — Reliability engineering & failure drills

**Goal:** BSD §14 forced-failure drills pass, scripted and repeatable.

**Deliverables**
- Dead-man's-switch cron (missed 4h tick → SMS); healthcheck endpoint depth (WS age,
  last tick, DB, scheduler); backup job (nightly encrypted pg_dump → object storage) +
  **restore drill script**; blue/green upgrade runbook; drill automation scripts
  (network cut, restart mid-trade, WS kill, DB restart, clock skew).

**QA test cases (QA-10):** each drill scripted with asserted outcomes — restart
mid-trade resumes + reconciles; network cut ≥10 min recovers with candle catch-up;
kill switch under load; breaker under restart; backup restores to a working stack
(full restore drill); dead-man fires on simulated missed tick.
**Playwright:** `stage-10.reliability.spec.ts` — UI reflects each degraded/recovered
state correctly (safe-mode banners, health panel, drill evidence page).

**Exit:** all drills green twice in a row from clean state; runbooks written.

---

## Stage 11 — DEMO acceptance soak (≥4 weeks) — G3 gate

**Goal:** the BSD's rollout gate: ≥4 weeks unattended DEMO with zero unexplained
deviations, SMS ≤60 s, reconciliation clean.

**Deliverables**
- Deployed to the production VPS (DEMO keys), TLS live, backups live, monitoring live.
- Weekly review protocol: every decision vs expectation, every event explained;
  deviation log; acceptance dashboard (the ops page rollout tracker fed by real data).
- Full regression: **all** Playwright suites run against the deployed VPS weekly.

**QA:** the soak itself + weekly regression + acceptance checklist (documented in
`docs/qa/QA_STRATEGY.md §Acceptance`). Any unexplained deviation resets the 4-week clock
per BSD G3.

**Exit:** 4 clean weeks + owner sign-off recorded.

---

## Stage 12 — LIVE pilot & production release

**Goal:** real trading, smallest sensible size, owner in control.

**Deliverables**
- LIVE API key onboarding (trade+read only, withdrawals disabled, VPS IP whitelist —
  verified programmatically before first start); Settings switch to LIVE (typed
  confirmation); pilot config (risk 1–2%, sleeve 50%); go-live runbook + rollback
  (switch back to DEMO) runbook; monthly review template vs Appendix A.

**QA test cases (QA-12):** key permission verification rejects a withdrawal-enabled
key; first LIVE start reconciles cleanly; first LIVE round-trip matches DEMO behaviour
for the same candles; kill switch verified on LIVE with dust position; SMS on LIVE.

**Exit — production release:** 4+ LIVE pilot weeks matching DEMO behaviour → raise to
validated defaults (3–5% risk, sleeve 75%) on owner sign-off. Ongoing: monthly review
vs Appendix A expectations.

---

## Cross-stage rules

1. **Regression:** every stage ends with ALL prior Playwright suites green.
2. **Bug policy:** bugs found in QA are fixed in-stage; a stage never closes with known
   open bugs (severity ≥ minor).
3. **Docs:** each stage updates affected docs (`architecture/`, guidelines) in the same
   PR — stale docs fail review (see `CODE_REVIEW.md`).
4. **Estimates** (single dev + AI pair): S0 3–4d · S1 3–4d · S2 4–5d · S3 5–6d ·
   S4 6–7d · S5 4–5d · S6 3–4d · S7 1–2d · S8 2–3d · S9 3–4d · S10 3–4d ·
   S11 4+ weeks (calendar) · S12 1–2d + 4 weeks pilot. Build effort ≈ 7–8 weeks, plus
   the two mandated soak periods.
