# CryptoPilot final prototype coverage

Source of truth: `BUSINESS_SOLUTION_v2.pdf`, version 2.0, 17 July 2026.

User override: strategy parameters are already configured and therefore remain read-only in the operator dashboard. This intentionally replaces the editable-parameter portion of FR-11 while preserving guarded strategy selection.

## Functional requirements

| Requirement | Final prototype surface | Interaction/state |
|---|---|---|
| FR-01 DEMO/LIVE environments and separate keys | Global environment badge; Settings > Environment | Guarded switch, bot-stopped requirement, typed LIVE confirmation, write-only credentials |
| FR-02 Start, safe stop, stop-and-close, restart persistence | Overview bot control and control menu | Reconcile-and-start confirmation; safe stop leaves position; stop-and-close flattens; persistent-state explanation |
| FR-03 Trend Rider v6 LONG and SHORT on closed 4h candles | Global strategy card; Overview strategy and live position state | Explicit plugin/version, both directions, next close, last closed-candle decision and 4h-only cover rule |
| FR-04 Long risk sizing, short vol sizing, rounding and leverage cap | Overview live position/protection map; Settings > Strategy release manifest | Read-only deployed values; 53% size-managed short; −4% breaker; 20% resize threshold; exchange-filter status |
| FR-05 Binance is account source of truth | Overview live mark, synchronized account cards and reconciliation banner | Streaming mark, synchronized equity/P&L, balance, position, income and proof detail |
| FR-06 notify.lk SMS events and logging | Alerts center; Settings > SMS; Events | Event toggles, full per-event template set (BSD §10), delivery status, retries and test message |
| FR-07 Filterable, reconstructable trade history | Trades | Search plus side/environment/strategy/month filters, CSV export, per-trade orders/fills drawer |
| FR-08 Independent long and short monthly breakers | Overview and Monthly | Separate meters, reset dates and historical trip states |
| FR-09 Kill switch | Persistent header | Typed `FLATTEN` confirmation; cancel orders, flatten, stop and SMS/audit consequences |
| FR-10 Read-only AI briefing | Overview and News | Source links, archive, FOMC/CPI panel, on-demand refresh and isolation notice |
| FR-11 Registered strategy selection | Settings > Strategy library | Active/fallback releases, switch blocked while running, immutable validated manifest |
| FR-12 Equity snapshots and benchmark | Overview | 1M/6M/ALL equity curve against buy-and-hold with 4h snapshot provenance |

## Dashboard and supporting requirements

| Area | Included |
|---|---|
| Authentication | Email + password, mandatory TOTP, invalid-code state, session security |
| Overview | Environment, bot state, active strategy, Binance account truth, open short, market state, both breakers, equity curve, daily briefing and recent events |
| Trades | Required filters, CSV export and linked order/fill details |
| Monthly | Calendar-month table, fees, both breakers, withdrawal allowance and manual mark-withdrawn |
| News | Daily briefing, source links, archive, upcoming macro calendar and isolated-agent boundary |
| Events | UTC log with level/category/search filters; each row opens a drawer with the reconstructable `payload_json` audit record |
| Settings | Environment, strategy library, API credentials, SMS, news agent, security and operations |
| Reliability | WebSocket/REST/database/scheduler/dead-man status, reconciliation and safe-mode messaging |
| Security | Argon2/JWT/TOTP, AES-GCM at rest, TLS, IP allowlist, futures-only/no-withdrawal keys, session revocation and backup status |
| Operations | Docker/VPS health, last backup, next 4h tick, reconnect/catch-up state and DEMO rollout gate |
| Scope boundaries | No automatic withdrawals, no multi-coin/HFT, no news-driven execution and no native mobile app |
| Honest risk | Futures warning, no-guarantee statement, stop-free short explanation, worst month/drawdown context |
