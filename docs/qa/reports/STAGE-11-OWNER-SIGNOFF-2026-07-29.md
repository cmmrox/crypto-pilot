# Stage 11 owner sign-off and Stage 12 authorization

**Date:** 2026-07-29 Asia/Colombo

## Decision

The owner explicitly approved Stage 11, opened Stage 12, authorized minimum-size
real Binance LIVE verification trades, and directed that the same immutable DEMO
strategy configuration be applied to LIVE.

## Evidence boundary

The current repository evidence states that the latest unattended DEMO soak began
with bot run 19 on 2026-07-29. Consequently, this sign-off is an explicit owner waiver
of the remaining four-week calendar observation period; it is not evidence that four
weeks elapsed.

The owner accepted the residual operational risk and separately approved the
aggressive Trend Rider v6 profile for LIVE:

- 15% equity risk target for a normal long stop;
- 6× leverage cap;
- native volatility-targeted short sleeve with no price stop by validated design;
- independent 4% monthly long and short breakers.

## Authorized Stage 12 scope

- Programmatically re-check LIVE key permissions and account controls.
- Normalize the flat account to one-way, single-asset, isolated BTCUSDT and 6×.
- Run exchange-minimum LIVE long and short order-lifecycle checks with unconditional
  cleanup.
- Verify reconciliation, protective Algo stop, take-profit, cancellation, reduce-only
  flatten, kill switch, persistence, audit events, and SMS.
- Keep VPS deployment separate until local LIVE evidence is reviewed with the owner.
