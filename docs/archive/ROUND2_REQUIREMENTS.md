# CryptoPilot Prototype - Round 2 Mandatory Requirements

This round supersedes conflicting prototype choices from the first round while preserving all business requirements in `PROTOTYPE_REQUIREMENTS.md`, `BUSINESS_SOLUTION_v2.pdf`, and `BTC_Trend_Rider_v6.pine`.

## 1. Multi-strategy clarity

- The Overview must prominently show the strategy currently controlling the bot.
- Show at minimum: display name, plugin ID/version, BTCUSDT, 4h timeframe, LONG + SHORT capability, current regime/intent, and the last closed-candle decision time.
- The active strategy must remain visible near bot status and environment state. It must not be buried only in Settings.
- The system may have multiple registered strategies. Include a Strategy Library or Registered Strategies area showing:
  - `trend_rider_v6` as the active strategy.
  - `trend_rider_v52` as an available long-only fallback.
  - Clear active/inactive status, version, validation state, supported direction, and last-updated information.
- A strategy switch may be represented only as a guarded operational selection while the bot is stopped, with confirmation and reconciliation before restart.

## 2. Strategy configuration is read-only

- Remove all editable strategy parameter fields from Settings.
- Do not allow the owner to change risk percentage, leverage, ATR values, sleeve weight, volatility target, rebalance tolerance, breaker thresholds, or indicator periods from this UI.
- Remove “reset defaults” controls because the configuration is already validated and deployed.
- The UI may show the deployed configuration in a read-only strategy profile or parameter manifest.
- Clearly label the profile as “Validated configuration - read only” and explain that configuration changes require a versioned strategy release, parity testing, and deployment outside the operator dashboard.
- Environment credentials, SMS/news preferences, security controls, and other non-strategy operational settings may remain editable.

## 3. Mandatory two-factor login

- Sign-in must use `Username` and `Password`, not email-only login.
- After valid username/password submission, always require a six-digit authenticator code.
- Remove every “skip TOTP”, “prototype without TOTP”, or bypass control.
- Include clear validation errors for invalid credentials and invalid/incomplete codes.
- The user cannot enter the dashboard until the TOTP step succeeds.
- Show appropriate security guidance without exposing real secrets.

## 4. Dark, highly legible interface

- Login and all application screens must use a dark visual system.
- Prioritize text visibility: body copy should normally be 14-16px, strong contrast, restrained muted text, clear status labels, visible focus states, and no low-contrast small gray text.
- Keep dangerous actions red and unmistakable; DEMO and LIVE must be visually distinct without relying on color alone.
- Use a real icon library and keep decorative icons hidden from assistive technology.
- Maintain usable responsive layouts at desktop and 390px mobile width.

## 5. Preserve full business and safety coverage

- Keep Login, Overview, Trades, Monthly, News, Events, and Settings.
- Preserve guarded Start, Stop, Stop & Close, two-step kill-switch, DEMO/LIVE switch guard, exchange reconciliation/safe mode, independent long/short breakers, trade detail, CSV export, monthly withdrawal record, news archive/calendar, event audit log, write-only credentials, notify.lk controls/templates, news controls, TOTP/security area, and responsive behavior.
- Never add a price stop to the short sleeve. Continue to state “No price stop - size-managed” and show its actual controls.
- News remains informational only and never feeds trading.
- Binance remains the source of truth for balances, positions, and income.

## Round 2 evaluation weights

- Mandatory new requirements: 35%
- Business/safety feature coverage: 25%
- Information architecture and operational clarity: 15%
- Dark-theme readability and visual polish: 15%
- Interaction completeness: 7%
- Responsive/accessibility quality: 3%

