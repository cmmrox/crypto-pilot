# CryptoPilot Full Prototype Requirements

## Product and user outcome

CryptoPilot is a single-owner, self-hosted web application for safely operating the Trend Rider v6 automated BTCUSDT long/short futures strategy. The prototype must help the owner understand account state at a glance, control the bot safely, inspect every trading decision, configure the system, read informational market news, and recover from errors without confusing informational UI with live exchange truth.

The business source of truth is `BUSINESS_SOLUTION_v2.pdf`. The strategy source is `BTC_Trend_Rider_v6.pine`. Every prototype must preserve the safety model and validated strategy rules described in those files.

## Required prototype shape

- Desktop-first responsive web application with a polished mobile layout.
- Runnable locally as a static HTML prototype.
- Realistic mock data anchored to 17 July 2026.
- Persistent global navigation and an always-reachable two-step kill-switch.
- Meaningful interactions for primary flows: navigation, filters, dialogs, drawers, toggles, forms, start/stop controls, environment switching, CSV export, news refresh, and mark-withdrawn.
- Use accessible semantic HTML, visible focus states, keyboard-friendly dialogs, readable contrast, and no color-only status communication.
- Do not use emoji as interface icons. Use a real icon library or clear text labels.
- Make DEMO versus LIVE unmistakable. Dangerous LIVE actions must require explicit confirmation.

## Required screens and states

### Login

- Email, password, optional TOTP step, remember-device option, error state, and security guidance.
- Successful sign-in enters the application.

### Overview

- DEMO/LIVE badge and connection/reconciliation health.
- Bot status with Start, Stop, optional Stop & Close, and safe-mode/paused states.
- Kill-switch reachable in two clicks; confirmation states must explicitly say it cancels orders, flattens positions, stops the bot, and sends SMS.
- Account balance, available balance/margin, unrealized and realized P&L.
- Open position showing LONG/SHORT, entry, size, leverage, liquidation distance or relevant safety context, unrealized P&L, long stop/TP1/trail or “No price stop - size-managed” for shorts.
- Current 4h market/regime state and next candle-close countdown.
- Independent long-book and short-sleeve monthly breaker meters with -4% thresholds and reset date.
- Equity curve compared with buy-and-hold.
- Today’s AI news briefing with source links and clear “informational only - never a trading input” labeling.
- Recent events or activity.

### Trades

- Filterable by side, environment, strategy, and month.
- Search, reset, realistic empty state, sortable-looking data, totals, fees, R-multiple, exit reason, and status.
- Per-trade detail drawer or modal with linked orders, fills, fees/funding, timeline, strategy, environment, and reconciliation state.
- Working CSV export interaction.

### Monthly

- Calendar-month table with trades, realized P&L, fees/funding, withdrawals, net result, and independent breaker status.
- Manual “mark withdrawn” action with confirmation and audit note.
- Honest performance context; do not promise monthly profit.

### News

- Daily briefing archive, 5-8 neutral market-relevant bullets, source links, generated time/model, and on-demand refresh.
- Upcoming FOMC/CPI economic-calendar panel.
- Source configuration visibility.
- Strong read-only/informational boundary from trading.

### Events

- Audit log with level and category filters plus search.
- Events for trades, bot lifecycle, breakers, errors, SMS, reconciliation, and news.
- Timestamp in UTC, expandable payload/details, SMS delivery status, and export/copy affordance.

### Settings

- Environment switch between Binance USDT-M DEMO and LIVE. Switching is blocked while the bot is running and requires confirmation when stopped.
- Per-environment Binance API credentials as write-only fields, never displayed back; test-connection action; withdrawal-disabled and IP-whitelist guidance.
- Strategy selection from registered plugins: `trend_rider_v6` default and `trend_rider_v52` fallback.
- Editable validated parameters with defaults and reset-to-validated-defaults action.
- Long risk %, leverage cap, sleeve weight, vol target, rebalance tolerance, long breaker, short breaker.
- SMS via notify.lk: enabled toggle, write-only credentials, sender ID, event toggles/templates, and test SMS.
- News sources, local briefing time, model choice, refresh.
- Security: optional TOTP, session/security information.
- Save states, validation, and unsaved-changes feedback.

## Strategy truths the UI must not distort

- Decisions occur only on closed 4h candles.
- Long regime: close above SMA200 and EMA50 above EMA200.
- Long: 2.5 ATR stop, TP1 at 1R sells 40%, stop to breakeven, 4 ATR runner trail, regime exit.
- Short sleeve: deep-bear condition, default 75% sleeve weight scaled by realized volatility with 40% annualized target; resize only beyond 20% drift.
- Shorts intentionally have no price stop. Say “No price stop - size-managed” and explain the risk controls; never fabricate a short stop-loss.
- Long and short monthly loss breakers are independent at -4% and halt their own side until the first of the next month.
- Long and short regimes are mutually exclusive; no leverage stacking.
- Binance account API is the source of truth for balance, positions, and income.
- Reconciliation mismatch causes safe mode, blocks new entries, and sends an SMS.
- News is informational only and never feeds the strategy.

## Key validated context

- Backtest figures are kept private and are not published in this repository.

## Evaluation rubric

- Requirement coverage and fidelity: 35%
- Safety clarity and control design: 20%
- Information architecture and task flow: 15%
- Visual hierarchy and polish: 15%
- Interaction completeness: 10%
- Responsive and accessibility quality: 5%

